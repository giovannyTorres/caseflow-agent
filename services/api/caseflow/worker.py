import asyncio
import logging
import psycopg
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from opentelemetry import trace
from .config import settings
from .db import connection, migrate, seed, event
from .domain import get_case
from .execution import capability, require_execution
from .graph import graph
from .telemetry import setup

log = logging.getLogger('caseflow.worker')


def claim():
    with connection() as conn:
        return conn.execute("""UPDATE jobs SET status='running',lease_until=now()+interval '60 seconds',attempts=attempts+1,updated_at=now()
          WHERE id=(SELECT j.id FROM jobs j JOIN cases c ON c.id=j.case_id WHERE c.mode=%s AND
            (j.status='queued' OR (j.status='running' AND j.lease_until<now()))
            ORDER BY j.created_at FOR UPDATE OF j SKIP LOCKED LIMIT 1) RETURNING *""", (settings.mode,)).fetchone()


def recoverable_state(conn, case_id):
    """Do not strand a proposal/approval when its execution is cancelled or fails."""
    conn.execute("""UPDATE cases SET status=CASE
       WHEN approved_version=proposal_version AND approved_version IS NOT NULL THEN 'approved'
       WHEN proposal_version>0 THEN 'awaiting_approval' ELSE 'failed' END
       WHERE id=%s AND status NOT IN ('resolved','rejected','needs_evidence')""", (case_id,))


async def heartbeat(job, task):
    while not task.done():
        await asyncio.sleep(1)
        with connection() as conn:
            row = conn.execute("""UPDATE jobs SET lease_until=now()+interval '60 seconds',updated_at=now()
               WHERE id=%s AND status='running' AND attempts=%s AND lease_until>now() RETURNING id""",
                               (job['id'], job['attempts'])).fetchone()
            if row is None:
                task.cancel()
                return


async def execute(job, compiled):
    config = {'configurable': {'thread_id': f"{settings.mode}:{job['case_id']}"}, 'recursion_limit': settings.max_steps}
    snapshot = await compiled.aget_state(config)
    if job['resume'] and snapshot.values:
        value = None if job['resume']['kind'] == 'retry' else Command(resume=job['resume'])
    elif snapshot.values:
        value = None
    else:
        value = {'case_id': job['case_id'], 'actor': job['actor'], 'correlation': job['correlation_id']}
    with trace.get_tracer('caseflow.worker').start_as_current_span('investigation.run') as span:
        span.set_attribute('case.id', job['case_id'])
        result = await compiled.ainvoke(value, config=config)
    with connection() as conn:
        get_case(conn, job['case_id'], True)
        require_execution(conn, job['case_id'])
        if result.get('__interrupt__'):
            kind = result['__interrupt__'][0].value['kind']
            if kind == 'interruption':
                conn.execute("UPDATE cases SET status='interrupted' WHERE id=%s", (job['case_id'],))
            elif kind == 'approval':
                recoverable_state(conn, job['case_id'])
            status = 'waiting'
        else:
            status = 'completed'
        conn.execute('UPDATE jobs SET status=%s,lease_until=NULL,updated_at=now() WHERE id=%s AND attempts=%s',
                     (status, job['id'], job['attempts']))
        event(conn, job['case_id'], job['actor'], 'job_' + status, {'job_id': str(job['id'])}, job['correlation_id'])


def record_failure(job, cancelled):
    with connection() as conn:
        get_case(conn, job['case_id'], True)
        row = conn.execute('SELECT status,attempts FROM jobs WHERE id=%s FOR UPDATE', (job['id'],)).fetchone()
        if not row or row['attempts'] != job['attempts'] or row['status'] not in {'running', 'cancelled'}:
            return  # Superseded worker must not overwrite the new owner's state.
        if conn.execute("SELECT 1 FROM jobs WHERE case_id=%s AND id<>%s AND status IN ('queued','running')", (job['case_id'], job['id'])).fetchone():
            return
        status = 'cancelled' if cancelled or row['status'] == 'cancelled' else 'failed'
        conn.execute('UPDATE jobs SET status=%s,error=%s,lease_until=NULL,updated_at=now() WHERE id=%s',
                     (status, None if status == 'cancelled' else 'Investigation interrupted. Review the timeline and retry.', job['id']))
        recoverable_state(conn, job['case_id'])
        event(conn, job['case_id'], job['actor'], 'job_' + status, {}, job['correlation_id'])


async def process(job, compiled):
    # A session advisory lock serializes checkpoint writes for the case, even when a
    # lease expires while the former process still exists. The attempt fences effects.
    with psycopg.connect(settings.database_url, autocommit=True) as lock:
        locked = lock.execute('SELECT pg_try_advisory_lock(hashtextextended(%s, 914024))',
                              (f'{settings.mode}:{job["case_id"]}',)).fetchone()[0]
        if not locked:
            return  # Lease remains reclaimable; never race an existing graph writer.
        token = capability.set({'id': job['id'], 'attempts': job['attempts'], 'case_id': job['case_id']})
        task = pulse = None
        try:
            with connection() as conn:
                get_case(conn, job['case_id'], True)
                require_execution(conn, job['case_id'])
            task = asyncio.create_task(execute(job, compiled))
            pulse = asyncio.create_task(heartbeat(job, task))
            async with asyncio.timeout(settings.execution_timeout):
                await task
        except asyncio.CancelledError:
            record_failure(job, True)
        except Exception as exc:
            log.warning('job_failed:' + type(exc).__name__, extra={'correlation_id': job['correlation_id']})
            record_failure(job, False)
        finally:
            if task and not task.done():
                task.cancel()
            if pulse:
                pulse.cancel()
            await asyncio.gather(*(t for t in (task, pulse) if t), return_exceptions=True)
            capability.reset(token)


async def main():
    setup()
    migrate()
    seed()
    async with AsyncPostgresSaver.from_conn_string(settings.database_url) as saver:
        await saver.setup()
        compiled = graph(saver)
        while True:
            job = claim()
            if job:
                await process(job, compiled)
            else:
                await asyncio.sleep(0.5)

if __name__ == '__main__':
    asyncio.run(main())
