import asyncio
import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from caseflow.config import settings
from caseflow.db import connection
from caseflow.domain import ProposalInput, approve, proposal
from caseflow.execution import capability
from caseflow.graph import graph
from caseflow.jobs import enqueue
from caseflow.mcp_client import call_tool
from caseflow.worker import claim, process, record_failure


@pytest.mark.asyncio
async def test_superseded_actual_mcp_cannot_prepare_proposal():
    enqueue('demo-001', 'analyst', 'old')
    old = claim()
    with connection() as conn:
        conn.execute("UPDATE jobs SET lease_until=now()-interval '1 second' WHERE id=%s", (old['id'],))
    current = claim()
    token = capability.set({'id': old['id'], 'attempts': old['attempts'], 'case_id': old['case_id']})
    try:
        with pytest.raises(RuntimeError, match='MCP tool failed'):
            await call_tool('prepare_proposal', {'case_id':'demo-001','amount':100,'reason':'A stale worker must not write.'}, case_id='demo-001',actor='analyst',correlation='old')
    finally:
        capability.reset(token)
    record_failure(old, False)
    with connection() as conn:
        assert conn.execute("SELECT proposal_version FROM cases WHERE id='demo-001'").fetchone()['proposal_version']==0
        assert conn.execute('SELECT status FROM jobs WHERE id=%s',(current['id'],)).fetchone()['status']=='running'


@pytest.mark.asyncio
async def test_cancelled_mcp_cannot_resolve_after_backend_cancel(supervisor):
    proposal('demo-001','analyst',ProposalInput(amount=100,reason='Supported synthetic proposal.'),'audit')
    approve('demo-001','supervisor',1,'audit')
    enqueue('demo-001','supervisor','audit','resolve',1)
    old=claim()
    assert supervisor.post('/api/cases/demo-001/cancel',json={}).status_code==200
    token=capability.set({'id':old['id'],'attempts':old['attempts'],'case_id':'demo-001'})
    try:
        with pytest.raises(RuntimeError,match='MCP tool failed'):
            await call_tool('register_resolution',{'case_id':'demo-001','version':1},case_id='demo-001',actor='supervisor',correlation='audit')
    finally:
        capability.reset(token)
    with connection() as conn:
        assert conn.execute('SELECT count(*) AS n FROM resolutions').fetchone()['n']==0
        assert conn.execute("SELECT status FROM cases WHERE id='demo-001'").fetchone()['status']=='approved'


@pytest.mark.asyncio
async def test_resolution_retry_after_failure_preserves_exact_approval():
    async with AsyncPostgresSaver.from_conn_string(settings.database_url) as saver:
        await saver.setup()
        compiled=graph(saver)
        enqueue('demo-001','analyst','audit')
        await process(claim(),compiled)
        approve('demo-001','supervisor',1,'audit')
        enqueue('demo-001','supervisor','audit','resolve',1)
        failed=claim()
        record_failure(failed,False)
        with connection() as conn:
            assert conn.execute("SELECT status FROM cases WHERE id='demo-001'").fetchone()['status']=='approved'
        enqueue('demo-001','supervisor','audit','resolve',1)
        await process(claim(),compiled)
    with connection() as conn:
        assert conn.execute('SELECT count(*) AS n FROM resolutions').fetchone()['n']==1


def test_cancelled_worker_cannot_overwrite_replacement_job(analyst):
    enqueue('demo-001','analyst','old')
    old=claim()
    analyst.post('/api/cases/demo-001/cancel',json={})
    replacement=analyst.post('/api/cases/demo-001/resume',json={})
    assert replacement.status_code==202
    record_failure(old,True)
    assert analyst.get('/api/cases/demo-001').json()['status']=='investigating'


def test_direct_resolution_cannot_claim_an_investigation_is_resolution(supervisor):
    enqueue('demo-001','analyst','audit')
    proposal('demo-001','analyst',ProposalInput(amount=100,reason='Proposal committed before graph checkpoint.'),'audit')
    approve('demo-001','supervisor',1,'audit')
    response=supervisor.post('/api/cases/demo-001/resolve',json={'version':1})
    assert response.status_code==409
    assert 'checkpoint' in response.json()['detail']


def test_direct_api_cannot_create_proposal_without_investigation(analyst):
    response=analyst.post('/api/cases/demo-001/proposal',json={'amount':100,'reason':'Skip investigation and create manually.'})
    assert response.status_code==409


