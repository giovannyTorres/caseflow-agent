"""Documented HTTP wire-shape fixtures, including valid JSON in incomplete responses.

References checked 2026-11-05: OpenAI official generated ChatCompletion types/SDK README;
Google GenerateContent API Candidate/PromptFeedback and Python SDK lifecycle reference.
No external model endpoint is contacted by these tests.
"""
import asyncio
from dataclasses import replace
import json
import os

import httpx
import pytest

import caseflow.providers as adapters
from caseflow.providers import GeminiProvider, OpenAIProvider, ProviderError, provider

DECISION = {'action': 'propose', 'amount': 100, 'reason': 'A synthetic duplicate is evidenced.'}


def openai_response(finish='stop', content=None, **message):
    return {'id': 'chatcmpl-contract-fixture', 'object': 'chat.completion', 'created': 1760000000,
            'model': 'gpt-4.1-mini', 'choices': [{'index': 0, 'finish_reason': finish,
                'message': {'role': 'assistant', 'content': json.dumps(DECISION) if content is None else content,
                            'refusal': None, **message}}],
            'usage': {'prompt_tokens': 18, 'completion_tokens': 15, 'total_tokens': 33}}


def gemini_response(finish='STOP', content=None):
    return {'candidates': [{'index': 0, 'content': {'role': 'model', 'parts': [
                {'text': json.dumps(DECISION) if content is None else content}]}, 'finishReason': finish,
                'safetyRatings': [{'category': 'HARM_CATEGORY_DANGEROUS_CONTENT', 'probability': 'NEGLIGIBLE'}]}],
            'usageMetadata': {'promptTokenCount': 18, 'candidatesTokenCount': 15, 'totalTokenCount': 33},
            'modelVersion': 'gemini-2.5-flash'}


def adapter_for(name, handler, monkeypatch):
    model = 'gpt-4.1-mini' if name == 'openai' else 'gemini-2.5-flash'
    monkeypatch.setattr(adapters, 'settings', replace(adapters.settings, model=model))
    cls = OpenAIProvider if name == 'openai' else GeminiProvider
    return cls('contract-fixture-not-a-real-key', httpx.MockTransport(handler))


@pytest.mark.asyncio
@pytest.mark.parametrize('name', ['openai', 'gemini'])
async def test_official_sdk_contract_and_resource_close(name, monkeypatch):
    def handle(request):
        body = json.loads(request.content)
        assert request.method == 'POST'
        if name == 'openai':
            assert request.url.path.endswith('/chat/completions')
            assert body['model'] == 'gpt-4.1-mini'
            assert body['response_format']['json_schema']['strict'] is True
            assert body['response_format']['json_schema']['schema']['additionalProperties'] is False
            assert body['messages'][0]['role'] == 'system'
            assert body['max_completion_tokens'] == adapters.settings.max_tokens
            return httpx.Response(200, json=openai_response())
        assert request.url.path.endswith('/models/gemini-2.5-flash:generateContent')
        assert body['generationConfig']['responseMimeType'] == 'application/json'
        assert body['generationConfig']['responseSchema']['required'] == ['action', 'amount', 'reason']
        assert body['systemInstruction']['parts'][0]['text'] == adapters.SYSTEM
        return httpx.Response(200, json=gemini_response())
    adapter = adapter_for(name, handle, monkeypatch)
    assert (await adapter.decide({'case': 'synthetic fixture'})).amount == 100
    assert adapter.http.is_closed


@pytest.mark.asyncio
@pytest.mark.parametrize('finish', ['length', 'content_filter', 'tool_calls', None])
async def test_openai_rejects_incomplete_terminal_even_when_json_is_valid(finish):
    adapter = OpenAIProvider('fixture', httpx.MockTransport(lambda _: httpx.Response(200, json=openai_response(finish))))
    with pytest.raises(ProviderError, match='incomplete'):
        await adapter.decide({})
    assert adapter.http.is_closed


@pytest.mark.asyncio
@pytest.mark.parametrize('finish', ['MAX_TOKENS', 'SAFETY', 'RECITATION', 'MALFORMED_FUNCTION_CALL', None])
async def test_gemini_rejects_incomplete_terminal_even_when_json_is_valid(finish):
    adapter = GeminiProvider('fixture', httpx.MockTransport(lambda _: httpx.Response(200, json=gemini_response(finish))))
    with pytest.raises(ProviderError, match='incomplete'):
        await adapter.decide({})
    assert adapter.http.is_closed


@pytest.mark.asyncio
async def test_gemini_unspecified_prompt_feedback_is_not_a_block():
    payload = gemini_response()
    payload['promptFeedback'] = {'blockReason': 'BLOCKED_REASON_UNSPECIFIED'}
    adapter = GeminiProvider('fixture', httpx.MockTransport(lambda _: httpx.Response(200, json=payload)))
    assert (await adapter.decide({})).action == 'propose'


