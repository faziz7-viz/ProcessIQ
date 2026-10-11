import json
from types import SimpleNamespace

import httpx
import pytest
from openai import OpenAI

from processiq.llm import InterviewError, OpenAIInterviewer
from processiq.models import SourceMessage


def response(content=None, status="completed", refusal=False):
    item = {"type": "refusal", "refusal": "Cannot comply"} if refusal else {
        "type": "output_text", "text": json.dumps(content), "annotations": [],
    }
    return {
        "id": "resp_test", "object": "response", "created_at": 1, "status": status,
        "model": "gpt-5-mini", "output": [{"id": "msg_test", "type": "message", "role": "assistant",
                                               "status": "completed", "content": [item]}],
        "parallel_tool_calls": False, "tools": [], "tool_choice": "auto",
    }


def request(adapter):
    return adapter.extract(sources=(SourceMessage(id="owner-1", text="We do estimates."),),
                           previous=None, missing=["process_details"], skipped=())


def test_real_sdk_sends_structured_schema_and_parses_result():
    received = []
    def handler(req):
        received.append(json.loads(req.content))
        return httpx.Response(200, json=response({"workflow": None, "question": "What are the steps?", "target": "process_details"}))
    with OpenAI(api_key="test-only-key", http_client=httpx.Client(transport=httpx.MockTransport(handler))) as client:
        result = request(OpenAIInterviewer(client=client))
    assert result.question == "What are the steps?"
    body = received[0]
    assert body["store"] is False
    assert body["text"]["format"]["type"] == "json_schema"
    assert body["text"]["format"]["strict"] is True
    assert "owner_messages" in body["input"][1]["content"]
    assert "test-only-key" not in json.dumps(body)


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_provider_errors_are_safe_and_do_not_expose_response_details(status):
    def handler(req):
        return httpx.Response(status, json={"error": {"message": "secret-provider-details", "type": "api_error"}})
    with OpenAI(api_key="test-only-key", max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(handler))) as client:
        with pytest.raises(InterviewError) as exc:
            request(OpenAIInterviewer(client=client))
    assert "secret-provider-details" not in str(exc.value)
    assert "test-only-key" not in str(exc.value)


@pytest.mark.parametrize("body", [response(refusal=True), response(status="incomplete"),
                                      response({"workflow": "malformed", "question": None, "target": None})])
def test_refused_incomplete_or_malformed_output_is_rejected(body):
    def handler(req):
        return httpx.Response(200, json=body)
    with OpenAI(api_key="test-only-key", http_client=httpx.Client(transport=httpx.MockTransport(handler))) as client:
        with pytest.raises(InterviewError):
            request(OpenAIInterviewer(client=client))


def test_network_timeout_is_reported_without_request_details():
    def handler(req):
        raise httpx.ReadTimeout("secret-network-details", request=req)
    with OpenAI(api_key="test-only-key", max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(handler))) as client:
        with pytest.raises(InterviewError, match="could not be reached") as exc:
            request(OpenAIInterviewer(client=client))
    assert "secret-network-details" not in str(exc.value)


def test_missing_key_has_actionable_error(monkeypatch):
    import processiq.llm as llm
    monkeypatch.setattr(llm, "load_api_configuration", lambda: None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(InterviewError, match="ProcessIQ/.env"):
        request(OpenAIInterviewer())


def test_real_sdk_parses_full_workflow_schema():
    from test_interview import output
    from processiq.interview import InterviewSession, advance_interview
    def handler(req):
        return httpx.Response(200, json=response(output()))
    with OpenAI(api_key="test-only-key", http_client=httpx.Client(transport=httpx.MockTransport(handler))) as client:
        result = advance_interview(InterviewSession(), "Receiving takes 10 minutes.", OpenAIInterviewer(client=client))
    assert result.workflow.steps[0].active_time.value == 10
    assert result.workflow.steps[0].active_time.confirmed is False


@pytest.mark.parametrize("recover", [True, False])
def test_transient_retry_is_bounded_at_two_http_attempts(recover):
    calls = []
    def handler(req):
        calls.append(req)
        if recover and len(calls) == 2:
            return httpx.Response(200, json=response({"workflow": None, "question": "What are the steps?", "target": "process_details"}))
        return httpx.Response(503, json={"error": {"message": "Temporary", "type": "api_error"}})
    with OpenAI(api_key="test-only-key", max_retries=1, http_client=httpx.Client(transport=httpx.MockTransport(handler))) as client:
        if recover:
            assert request(OpenAIInterviewer(client=client)).question == "What are the steps?"
        else:
            with pytest.raises(InterviewError):
                request(OpenAIInterviewer(client=client))
    assert len(calls) == 2


def test_configuration_reads_current_file_without_caching_key_in_environment(monkeypatch, tmp_path):
    import processiq.llm as llm
    env_file = tmp_path / '.env'
    monkeypatch.setattr(llm, 'ENV_PATH', env_file, raising=False)
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.delenv('OPENAI_MODEL', raising=False)
    env_file.write_text('OPENAI_API_KEY=\nOPENAI_MODEL=gpt-5-mini\n')
    assert llm.load_api_configuration()['api_key'] == ''
    env_file.write_text('OPENAI_API_KEY=test-only-key\nOPENAI_MODEL=gpt-5-mini\n')
    assert llm.load_api_configuration()['api_key'] == 'test-only-key'
    import os
    assert os.getenv('OPENAI_API_KEY') is None
