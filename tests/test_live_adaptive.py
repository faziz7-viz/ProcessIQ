"""Explicitly opt-in synthetic-only real-model adaptive interview check."""
import os
import pytest
from processiq.interview import InterviewSession, advance_interview
from processiq.llm import OpenAIInterviewer, load_api_configuration


@pytest.mark.live
def test_live_two_workday_paths_and_unknown():
    if os.getenv('PROCESSIQ_LIVE_ADAPTIVE_TEST') != '1':
        pytest.skip('Set PROCESSIQ_LIVE_ADAPTIVE_TEST=1 to opt into synthetic live adaptive verification')
    if not load_api_configuration()['api_key']:
        pytest.fail('No existing configured provider key available for live adaptive verification')
    client = OpenAIInterviewer()
    answers = [
        'Yesterday I first checked a customer email asking us to quote a kitchen renovation.',
        'Yesterday I first loaded ladders and paint into the work van.',
    ]
    states = [advance_interview(InterviewSession(), answer, client) for answer in answers]
    for state in states:
        assert state.question and state.question.count('?') <= 1
        assert state.workflow is None, 'A single activity does not establish explicit workflow boundaries'
    assert states[0].question != states[1].question
    assert any(word in states[0].question.lower() for word in ('email','customer','quote','renovation','request'))
    assert any(word in states[1].question.lower() for word in ('van','paint','ladder','load','job','tools','drive'))
    unknown = advance_interview(states[0], 'Not sure', client)
    assert unknown.question != states[0].question
    assert unknown.workflow is None, 'Not sure must not invent the workflow or force completeness'
    print('SYNTHETIC LIVE FOLLOW-UPS:', states[0].question, '|', states[1].question)
    print('SYNTHETIC UNKNOWN FOLLOW-UP:', unknown.question)