@pytest.mark.asyncio
async def test_gemini_blocked_safety_rating_rejected_even_with_stop():
    payload = gemini_response()
    payload['candidates'][0]['safetyRatings'][0]['blocked'] = True
    adapter = GeminiProvider('fixture', httpx.MockTransport(lambda _: httpx.Response(200, json=payload)))
    with pytest.raises(ProviderError, match='blocked'):
        await adapter.decide({})


@pytest.mark.asyncio
@pytest.mark.parametrize('name', ['openai', 'gemini'])
async def test_blocked_or_refused_responses_never_become_decisions(name, monkeypatch):
    payload = (openai_response(refusal='Unable to help with that request') if name == 'openai' else
               {'promptFeedback': {'blockReason': 'SAFETY'}, 'candidates': []})
    adapter = adapter_for(name, lambda _: httpx.Response(200, json=payload), monkeypatch)
    with pytest.raises(ProviderError, match='declined'):
        await adapter.decide({})
    assert adapter.http.is_closed


@pytest.mark.asyncio
@pytest.mark.parametrize('name', ['openai', 'gemini'])
@pytest.mark.parametrize('text', ['{"action":"wire_money"}', '{"action":', 'null',
    json.dumps({**DECISION, 'amount': '100'}), json.dumps({**DECISION, 'amount': True})])
async def test_invalid_structured_result_rejected(name, text, monkeypatch):
    payload = openai_response(content=text) if name == 'openai' else gemini_response(content=text)
    adapter = adapter_for(name, lambda _: httpx.Response(200, json=payload), monkeypatch)
    with pytest.raises(ProviderError, match='invalid structured'):
        await adapter.decide({})
    assert adapter.http.is_closed


@pytest.mark.asyncio
@pytest.mark.parametrize('name', ['openai', 'gemini'])
async def test_unexpected_tool_calls_are_not_executed(name, monkeypatch):
    payload = openai_response(tool_calls=[{'id': 'call_fixture', 'type': 'function',
        'function': {'name': 'register_resolution', 'arguments': '{}'}}])
    if name == 'gemini':
        payload = gemini_response()
        payload['candidates'][0]['content']['parts'].append({'functionCall': {'name': 'register_resolution', 'args': {}}})
    adapter = adapter_for(name, lambda _: httpx.Response(200, json=payload), monkeypatch)
    with pytest.raises(ProviderError, match='unexpected'):
        await adapter.decide({})


@pytest.mark.asyncio
@pytest.mark.parametrize('name', ['openai', 'gemini'])
@pytest.mark.parametrize('status', [401, 429, 503])
async def test_failures_have_bounded_retries_safe_errors_and_no_demo_fallback(name, status, monkeypatch):
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(status, headers={'retry-after': '0'}, json={
            'error': {'code': status, 'message': 'secret-provider-body fixture-key',
                      'type': 'server_error', 'status': 'RESOURCE_EXHAUSTED' if status == 429 else 'UNAVAILABLE'}})
    adapter = adapter_for(name, handle, monkeypatch)
    with pytest.raises(ProviderError) as exc:
        await adapter.decide({})
    assert 'secret-provider-body' not in str(exc.value) and 'fixture-key' not in str(exc.value)
    assert len(calls) == (1 if status == 401 else 2)
    assert adapter.http.is_closed


@pytest.mark.asyncio
@pytest.mark.parametrize('name', ['openai', 'gemini'])
async def test_cancellation_closes_client(name, monkeypatch):
    started = asyncio.Event()
    async def handle(request):
        started.set()
        await asyncio.Event().wait()
    adapter = adapter_for(name, handle, monkeypatch)
    task = asyncio.create_task(adapter.decide({}))
    await asyncio.wait_for(started.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert adapter.http.is_closed


@pytest.mark.asyncio
@pytest.mark.parametrize('name', ['openai', 'gemini'])
async def test_deadline_includes_wait_for_capacity(name, monkeypatch):
    calls = []
    adapter = adapter_for(name, lambda request: calls.append(request), monkeypatch)
    monkeypatch.setattr(adapters, 'settings', replace(adapters.settings, timeout=0.01))
    monkeypatch.setattr(adapters, '_LIMIT', asyncio.Semaphore(0))
    with pytest.raises(ProviderError, match='timed out'):
        await asyncio.wait_for(adapter.decide({}), timeout=1)
    assert calls == []
    assert adapter.http.is_closed


@pytest.mark.live
@pytest.mark.asyncio
@pytest.mark.skipif(os.getenv('RUN_LIVE') != '1', reason='External provider not verified; opt in with RUN_LIVE=1')
async def test_live_provider_smoke():
    result = await provider().decide({'case': {'amount': 100}, 'movements': [], 'policy': 'Request missing evidence.'})
    assert result.action in {'propose', 'request_evidence', 'reject'}
