import hashlib
import json
import secrets
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from .config import settings

@contextmanager
def connection():
    with psycopg.connect(settings.database_url, row_factory=dict_row) as conn:
        yield conn


def migrate():
    sql = (Path(__file__).parent / 'schema.sql').read_text()
    with connection() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(914022)')
        conn.execute(sql)
        conn.execute((Path(__file__).parent / 'migration_002.sql').read_text())


def password_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()


def scenario_fixtures():
    return json.loads((Path(__file__).resolve().parents[3] / "fixtures" / "scenarios.json").read_text())


def seed():
    with connection() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(914023)')
        if settings.mode == 'DEMO':
            for username, role in [('analyst', 'analyst'), ('supervisor', 'supervisor')]:
                salt = secrets.token_hex(16)
                conn.execute('INSERT INTO users(username,role,salt,password_hash,mode) VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                             (username, role, salt, password_hash('demo-pass', salt), 'DEMO'))
        for i, fixture in enumerate(scenario_fixtures(), 1):
            scenario, title, priority, amount = (fixture[k] for k in ['scenario', 'title', 'priority', 'amount'])
            ident = f'{settings.mode.lower()}-{i:03}'
            movements = [{'id': f'TX-{i}A', 'merchant': 'Juniper Stationery', 'amount': amount, 'currency': 'MXN', 'posted_at': '2026-09-01T10:00:00Z'}]
            if scenario in {'duplicate', 'tool_failure', 'interruption'}:
                movements.append({**movements[0], 'id': f'TX-{i}B'})
            conn.execute('INSERT INTO cases(id,mode,title,scenario,priority,amount,movements) VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                         (ident, settings.mode, title, scenario, priority, amount, Jsonb(movements)))


def event(conn, case_id, actor, name, detail, correlation):
    conn.execute('INSERT INTO events(case_id,actor,event,detail,correlation_id) VALUES(%s,%s,%s,%s,%s)',
                 (case_id, actor, name, Jsonb(detail), correlation))


def serial(value):
    return json.loads(json.dumps(value, default=str))
