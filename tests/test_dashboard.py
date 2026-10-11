from importlib import import_module
from pathlib import Path

import pytest

from processiq.analysis import analyze_workflow
from processiq.models import Workflow


@pytest.fixture
def dashboard():
    return import_module("processiq.dashboard")


def analysis(incomplete=False):
    name = "contractor_estimate_incomplete.json" if incomplete else "contractor_estimate.json"
    path = Path(__file__).resolve().parents[1] / "data" / name
    return analyze_workflow(Workflow.model_validate_json(path.read_text()))


def test_chart_values_match_engine_results(dashboard):
    charts = dashboard.build_charts(analysis())
    assert list(charts["time"].data[0].x) == [10, 15, 60, 45, 5, 10]
    assert list(charts["time"].data[1].x) == [0, 120, 1440, 240, 0, 2880]
    assert list(charts["labor"].data[0].x) == [10, 15, 120, 45, 5, 10]
    assert list(charts["cost"].data[0].x) == [5, 11.25, 80, 33.75, 2.5, 5]


def test_chart_unknowns_stay_blank_and_zero_stays_zero(dashboard):
    charts = dashboard.build_charts(analysis(True))
    assert list(charts["time"].data[1].x) == [0, None, None, None, None, None]
    assert list(charts["cost"].data[0].x) == [5, None, None, None, None, None]


def test_display_formats_exact_totals_and_labels_unavailable(dashboard):
    complete = analysis()
    assert dashboard.format_metric(complete.labor_cost_per_case) == "$137.50"
    assert dashboard.format_metric(complete.total_active_minutes) == "145"
    incomplete = analysis(True)
    assert dashboard.format_metric(incomplete.labor_cost_per_case) == "Unavailable"
    table = dashboard.step_table(incomplete)
    assert table.iloc[0]["Waiting (min)"] == "0"
    assert table.iloc[1]["Labor cost (USD)"] == "Unavailable"


def test_duplicate_step_names_still_have_distinct_chart_bars(dashboard):
    path = Path(__file__).resolve().parents[1] / "data" / "contractor_estimate.json"
    workflow = Workflow.model_validate_json(path.read_text())
    raw = workflow.model_dump(mode="json")
    raw["steps"][1]["name"] = raw["steps"][0]["name"]
    result = analyze_workflow(Workflow.model_validate(raw))
    for chart in dashboard.build_charts(result).values():
        assert list(chart.data[0].y) == [step.step_id for step in result.steps]
        assert len(set(chart.data[0].y)) == 6
        assert list(chart.layout.yaxis.ticktext)[:2] == ["1. Receive inquiry", "2. Receive inquiry"]


def test_chart_sort_is_per_lens_and_keeps_original_step_numbers(dashboard):
    result = analysis()
    charts = dashboard.build_charts(result, sort_by="contribution")
    assert list(charts["time"].data[0].y)[0] == result.steps[5].step_id
    assert list(charts["cost"].data[0].y)[0] == result.steps[2].step_id
    assert list(charts["time"].layout.yaxis.ticktext)[0].startswith("6. ")


def test_chart_mode_filter_and_selection_keep_stable_ids(dashboard):
    result = analysis()
    selected = result.steps[1].step_id
    chart = dashboard.build_charts(result, time_mode="waiting", step_ids=[selected], selected_step_id=selected)["time"]
    assert len(chart.data) == 1
    assert chart.data[0].name == "Waiting"
    assert list(chart.data[0].x) == [120]
    assert chart.data[0].customdata[0][0] == selected
    assert dashboard.selected_step_from_event({"selection": {"points": [{"customdata": [selected, "120"]}]}}, result) == selected
    assert dashboard.selected_step_from_event({"selection": {"points": [{"customdata": ["unknown", "120"]}]}}, result) is None


def test_sorted_unknowns_are_last_without_becoming_zero(dashboard):
    result = analysis(True)
    chart = dashboard.build_charts(result, sort_by="contribution")["cost"]
    assert list(chart.data[0].x) == [5, None, None, None, None, None]


def test_hero_escapes_workflow_and_step_names(dashboard):
    result = analysis().model_copy(update={"workflow_name": '<img src=x onerror="alert(1)">'})
    markup = dashboard.hero_html(result)
    assert '<img src=x' not in markup
    assert '&lt;img src=x' in markup


def test_dashboard_step_selection_shows_role_evidence_and_is_stable_with_duplicate_names():
    from streamlit.testing.v1 import AppTest
    script = '''
from pathlib import Path
from processiq.models import Workflow
from processiq.analysis import analyze_workflow
from processiq.dashboard import render_dashboard
raw = Workflow.model_validate_json(Path("data/contractor_estimate.json").read_text()).model_dump(mode="json")
raw["steps"][1]["name"] = raw["steps"][0]["name"]
workflow = Workflow.model_validate(raw)
render_dashboard(analyze_workflow(workflow), workflow)
'''
    app = AppTest.from_string(script).run()
    assert not app.exception
    picker = next(item for item in app.selectbox if item.label == "Inspect a step")
    picker.set_value("collect-details").run()
    assert not app.exception
    assert app.session_state["pi-selected-step"] == "collect-details"
    assert len(app.get("plotly_chart")) == 3
    assert any("2. Receive inquiry" in item.value for item in app.markdown)
    assert any("Quoted source" in item.value for item in app.markdown)


def test_chart_callback_updates_the_same_canonical_step_as_the_picker(dashboard, monkeypatch):
    result = analysis()
    selected = result.steps[2].step_id
    state = {"pi-selected-step": result.steps[0].step_id,
             "chart-time": {"selection": {"points": [{"customdata": [selected, "60"]}]}}}
    monkeypatch.setattr(dashboard.st, "session_state", state)
    dashboard._select_chart_step("chart-time", result)
    assert state["pi-selected-step"] == selected
    state["pi-step-picker"] = result.steps[1].step_id
    dashboard._select_picker_step()
    assert state["pi-selected-step"] == result.steps[1].step_id


def test_large_workflow_chart_filter_keeps_search_and_selection_independent():
    from streamlit.testing.v1 import AppTest
    script = '''
from pathlib import Path
from processiq.models import Workflow
from processiq.analysis import analyze_workflow
from processiq.dashboard import render_dashboard
raw = Workflow.model_validate_json(Path("data/contractor_estimate.json").read_text()).model_dump(mode="json")
source = raw["steps"][0]
raw["steps"] = [dict(source, id=f"step-{n}", order=n, name=f"Task {n}") for n in range(1, 201)]
workflow = Workflow.model_validate(raw)
render_dashboard(analyze_workflow(workflow), workflow)
'''
    app = AppTest.from_string(script, default_timeout=10).run()
    assert not app.exception
    assert len(app.get("plotly_chart")) == 3
    picker = next(item for item in app.selectbox if item.label == "Inspect a step")
    picker.set_value("step-200").run()
    app.text_input[0].set_value("Task 199").run()
    assert not app.exception
    assert app.session_state["pi-selected-step"] == "step-200"
    assert any("Showing 1 of 200 steps" in item.value for item in app.caption)
    app.text_input[0].set_value("No matching step").run()
    assert not app.exception
    assert any("No steps match" in item.value for item in app.info)
