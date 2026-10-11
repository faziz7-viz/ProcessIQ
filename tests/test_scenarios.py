"""Hand-derived scenario arithmetic and isolated Streamlit controls."""

from decimal import Decimal, Inexact, ROUND_DOWN, localcontext
from pathlib import Path

import pytest

from processiq.analysis import analyze_workflow
from processiq.models import Workflow

DATA = Path(__file__).resolve().parents[1] / "data"


def demo(name="contractor_estimate.json"):
    return Workflow.model_validate_json((DATA / name).read_text())


def small_workflow(rows, volume=3):
    messages, steps = [], []
    for order, row in enumerate(rows, start=1):
        fields = {}
        quotes = []
        step_id = f"step-{order}"
        for field, value in zip(
            ("active_time", "waiting_time", "people", "hourly_labor_cost"), row, strict=True,
        ):
            quote = f"{field}: {value}."
            quotes.append(quote)
            fields[field] = {
                "value": value, "confirmed": value is not None,
                "evidence": [{"message_id": step_id, "quote": quote}],
            }
        messages.append({"id": step_id, "text": " ".join(quotes)})
        steps.append({"id": step_id, "order": order, "name": "Repeated name", **fields})
    volume_quote = f"Monthly volume: {volume}."
    messages.append({"id": "volume", "text": volume_quote})
    return Workflow.model_validate({
        "name": "Scenario fixture", "start_point": "Start", "end_point": "End",
        "data_kind": "synthetic", "source_messages": messages, "steps": steps,
        "monthly_volume": {
            "value": volume, "confirmed": volume is not None,
            "evidence": [{"message_id": "volume", "quote": volume_quote}],
        },
    })


def scenario(*args, **kwargs):
    from processiq.scenarios import calculate_scenario
    return calculate_scenario(*args, **kwargs)


def test_zero_reduction_preserves_baseline_values_and_workflow():
    workflow = demo()
    before = workflow.model_dump_json()
    result = scenario(workflow, "site-visit")
    assert result.baseline == analyze_workflow(workflow)
    assert result.hypothetical.total_elapsed_minutes.value == Decimal("4825")
    assert result.hypothetical.labor_cost_per_case.value == Decimal("137.50")
    assert result.delta.total_elapsed_minutes == Decimal("0")
    assert result.delta.labor_cost_per_case == Decimal("0.00")
    assert workflow.model_dump_json() == before


def test_thirty_percent_active_reduction_recalculates_selected_step_only():
    workflow = demo()
    before = workflow.model_dump_json()
    result = scenario(workflow, "prepare-estimate", active_reduction_pct=30)
    assert result.baseline.labor_cost_per_case.value == Decimal("137.50")
    assert result.hypothetical.steps[3].active_minutes.value == Decimal("31.5")
    assert result.hypothetical.steps[3].labor_cost.value == Decimal("23.63")
    assert result.hypothetical.total_active_minutes.value == Decimal("131.5")
    assert result.hypothetical.total_elapsed_minutes.value == Decimal("4811.5")
    assert result.hypothetical.total_labor_minutes.value == Decimal("191.5")
    assert result.hypothetical.labor_cost_per_case.value == Decimal("127.38")
    assert result.hypothetical.monthly_labor_cost.value == Decimal("2547.60")
    assert result.delta.labor_cost_per_case == Decimal("10.12")
    assert result.delta.monthly_labor_cost == Decimal("202.40")
    assert result.hypothetical.steps[2] == result.baseline.steps[2]
    assert workflow.model_dump_json() == before


