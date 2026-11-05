import asyncio
import logging
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from opentelemetry import trace
from .config import settings
from .db import connection, migrate, seed, event
from .graph import graph
from .telemetry import setup

log = logging.getLogger('caseflow.worker')

def claim():
    with connection() as conn:
        return conn.execute("""UPDATE jobs SET status='running',lease_until=now()+interval '60 seconds',attempts=attempts+1,updated_at=now()
          WHERE id=(SELECT j.id FROM jobs j JOIN cases c ON c.id=j.case_id WHERE c.mode=%s AND
            (j.status='queued' OR (j.status='running' AND j.lease_until<now()))
            ORDER BY j.created_at FOR UPDATE OF j SKIP LOCKED LIMIT 1) RETURNING *""", (settings.mode,)).fetchone()

async def heartbeat(job, task):
    while not task.done():
        await asyncio.sleep(5)
        with connection() as conn:
            row = conn.execute('SELECT status FROM jobs WHERE id=%s', (job['id'],)).fetchone()
            if row['status'] == 'cancelled':
                task.cancel()
                return
            conn.execute("UPDATE jobs SET lease_until=now()+interval '60 seconds',updated_at=now() WHERE id=%s AND status='running'", (job['id'],))

async def execute(job, compiled):
    config = {'configurable': {'thread_id': f"{settings.mode}:{job['case_id']}"}, 'recursion_limit': settings.max_steps}
    snapshot = await compiled.aget_state(config)
    if job['resume'] and snapshot.values:
        value = None if job['resume']['kind'] == 'retry' else Command(resume=job['resume'])
    elif snapshot.values:
        value = None  # A lease reclaimed after process death resumes its last persisted node.
    else:
        value = {'case_id': job['case_id'], 'actor': job['actor'], 'correlation': job['correlation_id']}
    with trace.get_tracer('caseflow.worker').start_as_current_span('investigation.run') as span:
        span.set_attribute('case.id', job['case_id'])
        result = await compiled.ainvoke(value, config=config)
    with connection() as conn:
        if result.get('__interrupt__'):
            kind = result['__interrupt__'][0].value['kind']
            if kind == 'interruption':
                conn.execute("UPDATE cases SET status='interrupted' WHERE id=%s", (job['case_id'],))
            status = 'waiting'
        else:
            status = 'completed'
        conn.execute('UPDATE jobs SET status=%s,lease_until=NULL,updated_at=now() WHERE id=%s AND status<>%s',
                     (status, job['id'], 'cancelled'))
        event(conn, job['case_id'], job['actor'], 'job_' + status, {'job_id': str(job['id'])}, job['correlation_id'])

async def process(job, compiled):
    task = asyncio.create_task(execute(job, compiled))
    pulse = asyncio.create_task(heartbeat(job, task))
    try:
        await task
    except asyncio.CancelledError:
        with connection() as conn:
            conn.execute("UPDATE cases SET status='failed' WHERE id=%s AND status NOT IN ('resolved','rejected')", (job['case_id'],))
            event(conn, job['case_id'], job['actor'], 'job_cancelled', {}, job['correlation_id'])
    except Exception as exc:
        log.warning('job_failed:' + type(exc).__name__, extra={'correlation_id': job['correlation_id']})
        with connection() as conn:
            conn.execute("UPDATE jobs SET status='failed',error='Investigation interrupted. Review the timeline and retry.',lease_until=NULL,updated_at=now() WHERE id=%s", (job['id'],))
            conn.execute("UPDATE cases SET status='failed' WHERE id=%s AND status NOT IN ('resolved','rejected')", (job['case_id'],))
            event(conn, job['case_id'], job['actor'], 'job_failed', {'message': 'A provider or tool could not complete the request. Resume to retry.'}, job['correlation_id'])
    finally:
        pulse.cancel()
        await asyncio.gather(pulse, return_exceptions=True)

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
