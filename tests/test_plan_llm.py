import json

import httpx
import pytest
from openai import OpenAI

from processiq.llm import InterviewError, OpenAIPlanner
from processiq.recommendations import generate_plan
from test_llm import response
from test_recommendations import selection, workflow


def test_real_sdk_selects_plan_without_generating_numbers_or_quotes():
    received = []
    def handler(req):
        received.append(json.loads(req.content))
        return httpx.Response(200, json=response(selection()))
    with OpenAI(api_key='test-only-key', http_client=httpx.Client(transport=httpx.MockTransport(handler))) as client:
        plan = generate_plan(workflow(), OpenAIPlanner(client=client))
    assert plan.mode == 'ai'
    assert plan.actions[0].code == 'track_wait'
    body = received[0]
    assert body['store'] is False
    schema = body['text']['format']['schema']
    assert body['text']['format']['strict'] is True
    assert set(schema['properties']) == {'finding_ids', 'actions'}
    payload = json.loads(body['input'][1]['content'])
    assert any(f['id'] == 'waiting-step-follow-up' for f in payload['catalog'])
    assert 'test-only-key' not in json.dumps(body)


@pytest.mark.parametrize('status', [401, 403, 429, 500])
def test_plan_provider_errors_are_safe(status):
    def handler(req):
        return httpx.Response(status, json={'error': {'message': 'secret-provider-details', 'type': 'api_error'}})
    with OpenAI(api_key='test-only-key', max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(handler))) as client:
        with pytest.raises(InterviewError) as exc:
            generate_plan(workflow(), OpenAIPlanner(client=client))
    assert 'secret-provider-details' not in str(exc.value)
    assert 'test-only-key' not in str(exc.value)


@pytest.mark.parametrize('body', [
    response(refusal=True), response(status='incomplete'),
    response({**selection(), 'savings': '9999'}),
    response({'finding_ids': ['waiting-step-follow-up'], 'actions': []}),
])
def test_bad_plan_response_is_rejected(body):
    def handler(req):
        return httpx.Response(200, json=body)
    with OpenAI(api_key='test-only-key', http_client=httpx.Client(transport=httpx.MockTransport(handler))) as client:
        with pytest.raises(InterviewError):
            generate_plan(workflow(), OpenAIPlanner(client=client))


def test_plan_timeout_is_safe():
    def handler(req):
        raise httpx.ReadTimeout('secret-network-details', request=req)
    with OpenAI(api_key='test-only-key', max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(handler))) as client:
        with pytest.raises(InterviewError, match='could not be reached') as exc:
            generate_plan(workflow(), OpenAIPlanner(client=client))
    assert 'secret-network-details' not in str(exc.value)


def test_missing_key_plan_error_is_actionable(monkeypatch):
    import processiq.llm as llm
    monkeypatch.setattr(llm, 'load_api_configuration', lambda: {})
    with pytest.raises(InterviewError, match='ProcessIQ/.env'):
        generate_plan(workflow(), OpenAIPlanner())


def test_invalid_catalog_reference_from_real_sdk_is_rejected():
    def handler(req):
        return httpx.Response(200, json=response(selection('invented')))
    with OpenAI(api_key='test-only-key', http_client=httpx.Client(transport=httpx.MockTransport(handler))) as client:
        with pytest.raises(ValueError, match='unknown'):
            generate_plan(workflow(), OpenAIPlanner(client=client))
