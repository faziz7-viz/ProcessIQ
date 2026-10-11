from pathlib import Path
import json
import re
import httpx
import pytest
from openai import OpenAI
from streamlit.testing.v1 import AppTest
from test_llm import response
from test_interview import output, Reply
from test_app import button, open_optional_interview, open_sample_data
from processiq.interview import InterviewSession, advance_interview

APP = Path(__file__).resolve().parents[1] / 'app.py'
FIRST = 'Walk me through your typical workday.'


def test_optional_interview_has_one_easy_question_and_no_transcript():
    app = AppTest.from_file(str(APP)).run()
    open_optional_interview(app)
    assert not app.title
    assert FIRST in re.sub('<[^>]+>', '', ''.join(str(x.proto.body) for x in app.get('html')))
    assert not app.subheader
    assert not app.sidebar.title
    assert not app.get('progress')
    assert app.text_input[0].value == ''
    assert not any(b.label == 'Finish & review' for b in app.button)
    assert len(app.text_input) == 1
    assert not app.chat_message
    assert button(app, 'Continue')
    assert not any(b.label == 'Back' for b in app.button)
    assert button(app, 'Not sure')


@pytest.mark.parametrize('answer,question', [
    ('I checked a customer estimate request.', 'What did you do with that request next?'),
    ('I loaded tools into the van.', 'Where did you take those tools next?'),
])
def test_real_adapter_receives_question_answer_context_and_model_branches(answer, question):
    from processiq.llm import OpenAIInterviewer
    requests = []
    def handle(req):
        payload = json.loads(req.content)
        requests.append(json.loads(payload['input'][1]['content']))
        return httpx.Response(200, json=response({'workflow': None, 'question': question, 'target': 'process_details'}))
    with OpenAI(api_key='synthetic-test', http_client=httpx.Client(transport=httpx.MockTransport(handle))) as sdk:
        state = advance_interview(InterviewSession(), answer, OpenAIInterviewer(client=sdk))
    assert state.question == question
    assert requests[0]['conversation'][0] == {'question': FIRST, 'answer': answer, 'message_id': 'owner-1'}


def test_back_removes_dependent_sources_and_extraction():
    from processiq.interview import rewind_interview
    first = advance_interview(InterviewSession(), 'Receiving takes 10 minutes.', Reply(output()))
    second = advance_interview(first, 'Not sure', Reply({'workflow': None, 'question': 'Who receives the inquiry?', 'target': 'process_details'}))
    restored = rewind_interview(second)
    assert restored == first
    empty = rewind_interview(restored)
    assert empty.sources == ()
    assert empty.workflow is None


def test_duplicate_question_is_not_reasked():
    first = advance_interview(InterviewSession(), 'Receiving takes 10 minutes.', Reply(output()))
    second = advance_interview(first, 'Not sure', Reply(output()))
    assert second.question is None
    assert second.workflow.monthly_volume.value is None


def test_multi_question_output_is_rejected_atomically():
    with pytest.raises(ValueError):
        advance_interview(InterviewSession(), 'I received an inquiry.', Reply({'workflow': None, 'question': 'What happened next? Who did it?', 'target': 'process_details'}))


def test_ui_back_revises_and_clears_dependent_results(monkeypatch):
    import processiq.llm as llm
    replies = [
        {'workflow': None, 'question': 'What happened after loading the van?', 'target': 'process_details'},
        {'workflow': None, 'question': 'What did you do with the request next?', 'target': 'process_details'},
    ]
    class Client:
        def extract(self, **kwargs):
            return replies.pop(0)
    monkeypatch.setattr(llm, 'OpenAIInterviewer', Client)
    app = AppTest.from_file(str(APP)).run()
    open_optional_interview(app)
    app.text_input[0].set_value('I loaded tools into the van.').run()
    button(app, 'Continue').click().run()
    assert len(app.get('html')) >= 1
    assert 'What happened after loading the van?' in re.sub('<[^>]+>', '', ''.join(str(x.proto.body) for x in app.get('html')))
    button(app, 'Back').click().run()
    assert FIRST in re.sub('<[^>]+>', '', ''.join(str(x.proto.body) for x in app.get('html')))
    assert app.text_input[0].value == 'I loaded tools into the van.'
    assert app.session_state['interview_session'].sources == ()
    app.text_input[0].set_value('I checked a customer request.').run()
    button(app, 'Continue').click().run()
    assert 'What did you do with the request next?' in re.sub('<[^>]+>', '', ''.join(str(x.proto.body) for x in app.get('html')))
    assert app.session_state['analysis'] is None
    assert app.session_state['plan'] is None
    assert not app.chat_message


