"""Hand-derived expectations for deterministic analysis and incomplete inputs."""

from decimal import Decimal, Inexact, ROUND_DOWN, localcontext
from importlib import import_module
from pathlib import Path

import pytest
from pydantic import ValidationError

from processiq.models import Workflow

DATA = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture
def analyze():
    return import_module("processiq.analysis").analyze_workflow


def demo(name="contractor_estimate.json"):
    return Workflow.model_validate_json((DATA / name).read_text())


def small_workflow(rows, volume=2, volume_confirmed=True):
    """Build honest owner evidence for controlled inputs, not expected results."""
    messages, steps = [], []
    for order, values in enumerate(rows, start=1):
        step_id = f"step-{order}"
        fields = {}
        sentences = []
        for field, value, unit in zip(
            ("active_time", "waiting_time", "people", "hourly_labor_cost"),
            values, ("minutes", "minutes", "people", "currency/hour"), strict=True,
        ):
            sentence = f"{field}: {value} {unit}."
            sentences.append(sentence)
            fields[field] = {
                "value": value, "unit": unit, "confirmed": value is not None,
                "evidence": [{"message_id": step_id, "quote": sentence}],
            }
        messages.append({"id": step_id, "text": " ".join(sentences)})
        steps.append({"id": step_id, "order": order, "name": f"Step {order}", **fields})
    volume_text = f"Monthly volume: {volume} cases."
    messages.append({"id": "volume", "text": volume_text})
    return Workflow.model_validate({
        "name": "Synthetic test process", "start_point": "Start", "end_point": "End",
        "data_kind": "synthetic", "source_messages": messages, "steps": steps,
        "monthly_volume": {
            "value": volume, "confirmed": volume is not None and volume_confirmed,
            "evidence": [{"message_id": "volume", "quote": volume_text}],
        },
    })


def test_complete_demo_matches_hand_calculated_time_and_cost(analyze):
    result = analyze(demo())
    assert result.total_active_minutes.value == Decimal("145")
    assert result.total_waiting_minutes.value == Decimal("4680")
    assert result.total_elapsed_minutes.value == Decimal("4825")
    assert result.total_labor_minutes.value == Decimal("205")
    assert result.labor_cost_per_case.value == Decimal("137.50")
    assert result.monthly_labor_cost.value == Decimal("2750.00")
    assert [step.labor_cost.value for step in result.steps] == [
        Decimal("5.00"), Decimal("11.25"), Decimal("80.00"),
        Decimal("33.75"), Decimal("2.50"), Decimal("5.00"),
    ]
    assert result.steps[2].elapsed_minutes.value == Decimal("1500")
    assert result.steps[2].labor_minutes.value == Decimal("120")
    assert result.labor_cost_per_case.unit == "USD/case"
    assert result.monthly_labor_cost.unit == "USD/month"
    assert result.labor_cost_per_case.blocked_by == ()
    assert result.labor_cost_per_case.known_subtotal is None


def test_complete_demo_ranks_wait_and_labor_separately(analyze):
    result = analyze(demo())
    assert result.waiting_ranking.complete is True
    assert [(item.step_id, item.value, item.rank) for item in result.waiting_ranking.entries] == [
        ("follow-up", Decimal("2880"), 1), ("site-visit", Decimal("1440"), 2),
        ("prepare-estimate", Decimal("240"), 3), ("collect-details", Decimal("120"), 4),
    ]
    assert result.labor_ranking.entries[0].step_id == "site-visit"
    assert result.labor_ranking.entries[0].value == Decimal("120")
    assert result.labor_ranking.complete is True
    assert "potential" in result.waiting_ranking.description.lower()


def test_incomplete_demo_excludes_unconfirmed_numbers_and_exposes_gaps(analyze):
    result = analyze(demo("contractor_estimate_incomplete.json"))
    assert result.total_active_minutes.value is None
    assert result.total_active_minutes.known_subtotal == Decimal("10")
    assert result.total_waiting_minutes.value is None
    assert result.total_waiting_minutes.known_subtotal == Decimal("0")
    assert result.labor_cost_per_case.value is None
    assert result.labor_cost_per_case.known_subtotal == Decimal("5.00")
    assert result.monthly_labor_cost.value is None
    assert result.monthly_labor_cost.known_subtotal is None
    gaps = {(gap.path, gap.reason) for gap in result.labor_cost_per_case.blocked_by}
    assert ("steps.collect-details.active_time", "unconfirmed") in gaps
    assert ("steps.prepare-estimate.active_time", "missing") in gaps
    assert ("steps.prepare-estimate.hourly_labor_cost", "missing") in gaps
    assert result.waiting_ranking.complete is False
    assert result.waiting_ranking.entries == ()
    assert result.labor_ranking.complete is False
    assert result.labor_ranking.entries[0].step_id == "receive-inquiry"


