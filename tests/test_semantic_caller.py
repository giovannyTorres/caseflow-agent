import importlib.util
import json
from pathlib import Path
from dataclasses import replace
import hashlib
import os

import httpx
import pytest

from caseflow.config import settings
from caseflow.policy import current_policy

spec = importlib.util.spec_from_file_location('caseflow_semantic_caller',
    Path(__file__).resolve().parents[1] / 'scripts/semantic_benchmark_caller.py')
caller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(caller)


def request():
    context = {'mode': 'LIVE', 'case': {'id': 'sample', 'amount': 100, 'evidence': []},
               'movements': {'movements': [{'id': 'tx-1', 'amount': 100, 'status': 'settled'}]},
               'policy': current_policy()}
    return {'case': {'id': 'sample', 'kind': 'agent', 'prompt': 'Investigate the observed charge.',
                     'context': json.dumps(context)}, 'arm': 'baseline', 'options': {}}


@pytest.mark.asyncio
async def test_caller_uses_model_decision_without_workflow_or_goldens():
    captured = []

    def respond(http_request):
        body = json.loads(http_request.content)
        captured.append(body)
        return httpx.Response(200, json={'done': True, 'done_reason': 'stop', 'model': body['model'],
            'message': {'content': json.dumps({'decision': {'action': 'request_evidence', 'amount': 0,
                'reason': 'Observed evidence is insufficient.'}, 'evidence_ids': ['juniper-policy-v1@1']})},
            'prompt_eval_count': 10, 'eval_count': 20})
    result = await caller.run(request(), model_transport=httpx.MockTransport(respond))
    assert result['status'] == 'completed' and result['execution'] == 'transport_mock'
    assert result['output']['tool_calls'] == [{'name': 'decision', 'arguments': {
        'action': 'request_evidence', 'amount': 0, 'evidence_ids': ['juniper-policy-v1@1']}}]
    assert result['output']['authorization'] is None and result['output']['tokens'] == 30
    assert captured[0]['options'] == {'temperature': 0, 'seed': 42, 'num_predict': 1600}
    assert all(entry.get('effects_executed', False) is False for entry in result['trace'])
    contaminated = request()
    contaminated['case']['expected'] = {'answer': 'golden'}
    with pytest.raises(ValueError, match='without goldens'):
        await caller.run(contaminated, model_transport=httpx.MockTransport(respond))


@pytest.mark.asyncio
async def test_caller_rejects_invented_evidence_and_incomplete_model_output():
    for evidence, done in [(['invented'], 'stop'), (['tx-1'], 'length'), (['tx-1'], None)]:
        payload = {'model': os.getenv('CASEFLOW_EVAL_MODEL', 'qwen3.5:4b'),
                   'done': True, 'done_reason': done, 'message': {'content': json.dumps({
            'decision': {'action': 'propose', 'amount': 100, 'reason': 'An observed charge is disputed.'},
            'evidence_ids': evidence})}}
        with pytest.raises(ValueError):
            await caller.run(request(), model_transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json=payload)))


@pytest.mark.asyncio
async def test_unconfigured_auto_ontology_is_skipped_before_model(monkeypatch):
    monkeypatch.setattr(caller, 'settings', type('Config', (), {'auto_ontology_url': '',
                                                             'auto_ontology_api_token': ''})())
    value = request()
    value['arm'] = 'auto_ontology'

    def forbidden(_):
        raise AssertionError('Model should not be called')
    result = await caller.run(value, model_transport=httpx.MockTransport(forbidden))
    assert result['status'] == 'skipped' and 'output' not in result


@pytest.mark.asyncio
async def test_injected_ontology_transport_cannot_claim_live_execution(monkeypatch):
    path = Path(__file__).resolve().parents[1] / 'fixtures/ontology/auto-ontology-live.json'
    snapshot = json.loads(path.read_text(encoding='utf-8'))
    config = replace(settings, auto_ontology_url='https://ontology.example',
                     auto_ontology_api_token='test-token')
    monkeypatch.setattr(caller, 'settings', config)
    original_client = httpx.AsyncClient

    def model_response(http_request):
        return httpx.Response(200, json={'model': json.loads(http_request.content)['model'],
            'done': True, 'done_reason': 'stop', 'message': {'content': json.dumps({
                'decision': {'action': 'request_evidence', 'amount': 0, 'reason': 'More case evidence is required.'},
                'evidence_ids': ['juniper-policy-v1@1']})}})

    def clients(**kwargs):
        if kwargs.get('trust_env') is False and kwargs.get('transport') is None:
            kwargs['transport'] = httpx.MockTransport(model_response)
        return original_client(**kwargs)
    monkeypatch.setattr(httpx, 'AsyncClient', clients)

    def ontology_response(http_request):
        if http_request.url.path == '/api/terms':
            return httpx.Response(200, json={'terms': snapshot['terms'], 'total': 3})
        term = next(term for term in snapshot['terms'] if http_request.url.path.endswith(term['id']))
        return httpx.Response(200, json={'data': term})
    value = request()
    value['arm'] = 'auto_ontology'
    value['options'] = {'snapshot': {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}}
    result = await caller.run(value, ontology_transport=httpx.MockTransport(ontology_response))
    assert result['status'] == 'completed' and result['execution'] == 'transport_mock'


@pytest.mark.asyncio
async def test_caller_rejects_model_identity_mismatch():
    payload = {'model': 'some-other-model', 'done': True, 'done_reason': 'stop',
               'message': {'content': '{}'}}
    with pytest.raises(ValueError, match='identity'):
        await caller.run(request(), model_transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json=payload)))
