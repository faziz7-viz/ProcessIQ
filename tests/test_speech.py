import io
import wave
import httpx
import pytest
from openai import OpenAI
from processiq.llm import InterviewError
from processiq.speech import transcribe_recording


def wav(seconds=1):
    out = io.BytesIO()
    with wave.open(out, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b'\0\0' * (16000 * seconds))
    return out.getvalue()


def test_recording_transcribes_without_submitting_an_interview_answer():
    requests = []
    def respond(req):
        requests.append(req)
        return httpx.Response(200, json={'text':'I check the incoming orders.'})
    with OpenAI(api_key='synthetic', http_client=httpx.Client(transport=httpx.MockTransport(respond))) as sdk:
        text = transcribe_recording(wav(), client=sdk)
    assert text == 'I check the incoming orders.'
    assert len(requests) == 1
    assert requests[0].url.path == '/v1/audio/transcriptions'
    assert b'gpt-4o-mini-transcribe' in requests[0].content


@pytest.mark.parametrize('audio', [b'', b'not audio', wav(121)])
def test_invalid_recording_is_rejected_before_provider_call(audio):
    with pytest.raises(InterviewError):
        transcribe_recording(audio, client=object())


def test_transcription_failure_is_safe_and_retryable():
    def respond(req):
        return httpx.Response(503, json={'error':{'message':'private provider detail'}})
    with OpenAI(api_key='synthetic', max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(respond))) as sdk:
        with pytest.raises(InterviewError, match='Try again or type'):
            transcribe_recording(wav(), client=sdk)


def test_empty_transcription_does_not_invent_an_answer():
    with OpenAI(api_key='synthetic', http_client=httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'text':''})))) as sdk:
        with pytest.raises(InterviewError, match='No speech'):
            transcribe_recording(wav(), client=sdk)
