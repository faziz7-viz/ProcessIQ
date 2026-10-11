from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from processiq.llm import InterviewError
from processiq.recommendations import generate_plan
from test_app import open_sample_data, button, text
from test_recommendations import workflow

APP = Path(__file__).resolve().parents[1] / 'app.py'


def test_actions_include_suggested_effort_and_ui_explains_it():
    plan = generate_plan(workflow())
    assert all(action.effort in ('Small trial', 'Team review') for action in plan.actions)
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    open_sample_data(app)
    button(app, "Load selected demo").click().run()
    button(app, 'Calculate dashboard').click().run()
    button(app, 'Create offline plan').click().run()
    assert not app.exception
    assert any('Suggested effort:' in item.value for item in app.text)


def test_return_from_interview_preserves_saved_process_and_pending_edits(monkeypatch):
    import processiq.llm as llm
    def unexpected():
        pytest.fail('Navigation must not make an AI request')
    monkeypatch.setattr(llm, 'OpenAIInterviewer', unexpected)
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    open_sample_data(app)
    button(app, "Load selected demo").click().run()
    text(app, 'monthly_volume').set_value('17').run()
    saved = app.session_state['workflow']
    button(app, 'Start AI interview').click().run()
    app.text_input[0].set_value('Draft description, not submitted').run()
    button(app, 'Return to saved process').click().run()
    assert not app.exception
    assert app.session_state['workflow'] == saved
    assert text(app, 'monthly_volume').value == '17'
    assert app.session_state['dirty'] is True
    assert button(app, 'Calculate dashboard').disabled


def test_restart_while_interviewing_keeps_interview_mode_even_with_loaded_demo():
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    open_sample_data(app)
    button(app, "Load selected demo").click().run()
    button(app, 'Start AI interview').click().run()
    app.text_input[0].set_value('Draft description, not submitted').run()
    button(app, 'Restart AI interview').click().run()
    assert not app.exception
    assert app.session_state['interviewing'] is True
    assert app.text_input[0].value == ''
    assert app.session_state['interview_session'].sources == ()


def test_old_cached_action_without_effort_still_renders():
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    open_sample_data(app)
    button(app, "Load selected demo").click().run()
    button(app, 'Calculate dashboard').click().run()
    plan = generate_plan(app.session_state['workflow'])
    # Simulate a pre-update session object missing the newly added field.
    for action in plan.actions:
        action.__dict__.pop('effort', None)
    app.session_state['plan'] = plan
    app.run()
    assert not app.exception
    assert any('Suggested effort:' in item.value for item in app.text)
