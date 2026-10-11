"""Navigation preserves facts and only presents current assessment results."""
from streamlit.testing.v1 import AppTest

from test_app import APP, button, text, checkbox, open_sample_data


def sample():
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    open_sample_data(app)
    button(app, "Load selected demo").click().run()
    return app


def test_calculation_routes_to_overview_and_review_preserves_pending_values():
    app = sample()
    assert app.session_state["workspace"] == "Workflow"
    button(app, "Calculate dashboard").click().run()
    assert app.session_state["workspace"] == "Overview"
    app.button(key="nav-Workflow").click().run()
    text(app, "monthly_volume").set_value("17").run()
    app.button(key="nav-Overview").click().run()
    app.button(key="nav-Workflow").click().run()
    assert text(app, "monthly_volume").value == "17"
    assert not checkbox(app, "confirmed.monthly_volume").value
    assert app.session_state["analysis"] is None
    assert button(app, "Calculate dashboard").disabled
    assert not app.exception


def test_explicit_demo_link_opens_calculated_sample_without_provider(monkeypatch):
    import processiq.llm as llm
    def unexpected(*args, **kwargs):
        raise AssertionError("Preview must not call AI")
    monkeypatch.setattr(llm, "OpenAIInterviewer", unexpected)
    monkeypatch.setattr(llm, "OpenAIPlanner", unexpected)
    app = AppTest.from_file(str(APP), default_timeout=20)
    app.query_params["demo"] = "complete"
    app.run()
    assert not app.exception
    assert not app.session_state["show_start"]
    assert app.session_state["workspace"] == "Overview"
    assert app.session_state["analysis"].labor_cost_per_case.value == 137.50
    text(app, "monthly_volume").set_value("17").run()
    assert text(app, "monthly_volume").value == "17"
    assert app.session_state["analysis"] is None


def test_incomplete_preview_does_not_invent_totals():
    app = AppTest.from_file(str(APP), default_timeout=20)
    app.query_params["demo"] = "incomplete"
    app.run()
    assert not app.exception
    assert app.session_state["analysis"].labor_cost_per_case.value is None
    assert app.session_state["analysis"].labor_cost_per_case.known_subtotal == 5
    assert app.session_state["workspace"] == "Overview"


def test_workspace_navigation_preserves_valid_report():
    app = sample()
    button(app, "Calculate dashboard").click().run()
    button(app, "Create offline plan").click().run()
    plan = app.session_state["plan"]
    for view in ["What if", "Workflow", "Overview", "Improvements"]:
        app.button(key=f"nav-{view}").click().run()
        assert app.session_state["workspace"] == view
        assert app.session_state["plan"] == plan
    assert not app.exception
