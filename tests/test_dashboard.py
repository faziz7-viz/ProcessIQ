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