@pytest.mark.asyncio
async def test_worker_overall_deadline_returns_recoverable_failure():
    class NeverCompletes:
        async def aget_state(self,config):
            await asyncio.Event().wait()
    enqueue('demo-001','analyst','audit')
    # Frozen dataclass instance needs a narrowly scoped test override.
    previous=settings.execution_timeout
    object.__setattr__(settings,'execution_timeout',0.02)
    try:
        await process(claim(),NeverCompletes())
    finally:
        object.__setattr__(settings,'execution_timeout',previous)
    with connection() as conn:
        assert conn.execute("SELECT status FROM jobs WHERE case_id='demo-001'").fetchone()['status']=='failed'


def test_body_limits_and_validation_never_echo_password(client):
    secret='synthetic-secret-'*20
    response=client.post('/api/auth/login',json={'username':'analyst','password':secret})
    assert response.status_code==422 and secret not in response.text
    response=client.post('/api/auth/login',content=iter([b'{"password":"',b'x'*65536,b'"}']),headers={'Content-Type':'application/json'})
    assert response.status_code==413


def test_login_rate_limit_is_persisted(client):
    for _ in range(20):
        assert client.post('/api/auth/login',json={'username':'analyst','password':'wrong'}).status_code==401
    assert client.post('/api/auth/login',json={'username':'analyst','password':'demo-pass'}).status_code==429
    with connection() as conn:
        conn.execute("UPDATE login_attempts SET window_start=now()-interval '61 seconds'")
    assert client.post('/api/auth/login',json={'username':'analyst','password':'demo-pass'}).status_code==200


@pytest.mark.asyncio
async def test_mcp_strict_arguments_reject_boolean_amount():
    with pytest.raises(RuntimeError,match='MCP tool failed'):
        await call_tool('prepare_proposal',{'case_id':'demo-001','amount':True,'reason':'Boolean is not a monetary amount.'},case_id='demo-001',actor='analyst',correlation='audit')
    with connection() as conn:
        assert conn.execute("SELECT proposal_version FROM cases WHERE id='demo-001'").fetchone()['proposal_version']==0


def test_session_expiry_and_cookie_security_flags(client):
    response=client.post('/api/auth/login',json={'username':'analyst','password':'demo-pass'})
    cookie=response.headers['set-cookie'].lower()
    assert 'httponly' in cookie and 'samesite=strict' in cookie and 'max-age=28800' in cookie
    with connection() as conn:
        conn.execute("UPDATE sessions SET expires_at=now()-interval '1 second'")
    assert client.get('/api/me').status_code==401


def test_demo_session_and_credentials_cannot_cross_to_live(analyst):
    previous=settings.mode
    object.__setattr__(settings,'mode','LIVE')
    try:
        assert analyst.get('/api/me').status_code==401
        assert analyst.post('/api/auth/login',json={'username':'analyst','password':'demo-pass'}).status_code==401
    finally:
        object.__setattr__(settings,'mode',previous)


def test_boolean_approval_version_rejected(supervisor):
    response=supervisor.post('/api/cases/demo-001/approve',json={'version':True})
    assert response.status_code==422


@pytest.mark.asyncio
async def test_concurrent_http_resolution_retries_enqueue_and_apply_once(supervisor):
    from concurrent.futures import ThreadPoolExecutor
    async with AsyncPostgresSaver.from_conn_string(settings.database_url) as saver:
        await saver.setup()
        compiled=graph(saver)
        enqueue('demo-001','analyst','audit')
        await process(claim(),compiled)
        assert supervisor.post('/api/cases/demo-001/approve',json={'version':1}).status_code==200
        with ThreadPoolExecutor(max_workers=8) as pool:
            responses=list(pool.map(lambda _: supervisor.post('/api/cases/demo-001/resolve',json={'version':1}),range(16)))
        assert all(r.status_code==202 for r in responses)
        assert len({r.json()['id'] for r in responses})==1
        await process(claim(),compiled)
    with connection() as conn:
        assert conn.execute('SELECT count(*) AS n FROM resolutions').fetchone()['n']==1
        assert conn.execute("SELECT count(*) AS n FROM events WHERE event='resolution_registered'").fetchone()['n']==1
