"""One-command host DEMO; PostgreSQL stays in Docker. No model credentials required."""
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
env = os.environ.copy()
env.update(APP_MODE='DEMO', APP_ORIGIN='http://localhost:3102', COOKIE_SECURE='false',
           DATABASE_URL='postgresql://caseflow:caseflow-demo@localhost:5542/caseflow',
           PYTHONPATH=str(ROOT / 'services/api'), API_INTERNAL_URL='http://127.0.0.1:8102',
           NEXT_TELEMETRY_DISABLED='1')
# This launcher deliberately uses the isolated, documented local simulator credentials.
env['POSTGRES_PASSWORD'] = 'caseflow-demo'
web_env = {k: v for k, v in env.items() if k not in {'OPENAI_API_KEY', 'GEMINI_API_KEY', 'DATABASE_URL', 'POSTGRES_PASSWORD'}}
for port in [3102, 8102]:
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1', port)) == 0:
            raise SystemExit(f'Port {port} is already in use. Stop the existing Caseflow web/API first.')

subprocess.run(['docker', 'compose', 'up', '-d', '--wait', 'db'], check=True, env=env)
subprocess.run(['uv', 'sync', '--frozen'], check=True, env=env)
web = ROOT / 'apps/web'
locked = json.loads((web / 'package-lock.json').read_text())['packages']
installed_path = web / 'node_modules/.package-lock.json'
installed = json.loads(installed_path.read_text())['packages'] if installed_path.exists() else {}
if any(k and (k in installed or not v.get('optional', False)) and installed.get(k, {}).get('version') != v.get('version') for k, v in locked.items()):
    subprocess.run(['npm', 'ci', '--prefer-offline', '--no-audit'], cwd=web, env=web_env, check=True)
subprocess.run(['npm', 'run', 'build'], cwd=web, env=web_env, check=True)
processes = []

def stop(*_):
    raise KeyboardInterrupt

signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
try:
    for command in [
        ['uv', 'run', '--no-sync', 'uvicorn', 'caseflow.main:app', '--host', '127.0.0.1', '--port', '8102'],
        ['uv', 'run', '--no-sync', 'python', '-m', 'caseflow.worker'],
    ]:
        processes.append(subprocess.Popen(command, env=env, start_new_session=True))
    for _ in range(60):
        try:
            with urllib.request.urlopen('http://127.0.0.1:8102/api/health', timeout=1) as response:
                if response.status == 200:
                    break
        except OSError:
            time.sleep(0.5)
    else:
        raise RuntimeError('API readiness timed out')
    processes.append(subprocess.Popen(['npm', 'start'], cwd=web, env=web_env, start_new_session=True))
    print('\nCaseflow DEMO: http://localhost:3102 | analyst / supervisor, password demo-pass\nCtrl+C stops app processes; PostgreSQL data is retained.\n', flush=True)
    while True:
        if any(p.poll() is not None for p in processes):
            raise RuntimeError('An application process exited. Review its output above.')
        time.sleep(1)
except KeyboardInterrupt:
    pass
finally:
    for process in reversed(processes):
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
    for process in processes:
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
