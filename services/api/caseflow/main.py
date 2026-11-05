import hashlib
import hmac
import logging
import secrets
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Depends, Request, Response
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyCookie
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from pydantic import BaseModel, ConfigDict, Field
from .config import settings, live_missing
from .db import connection, migrate, seed, password_hash, serial, event
from .domain import DomainError, ProposalInput, approve, reject, proposal, get_case
from .jobs import enqueue
from .telemetry import setup

@asynccontextmanager
async def lifespan(app):
    setup()
    migrate()
    seed()
    yield

app = FastAPI(title='Caseflow Agent API', version='1.0.0', lifespan=lifespan,
              docs_url='/api/docs', openapi_url='/api/openapi.json', redoc_url='/api/redoc',
              description='Synthetic investigations; no real banking operations. DEMO fixtures are explicitly labelled.')
FastAPIInstrumentor.instrument_app(app)

@app.middleware('http')
async def correlation_and_csrf(request: Request, call_next):
    request.state.correlation = str(uuid.uuid4())
    if request.method in {'POST', 'PUT', 'DELETE', 'PATCH'}:
        origin = request.headers.get('origin')
        if origin and origin != settings.allowed_origin:
            return JSONResponse({'detail': 'Request origin is not allowed'}, status_code=403)
        if request.headers.get('sec-fetch-site') == 'cross-site':
            return JSONResponse({'detail': 'Cross-site request rejected'}, status_code=403)
        if request.headers.get('content-type', '').split(';')[0] != 'application/json':
            return JSONResponse({'detail': 'Use application/json'}, status_code=415)
    response = await call_next(request)
    response.headers['X-Correlation-ID'] = request.state.correlation
    response.headers['Cache-Control'] = 'no-store'
    logging.getLogger('caseflow.http').info(f'{request.method} {response.status_code}', extra={'correlation_id': request.state.correlation})
    return response

@app.exception_handler(DomainError)
async def domain_error(request, exc):
    return JSONResponse({'detail': exc.message, 'correlation_id': request.state.correlation}, status_code=exc.status)

@app.exception_handler(Exception)
async def internal_error(request, exc):
    logging.getLogger('caseflow.http').error(type(exc).__name__, extra={'correlation_id': request.state.correlation})
    return JSONResponse({'detail': 'The request could not be completed. Please retry.', 'correlation_id': request.state.correlation}, status_code=500)

class Login(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=128)

