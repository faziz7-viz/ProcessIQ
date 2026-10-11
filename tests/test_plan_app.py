from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from processiq.llm import InterviewError
from processiq.recommendations import generate_plan
from test_app import open_sample_data, button, text, checkbox
from test_recommendations import selection

APP = Path(__file__).resolve().parents[1] / 'app.py'


def assessed():
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    open_sample_data(app)
    button(app, "Load selected demo").click().run()
    button(app, 'Calculate dashboard').click().run()
    assert not app.exception
    return app


def test_offline_plan_shows_explanations_actions_and_evidence_without_provider(monkeypatch):
    import processiq.llm as llm
    def unexpected():
        pytest.fail('Offline plan must never construct an API client')
    monkeypatch.setattr(llm, 'OpenAIPlanner', unexpected)
    app = assessed()
    button(app, 'Create offline plan').click().run()
    assert not app.exception
    assert app.session_state['plan'].mode == 'offline'
    assert any('$137.50' in item.value for item in app.text)
    assert any('2,880' in item.value for item in app.text)
    assert any('owner-follow-up' in item.value for item in app.text)
    assert any('offline' in item.value.lower() for item in app.caption)
    assert any('Try' in item.value or 'Track' in item.value for item in app.subheader)


def test_live_plan_only_calls_provider_on_explicit_button(monkeypatch):
    import processiq.llm as llm
    calls = []
    class Planner:
        def select(self, **kwargs):
            calls.append(kwargs)
            return selection()
    monkeypatch.setattr(llm, 'OpenAIPlanner', Planner)
    app = assessed()
    assert not calls
    button(app, 'Generate AI plan').click().run()
    assert not app.exception
    assert app.session_state['plan'].mode == 'ai'
    app.run()
    assert len(calls) == 1


@pytest.mark.parametrize('failure', ['provider', 'invalid'])
def test_failed_generation_preserves_existing_report(monkeypatch, failure):
    import processiq.llm as llm
    class BadPlanner:
        def select(self, **kwargs):
            if failure == 'provider':
                raise InterviewError('Service temporarily unavailable')
            return selection('invented')
    monkeypatch.setattr(llm, 'OpenAIPlanner', BadPlanner)
    app = assessed()
    button(app, 'Create offline plan').click().run()
    previous = app.session_state['plan']
    button(app, 'Generate AI plan').click().run()
    assert not app.exception
    assert app.error
    assert app.session_state['plan'] == previous
    assert app.metric


@pytest.mark.parametrize('action', ['edit', 'save', 'reset', 'load', 'interview', 'calculate', 'confirm'])
def test_report_is_cleared_when_assessment_changes(action):
    app = assessed()
    button(app, 'Create offline plan').click().run()
    if action == 'edit':
        text(app, 'monthly_volume').set_value('17').run()
    elif action == 'confirm':
        checkbox(app, 'confirmed.monthly_volume').uncheck().run()
    else:
        label = {'save': 'Save reviewed facts', 'reset': 'Reset current demo',
                 'load': 'Load selected demo', 'interview': 'Start AI interview',
                 'calculate': 'Calculate dashboard'}[action]
        button(app, label).click().run()
    assert not app.exception
    assert app.session_state['plan'] is None


def test_same_rerun_edit_cannot_generate_a_plan_from_unsaved_facts():
    app = assessed()
    text(app, 'monthly_volume').set_value('17')
    button(app, 'Create offline plan').click().run()
    assert not app.exception
    assert app.session_state['plan'] is None
    assert app.session_state['analysis'] is None


def test_incomplete_plan_renders_gaps_and_partial_results():
    app = assessed()
    app.sidebar.radio[0].set_value('Incomplete contractor demo').run()
    button(app, 'Load selected demo').click().run()
    button(app, 'Calculate dashboard').click().run()
    button(app, 'Create offline plan').click().run()
    assert not app.exception
    assert app.session_state['plan'].actions[0].code == 'collect_facts'
    assert any('Unavailable' in item.value for item in app.text)
    assert any('partial' in item.value.lower() for item in app.text)


def test_stale_report_fingerprint_clears_report():
    app = assessed()
    app.session_state['plan'] = generate_plan(app.session_state['workflow']).model_copy(update={'snapshot': 'old'})
    app.run()
    assert not app.exception
    assert app.session_state['plan'] is None


def test_legacy_assessment_session_initializes_missing_report_key():
    app = assessed()
    del app.session_state['plan']
    app.run()
    assert not app.exception
    assert app.session_state['plan'] is None


def test_changed_workflow_cannot_mix_old_dashboard_with_new_plan():
    from processiq.assessment import apply_review, review_values
    app = assessed()
    button(app, 'Create offline plan').click().run()
    owner = app.session_state['workflow']
    values = review_values(owner)
    values['steps.prepare-estimate.active_time'] = '30'
    app.session_state['workflow'] = apply_review(owner, values, confirm_all=True)
    app.run()
    assert not app.exception
    assert not app.metric
    assert app.session_state['analysis'] is None
    assert app.session_state['plan'] is None
    button(app, 'Calculate dashboard').click().run()
    button(app, 'Create offline plan').click().run()
    assert next(m for m in app.metric if m.label == 'Labor cost / case').value == '$126.25'
    assert any('$126.25' in item.value for item in app.text)


def test_legacy_stale_analysis_is_not_assumed_current():
    from processiq.assessment import apply_review, review_values
    app = assessed()
    del app.session_state['analysis_snapshot']
    owner = app.session_state['workflow']
    values = review_values(owner)
    values['steps.prepare-estimate.active_time'] = '30'
    app.session_state['workflow'] = apply_review(owner, values, confirm_all=True)
    app.run()
    assert not app.exception
    assert not app.metric
    assert app.session_state['analysis'] is None