def test_full_reduction_changes_only_selected_step_even_with_duplicate_names():
    workflow = small_workflow([("60", "120", 2, "30"), ("10", "20", 1, "30")])
    result = scenario(workflow, "step-1", active_reduction_pct=100, waiting_reduction_pct=100)
    assert result.hypothetical.steps[0].active_minutes.value == Decimal("0")
    assert result.hypothetical.steps[0].waiting_minutes.value == Decimal("0")
    assert result.hypothetical.steps[0].labor_cost.value == Decimal("0.00")
    assert result.hypothetical.steps[1].active_minutes.value == Decimal("10")
    assert result.hypothetical.total_elapsed_minutes.value == Decimal("30")
    assert result.hypothetical.labor_cost_per_case.value == Decimal("5.00")


def test_wait_reduction_never_claims_labor_cost_reduction():
    result = scenario(demo(), "follow-up", waiting_reduction_pct=50)
    assert result.hypothetical.total_waiting_minutes.value == Decimal("3240")
    assert result.delta.total_elapsed_minutes == Decimal("1440")
    assert result.delta.total_labor_minutes == Decimal("0")
    assert result.delta.labor_cost_per_case == Decimal("0.00")
    assert result.delta.monthly_labor_cost == Decimal("0.00")


def test_cost_is_recomputed_before_per_step_half_up_rounding():
    # The selected raw cost goes from .01 to .005, which still rounds to .01.
    workflow = small_workflow([("2", "0", 1, "0.30"), ("1", "0", 1, "0.30")])
    result = scenario(workflow, "step-1", active_reduction_pct=50)
    assert result.hypothetical.steps[0].labor_cost.value == Decimal("0.01")
    assert result.hypothetical.labor_cost_per_case.value == Decimal("0.02")
    assert result.hypothetical.monthly_labor_cost.value == Decimal("0.06")
    assert result.delta.labor_cost_per_case == Decimal("0.00")


def test_fractional_percentage_keeps_exact_minutes():
    result = scenario(small_workflow([("10", "0", 1, "30")]), "step-1", active_reduction_pct="12.5")
    assert result.hypothetical.total_active_minutes.value == Decimal("8.75")
    assert result.hypothetical.labor_cost_per_case.value == Decimal("4.38")


def test_missing_inputs_stay_unavailable_at_full_reduction():
    result = scenario(demo("contractor_estimate_incomplete.json"), "prepare-estimate", active_reduction_pct=100, waiting_reduction_pct=100)
    assert result.hypothetical.total_active_minutes.value is None
    assert result.hypothetical.total_active_minutes.known_subtotal == Decimal("10")
    assert result.hypothetical.labor_cost_per_case.value is None
    assert result.hypothetical.labor_cost_per_case.known_subtotal == Decimal("5.00")
    assert result.hypothetical.monthly_labor_cost.value is None
    assert result.hypothetical.monthly_labor_cost.known_subtotal is None
    assert result.delta.total_active_minutes is None
    assert result.delta.labor_cost_per_case is None
    assert result.hypothetical.total_active_minutes.blocked_by == result.baseline.total_active_minutes.blocked_by


def test_partial_known_values_can_change_without_becoming_complete_totals():
    workflow = small_workflow([("10", "0", 1, "30"), (None, None, 1, "30")])
    result = scenario(workflow, "step-1", active_reduction_pct=100)
    assert result.hypothetical.total_active_minutes.value is None
    assert result.hypothetical.total_active_minutes.known_subtotal == Decimal("0")
    assert result.hypothetical.labor_cost_per_case.value is None
    assert result.hypothetical.labor_cost_per_case.known_subtotal == Decimal("0.00")
    assert result.hypothetical.monthly_labor_cost.value is None
    assert result.hypothetical.monthly_labor_cost.known_subtotal is None
    assert result.delta.monthly_labor_cost is None


def test_known_zero_stays_available():
    result = scenario(small_workflow([("0", "0", 1, "0")], volume=0), "step-1", active_reduction_pct=100, waiting_reduction_pct=100)
    assert result.hypothetical.total_elapsed_minutes.value == Decimal("0")
    assert result.hypothetical.monthly_labor_cost.value == Decimal("0.00")
    assert result.delta.monthly_labor_cost == Decimal("0.00")


