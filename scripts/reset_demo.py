"""Explicitly reset only the five shipped synthetic DEMO cases, never LIVE data."""
import argparse
from caseflow.config import settings
from caseflow.db import connection, scenario_fixtures

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--confirm-synthetic-data', action='store_true', required=True)
parser.parse_args()
if settings.mode != 'DEMO':
    raise SystemExit('Reset is disabled outside DEMO.')
ids = [f'demo-{i:03}' for i, _ in enumerate(scenario_fixtures(), 1)]
with connection() as conn:
    conn.execute("SELECT id FROM cases WHERE id=ANY(%s) AND mode='DEMO' FOR UPDATE", (ids,))
    active = conn.execute("SELECT count(*) AS n FROM jobs WHERE case_id=ANY(%s) AND status IN ('queued','running')", (ids,)).fetchone()['n']
    if active:
        raise SystemExit('Wait for or cancel active jobs before resetting the DEMO cases.')
    for table in ['resolutions', 'tool_receipts', 'events', 'messages', 'jobs']:
        conn.execute(f'DELETE FROM {table} WHERE case_id=ANY(%s)', (ids,))
    for table in ['checkpoint_writes', 'checkpoint_blobs', 'checkpoints']:
        if conn.execute('SELECT to_regclass(%s) AS name', (table,)).fetchone()['name']:
            conn.execute(f'DELETE FROM {table} WHERE thread_id=ANY(%s)', ([f'DEMO:{ident}' for ident in ids],))
    conn.execute("""UPDATE cases SET status='new',evidence='[]',proposal_version=0,proposal_amount=NULL,
      proposal_reason=NULL,approved_version=NULL,approved_by=NULL,rejection_reason=NULL,recovery_enabled=false
      WHERE id=ANY(%s) AND mode='DEMO'""", (ids,))
print('Reset the five shipped synthetic DEMO cases and their checkpoints. LIVE and other cases were untouched.')
