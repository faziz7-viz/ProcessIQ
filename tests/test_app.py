from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from processiq.analysis import analyze_workflow
from processiq.interview import InterviewSession
from processiq.models import Workflow

APP = Path(__file__).resolve().parents[1] / "app.py"


@pytest.mark.parametrize("pending_edits", [False, True])
def test_legacy_session_initializes_interview_without_losing_work(pending_edits):
    workflow = Workflow.model_validate_json(
        (APP.parent / "data" / "contractor_estimate.json").read_text()
    )
    analysis = None if pending_edits else analyze_workflow(workflow)
    app = AppTest.from_file(str(APP), default_timeout=20)
    for key, value in {
        "workflow": workflow, "loaded_demo": "Complete contractor demo",
        "analysis": analysis, "dirty": pending_edits, "notice": "Saved facts",
        "epoch": 3,
    }.items():
        app.session_state[key] = value
    if pending_edits:
        app.session_state["editor-3.monthly_volume"] = "17"
    app.run()
    assert not app.exception
    assert app.session_state["workflow"] == workflow
    assert app.session_state["analysis"] == analysis
    assert app.session_state["dirty"] is pending_edits
    assert app.session_state["epoch"] == 3
    assert app.session_state["notice"] == "Saved facts"
    assert app.session_state["interviewing"] is False
    assert app.session_state["interview_session"] == InterviewSession()
    if pending_edits:
        assert text(app, "monthly_volume").value == "17"
    else:
        assert app.metric


def test_partial_interview_session_initializes_missing_epoch():
    app = AppTest.from_file(str(APP), default_timeout=20)
    workflow = Workflow.model_validate_json(
        (APP.parent / "data" / "contractor_estimate.json").read_text()
    )
    app.session_state["workflow"] = workflow
    app.session_state["interviewing"] = True
    app.session_state["interview_session"] = InterviewSession()
    app.run()
    assert not app.exception
    assert app.session_state["interviewing"] is True
    assert app.text_input[0].key == "interview-answer-0-0"


def button(app, label):
    return next(widget for widget in app.button if widget.label == label)


def text(app, key):
    return next(widget for widget in app.text_input if widget.key.endswith(key))


def checkbox(app, key):
    return next(widget for widget in app.checkbox if widget.key.endswith(key))


def open_sample_data(app):
    app.radio[0].set_value("Use sample data").run()


def open_optional_interview(app):
    app.radio[0].set_value("AI interview (optional)").run()
    button(app, "Start AI interview").click().run()


@pytest.fixture
def app():
    result = AppTest.from_file(str(APP), default_timeout=20).run()
    open_sample_data(result)
    button(result, "Load selected demo").click().run()
    assert not result.exception
    return result


def test_complete_demo_displays_calculated_dashboard(app):
    button(app, "Calculate dashboard").click().run()
    assert not app.exception
    assert next(metric for metric in app.metric if metric.label == "Labor cost / case").value == "$137.50"
    assert next(metric for metric in app.metric if metric.label == "Projected labor cost / month").value == "$2,750.00"
    assert len(app.get("plotly_chart")) == 3


def test_incomplete_demo_labels_missing_totals_and_known_subtotal(app):
    app.sidebar.radio[0].set_value("Incomplete contractor demo").run()
    button(app, "Load selected demo").click().run()
    button(app, "Calculate dashboard").click().run()
    assert not app.exception
    assert next(metric for metric in app.metric if metric.label == "Labor cost / case").value == "Unavailable"
    assert any("Known subtotal only: $5.00" in item.value for item in app.caption)
    assert any("unavailable" in item.value.lower() for item in app.warning)


def test_edit_hides_old_results_clears_confirmation_and_recalculates(app):
    button(app, "Calculate dashboard").click().run()
    text(app, "steps.prepare-estimate.active_time").set_value("30").run()
    assert not app.metric
    assert checkbox(app, "confirmed.steps.prepare-estimate.active_time").value is False
    assert button(app, "Calculate dashboard").disabled is True
    checkbox(app, "confirmed.steps.prepare-estimate.active_time").check().run()
    button(app, "Save reviewed facts").click().run()
    button(app, "Calculate dashboard").click().run()
    assert not app.exception
    assert next(metric for metric in app.metric if metric.label == "Labor cost / case").value == "$126.25"


def test_invalid_edit_keeps_saved_workflow_and_hides_dashboard(app):
    button(app, "Calculate dashboard").click().run()
    text(app, "steps.receive-inquiry.active_time").set_value("-1").run()
    button(app, "Save reviewed facts").click().run()
    assert not app.exception
    assert app.error
    assert app.session_state["workflow"].steps[0].active_time.value == 10
    assert not app.metric


def test_bulk_confirmation_preserves_missing_inputs(app):
    app.sidebar.radio[0].set_value("Incomplete contractor demo").run()
    button(app, "Load selected demo").click().run()
    checkbox(app, "confirm_all").check().run()
    button(app, "Save reviewed facts").click().run()
    assert not app.exception
    assert app.session_state["workflow"].steps[1].active_time.confirmed is True
    assert app.session_state["workflow"].monthly_volume.value is None
    assert app.session_state["workflow"].monthly_volume.confirmed is False
    button(app, "Calculate dashboard").click().run()
    assert next(metric for metric in app.metric if metric.label == "Labor cost / case").value == "Unavailable"


def test_reset_discards_edits_and_old_analysis(app):
    text(app, "monthly_volume").set_value("0").run()
    button(app, "Reset current demo").click().run()
    assert not app.exception
    assert text(app, "monthly_volume").value == "20"
    assert not app.metric
    assert button(app, "Calculate dashboard").disabled is False


def test_edit_and_calculate_in_same_rerun_cannot_show_stale_results(app):
    button(app, "Calculate dashboard").click().run()
    text(app, "steps.prepare-estimate.active_time").set_value("30")
    button(app, "Calculate dashboard").click().run()
    assert not app.exception
    assert app.session_state["dirty"] is True
    assert app.session_state["analysis"] is None
    assert not app.metric