def test_zero_volume_cannot_make_incomplete_cost_available():
    result = scenario(small_workflow([("10", "0", 1, None)], volume=0), "step-1", active_reduction_pct=100)
    assert result.hypothetical.labor_cost_per_case.value is None
    assert result.hypothetical.monthly_labor_cost.value is None


def test_unconfirmed_facts_remain_unconfirmed_without_new_evidence():
    workflow = demo("contractor_estimate_incomplete.json")
    before = workflow.model_dump_json()
    result = scenario(workflow, "collect-details", active_reduction_pct=100)
    selected = next(step for step in result.hypothetical.steps if step.step_id == "collect-details")
    assert selected.active_minutes.value is None
    assert any(g.reason == "unconfirmed" for g in selected.active_minutes.blocked_by)
    original_refs = {ref for step in result.baseline.steps for metric in (step.active_minutes, step.waiting_minutes, step.labor_cost) for ref in metric.evidence}
    scenario_refs = {ref for step in result.hypothetical.steps for metric in (step.active_minutes, step.waiting_minutes, step.labor_cost) for ref in metric.evidence}
    assert scenario_refs <= original_refs
    assert workflow.model_dump_json() == before


@pytest.mark.parametrize("bad", [True, False, None, "bad", "", "NaN", "Infinity", Decimal("-Infinity"), -1, 101, 0.5])
@pytest.mark.parametrize("field", ["active_reduction_pct", "waiting_reduction_pct"])
def test_rejects_invalid_percentages(bad, field):
    with pytest.raises(ValueError, match="percentage"):
        scenario(demo(), "site-visit", **{field: bad})


def test_rejects_unknown_step_id():
    with pytest.raises(ValueError, match="step"):
        scenario(demo(), "not-a-step", active_reduction_pct=30)


def test_scenario_ignores_callers_decimal_context():
    with localcontext() as context:
        context.prec = 3
        context.rounding = ROUND_DOWN
        context.traps[Inexact] = True
        result = scenario(demo(), "prepare-estimate", active_reduction_pct=30)
    assert result.hypothetical.labor_cost_per_case.value == Decimal("127.38")
    assert result.delta.monthly_labor_cost == Decimal("202.40")


def test_small_nonzero_time_reduction_is_not_displayed_as_zero():
    from processiq.scenario_ui import _delta_label
    assert _delta_label(Decimal("0.001")) == "-0.001 min vs baseline"


def test_controls_update_comparison_and_reset_without_changing_facts():
    from streamlit.testing.v1 import AppTest

    def app_script():
        import streamlit as st
        from pathlib import Path
        from processiq.analysis import analyze_workflow
        from processiq.models import Workflow
        from processiq.scenario_ui import render_scenarios
        if "workflow" not in st.session_state:
            st.session_state.workflow = Workflow.model_validate_json(Path("data/contractor_estimate.json").read_text())
        workflow = st.session_state.workflow
        render_scenarios(workflow, analyze_workflow(workflow))

    app = AppTest.from_function(app_script).run()
    assert not app.exception
    before = app.session_state["workflow"].model_dump_json()
    app.selectbox[0].select("prepare-estimate").run()
    app.slider[0].set_value(30).run()
    assert not app.exception
    assert any(metric.label == "Hypothetical labor / case" and metric.value == "$127.38" for metric in app.metric)
    assert app.session_state["workflow"].model_dump_json() == before
    next(button for button in app.button if button.label == "Reset scenario").click().run()
    assert app.slider[0].value == 0
    assert app.slider[1].value == 0
    assert any(metric.label == "Hypothetical labor / case" and metric.value == "$137.50" for metric in app.metric)
    app.slider[0].set_value(30).run()
    app.session_state["workflow"] = demo("contractor_estimate_incomplete.json")
    app.run()
    assert not app.exception
    assert app.slider[0].value == 0
    assert app.slider[1].value == 0
