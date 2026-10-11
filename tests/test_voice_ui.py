from pathlib import Path
import io
import streamlit as st
from streamlit.testing.v1 import AppTest
from test_app import button, open_optional_interview, open_sample_data
from test_speech import wav
from processiq.llm import InterviewError

APP = Path(__file__).resolve().parents[1] / 'app.py'


def test_transcript_is_editable_and_never_automatically_an_answer(monkeypatch):
    import processiq.speech as speech
    calls = []
    monkeypatch.setattr(st, 'audio_input', lambda *a, **kw:io.BytesIO(wav()))
    monkeypatch.setattr(speech, 'transcribe_recording', lambda audio:calls.append(audio) or 'I check orders.')
    app = AppTest.from_file(str(APP)).run()
    open_optional_interview(app)
    assert calls == []
    button(app, 'Transcribe recording').click().run()
    assert len(calls) == 1
    assert app.text_input[0].value == 'I check orders.'
    assert app.session_state['interview_session'].sources == ()
    app.text_input[0].set_value('I check customer orders.').run()
    assert app.text_input[0].value == 'I check customer orders.'
    assert len(calls) == 1


def test_transcription_failure_preserves_typed_draft(monkeypatch):
    import processiq.speech as speech
    def fail(audio):
        raise InterviewError('Try again or type your answer.')
    monkeypatch.setattr(st, 'audio_input', lambda *a, **kw:io.BytesIO(wav()))
    monkeypatch.setattr(speech, 'transcribe_recording', fail)
    app = AppTest.from_file(str(APP)).run()
    open_optional_interview(app)
    app.text_input[0].set_value('Keep my existing answer.').run()
    button(app, 'Transcribe recording').click().run()
    assert app.error
    assert app.text_input[0].value == 'Keep my existing answer.'
    assert app.session_state['interview_session'].sources == ()


def test_empty_continue_cannot_submit_a_hint(monkeypatch):
    import processiq.llm as llm
    def unexpected():
        raise AssertionError('Placeholder must not make a provider request')
    monkeypatch.setattr(llm, 'OpenAIInterviewer', unexpected)
    app = AppTest.from_file(str(APP)).run()
    open_optional_interview(app)
    button(app, 'Continue').click().run()
    assert not app.exception
    assert app.info
    assert app.text_input[0].value == ''
    assert app.session_state['interview_session'].sources == ()
