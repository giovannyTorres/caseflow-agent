import asyncio
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys

import httpx
import pytest
from psycopg.types.json import Jsonb

from caseflow.config import settings
from caseflow.db import connection
from caseflow.domain import DomainError, ProposalInput, approve, get_case, proposal, register_resolution
from caseflow.mcp_client import call_tool
from caseflow.ontology import (OntologyError, bind_context, digest, load_snapshot, project_evidence,
                               resolve_context, validate_binding)
from caseflow.policy import current_policy


def case(mode='LIVE'):
    return {'id': 'scope-case', 'mode': mode, 'amount': 100, 'currency': 'MXN',
            'movements': [{'id': 'tx-1', 'amount': 100, 'status': 'settled'}], 'evidence': []}


def snapshot(tmp_path, source='auto_ontology', mutate=None):
    root = Path(__file__).resolve().parents[1]
    value = json.loads((root / 'fixtures/ontology/auto-ontology-live.json').read_text(encoding='utf-8'))
    value['source'] = source
    if mutate:
        mutate(value)
    raw = (json.dumps(value, ensure_ascii=False) + '\n').encode()
    path = tmp_path / (source + '.json')
    path.write_bytes(raw)
    return replace(settings, ontology_mode=source, ontology_snapshot_path=str(path),
                   ontology_snapshot_sha256=hashlib.sha256(raw).hexdigest(), ontology_required=True,
                   auto_ontology_url='https://ontology.example', auto_ontology_api_token='test-token')


@pytest.fixture
def configure(monkeypatch):
    original = {}
    names = {'mode': 'APP_MODE', 'ontology_mode': 'ONTOLOGY_MODE',
             'ontology_snapshot_path': 'ONTOLOGY_SNAPSHOT_PATH',
             'ontology_snapshot_sha256': 'ONTOLOGY_SNAPSHOT_SHA256',
             'ontology_required': 'ONTOLOGY_REQUIRED'}

    def update(**values):
        for key, value in values.items():
            original.setdefault(key, getattr(settings, key))
            object.__setattr__(settings, key, value)
            if key in names:
                monkeypatch.setenv(names[key], str(value).lower() if type(value) is bool else str(value))
    yield update
    for key, value in original.items():
        object.__setattr__(settings, key, value)