def test_waiting_time_does_not_increase_labor_cost(analyze):
    result = analyze(small_workflow([("30", "600", 2, "20")]))
    assert result.total_elapsed_minutes.value == Decimal("630")
    assert result.total_labor_minutes.value == Decimal("60")
    assert result.labor_cost_per_case.value == Decimal("20.00")


@pytest.mark.parametrize("field", ["active_time", "people", "hourly_labor_cost"])
def test_unconfirmed_dependency_blocks_step_cost(analyze, field):
    workflow = small_workflow([("30", "0", 1, "20")])
    raw = workflow.model_dump(mode="json")
    raw["steps"][0][field]["confirmed"] = False
    result = analyze(Workflow.model_validate(raw))
    assert result.steps[0].labor_cost.value is None
    assert [(g.path, g.reason) for g in result.steps[0].labor_cost.blocked_by] == [
        (f"steps.step-1.{field}", "unconfirmed")
    ]


def test_missing_rate_blocks_cost_but_not_time_or_labor_ranking(analyze):
    result = analyze(small_workflow([("30", "20", 2, None)]))
    assert result.total_elapsed_minutes.value == Decimal("50")
    assert result.total_labor_minutes.value == Decimal("60")
    assert result.labor_cost_per_case.value is None
    assert result.labor_cost_per_case.known_subtotal is None
    assert result.labor_ranking.complete is True


def test_missing_wait_blocks_elapsed_but_not_labor_cost(analyze):
    result = analyze(small_workflow([("30", None, 1, "20")]))
    assert result.total_elapsed_minutes.value is None
    assert result.labor_cost_per_case.value == Decimal("10.00")
    assert result.waiting_ranking.complete is False


@pytest.mark.parametrize("confirmed,reason", [(True, "missing"), (False, "unconfirmed")])
def test_missing_or_unconfirmed_volume_blocks_only_monthly_cost(analyze, confirmed, reason):
    volume = None if confirmed else 2
    result = analyze(small_workflow([("60", "0", 1, "20")], volume, confirmed))
    assert result.labor_cost_per_case.value == Decimal("20.00")
    assert result.monthly_labor_cost.value is None
    assert ("monthly_volume", reason) in [(g.path, g.reason) for g in result.monthly_labor_cost.blocked_by]


def test_zero_monthly_volume_produces_zero_cost(analyze):
    result = analyze(small_workflow([("60", "0", 1, "20")], volume=0))
    assert result.monthly_labor_cost.value == Decimal("0.00")
    assert result.labor_cost_per_case.value == Decimal("20.00")


def test_zero_volume_does_not_hide_missing_per_case_cost(analyze):
    result = analyze(small_workflow([("60", "0", 1, None)], volume=0))
    assert result.monthly_labor_cost.value is None


def test_zero_times_and_rate_are_available_and_do_not_create_bottlenecks(analyze):
    result = analyze(small_workflow([("0", "0", 1, "0")]))
    assert result.total_elapsed_minutes.value == Decimal("0")
    assert result.total_labor_minutes.value == Decimal("0")
    assert result.labor_cost_per_case.value == Decimal("0.00")
    assert result.waiting_ranking.entries == ()
    assert result.labor_ranking.entries == ()
    assert result.waiting_ranking.complete is True


def test_all_missing_facts_produce_no_invented_subtotals(analyze):
    result = analyze(small_workflow([(None, None, None, None)], volume=None))
    assert result.total_active_minutes.value is None
    assert result.total_active_minutes.known_subtotal is None
    assert result.labor_cost_per_case.known_subtotal is None
    assert result.waiting_ranking.entries == ()
    assert result.waiting_ranking.complete is False


def test_round_half_up_per_step_then_sum_and_scale(analyze):
    # One minute * 0.30 per hour / 60 = 0.005; each of two steps rounds to 0.01.
    result = analyze(small_workflow([("1", "0", 1, "0.30"), ("1", "0", 1, "0.30")], volume=3))
    assert [step.labor_cost.value for step in result.steps] == [Decimal("0.01"), Decimal("0.01")]
    assert result.labor_cost_per_case.value == Decimal("0.02")
    assert result.monthly_labor_cost.value == Decimal("0.06")


def test_repeating_division_rounds_to_cents(analyze):
    result = analyze(small_workflow([("1", "0", 1, "1")], volume=3))
    assert result.labor_cost_per_case.value == Decimal("0.02")
    assert result.monthly_labor_cost.value == Decimal("0.06")


def test_results_do_not_depend_on_callers_decimal_context(analyze):
    with localcontext() as context:
        context.prec = 3
        context.rounding = ROUND_DOWN
        context.traps[Inexact] = True
        result = analyze(demo())
        assert context.prec == 3
        assert context.rounding == ROUND_DOWN
        assert context.traps[Inexact] is True
    assert result.labor_cost_per_case.value == Decimal("137.50")
    assert result.monthly_labor_cost.value == Decimal("2750.00")