class Version(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(ge=0)


session_cookie = APIKeyCookie(name='caseflow_session', auto_error=False)

def user(request: Request, token: str | None = Depends(session_cookie)):
    token = token or ''
    with connection() as conn:
        row = conn.execute('SELECT u.username,u.role FROM sessions s JOIN users u ON s.username=u.username AND s.mode=u.mode WHERE s.token_hash=%s AND s.expires_at>now() AND s.mode=%s',
                           (hashlib.sha256(token.encode()).hexdigest(), settings.mode)).fetchone()
    if not row:
        raise DomainError('Sign in to continue', 401)
    return row

@app.get('/api/health')
def health():
    with connection() as conn:
        conn.execute('SELECT 1')
    return {'status': 'ok', 'mode': settings.mode}

@app.get('/api/config')
def config():
    return {'mode': settings.mode, 'provider': settings.provider, 'model': settings.model,
            'live_ready': not live_missing(), 'missing': live_missing(),
            'provider_verification': 'SDK contract fixtures only; external service not verified'}

@app.post('/api/auth/login')
def login(data: Login, response: Response):
    with connection() as conn:
        row = conn.execute('SELECT * FROM users WHERE username=%s AND mode=%s', (data.username, settings.mode)).fetchone()
        # Equal-cost hash even for an unknown username.
        salt = row['salt'] if row else '00' * 16
        valid = hmac.compare_digest(password_hash(data.password, salt), row['password_hash'] if row else '00' * 64)
        if not row or not valid:
            raise DomainError('Invalid username or password', 401)
        token = secrets.token_urlsafe(32)
        conn.execute('INSERT INTO sessions(token_hash,username,mode,expires_at) VALUES(%s,%s,%s,%s)',
                     (hashlib.sha256(token.encode()).hexdigest(), row['username'], settings.mode, datetime.now(timezone.utc) + timedelta(hours=8)))
    response.set_cookie('caseflow_session', token, httponly=True, secure=settings.cookie_secure, samesite='strict', max_age=28800)
    return {'username': row['username'], 'role': row['role'], 'mode': settings.mode}

@app.post('/api/auth/logout')
def logout(request: Request, response: Response):
    with connection() as conn:
        conn.execute('DELETE FROM sessions WHERE token_hash=%s', (hashlib.sha256(request.cookies.get('caseflow_session', '').encode()).hexdigest(),))
    response.delete_cookie('caseflow_session')
    return {'status': 'signed_out'}

@app.get('/api/me')
def me(actor=Depends(user)):
    return {**actor, 'mode': settings.mode}

@app.get('/api/cases')
def cases(actor=Depends(user)):
    with connection() as conn:
        return serial(conn.execute('SELECT id,title,scenario,status,priority,assignee,amount,currency FROM cases WHERE mode=%s ORDER BY id', (settings.mode,)).fetchall())

@app.get('/api/cases/{case_id}')
def detail(case_id: str, actor=Depends(user)):
    with connection() as conn:
        case = get_case(conn, case_id)
        case['proposal'] = None if not case['proposal_version'] else {'version': case['proposal_version'], 'amount': case['proposal_amount'], 'reason': case['proposal_reason'], 'status': case['status']}
        for table in ['events', 'messages']:
            case[table] = conn.execute(f'SELECT * FROM {table} WHERE case_id=%s ORDER BY id', (case_id,)).fetchall()
        case['job'] = conn.execute('SELECT id,status,attempts,error,created_at,updated_at FROM jobs WHERE case_id=%s ORDER BY created_at DESC LIMIT 1', (case_id,)).fetchone()
        case['resolution'] = conn.execute('SELECT * FROM resolutions WHERE case_id=%s', (case_id,)).fetchone()
        return serial(case)

@app.post('/api/cases/{case_id}/investigate', status_code=202)
def investigate(case_id: str, request: Request, actor=Depends(user)):
    return enqueue(case_id, actor['username'], request.state.correlation)

@app.post('/api/cases/{case_id}/resume', status_code=202)
def resume(case_id: str, request: Request, actor=Depends(user)):
    return enqueue(case_id, actor['username'], request.state.correlation, 'resume')

@app.post('/api/cases/{case_id}/approve')
def approve_case(case_id: str, data: Version, request: Request, actor=Depends(user)):
    return approve(case_id, actor['username'], data.version, request.state.correlation)

@app.post('/api/cases/{case_id}/reject')
def reject_case(case_id: str, data: Version, request: Request, actor=Depends(user)):
    return reject(case_id, actor['username'], data.version, request.state.correlation)

@app.post('/api/cases/{case_id}/resolve', status_code=202)
def resolve_case(case_id: str, data: Version, request: Request, actor=Depends(user)):
    return enqueue(case_id, actor['username'], request.state.correlation, 'resolve', data.version)

@app.post('/api/cases/{case_id}/proposal')
def edit_proposal(case_id: str, data: ProposalInput, request: Request, actor=Depends(user)):
    return proposal(case_id, actor['username'], data, request.state.correlation)

@app.post('/api/cases/{case_id}/cancel')
def cancel(case_id: str, request: Request, actor=Depends(user)):
    with connection() as conn:
        get_case(conn, case_id, True)
        conn.execute("UPDATE jobs SET status='cancelled',updated_at=now() WHERE case_id=%s AND status IN ('queued','running')", (case_id,))
        conn.execute("UPDATE cases SET status='failed' WHERE id=%s AND status='investigating'", (case_id,))
        event(conn, case_id, actor['username'], 'cancellation_requested', {}, request.state.correlation)
    return {'status': 'cancelled'}