@pytest.mark.asyncio
async def test_off_and_demo_never_construct_network_client(monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        raise AssertionError('Network client constructed')
    monkeypatch.setattr('caseflow.ontology.AutoOntologyClient', forbidden)
    for subject, config in [(case(), settings), (case('DEMO'), snapshot(tmp_path))]:
        context, audit = await resolve_context(subject, current_policy(), config)
        assert context.strategy == 'baseline' and not context.terms
        assert audit['status'] == 'disabled'


@pytest.mark.asyncio
async def test_glossary_has_reviewed_policy_case_and_terms(tmp_path):
    config = snapshot(tmp_path, 'glossary')
    context, audit = await resolve_context(case(), current_policy(), config)
    assert context.strategy == 'glossary' and len(context.terms) == 3
    assert audit['remote_requests'] == 0
    assert context.policy.text == current_policy()['text']
    assert validate_binding(context.model_dump(), case(), current_policy()) == context


@pytest.mark.parametrize('change', [
    lambda s: s.update(schema_version=True),
    lambda s: s.update(application='another-app'),
    lambda s: s['scope'].update(mode='DEMO'),
    lambda s: s.update(certified=False),
    lambda s: s.update(approved_by=''),
    lambda s: s['policy'].update(version=2),
    lambda s: s['terms'][0].update(description='Unreviewed text'),
    lambda s: s['terms'][0].update(name_certified=False),
    lambda s: s['terms'].append(s['terms'][0]),
])
def test_snapshot_rejects_scope_policy_and_uncertified_revisions(tmp_path, change):
    config = snapshot(tmp_path, mutate=change)
    with pytest.raises(OntologyError):
        load_snapshot(config.ontology_snapshot_path, config.ontology_snapshot_sha256, 'LIVE', current_policy())


def test_snapshot_pin_and_duplicate_json_keys_rejected(tmp_path):
    config = snapshot(tmp_path)
    with pytest.raises(OntologyError):
        load_snapshot(config.ontology_snapshot_path, '0' * 64, 'LIVE', current_policy())
    raw = b'{"schema_version":1,"schema_version":1}'
    Path(config.ontology_snapshot_path).write_bytes(raw)
    with pytest.raises(OntologyError):
        load_snapshot(config.ontology_snapshot_path, hashlib.sha256(raw).hexdigest(), 'LIVE', current_policy())


def transport(config, requests, mutation=None):
    snap = load_snapshot(config.ontology_snapshot_path, config.ontology_snapshot_sha256, 'LIVE', current_policy())

    def respond(request):
        requests.append(request)
        assert request.method == 'GET'
        assert request.headers['x-api-key'] == 'test-token'
        if request.url.path == '/api/terms':
            return httpx.Response(200, json={'terms': [term.model_dump() for term in snap.terms], 'total': 3})
        term = next(term.model_dump() for term in snap.terms if request.url.path.endswith(term.id))
        if mutation:
            mutation(term)
        return httpx.Response(200, json={'data': term})
    return httpx.MockTransport(respond)


@pytest.mark.asyncio
async def test_official_get_envelopes_match_reviewed_ids_and_digests(tmp_path):
    config = snapshot(tmp_path)
    requests = []
    context, audit = await resolve_context(case(), current_policy(), config,
                                         transport=transport(config, requests))
    assert context.strategy == 'auto_ontology' and audit['remote_requests'] == 6
    assert len(requests) == 6 and all('test-token' not in str(request.url) for request in requests)


@pytest.mark.asyncio
async def test_remote_drift_never_becomes_certified_context(tmp_path):
    config = snapshot(tmp_path)
    def mutation(term):
        term.update(description='Changed despite remote certified flags')
    with pytest.raises(OntologyError, match='reviewed revision'):
        await resolve_context(case(), current_policy(), config,
                              transport=transport(config, [], mutation))
    optional = replace(config, ontology_required=False)
    context, audit = await resolve_context(case(), current_policy(), optional,
                                         transport=transport(optional, [], mutation))
    assert context.strategy == 'baseline' and not context.terms
    assert audit['status'] == 'unavailable_baseline_fallback'


@pytest.mark.asyncio
async def test_total_budget_bounds_all_remote_pages_and_terms(tmp_path):
    config = replace(snapshot(tmp_path), ontology_timeout=.03)
    calls = []

    async def slow(request):
        calls.append(request)
        await asyncio.sleep(.02)
        return httpx.Response(200, json={'terms': [{'id': 'cf-settled-duplicate-v1'}], 'total': 1})
    with pytest.raises(OntologyError, match='total request budget'):
        await resolve_context(case(), current_policy(), config, transport=httpx.MockTransport(slow))
    assert len(calls) <= 2


@pytest.mark.asyncio
async def test_remote_oversized_and_redirect_responses_fail_closed(tmp_path):
    config = snapshot(tmp_path)
    for response in [httpx.Response(302, headers={'location': 'https://elsewhere.invalid'}),
                     httpx.Response(200, content=b'x' * 256001)]:
        with pytest.raises(OntologyError):
            await resolve_context(case(), current_policy(), config,
                                  transport=httpx.MockTransport(lambda _: response))


def test_case_binding_and_readonly_projection_exclude_operational_data():
    subject = {**case(), 'sessions': ['secret'], 'password': 'secret', 'jobs': ['private']}
    bound = bind_context(subject, current_policy())
    for changed in [{**subject, 'id': 'another'}, {**subject, 'mode': 'DEMO'}, {**subject, 'amount': 99}]:
        with pytest.raises(OntologyError):
            validate_binding(bound.model_dump(), changed, current_policy())
    projection = project_evidence(subject, current_policy())
    assert set(projection) == {'case_summary', 'movements', 'policy_version'}
    assert 'secret' not in json.dumps(projection) and 'sessions' not in json.dumps(projection)


def prepare():
    return proposal('demo-001', 'analyst', ProposalInput(amount=100, reason='Synthetic reviewed evidence.'), 'test')


def test_proposal_approval_and_resolution_bind_exact_context():
    prepare()
    approve('demo-001', 'supervisor', 1, 'test')
    with connection() as conn:
        subject = get_case(conn, 'demo-001')
        assert subject['approved_context_sha256'] == digest(subject['proposal_context'])
        conn.execute("UPDATE cases SET proposal_context_sha256='altered' WHERE id='demo-001'")
    with pytest.raises(DomainError, match='context'):
        register_resolution('demo-001', 'supervisor', 1, 'test')
    with connection() as conn:
        assert conn.execute('SELECT count(*) AS n FROM resolutions').fetchone()['n'] == 0


def test_case_evidence_change_requires_refresh_and_new_approval(supervisor):
    prepare()
    approve('demo-001', 'supervisor', 1, 'test')
    with connection() as conn:
        conn.execute("UPDATE cases SET evidence=%s WHERE id='demo-001'",
                     (Jsonb([{'id': 'new-receipt', 'status': 'received'}]),))
    assert supervisor.post('/api/cases/demo-001/resolve', json={'version': 1}).status_code == 202
    with pytest.raises(DomainError, match='context'):
        register_resolution('demo-001', 'supervisor', 1, 'test')
    # No worker is active: remove the queued simulator resolution before a deliberate refresh.
    with connection() as conn:
        conn.execute("DELETE FROM jobs WHERE case_id='demo-001'")
    response = supervisor.post('/api/cases/demo-001/context/refresh', json={'version': 1})
    assert response.status_code == 200 and response.json()['version'] == 2
    with connection() as conn:
        history = conn.execute("SELECT detail FROM events WHERE case_id='demo-001' AND event='proposal_prepared' ORDER BY id").fetchall()
        assert [row['detail']['version'] for row in history] == [1, 2]
        assert history[0]['detail']['context']['case_sha256'] != history[1]['detail']['context']['case_sha256']
        assert all(digest(row['detail']['context']) == row['detail']['context_sha256'] for row in history)
    assert supervisor.post('/api/cases/demo-001/approve', json={'version': 1}).status_code == 409
    assert supervisor.post('/api/cases/demo-001/approve', json={'version': 2}).status_code == 200
    assert register_resolution('demo-001', 'supervisor', 2, 'test')['proposal_version'] == 2


def test_refresh_checks_current_version_and_edit_keeps_bound_evidence(supervisor):
    prepare()
    with connection() as conn:
        original = get_case(conn, 'demo-001')['proposal_context_sha256']
    assert supervisor.post('/api/cases/demo-001/context/refresh', json={'version': 0}).status_code == 409
    revised = proposal('demo-001', 'analyst', ProposalInput(amount=90, reason='Revised proposed amount only.'),
                       'test', edit_existing=True)
    with connection() as conn:
        subject = get_case(conn, 'demo-001')
        assert subject['proposal_context_sha256'] == original and subject['approved_context_sha256'] is None
    assert revised['version'] == 2


@pytest.mark.asyncio
async def test_actual_mcp_rejects_context_from_another_case():
    with connection() as conn:
        subject = get_case(conn, 'demo-001')
    context = bind_context(subject, current_policy()).model_dump()
    context['case_id'] = 'another-case'
    with pytest.raises(RuntimeError, match='MCP tool failed'):
        await call_tool('prepare_proposal', {'case_id': 'demo-001', 'amount': 100,
                        'reason': 'Synthetic evidence must match.', 'context_binding': context},
                        case_id='demo-001', actor='analyst', correlation='test')
    with connection() as conn:
        assert get_case(conn, 'demo-001')['proposal_version'] == 0


@pytest.mark.asyncio
async def test_semantic_context_persists_and_snapshot_switch_does_not_rewrite_approval(tmp_path, configure):
    config = snapshot(tmp_path, 'glossary')
    configure(mode='LIVE', ontology_mode='glossary', ontology_snapshot_path=config.ontology_snapshot_path,
              ontology_snapshot_sha256=config.ontology_snapshot_sha256, ontology_required=True)
    with connection() as conn:
        conn.execute("INSERT INTO users VALUES('analyst','LIVE','analyst','00','00'),('supervisor','LIVE','supervisor','00','00')")
        conn.execute("INSERT INTO cases(id,mode,title,scenario,priority,amount,movements) VALUES('scope-case','LIVE','Synthetic','duplicate','high',100,%s)",
                     (Jsonb(case()['movements']),))
        subject = get_case(conn, 'scope-case')
    context, _ = await resolve_context(subject, current_policy(), settings)
    await call_tool('prepare_proposal', {'case_id': 'scope-case', 'amount': 100,
                    'reason': 'Synthetic reviewed duplicate.', 'context_binding': context.model_dump()},
                    case_id='scope-case', actor='analyst', correlation='test')
    # A later config revision cannot silently replace already persisted evidence.
    configure(ontology_snapshot_path='missing-next-snapshot.json', ontology_snapshot_sha256='0' * 64)
    approve('scope-case', 'supervisor', 1, 'test')
    assert register_resolution('scope-case', 'supervisor', 1, 'test')['amount'] == 100
    with connection() as conn:
        subject = get_case(conn, 'scope-case')
        assert subject['proposal_context']['snapshot_sha256'] == config.ontology_snapshot_sha256


@pytest.mark.asyncio
async def test_required_missing_context_fails_before_graph_proposal(monkeypatch, configure):
    import importlib
    graph_module = importlib.import_module('caseflow.graph')
    configure(mode='LIVE', ontology_mode='auto_ontology', ontology_required=True)
    with connection() as conn:
        conn.execute("INSERT INTO cases(id,mode,title,scenario,priority,amount) VALUES('scope-case','LIVE','Synthetic','duplicate','high',100)")

    async def tools(state, name, **args):
        assert name in {'get_movements', 'get_policy'}
        return current_policy() if name == 'get_policy' else {'movements': [], 'amount': 100}
    monkeypatch.setattr(graph_module, 'tool', tools)
    with pytest.raises(OntologyError):
        await graph_module.gather({'case_id': 'scope-case', 'actor': 'analyst', 'correlation': 'test'})
    with connection() as conn:
        assert get_case(conn, 'scope-case')['proposal_version'] == 0
        assert conn.execute('SELECT count(*) AS n FROM resolutions').fetchone()['n'] == 0


@pytest.mark.asyncio
async def test_gather_does_not_bind_new_case_revision_to_old_tool_movements(monkeypatch):
    import importlib
    graph_module = importlib.import_module('caseflow.graph')

    async def old_movements(state, name, **args):
        return current_policy() if name == 'get_policy' else {'movements': [], 'amount': 1280}
    monkeypatch.setattr(graph_module, 'tool', old_movements)
    with pytest.raises(OntologyError, match='changed while gathering'):
        await graph_module.gather({'case_id': 'demo-001', 'actor': 'analyst', 'correlation': 'test'})


@pytest.mark.asyncio
async def test_gather_rejects_tool_policy_that_changed_before_binding(monkeypatch):
    import importlib
    graph_module = importlib.import_module('caseflow.graph')
    with connection() as conn:
        subject = get_case(conn, 'demo-001')

    async def old_policy(state, name, **args):
        return ({**current_policy(), 'version': 99} if name == 'get_policy' else
                {'movements': subject['movements'], 'amount': subject['amount']})
    monkeypatch.setattr(graph_module, 'tool', old_policy)
    with pytest.raises(OntologyError, match='Policy changed'):
        await graph_module.gather({'case_id': 'demo-001', 'actor': 'analyst', 'correlation': 'test'})


def test_legacy_open_proposal_without_context_requires_explicit_refresh(supervisor):
    prepare()
    with connection() as conn:
        conn.execute("UPDATE cases SET proposal_context=NULL,proposal_context_sha256=NULL WHERE id='demo-001'")
    assert supervisor.post('/api/cases/demo-001/approve', json={'version': 1}).status_code == 409
    assert supervisor.post('/api/cases/demo-001/context/refresh', json={'version': 1}).json()['version'] == 2
    assert supervisor.post('/api/cases/demo-001/approve', json={'version': 2}).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize('legacy_binding', [None, 'stale'])
@pytest.mark.parametrize('manual_proposal', [False, True])
async def test_legacy_or_stale_checkpoint_regathers_and_redecides_before_first_effect(legacy_binding, manual_proposal):
    from langgraph.checkpoint.memory import InMemorySaver
    from caseflow.graph import graph
    with connection() as conn:
        subject = get_case(conn, 'demo-001')
    binding = bind_context(subject, current_policy()).model_dump() if legacy_binding else None
    if binding:
        binding['case_sha256'] = '0' * 64
    compiled = graph(InMemorySaver())
    config = {'configurable': {'thread_id': 'legacy-demo-001'}, 'recursion_limit': 12}
    state = {'case_id': 'demo-001', 'actor': 'analyst', 'correlation': 'test',
             'decision': {'action': 'propose', 'amount': 90, 'reason': 'An old unbound synthetic decision.'},
             'movements': {}, 'policy': {}, 'context_binding': binding}
    await compiled.aupdate_state(config, state, as_node='decide')
    if manual_proposal:
        proposal('demo-001', 'analyst', ProposalInput(amount=50, reason='An intervening operator proposal.'), 'test')
    result = await compiled.ainvoke(None, config)
    assert result.get('__interrupt__') and not result.get('context_refresh_required')
    with connection() as conn:
        subject = get_case(conn, 'demo-001')
        # DEMO fixture redecides 1280: attaching a binding to old decision 90 would fail this.
        assert subject['proposal_amount'] == 1280
        assert subject['proposal_version'] == (2 if manual_proposal else 1)
        assert subject['proposal_context']['case_id'] == 'demo-001'
        assert conn.execute("SELECT count(*) AS n FROM events WHERE event='context_refresh_required'").fetchone()['n'] == 1


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform == 'win32', reason='Existing psycopg async/Proactor incompatibility; Linux CI runs this')
async def test_postgres_legacy_checkpoint_survives_restart_and_redecides():
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from caseflow.graph import graph
    config = {'configurable': {'thread_id': 'DEMO:demo-001'}, 'recursion_limit': 12}
    state = {'case_id': 'demo-001', 'actor': 'analyst', 'correlation': 'test',
             'decision': {'action': 'propose', 'amount': 90, 'reason': 'A pre-migration synthetic decision.'},
             'movements': {}, 'policy': {}}
    async with AsyncPostgresSaver.from_conn_string(settings.database_url) as saver:
        await saver.setup()
        await graph(saver).aupdate_state(config, state, as_node='decide')
    async with AsyncPostgresSaver.from_conn_string(settings.database_url) as saver:
        result = await graph(saver).ainvoke(None, config)
    assert result.get('__interrupt__')
    with connection() as conn:
        subject = get_case(conn, 'demo-001')
        assert subject['proposal_amount'] == 1280
        assert digest(subject['proposal_context']) == subject['proposal_context_sha256']
