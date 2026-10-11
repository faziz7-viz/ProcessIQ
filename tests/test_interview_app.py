from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from test_interview import Reply, output
from test_app import open_sample_data

APP = Path(__file__).resolve().parents[1] / "app.py"


def button(app, label):
    return next(widget for widget in app.button if widget.label == label)


def test_interview_handoff_leads_to_unconfirmed_owner_draft(monkeypatch):
    import processiq.llm as llm
    client = Reply(output())
    monkeypatch.setattr(llm, "OpenAIInterviewer", lambda: client)
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    open_sample_data(app)
    button(app, "Load selected demo").click().run()
    button(app, "Start AI interview").click().run()
    app.text_input[0].set_value("Receiving takes 10 minutes.").run()
    button(app, "Continue").click().run()
    assert not app.exception
    assert client.calls == 1
    app.run()
    assert client.calls == 1  # ordinary reruns never trigger paid requests
    button(app, "Finish & review").click().run()
    next(c for c in app.checkbox if c.label == "This matches the workflow I want to assess").check().run()
    button(app, "Save reviewed facts").click().run()
    assert not app.exception
    assert app.session_state["workflow"].data_kind == "owner_provided"
    assert app.session_state["workflow"].steps[0].active_time.confirmed is False
    assert not app.metric
    button(app, "Calculate dashboard").click().run()
    assert next(metric for metric in app.metric if metric.label == "Labor cost / case").value == "Unavailable"
    button(app, "Start AI interview").click().run()
    assert not app.exception
    assert app.session_state["interviewing"] is True
    assert app.session_state["interview_session"].sources == ()


def test_api_failure_preserves_answer_and_does_not_replace_saved_workflow(monkeypatch):
    import processiq.llm as llm
    class Failure:
        def extract(self, **kwargs):
            raise llm.InterviewError("Service temporarily unavailable")
    monkeypatch.setattr(llm, "OpenAIInterviewer", lambda: Failure())
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    open_sample_data(app)
    button(app, "Load selected demo").click().run()
    button(app, "Start AI interview").click().run()
    app.text_input[0].set_value("Receiving takes 10 minutes.").run()
    button(app, "Continue").click().run()
    assert not app.exception
    assert app.error
    assert app.text_input[0].value == "Receiving takes 10 minutes."
    assert app.session_state["interview_session"].sources == ()
    assert app.session_state["workflow"].data_kind == "synthetic"
