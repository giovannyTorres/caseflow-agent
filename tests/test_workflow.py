import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from caseflow.config import settings
from caseflow.db import connection
from caseflow.domain import approve
from caseflow.graph import graph
from caseflow.jobs import enqueue
from caseflow.worker import claim, process
from caseflow.mcp_client import call_tool

async def run_one():
    async with AsyncPostgresSaver.from_conn_string(settings.database_url) as saver:
        await saver.setup()
        await process(claim(), graph(saver))


def status(case_id):
    with connection() as conn:
        return conn.execute('SELECT status FROM cases WHERE id=%s', (case_id,)).fetchone()['status']

@pytest.mark.asyncio
async def test_mcp_real_transport_and_capability():
    data = await call_tool('get_movements', {'case_id': 'demo-001'}, case_id='demo-001', actor='analyst', correlation='test')
    assert len(data['movements']) == 2
    with pytest.raises(ValueError):
        await call_tool('get_movements', {'case_id': 'demo-002'}, case_id='demo-001', actor='analyst', correlation='test')
    with pytest.raises(Exception):
        await call_tool('register_resolution', {'case_id': 'demo-001', 'version': 1}, case_id='demo-001', actor='analyst', correlation='test')

@pytest.mark.asyncio
async def test_investigate_restart_approve_resolve():
    enqueue('demo-001', 'analyst', 'test')
    await run_one()
    assert status('demo-001') == 'awaiting_approval'
    approve('demo-001', 'supervisor', 1, 'test')
    enqueue('demo-001', 'supervisor', 'test', 'resolve', 1)
    # New graph and DB connection emulate process restart with only DB state retained.
    await run_one()
    assert status('demo-001') == 'resolved'

@pytest.mark.asyncio
async def test_insufficient_and_rejection_scenarios():
    for case_id in ['demo-002', 'demo-003']:
        enqueue(case_id, 'analyst', 'test')
        await run_one()
        assert status(case_id) == 'needs_evidence'
    with connection() as conn:
        events = conn.execute("SELECT event FROM events WHERE case_id='demo-003'").fetchall()
        assert any(x['event'] == 'rejection_recommended' for x in events)

@pytest.mark.asyncio
async def test_tool_failure_recovery():
    enqueue('demo-004', 'analyst', 'test')
    await run_one()
    assert status('demo-004') == 'failed'
    enqueue('demo-004', 'analyst', 'test', 'resume')
    await run_one()
    assert status('demo-004') == 'awaiting_approval'

@pytest.mark.asyncio
async def test_interruption_recovery():
    enqueue('demo-005', 'analyst', 'test')
    await run_one()
    assert status('demo-005') == 'interrupted'
    enqueue('demo-005', 'analyst', 'test', 'resume')
    await run_one()
    assert status('demo-005') == 'awaiting_approval'

@pytest.mark.asyncio
async def test_expired_worker_lease_is_reclaimed():
    enqueue('demo-001', 'analyst', 'test')
    original = claim()
    with connection() as conn:
        conn.execute("UPDATE jobs SET lease_until=now()-interval '1 minute' WHERE id=%s", (original['id'],))
    await run_one()
    assert status('demo-001') == 'awaiting_approval'

@pytest.mark.asyncio
async def test_cancelled_before_start_can_resume():
    enqueue('demo-001', 'analyst', 'test')
    with connection() as conn:
        conn.execute("UPDATE jobs SET status='cancelled' WHERE case_id='demo-001'")
        conn.execute("UPDATE cases SET status='failed' WHERE id='demo-001'")
    enqueue('demo-001', 'analyst', 'test', 'resume')
    await run_one()
    assert status('demo-001') == 'awaiting_approval'