def test_adapter_gets_all_previous_answers_and_questions():
    from processiq.llm import OpenAIInterviewer
    payloads = []
    def handle(req):
        payloads.append(json.loads(json.loads(req.content)['input'][1]['content']))
        question = 'What happened after loading the van?' if len(payloads) == 1 else 'What did you do at the job site?'
        return httpx.Response(200, json=response({'workflow': None, 'question': question, 'target': 'process_details'}))
    with OpenAI(api_key='synthetic-test', http_client=httpx.Client(transport=httpx.MockTransport(handle))) as sdk:
        client = OpenAIInterviewer(client=sdk)
        first = advance_interview(InterviewSession(), 'I loaded tools.', client)
        second = advance_interview(first, 'I drove to the job site.', client)
    assert payloads[1]['conversation'] == [
        {'question': FIRST, 'answer': 'I loaded tools.', 'message_id': 'owner-1'},
        {'question': first.question, 'answer': 'I drove to the job site.', 'message_id': 'owner-2'},
    ]
    assert second.question == 'What did you do at the job site?'


def test_unknown_during_discovery_does_not_skip_all_process_questions():
    first = advance_interview(InterviewSession(), 'I checked messages.', Reply({'workflow': None, 'question': 'Which message did you work on first?', 'target': 'process_details'}))
    second = advance_interview(first, 'Not sure', Reply({'workflow': None, 'question': 'What did you do after checking messages?', 'target': 'process_details'}))
    assert second.workflow is None
    assert second.question == 'What did you do after checking messages?'
    assert 'process_details' not in second.skipped


def test_ui_requires_workflow_confirmation_before_calculation(monkeypatch):
    import processiq.llm as llm
    monkeypatch.setattr(llm, 'OpenAIInterviewer', lambda: Reply(output()))
    app = AppTest.from_file(str(APP)).run()
    open_optional_interview(app)
    app.text_input[0].set_value('Receiving takes 10 minutes.').run()
    button(app, 'Continue').click().run()
    button(app, 'Finish & review').click().run()
    assert button(app, 'Calculate dashboard').disabled
    next(c for c in app.checkbox if c.label == 'This matches the workflow I want to assess').check().run()
    button(app, 'Save reviewed facts').click().run()
    button(app, 'Calculate dashboard').click().run()
    assert not app.exception
    assert next(m.value for m in app.metric if m.label == 'Labor cost / case') == 'Unavailable'




def test_hidden_review_preserves_workflow_confirmation(monkeypatch):
    app = AppTest.from_file(str(APP)).run()
    open_sample_data(app)
    button(app, 'Load selected demo').click().run()
    assert app.session_state['workflow_confirmed'] is True
    button(app, 'Start AI interview').click().run()
    app.run()  # allow Streamlit's hidden-widget cleanup
    button(app, 'Return to saved process').click().run()
    assert not app.exception
    assert app.session_state['workflow_confirmed'] is True
    assert not button(app, 'Calculate dashboard').disabled


def test_no_draft_duplicate_question_does_not_dead_end():
    first = advance_interview(InterviewSession(), 'I checked messages.', Reply({'workflow':None,'question':'What happened next?','target':'process_details'}))
    with pytest.raises(ValueError):
        advance_interview(first, 'Not sure', Reply({'workflow':None,'question':'What happened next?','target':'process_details'}))
    assert first.question == 'What happened next?'
    assert len(first.sources) == 1


def test_paraphrase_cannot_reask_known_unchanged_numeric_fact():
    first = advance_interview(InterviewSession(), 'Receiving takes 10 minutes.', Reply(output()))
    reply = {**output(), 'target':'steps.receive.active_time','question':'How long do you actively spend receiving an inquiry?'}
    second = advance_interview(first, 'Not sure', Reply(reply))
    assert second.question is None


def test_latest_answer_known_fact_is_not_immediately_reasked():
    reply = {**output(), 'target':'steps.receive.active_time','question':'How many active minutes does receiving take?'}
    state = advance_interview(InterviewSession(), 'Receiving takes 10 minutes.', Reply(reply))
    assert state.workflow.steps[0].active_time.value == 10
    assert state.question is None


def test_discovery_limit_offers_back_or_restart_without_fake_review():
    class Client:
        def extract(self, **kwargs):
            return {'workflow':None,'question':f'What happened in activity {len(kwargs["sources"])}?','target':'process_details'}
    from processiq.interview import MAX_TURNS
    state = InterviewSession()
    for _ in range(MAX_TURNS):
        state = advance_interview(state, 'Not sure', Client())
    app = AppTest.from_file(str(APP)).run()
    open_optional_interview(app)
    app.session_state['interview_session'] = state
    app.run()
    assert not app.exception
    assert not app.text_input
    assert not button(app, 'Back').disabled
    assert not any(b.label == 'Finish & review' for b in app.button)
    assert any('Go back or restart' in item.value for item in app.markdown)
