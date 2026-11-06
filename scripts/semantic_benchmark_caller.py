"""Blind Release Lab caller using a real local model; no workflow effects execute."""
import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
import sys

import httpx
from pydantic import BaseModel, ConfigDict, Field

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'services/api'))
from caseflow.config import settings  # noqa: E402
from caseflow.domain import Decision  # noqa: E402
from caseflow.ontology import digest, resolve_context  # noqa: E402
from caseflow.providers import SYSTEM  # noqa: E402


class Proof(BaseModel):
    model_config = ConfigDict(extra='forbid')
    decision: Decision
    evidence_ids: list[str] = Field(max_length=100)


def allowed_evidence(context):
    policy = context['policy']
    allowed = {policy.get('source_id', f"{policy['id']}@{policy['version']}")}
    allowed.update(item['id'] for item in context.get('movements', {}).get('movements', []))
    allowed.update(item['id'] for item in context.get('case', {}).get('evidence', []))
    return allowed


async def run(request, *, model_transport=None, ontology_transport=None):
    execution = 'transport_mock' if model_transport is not None or ontology_transport is not None else 'live'
    case = request['case']
    if set(case) != {'id', 'kind', 'prompt', 'context'} or case['kind'] != 'agent':
        raise ValueError('Expected a blind agent case without goldens')
    context = json.loads(case['context'])
    options = request.get('options', {})
    arm = request['arm']
    if arm not in {'baseline', 'glossary', 'auto_ontology'}:
        raise ValueError('Unsupported arm')
    trace = [{'scope': 'decision_only', 'effects_executed': False, 'arm': arm,
              'input_sha256': digest(context)}]
    if arm != 'baseline':
        if arm == 'auto_ontology' and (not settings.auto_ontology_url or not settings.auto_ontology_api_token):
            return {'status': 'skipped', 'execution': execution, 'trace': trace,
                    'detail': 'Auto Ontology gateway/token not configured; no model decision executed'}
        selection = options.get('snapshots', {}).get(case['id'], options.get('snapshot'))
        if not isinstance(selection, dict):
            raise ValueError('A reviewed snapshot is required')
        config = replace(settings, ontology_mode=arm, ontology_required=True,
                         ontology_snapshot_path=selection['path'], ontology_snapshot_sha256=selection['sha256'],
                         ontology_timeout=float(options.get('ontology_timeout_seconds', 20)))
        subject = {**context['case'], 'mode': context.get('mode', 'LIVE'),
                   'currency': context['case'].get('currency', 'MXN'),
                   'movements': context['movements']['movements']}
        binding, audit = await resolve_context(subject, context['policy'], config, strict=True,
                                              transport=ontology_transport)
        if binding.strategy == 'baseline':
            raise ValueError('Benchmark semantic arm requires LIVE reviewed context')
        context = {**context, 'semantic_context': {
            'snapshot_id': binding.snapshot_id, 'terms': [term.model_dump() for term in binding.terms]}}
        trace.append({'source': 'reviewed_glossary' if arm == 'glossary' else 'auto_ontology_http',
                      **audit, 'snapshot_sha256': binding.snapshot_sha256,
                      'term_ids': [term.id for term in binding.terms]})
    allowed = allowed_evidence(context)
    model = os.environ.get('CASEFLOW_EVAL_MODEL', 'qwen3.5:4b')
    endpoint = os.environ.get('CASEFLOW_EVAL_OLLAMA_URL', 'http://127.0.0.1:11434').rstrip('/')
    body = {'model': model, 'stream': False, 'think': False, 'format': Proof.model_json_schema(),
            'messages': [{'role': 'system', 'content': SYSTEM +
                          ' Return a wrapper with decision and evidence_ids. Cite only observed policy, movement, '
                          'or evidence source IDs that support the decision. Do not cite ontology terms as case evidence. '
                          'An evidence request may cite the policy but must not invent a missing document.'},
                         {'role': 'user', 'content': json.dumps({'question': case['prompt'], 'context': context,
                                                               'allowed_evidence_ids': sorted(allowed)})}],
            'options': {'temperature': 0, 'seed': 42, 'num_predict': 1600}}
    async with httpx.AsyncClient(timeout=180, trust_env=False, transport=model_transport) as client:
        async with asyncio.timeout(180):
            response = await client.post(endpoint + '/api/chat', json=body)
            response.raise_for_status()
            result = response.json()
    if result.get('done') is not True or result.get('done_reason') != 'stop':
        raise ValueError('Local model response incomplete')
    if result.get('model') != model:
        raise ValueError('Local model identity differs from the requested model')
    proof = Proof.model_validate_json(result['message']['content'])
    ids = sorted(set(proof.evidence_ids))
    if not set(ids) <= allowed:
        raise ValueError('Model cited an unobserved evidence ID')
    tokens = None
    if type(result.get('prompt_eval_count')) is int and type(result.get('eval_count')) is int:
        tokens = result['prompt_eval_count'] + result['eval_count']
    trace.append({'scope': 'decision_only', 'model': model, 'temperature': 0, 'seed': 42,
                  'context_sha256': digest(context), 'validated_against': 'caseflow.domain.Decision',
                  'evidence_ids_valid': True, 'effects_executed': False})
    return {'status': 'completed', 'execution': execution, 'trace': trace,
            'output': {'answer': proof.decision.reason, 'citations': ids,
                       'tool_calls': [{'name': 'decision', 'arguments': {
                           'action': proof.decision.action, 'amount': proof.decision.amount, 'evidence_ids': ids}}],
                       'authorization': None, 'tokens': tokens},
            'provenance': {'scope': 'decision_only', 'model': model, 'ontology_generation': 'curated_terms'}}


def main():
    try:
        raw = sys.stdin.buffer.read(200001)
        if len(raw) > 200000:
            raise ValueError('Caller input exceeds size limit')
        result = asyncio.run(run(json.loads(raw)))
    except Exception as exc:
        result = {'status': 'error', 'execution': 'live', 'trace': [],
                  'detail': 'Decision-only caller failed: ' + type(exc).__name__}
    sys.stdout.buffer.write((json.dumps(result, ensure_ascii=False) + '\n').encode('utf-8'))
    sys.stdout.buffer.flush()


if __name__ == '__main__':
    main()
