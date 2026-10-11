"""Exercise CSV -> review -> dashboard -> plan without an interview or API."""

from io import BytesIO

from streamlit.testing.v1 import AppTest

from test_app import APP, button, checkbox, text, open_sample_data, open_optional_interview
from test_csv_import import CSV


class Upload(BytesIO):
    name = "painting_quotes.csv"


def test_start_screen_defaults_to_csv_and_interview_is_optional(monkeypatch):
    import processiq.llm as llm
    def no_api(*args, **kwargs):
        raise AssertionError("Getting started must not call AI")
    monkeypatch.setattr(llm, "OpenAIInterviewer", no_api)
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    assert app.radio[0].value == "Upload a CSV"
    assert app.get("file_uploader")
    assert not app.text_input
    assert not app.session_state["interviewing"]
    app.radio[0].set_value("AI interview (optional)").run()
    button(app, "Start AI interview").click().run()
    assert app.session_state["interviewing"]
    assert app.text_input[0].label == "Your answer"


def test_csv_review_correction_dashboard_and_offline_plan_need_no_ai(monkeypatch):
    import streamlit as st
    import processiq.llm as llm
    monkeypatch.setattr(st, "file_uploader", lambda *args, **kwargs: Upload(CSV))
    def no_api(*args, **kwargs):
        raise AssertionError("CSV assessment must work without AI")
    monkeypatch.setattr(llm, "OpenAIInterviewer", no_api)
    monkeypatch.setattr(llm, "OpenAIPlanner", no_api)
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    button(app, "Review uploaded data").click().run()
    assert not app.exception
    assert not app.session_state["interviewing"]
    assert text(app, "monthly_volume").value == "20"
    assert not any(b.label == "Restart AI interview" for b in app.button)
    assert button(app, "Calculate dashboard").disabled
    text(app, "steps.csv-step-2.active_time").set_value("20").run()
    next(c for c in app.checkbox if c.label == "This matches the workflow I want to assess").check().run()
    checkbox(app, "confirm_all").check().run()
    button(app, "Save reviewed facts").click().run()
    button(app, "Calculate dashboard").click().run()
    button(app, "Create offline plan").click().run()
    assert not app.exception
    assert next(m.value for m in app.metric if m.label == "Labor cost / case") == "$27.50"
    assert next(m.value for m in app.metric if m.label == "Projected labor cost / month") == "$550.00"
    assert app.session_state["plan"].mode == "offline"


def test_invalid_csv_preserves_saved_workflow(monkeypatch):
    import streamlit as st
    monkeypatch.setattr(st, "file_uploader", lambda *args, **kwargs: Upload(b"step_name,people\nReceive,-1\n"))
    app = AppTest.from_file(str(APP)).run()
    before = app.session_state["workflow"]
    button(app, "Review uploaded data").click().run()
    assert not app.exception
    assert app.error
    assert app.session_state["workflow"] == before
    assert app.session_state["show_start"]


def test_return_from_data_picker_preserves_pending_review_edits():
    app = AppTest.from_file(str(APP)).run()
    open_sample_data(app)
    button(app, "Load selected demo").click().run()
    text(app, "monthly_volume").set_value("17").run()
    button(app, "Choose data source").click().run()
    app.run()
    button(app, "Return to saved process").click().run()
    assert not app.exception
    assert text(app, "monthly_volume").value == "17"
    assert app.session_state["dirty"]
    assert button(app, "Calculate dashboard").disabled


def test_return_from_data_picker_preserves_unsubmitted_interview_answer():
    app = AppTest.from_file(str(APP)).run()
    open_optional_interview(app)
    app.text_input[0].set_value("I prepare estimates.").run()
    button(app, "Choose data source").click().run()
    app.run()
    button(app, "Return to saved process").click().run()
    assert not app.exception
    assert app.text_input[0].value == "I prepare estimates."
    assert app.session_state["interview_session"].sources == ()


def test_partial_csv_can_generate_partial_dashboard_and_plan(monkeypatch):
    import streamlit as st
    monkeypatch.setattr(st, "file_uploader", lambda *args, **kwargs: Upload(b"step_name,active_minutes\nReceive,10\n"))
    app = AppTest.from_file(str(APP)).run()
    button(app, "Review uploaded data").click().run()
    checkbox(app, "workflow_confirmed").check().run()
    checkbox(app, "confirm_all").check().run()
    button(app, "Save reviewed facts").click().run()
    button(app, "Calculate dashboard").click().run()
    button(app, "Create offline plan").click().run()
    assert not app.exception
    assert next(m.value for m in app.metric if m.label == "Labor cost / case") == "Unavailable"
    assert app.session_state["workflow"].monthly_volume.value is None
    assert app.session_state["plan"]


def test_new_upload_clears_previous_results(monkeypatch):
    import streamlit as st
    monkeypatch.setattr(st, "file_uploader", lambda *args, **kwargs: Upload(CSV))
    app = AppTest.from_file(str(APP)).run()
    open_sample_data(app)
    button(app, "Load selected demo").click().run()
    button(app, "Calculate dashboard").click().run()
    button(app, "Create offline plan").click().run()
    assert app.session_state["plan"]
    button(app, "Choose data source").click().run()
    app.radio[0].set_value("Upload a CSV").run()
    button(app, "Review uploaded data").click().run()
    assert not app.exception
    assert app.session_state["workflow"].steps[0].id == "csv-step-1"
    assert app.session_state["analysis"] is None
    assert app.session_state["plan"] is None
    assert not app.session_state["workflow_confirmed"]
