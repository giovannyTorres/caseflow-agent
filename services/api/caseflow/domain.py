import uuid
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from psycopg.types.json import Jsonb
from .config import settings
from .db import connection, event, serial

class DomainError(Exception):
    def __init__(self, message, status=409):
        self.message, self.status = message, status

class ProposalInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    amount: int = Field(gt=0, le=100_000)
    reason: str = Field(min_length=10, max_length=1000)

class Decision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['propose', 'request_evidence', 'reject']
    amount: int = Field(ge=0, le=100_000)
    reason: str = Field(min_length=10, max_length=1000)


def get_case(conn, case_id, lock=False):
    row = conn.execute('SELECT * FROM cases WHERE id=%s AND mode=%s' + (' FOR UPDATE' if lock else ''),
                       (case_id, settings.mode)).fetchone()
    if not row:
        raise DomainError('Case not found', 404)
    return row


def require_actor(conn, actor, roles=('analyst', 'supervisor')):
    row = conn.execute('SELECT role FROM users WHERE username=%s AND mode=%s', (actor, settings.mode)).fetchone()
    if not row or row['role'] not in roles:
        raise DomainError('This role cannot perform that action', 403)
    return row


def proposal(case_id, actor, data: ProposalInput, correlation, operation_key=None):
    with connection() as conn:
        require_actor(conn, actor)
        case = get_case(conn, case_id, True)
        if operation_key:
            old = conn.execute('SELECT result FROM tool_receipts WHERE case_id=%s AND operation_key=%s', (case_id, operation_key)).fetchone()
            if old:
                return old['result']
        if case['status'] in {'resolved', 'rejected'}:
            raise DomainError('A closed case cannot be changed')
        if data.amount > case['amount']:
            raise DomainError('Proposal exceeds disputed amount', 422)
        version = case['proposal_version'] + 1
        conn.execute("UPDATE cases SET proposal_version=%s,proposal_amount=%s,proposal_reason=%s,approved_version=NULL,approved_by=NULL,status='awaiting_approval' WHERE id=%s",
                     (version, data.amount, data.reason, case_id))
        result = {'version': version, 'amount': data.amount, 'reason': data.reason, 'status': 'awaiting_approval'}
        if operation_key:
            conn.execute('INSERT INTO tool_receipts VALUES(%s,%s,%s)', (case_id, operation_key, Jsonb(result)))
        event(conn, case_id, actor, 'proposal_prepared', result, correlation)
        return result


def approve(case_id, actor, version, correlation):
    with connection() as conn:
        require_actor(conn, actor, ('supervisor',))
        case = get_case(conn, case_id, True)
        if case['status'] not in {'awaiting_approval', 'approved'} or version != case['proposal_version']:
            raise DomainError('Approval must match the current proposal version')
        conn.execute("UPDATE cases SET status='approved',approved_version=%s,approved_by=%s WHERE id=%s", (version, actor, case_id))
        event(conn, case_id, actor, 'proposal_approved', {'version': version}, correlation)
        return {'status': 'approved', 'version': version}


def register_resolution(case_id, actor, version, correlation):
    with connection() as conn:
        require_actor(conn, actor, ('supervisor',))
        case = get_case(conn, case_id, True)
        existing = conn.execute('SELECT * FROM resolutions WHERE case_id=%s', (case_id,)).fetchone()
        if existing:
            if existing['proposal_version'] != version:
                raise DomainError('Resolution belongs to a different proposal')
            return serial(existing)
        if case['status'] != 'approved' or case['approved_version'] != version or case['proposal_version'] != version:
            raise DomainError('An exact, current approval is required before resolution')
        ident = str(uuid.uuid4())
        conn.execute('INSERT INTO resolutions(id,case_id,proposal_version,amount,actor,correlation_id) VALUES(%s,%s,%s,%s,%s,%s)',
                     (ident, case_id, version, case['proposal_amount'], actor, correlation))
        conn.execute("UPDATE cases SET status='resolved' WHERE id=%s", (case_id,))
        event(conn, case_id, actor, 'resolution_registered', {'id': ident, 'version': version, 'amount': case['proposal_amount']}, correlation)
        return {'id': ident, 'case_id': case_id, 'proposal_version': version, 'amount': case['proposal_amount']}


def request_evidence(case_id, actor, reason, correlation):
    with connection() as conn:
        require_actor(conn, actor)
        case = get_case(conn, case_id, True)
        if case['status'] in {'resolved', 'rejected'}:
            raise DomainError('Case is closed')
        evidence = case['evidence']
        item = {'id': f'request-{case_id}', 'status': 'requested', 'description': reason}
        if not any(x['id'] == item['id'] for x in evidence):
            evidence.append(item)
            event(conn, case_id, actor, 'evidence_requested', item, correlation)
        conn.execute("UPDATE cases SET evidence=%s,status='needs_evidence' WHERE id=%s", (Jsonb(evidence), case_id))
        return item


def reject(case_id, actor, version, correlation):
    with connection() as conn:
        require_actor(conn, actor, ('supervisor',))
        case = get_case(conn, case_id, True)
        if case['status'] not in {'awaiting_approval', 'approved', 'needs_evidence'} or version != case['proposal_version']:
            raise DomainError('Only the current open proposal can be rejected')
        conn.execute("UPDATE cases SET status='rejected',approved_version=NULL,approved_by=NULL WHERE id=%s", (case_id,))
        event(conn, case_id, actor, 'proposal_rejected', {'version': version}, correlation)
        return {'status': 'rejected'}