def test_ties_keep_all_steps_in_process_order_with_dense_ranks(analyze):
    result = analyze(small_workflow([
        ("20", "10", 1, "30"), ("20", "10", 1, "30"), ("10", "5", 1, "30"),
    ]))
    for ranking in (result.waiting_ranking, result.labor_ranking):
        assert [item.step_id for item in ranking.entries] == ["step-1", "step-2", "step-3"]
        assert [item.rank for item in ranking.entries] == [1, 1, 2]


def test_partial_ranking_does_not_claim_a_complete_comparison(analyze):
    result = analyze(small_workflow([("10", "20", 1, "30"), (None, None, 1, "30")]))
    assert result.waiting_ranking.entries[0].step_id == "step-1"
    assert result.waiting_ranking.complete is False
    assert result.labor_ranking.complete is False
    assert [(g.path, g.reason) for g in result.waiting_ranking.blocked_by] == [
        ("steps.step-2.waiting_time", "missing")
    ]


def test_metrics_retain_formula_paths_and_owner_evidence(analyze):
    workflow = small_workflow([("30", "0", 2, "20")])
    cost = analyze(workflow).steps[0].labor_cost
    assert cost.input_paths == (
        "steps.step-1.active_time", "steps.step-1.people", "steps.step-1.hourly_labor_cost",
    )
    assert cost.formula == "active_minutes * people * hourly_labor_cost / 60; round half up to cents"
    assert len(cost.evidence) == 3
    for evidence in cost.evidence:
        assert evidence.quote in workflow.source_messages[0].text


def test_analysis_json_preserves_exact_money_and_unavailable_values(analyze):
    from processiq.models import WorkflowAnalysis
    result = analyze(small_workflow([("30", None, 1, "19.95")]))
    raw = result.model_dump(mode="json")
    assert raw["labor_cost_per_case"]["value"] == "9.98"
    assert raw["total_elapsed_minutes"]["value"] is None
    assert WorkflowAnalysis.model_validate_json(result.model_dump_json()) == result


def test_recalculation_uses_correction_without_mutating_original(analyze):
    workflow = small_workflow([("30", "0", 1, "20")])
    before = workflow.model_dump_json()
    first = analyze(workflow)
    raw = workflow.model_dump(mode="json")
    raw["source_messages"].append({"id": "correction", "text": "Active time is 15 minutes."})
    raw["steps"][0]["active_time"] = {
        "value": "15", "confirmed": True,
        "evidence": [{"message_id": "correction", "quote": "Active time is 15 minutes."}],
    }
    second = analyze(Workflow.model_validate(raw))
    assert first.labor_cost_per_case.value == Decimal("10.00")
    assert second.labor_cost_per_case.value == Decimal("5.00")
    assert workflow.model_dump_json() == before


def test_analysis_rejects_invalid_edits_that_bypassed_validation(analyze):
    workflow = small_workflow([("30", "0", 1, "20")])
    bad_fact = workflow.steps[0].active_time.model_copy(update={"value": Decimal("-1")})
    bad_step = workflow.steps[0].model_copy(update={"active_time": bad_fact})
    bad_workflow = workflow.model_copy(update={"steps": (bad_step,)})
    with pytest.raises(ValidationError):
        analyze(bad_workflow)


def test_fractional_minutes_preserve_time_and_round_money_only(analyze):
    result = analyze(small_workflow([("1.5", "0.25", 3, "19.95")]))
    assert result.total_active_minutes.value == Decimal("1.5")
    assert result.total_elapsed_minutes.value == Decimal("1.75")
    assert result.total_labor_minutes.value == Decimal("4.5")
    assert result.labor_cost_per_case.value == Decimal("1.50")


def test_large_exact_amounts_are_not_truncated_by_default_precision(analyze):
    result = analyze(small_workflow([("60", "0", 1, "123456789012345678901234567890.12")], volume=2))
    assert result.labor_cost_per_case.value == Decimal("123456789012345678901234567890.12")
    assert result.monthly_labor_cost.value == Decimal("246913578024691357802469135780.24")


def test_evidence_and_gap_references_are_deduplicated_in_monthly_results(analyze):
    result = analyze(small_workflow([(None, "10", 1, "20")], volume=None))
    assert [(gap.path, gap.reason) for gap in result.monthly_labor_cost.blocked_by] == [
        ("steps.step-1.active_time", "missing"), ("monthly_volume", "missing"),
    ]
    complete = analyze(demo())
    references = [(e.message_id, e.quote) for e in complete.monthly_labor_cost.evidence]
    assert len(references) == len(set(references))
