import json
import os
import httpx
import pytest
from pydantic import ValidationError
from caseflow.providers import OpenAIProvider, GeminiProvider, provider

DECISION = {'action': 'propose', 'amount': 100, 'reason': 'A synthetic duplicate is evidenced.'}

@pytest.mark.asyncio
async def test_openai_sdk_contract():
    def handle(request):
        body = json.loads(request.content)
        assert body['response_format']['json_schema']['strict'] is True
        assert body['messages'][0]['role'] == 'system'
        return httpx.Response(200, json={'id': 'fixture', 'object': 'chat.completion', 'created': 0, 'model': 'fixture',
            'choices': [{'index': 0, 'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': json.dumps(DECISION)}}]})
    assert (await OpenAIProvider('fixture-key', httpx.MockTransport(handle)).decide({'case': 'fixture'})).amount == 100

@pytest.mark.asyncio
async def test_gemini_sdk_contract():
    def handle(request):
        body = json.loads(request.content)
        assert body['generationConfig']['responseMimeType'] == 'application/json'
        return httpx.Response(200, json={'candidates': [{'content': {'role': 'model', 'parts': [{'text': json.dumps(DECISION)}]}, 'finishReason': 'STOP'}]})
    assert (await GeminiProvider('fixture-key', httpx.MockTransport(handle)).decide({'case': 'fixture'})).action == 'propose'

@pytest.mark.asyncio
async def test_invalid_structured_result_rejected():
    def handle(request):
        return httpx.Response(200, json={'id': 'fixture', 'object': 'chat.completion', 'created': 0, 'model': 'fixture',
            'choices': [{'index': 0, 'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': '{"action":"wire_money"}'}}]})
    with pytest.raises(ValidationError):
        await OpenAIProvider('fixture', httpx.MockTransport(handle)).decide({})

@pytest.mark.asyncio
async def test_provider_failure_has_no_demo_fallback():
    calls = []
    def handle(request):
        calls.append(1)
        return httpx.Response(503, json={'error': {'message': 'fixture outage', 'type': 'server_error'}})
    with pytest.raises(Exception):
        await OpenAIProvider('fixture', httpx.MockTransport(handle)).decide({})
    assert len(calls) == 2

@pytest.mark.live
@pytest.mark.asyncio
@pytest.mark.skipif(os.getenv('RUN_LIVE') != '1', reason='External provider not verified; opt in with RUN_LIVE=1')
async def test_live_provider_smoke():
    result = await provider().decide({'case': {'amount': 100}, 'movements': [], 'policy': 'Request missing evidence.'})
    assert result.action in {'propose', 'request_evidence', 'reject'}
