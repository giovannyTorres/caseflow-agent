import os
import pytest
from urllib.parse import urlparse

# Tests never touch the development database. The database must exist first.
os.environ['DATABASE_URL'] = os.getenv('TEST_DATABASE_URL', 'postgresql://caseflow:caseflow-demo@localhost:5542/caseflow_test')
if not urlparse(os.environ['DATABASE_URL']).path.endswith('_test'):
    raise RuntimeError('Destructive tests require an isolated database name ending in _test')
os.environ['APP_MODE'] = 'DEMO'
from caseflow.db import connection, migrate, seed  # noqa: E402
from caseflow.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

@pytest.fixture(autouse=True)
def clean_database():
    migrate()
    with connection() as conn:
        conn.execute('TRUNCATE users,sessions,cases,jobs,events,messages,resolutions,tool_receipts RESTART IDENTITY CASCADE')
        for table in ['checkpoint_writes', 'checkpoint_blobs', 'checkpoints']:
            if conn.execute('SELECT to_regclass(%s) AS name', (table,)).fetchone()['name']:
                conn.execute(f'TRUNCATE {table}')
    seed()

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

@pytest.fixture
def analyst(client):
    assert client.post('/api/auth/login', json={'username': 'analyst', 'password': 'demo-pass'}).status_code == 200
    return client

@pytest.fixture
def supervisor(client):
    assert client.post('/api/auth/login', json={'username': 'supervisor', 'password': 'demo-pass'}).status_code == 200
    return client
