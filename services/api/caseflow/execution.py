"""Fence durable side effects against cancellation and superseded worker leases."""
from contextvars import ContextVar

capability: ContextVar[dict | None] = ContextVar('caseflow_execution', default=None)


def require_execution(conn, case_id):
    from .domain import DomainError
    current = capability.get()
    if current is None:  # Authenticated API/domain operator; roles are checked separately.
        return
    if current['case_id'] != case_id:
        raise DomainError('Execution capability belongs to another case', 403)
    job = conn.execute('SELECT status,attempts,lease_until>now() AS valid_lease FROM jobs WHERE id=%s AND case_id=%s FOR UPDATE',
                       (current['id'], case_id)).fetchone()
    if not job or job['status'] != 'running' or job['attempts'] != current['attempts'] or not job['valid_lease']:
        raise DomainError('This execution is cancelled or its lease was superseded')
