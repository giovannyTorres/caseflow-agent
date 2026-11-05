from concurrent.futures import ThreadPoolExecutor
import pytest
from caseflow.db import connection
from caseflow.domain import DomainError, ProposalInput, approve, proposal, register_resolution


def prepare():
    return proposal('demo-001', 'analyst', ProposalInput(amount=100, reason='Synthetic supported reimbursement.'), 'test')


def test_authentication_and_csrf(client):
    assert client.get('/api/cases').status_code == 401
    assert client.post('/api/auth/login', json={'username': 'analyst', 'password': 'wrong'}).status_code == 401
    assert client.post('/api/auth/login', json={'username': 'analyst', 'password': 'demo-pass'}, headers={'Origin': 'https://evil.invalid'}).status_code == 403
    assert client.post('/api/auth/login', content='username=analyst').status_code == 415


def test_analyst_cannot_approve_or_resolve(analyst):
    p = prepare()
    for action in ['approve', 'resolve', 'reject']:
        assert analyst.post(f'/api/cases/demo-001/{action}', json={'version': p['version']}).status_code == 403


def test_stale_approval_invalidated(supervisor):
    p = prepare()
    assert supervisor.post('/api/cases/demo-001/approve', json={'version': p['version']}).status_code == 200
    p2 = proposal('demo-001', 'analyst', ProposalInput(amount=90, reason='Revised synthetic reimbursement.'), 'test')
    assert p2['version'] == 2
    assert supervisor.post('/api/cases/demo-001/resolve', json={'version': 1}).status_code == 409
    assert supervisor.post('/api/cases/demo-001/resolve', json={'version': 2}).status_code == 409
    assert supervisor.post('/api/cases/demo-001/approve', json={'version': 1}).status_code == 409


def test_resolution_without_approval_and_limits():
    prepare()
    with pytest.raises(DomainError):
        register_resolution('demo-001', 'supervisor', 1, 'test')
    with pytest.raises(DomainError):
        proposal('demo-001', 'analyst', ProposalInput(amount=99999, reason='Exceeds charge amount.'), 'test')


def test_concurrent_resolution_is_exactly_once():
    prepare()
    approve('demo-001', 'supervisor', 1, 'test')
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: register_resolution('demo-001', 'supervisor', 1, 'test'), range(16)))
    assert len({r['id'] for r in results}) == 1
    with connection() as conn:
        assert conn.execute('SELECT count(*) AS n FROM resolutions').fetchone()['n'] == 1
        assert conn.execute("SELECT count(*) AS n FROM events WHERE event='resolution_registered'").fetchone()['n'] == 1


def test_mode_isolation(analyst):
    with connection() as conn:
        conn.execute("INSERT INTO cases(id,mode,title,scenario,priority,amount) VALUES('live-private','LIVE','Hidden','duplicate','high',100)")
    assert analyst.get('/api/cases/live-private').status_code == 404
    assert all(x['id'] != 'live-private' for x in analyst.get('/api/cases').json())


def test_idempotent_job_submission(analyst):
    first = analyst.post('/api/cases/demo-001/investigate', json={}).json()
    second = analyst.post('/api/cases/demo-001/investigate', json={}).json()
    assert first['id'] == second['id']


def test_active_job_does_not_bypass_approval_guard(supervisor):
    assert supervisor.post('/api/cases/demo-001/investigate', json={}).status_code == 202
    assert supervisor.post('/api/cases/demo-001/resolve', json={'version': 0}).status_code == 409


def test_api_docs_are_same_origin(client):
    assert client.get('/api/docs').status_code == 200
    contract = client.get('/api/openapi.json').json()
    assert '/api/cases/{case_id}/resolve' in contract['paths']


def test_cancellation_is_persisted(analyst):
    analyst.post('/api/cases/demo-001/investigate', json={})
    assert analyst.post('/api/cases/demo-001/cancel', json={}).status_code == 200
    detail = analyst.get('/api/cases/demo-001').json()
    assert detail['job']['status'] == 'cancelled'
    assert detail['status'] == 'failed'
