"""Repeatable actual process-restart check on the isolated audit Compose project."""
import json
import subprocess
import time
import uuid
from pathlib import Path
import httpx
import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
compose = ['docker','compose','-p','audit-caseflow','-f','compose.yaml','-f','compose.audit.yaml','-f','compose.cloud.yaml']
case_id = 'audit-restart-' + uuid.uuid4().hex[:12]
url = 'postgresql://caseflow:caseflow-demo@localhost:5642/caseflow'
with psycopg.connect(url) as db:
    db.execute("INSERT INTO cases(id,mode,title,scenario,priority,amount,movements) SELECT %s,mode,title,scenario,priority,amount,movements FROM cases WHERE id='demo-005'", (case_id,))


def wait_status(client, wanted):
    for _ in range(90):
        response=client.get(f'/api/cases/{case_id}')
        if response.status_code==200 and response.json()['status']==wanted:
            return response.json()
        time.sleep(0.5)
    raise AssertionError(f'Expected {wanted}: {response.status_code} {response.text[:200]}')


with httpx.Client(base_url='http://localhost:3202',timeout=10) as client:
    assert client.post('/api/auth/login',json={'username':'analyst','password':'demo-pass'}).status_code==200
    assert client.post(f'/api/cases/{case_id}/investigate',json={}).status_code==202
    wait_status(client,'interrupted')
    subprocess.run(compose+['restart','api','worker'],cwd=ROOT,check=True)
    # The session and graph state must both survive actual process/container replacement.
    for _ in range(40):
        try:
            if client.get('/api/health').status_code==200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    assert client.post(f'/api/cases/{case_id}/resume',json={}).status_code==202
    detail=wait_status(client,'awaiting_approval')
    assert client.post('/api/auth/login',json={'username':'supervisor','password':'demo-pass'}).status_code==200
    version=detail['proposal_version']
    assert client.post(f'/api/cases/{case_id}/approve',json={'version':version}).status_code==200
    assert client.post(f'/api/cases/{case_id}/resolve',json={'version':version}).status_code==202
    detail=wait_status(client,'resolved')
with psycopg.connect(url,row_factory=dict_row) as db:
    count=db.execute('SELECT count(*) AS n FROM resolutions WHERE case_id=%s',(case_id,)).fetchone()['n']
    assert count==1
    result={'scenario':'interruption','containers_restarted':['api','worker'],'persisted_session':True,'final_status':detail['status'],'resolution_count':count,'events':[e['event'] for e in detail['events']]}
# Evidence contains no cookies, secrets or full logs. The synthetic audit case is retained.
(ROOT/'docs/audit-restart.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
