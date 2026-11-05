import uuid
from psycopg.types.json import Jsonb
from .db import connection, event, serial
from .domain import DomainError, get_case, require_actor
from .config import settings, live_missing


def enqueue(case_id, actor, correlation, action='investigate', version=None):
    with connection() as conn:
        require_actor(conn, actor, ('supervisor',) if action == 'resolve' else ('analyst', 'supervisor'))
        case = get_case(conn, case_id, True)
        active = conn.execute("SELECT * FROM jobs WHERE case_id=%s AND status IN ('queued','running')", (case_id,)).fetchone()
        if active:
            if action == 'resolve' and (case['status'] != 'approved' or version != case['proposal_version'] or version != case['approved_version']):
                raise DomainError('A current supervisor approval is required')
            return serial(active)
        if settings.mode == 'LIVE' and live_missing():
            raise DomainError('LIVE configuration is incomplete. Check provider settings.', 503)
        resume = None
        if action == 'investigate':
            if case['status'] != 'new':
                raise DomainError('Use the available review or recovery action for this case')
        elif action == 'resolve':
            if case['status'] != 'approved' or version != case['proposal_version'] or version != case['approved_version']:
                raise DomainError('A current supervisor approval is required')
            resume = {'kind': 'approval', 'actor': actor, 'version': version}
        elif action == 'resume':
            if case['status'] not in {'failed', 'interrupted'}:
                raise DomainError('Only a failed or interrupted case can be resumed')
            resume = {'kind': 'interruption'} if case['status'] == 'interrupted' else {'kind': 'retry'}
            conn.execute('UPDATE cases SET recovery_enabled=true WHERE id=%s', (case_id,))
        else:
            raise DomainError('Unknown action', 422)
        ident = str(uuid.uuid4())
        conn.execute('INSERT INTO jobs(id,case_id,actor,resume,correlation_id) VALUES(%s,%s,%s,%s,%s)',
                     (ident, case_id, actor, Jsonb(resume) if resume else None, correlation))
        if action != 'resolve':
            conn.execute("UPDATE cases SET status='investigating' WHERE id=%s", (case_id,))
        event(conn, case_id, actor, 'job_queued', {'id': ident, 'action': action}, correlation)
        return {'id': ident, 'status': 'queued'}
