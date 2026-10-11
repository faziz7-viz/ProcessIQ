"""Course journeys keep production SDK/controller/UI and mock only HTTP."""

import json
from pathlib import Path

import httpx
from openai import OpenAI
from streamlit.testing.v1 import AppTest

from test_app import open_sample_data, button, text, checkbox
from test_interview import output
from test_llm import response
from test_recommendations import selection, workflow

APP = Path(__file__).resolve().parents[1] / 'app.py'


def complete_extraction():
    owner = workflow()
    draft = owner.model_dump(mode='json')
    for key in ('currency', 'data_kind', 'source_messages'):
        draft.pop(key)
    facts = [draft['monthly_volume']]
    for step in draft['steps']:
        step.pop('order')
        facts.extend(step[field] for field in ('active_time', 'waiting_time', 'people', 'hourly_labor_cost'))
    for fact in facts:
        fact.pop('confirmed')
        for evidence in fact['evidence']:
            evidence['message_id'] = 'owner-1'
    description = f'The process starts when {owner.start_point} and ends when {owner.end_point}.\n'
    description += '\n'.join(source.text for source in owner.source_messages)
    return description, {'workflow': draft, 'question': None, 'target': None}


def metric(app, label):
    return next(item.value for item in app.metric if item.label == label)


def test_complete_description_to_corrected_assessment_and_failed_plan_recovery(monkeypatch):
    import processiq.llm as llm
    interview_adapter, planner_adapter = llm.OpenAIInterviewer, llm.OpenAIPlanner
    description, extracted = complete_extraction()
    requests = []
    failure = {'enabled': False}
    def handler(req):
        body = json.loads(req.content)
        requests.append(body['text']['format']['name'])
        if failure['enabled']:
            return httpx.Response(503, json={'error': {'message': 'secret-provider-details', 'type': 'api_error'}})
        reply = extracted if requests[-1] == 'InterviewOutput' else selection()
        return httpx.Response(200, json=response(reply))
    with OpenAI(api_key='test-only-key', max_retries=0,
                http_client=httpx.Client(transport=httpx.MockTransport(handler))) as client:
        monkeypatch.setattr(llm, 'OpenAIInterviewer', lambda: interview_adapter(client=client))
        monkeypatch.setattr(llm, 'OpenAIPlanner', lambda: planner_adapter(client=client))
        app = AppTest.from_file(str(APP), default_timeout=20).run()
        open_sample_data(app)
        button(app, "Load selected demo").click().run()
        button(app, 'Start AI interview').click().run()
        app.text_input[0].set_value(description).run()
        button(app, 'Continue').click().run()
        assert not app.exception
        button(app, 'Finish & review').click().run()
        next(c for c in app.checkbox if c.label == "This matches the workflow I want to assess").check().run()
        button(app, "Save reviewed facts").click().run()
        button(app, 'Calculate dashboard').click().run()
        assert metric(app, 'Labor cost / case') == 'Unavailable'
        checkbox(app, 'confirm_all').check().run()
        button(app, 'Save reviewed facts').click().run()
        button(app, 'Calculate dashboard').click().run()
        assert metric(app, 'Labor cost / case') == '$137.50'
        assert metric(app, 'Projected labor cost / month') == '$2,750.00'
        button(app, 'Generate AI plan').click().run()
        assert not app.exception
        assert app.session_state['plan'].mode == 'ai'
        assert app.session_state['workflow'].data_kind == 'owner_provided'
        text(app, 'steps.prepare-estimate.active_time').set_value('30').run()
        assert not app.metric
        assert app.session_state['plan'] is None
        checkbox(app, 'confirmed.steps.prepare-estimate.active_time').check().run()
        button(app, 'Save reviewed facts').click().run()
        button(app, 'Calculate dashboard').click().run()
        button(app, 'Generate AI plan').click().run()
        assert metric(app, 'Labor cost / case') == '$126.25'
        assert metric(app, 'Projected labor cost / month') == '$2,525.00'
        assert any('$126.25' in item.value for item in app.text)
        saved_plan = app.session_state['plan']
        failure['enabled'] = True
        button(app, 'Generate AI plan').click().run()
        assert not app.exception
        assert app.error
        assert app.session_state['plan'] == saved_plan
        assert metric(app, 'Labor cost / case') == '$126.25'
        assert all('secret-provider-details' not in error.value for error in app.error)
        request_count = len(requests)
        app.run()
        assert len(requests) == request_count


def test_failed_followup_preserves_answer_and_available_extraction(monkeypatch):
    import processiq.llm as llm
    adapter = llm.OpenAIInterviewer
    count = []
    def handler(req):
        count.append(req)
        if len(count) > 1:
            return httpx.Response(403, json={'error': {'message': 'secret-provider-details', 'type': 'api_error'}})
        return httpx.Response(200, json=response(output()))
    with OpenAI(api_key='test-only-key', max_retries=0,
                http_client=httpx.Client(transport=httpx.MockTransport(handler))) as client:
        monkeypatch.setattr(llm, 'OpenAIInterviewer', lambda: adapter(client=client))
        app = AppTest.from_file(str(APP), default_timeout=20).run()
        open_sample_data(app)
        button(app, "Load selected demo").click().run()
        button(app, 'Start AI interview').click().run()
        app.text_input[0].set_value('Receiving takes 10 minutes.').run()
        button(app, 'Continue').click().run()
        previous = app.session_state['interview_session']
        app.text_input[0].set_value('We handle 20 cases per month.').run()
        button(app, 'Continue').click().run()
        assert not app.exception
        assert app.error
        assert app.text_input[0].value == 'We handle 20 cases per month.'
        assert app.session_state['interview_session'] == previous
        button(app, 'Finish & review').click().run()
        next(c for c in app.checkbox if c.label == "This matches the workflow I want to assess").check().run()
        button(app, "Save reviewed facts").click().run()
        button(app, 'Calculate dashboard').click().run()
        button(app, 'Create offline plan').click().run()
        assert not app.exception
        assert metric(app, 'Labor cost / case') == 'Unavailable'
        assert app.session_state['plan'].actions[0].code == 'collect_facts'


def test_incomplete_demo_plan_correction_and_reset_keep_unknowns_unknown():
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    open_sample_data(app)
    button(app, "Load selected demo").click().run()
    app.sidebar.radio[0].set_value('Incomplete contractor demo').run()
    button(app, 'Load selected demo').click().run()
    button(app, 'Calculate dashboard').click().run()
    button(app, 'Create offline plan').click().run()
    assert metric(app, 'Labor cost / case') == 'Unavailable'
    assert any('Known subtotal only: $5.00' in caption.value for caption in app.caption)
    text(app, 'steps.receive-inquiry.active_time').set_value('15').run()
    checkbox(app, 'confirmed.steps.receive-inquiry.active_time').check().run()
    button(app, 'Save reviewed facts').click().run()
    button(app, 'Calculate dashboard').click().run()
    assert metric(app, 'Labor cost / case') == 'Unavailable'
    assert any('Known subtotal only: $7.50' in caption.value for caption in app.caption)
    button(app, 'Reset current demo').click().run()
    assert not app.exception
    assert app.session_state['analysis'] is None
    assert app.session_state['plan'] is None
    assert app.session_state['workflow'].steps[0].active_time.value == 10
    assert app.session_state['workflow'].monthly_volume.value is None
