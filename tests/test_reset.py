import os
from pathlib import Path
import subprocess
import sys
from caseflow.db import connection
from caseflow.domain import ProposalInput, proposal


def test_explicit_demo_reset_preserves_live_and_requires_confirmation():
    env = {**os.environ, 'PYTHONPATH': str(Path('services/api').resolve())}
    command = [sys.executable, 'scripts/reset_demo.py']
    assert subprocess.run(command, env=env, capture_output=True).returncode == 2
    proposal('demo-001', 'analyst', ProposalInput(amount=100, reason='Synthetic reset test proposal.'), 'test')
    with connection() as conn:
        conn.execute("INSERT INTO cases(id,mode,title,scenario,priority,amount) VALUES('live-kept','LIVE','Keep this synthetic test row','duplicate','high',100)")
    result = subprocess.run([*command, '--confirm-synthetic-data'], env=env, capture_output=True)
    assert result.returncode == 0, result.stderr.decode()
    with connection() as conn:
        assert conn.execute("SELECT status FROM cases WHERE id='demo-001'").fetchone()['status'] == 'new'
        assert conn.execute("SELECT count(*) AS n FROM cases WHERE id='live-kept'").fetchone()['n'] == 1
    assert subprocess.run([*command, '--confirm-synthetic-data'], env={**env, 'APP_MODE': 'LIVE'}, capture_output=True).returncode != 0


def test_reset_refuses_a_worker_still_writing_after_cancellation():
    env = {**os.environ, 'PYTHONPATH': str(Path('services/api').resolve())}
    proposal('demo-001', 'analyst', ProposalInput(amount=100, reason='Preserve while checkpoint writer exits.'), 'audit')
    with connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('DEMO:demo-001', 914024))")
        result = subprocess.run([sys.executable, 'scripts/reset_demo.py', '--confirm-synthetic-data'], env=env, capture_output=True, timeout=5)
        assert result.returncode != 0
        assert 'worker still owns' in result.stderr.decode()
    with connection() as conn:
        assert conn.execute("SELECT proposal_version FROM cases WHERE id='demo-001'").fetchone()['proposal_version'] == 1
