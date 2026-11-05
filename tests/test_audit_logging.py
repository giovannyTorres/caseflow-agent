"""Verify real Uvicorn and exported OTel logs, not only our logging formatter."""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
import httpx


def test_actual_uvicorn_and_trace_export_do_not_log_query_canary(tmp_path):
    root=Path(__file__).resolve().parents[1]
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        port=sock.getsockname()[1]
    env={**os.environ,'PYTHONPATH':str(root/'services/api'),'OTEL_CONSOLE':'true'}
    log=tmp_path/'actual-runtime.log'
    with log.open('w+') as output:
        process=subprocess.Popen([sys.executable,'-m','uvicorn','caseflow.main:app','--host','127.0.0.1','--port',str(port)],env=env,cwd=root,stdout=output,stderr=subprocess.STDOUT)
        try:
            with httpx.Client(timeout=1) as client:
                for _ in range(100):
                    try:
                        if client.get(f'http://127.0.0.1:{port}/api/health').status_code==200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(.05)
                else:
                    raise AssertionError('Audit Uvicorn process did not become ready')
                canary='CF_AUDIT_PRIVATE_QUERY_8c7e62'
                response=client.get(f'http://127.0.0.1:{port}/api/health',params={'api_key':canary})
                assert response.status_code==200
        finally:
            process.terminate()
            process.wait(timeout=10)
    captured=log.read_text()
    assert canary not in captured
    assert 'caseflow.http' not in captured or 'GET 200' in captured
    assert 'GET 200' in captured
    assert 'http.url' in captured  # A real console span was exported and inspected.
