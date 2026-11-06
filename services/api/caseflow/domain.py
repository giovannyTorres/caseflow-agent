import uuid
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from psycopg.types.json import Jsonb
from .config import settings
from .db import connection, event, serial
from .execution import require_execution
from .ontology import (OntologyError, bind_context, digest, validate_binding, verify_application_review)
from .policy import current_policy

class DomainError(Exception):
    def __init__(self, message, status=409):
        self.message, self.status = message, status

class ProposalInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    amount: int = Field(strict=True, gt=0, le=100_000)
    reason: str = Field(min_length=10, max_length=1000)

class Decision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['propose', 'request_evidence', 'reject']
    amount: int = Field(strict=True, ge=0, le=100_000)
    reason: str = Field(min_length=10, max_length=1000)

    @model_validator(mode='after')
    def consistent_amount(self):
        if (self.action == 'propose' and self.amount <= 0) or (self.action != 'propose' and self.amount != 0):
            raise ValueError('Only a reimbursement proposal can carry a positive amount')
        return self


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


def proposal(case_id, actor, data: ProposalInput, correlation, operation_key=None, edit_existing=False,
             context_binding=None, expected_version=None):
    with connection() as conn:
        require_actor(conn, actor)
        case = get_case(conn, case_id, True)
        require_execution(conn, case_id)
        if expected_version is not None and expected_version != case['proposal_version']:
            raise DomainError('Context refresh must match the current proposal version')
        if edit_existing and (not case['proposal_version'] or case['status'] not in {'awaiting_approval', 'approved'}):
            raise DomainError('Only an existing reviewable proposal can be edited')
        if operation_key:
            old = conn.execute('SELECT result FROM tool_receipts WHERE case_id=%s AND operation_key=%s', (case_id, operation_key)).fetchone()
            if old:
                return old['result']
        if case['status'] in {'resolved', 'rejected'}:
            raise DomainError('A closed case cannot be changed')
        if data.amount > case['amount']:
            raise DomainError('Proposal exceeds disputed amount', 422)
        try:
            if context_binding is not None:
                context = validate_binding(context_binding, case, current_policy())
                verify_application_review(context, settings)
            elif edit_existing and case['proposal_context']:
                context = stored_context(case)
            else:
                context = bind_context(case, current_policy())
                verify_application_review(context, settings)
        except OntologyError as exc:
            raise DomainError(str(exc)) from None
        context_data = context.model_dump()
        context_sha256 = digest(context_data)
        version = case['proposal_version'] + 1
        conn.execute("""UPDATE cases SET proposal_version=%s,proposal_amount=%s,proposal_reason=%s,
          proposal_context=%s,proposal_context_sha256=%s,approved_context_sha256=NULL,
          approved_version=NULL,approved_by=NULL,status='awaiting_approval' WHERE id=%s""",
                     (version, data.amount, data.reason, Jsonb(context_data), context_sha256, case_id))
        result = {'version': version, 'amount': data.amount, 'reason': data.reason, 'status': 'awaiting_approval'}
        if operation_key:
            conn.execute('INSERT INTO tool_receipts VALUES(%s,%s,%s)', (case_id, operation_key, Jsonb(result)))
        event(conn, case_id, actor, 'proposal_prepared',
              {**result, 'context_sha256': context_sha256, 'context': context_data}, correlation)
        return result


def stored_context(case):
    try:
        if not case['proposal_context'] or digest(case['proposal_context']) != case['proposal_context_sha256']:
            raise OntologyError('Missing or changed proposal context')
        return validate_binding(case['proposal_context'], case, current_policy())
    except (OntologyError, ValueError, TypeError):
        raise DomainError('Proposal evidence or policy changed. Refresh context and review a new version.') from None


def approve(case_id, actor, version, correlation):
    with connection() as conn:
        require_actor(conn, actor, ('supervisor',))
        case = get_case(conn, case_id, True)
        require_execution(conn, case_id)
        if case['status'] not in {'awaiting_approval', 'approved'} or version != case['proposal_version']:
            raise DomainError('Approval must match the current proposal version')
        stored_context(case)
        conn.execute("UPDATE cases SET status='approved',approved_version=%s,approved_by=%s,approved_context_sha256=%s WHERE id=%s",
                     (version, actor, case['proposal_context_sha256'], case_id))
        event(conn, case_id, actor, 'proposal_approved',
              {'version': version, 'context_sha256': case['proposal_context_sha256']}, correlation)
        return {'status': 'approved', 'version': version}


def register_resolution(case_id, actor, version, correlation):
    with connection() as conn:
        require_actor(conn, actor, ('supervisor',))
        case = get_case(conn, case_id, True)
        require_execution(conn, case_id)
        existing = conn.execute('SELECT * FROM resolutions WHERE case_id=%s', (case_id,)).fetchone()
        if existing:
            if existing['proposal_version'] != version:
                raise DomainError('Resolution belongs to a different proposal')
            return serial(existing)
        if case['status'] != 'approved' or case['approved_version'] != version or case['proposal_version'] != version:
            raise DomainError('An exact, current approval is required before resolution')
        stored_context(case)
        if case['approved_context_sha256'] != case['proposal_context_sha256']:
            raise DomainError('Approval belongs to another evidence context')
        ident = str(uuid.uuid4())
        conn.execute('INSERT INTO resolutions(id,case_id,proposal_version,amount,actor,correlation_id) VALUES(%s,%s,%s,%s,%s,%s)',
                     (ident, case_id, version, case['proposal_amount'], actor, correlation))
        conn.execute("UPDATE cases SET status='resolved' WHERE id=%s", (case_id,))
        event(conn, case_id, actor, 'resolution_registered',
              {'id': ident, 'version': version, 'amount': case['proposal_amount'],
               'context_sha256': case['proposal_context_sha256']}, correlation)
        return {'id': ident, 'case_id': case_id, 'proposal_version': version, 'amount': case['proposal_amount']}


def request_evidence(case_id, actor, reason, correlation):
    with connection() as conn:
        require_actor(conn, actor)
        case = get_case(conn, case_id, True)
        require_execution(conn, case_id)
        if case['status'] in {'resolved', 'rejected'}:
            raise DomainError('Case is closed')
        evidence = case['evidence']
        item = {'id': f'request-{case_id}', 'status': 'requested', 'description': reason}
        if not any(x['id'] == item['id'] for x in evidence):
            evidence.append(item)
            event(conn, case_id, actor, 'evidence_requested', item, correlation)
        conn.execute("UPDATE cases SET evidence=%s,status='needs_evidence',approved_version=NULL,approved_by=NULL,approved_context_sha256=NULL WHERE id=%s", (Jsonb(evidence), case_id))
        return item


def reject(case_id, actor, version, correlation):
    with connection() as conn:
        require_actor(conn, actor, ('supervisor',))
        case = get_case(conn, case_id, True)
        require_execution(conn, case_id)
        if case['status'] not in {'awaiting_approval', 'approved', 'needs_evidence'} or version != case['proposal_version']:
            raise DomainError('Only the current open proposal can be rejected')
        conn.execute("UPDATE cases SET status='rejected',approved_version=NULL,approved_by=NULL,approved_context_sha256=NULL WHERE id=%s", (case_id,))
        event(conn, case_id, actor, 'proposal_rejected', {'version': version}, correlation)
        return {'status': 'rejected'}
