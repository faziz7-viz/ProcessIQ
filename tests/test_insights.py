"""Presentation insights may only describe what reviewed facts establish."""

from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from processiq.analysis import analyze_workflow
from processiq.models import AnalysisMetric, BlockedFact, Workflow


def sample(incomplete=False):
    name = "contractor_estimate_incomplete.json" if incomplete else "contractor_estimate.json"
    return Workflow.model_validate_json((Path(__file__).resolve().parents[1] / "data" / name).read_text())


def metric(value, *, blocked=False):
    return AnalysisMetric(value=value, unit="minutes", formula="test", input_paths=(),
                          blocked_by=(BlockedFact(path="waiting_time", reason="missing"),) if blocked else ())


def test_waiting_share_uses_complete_elapsed_denominator_and_decimal_arithmetic():
    from processiq.insights import metric_share
    result = analyze_workflow(sample())
    assert metric_share(result.total_waiting_minutes, result.total_elapsed_minutes) == Decimal("97.0")
    with localcontext() as context:
        context.prec = 3
        assert metric_share(metric("1000000000000000000000001"), metric("3000000000000000000000003")) == Decimal("33.3")


@pytest.mark.parametrize("numerator,denominator", [(None,"10"),("2",None),("0","0"),("12","10")])
def test_share_is_unavailable_for_unknown_zero_or_invalid_total(numerator, denominator):
    from processiq.insights import metric_share
    assert metric_share(metric(numerator), metric(denominator)) is None


def test_even_known_subtotals_cannot_be_used_for_a_whole_process_percentage():
    from processiq.insights import hero_insight, metric_share
    result = analyze_workflow(sample(True))
    assert metric_share(result.total_waiting_minutes, result.total_elapsed_minutes) is None
    assert "%" not in hero_insight(result).title
    assert metric_share(metric("5", blocked=True), metric("10")) is None


@pytest.mark.parametrize("minutes,expected", [(None,"Unavailable"),("0","0m"),("0.5","0.5m"),("65","1h 5m"),("4825","3d 8h 25m")])
def test_human_duration_preserves_zero_fractional_minutes_and_days(minutes, expected):
    from processiq.insights import human_duration
    assert human_duration(None if minutes is None else Decimal(minutes)) == expected


def test_hero_is_derived_and_ranking_keeps_ties_and_partial_scope():
    from processiq.insights import hero_insight, ranking_insight
    complete = analyze_workflow(sample())
    assert hero_insight(complete).title == "97% of elapsed time is waiting."
    raw = sample().model_dump(mode="python")
    raw["steps"][1]["waiting_time"]["value"] = Decimal("2880")
    tied = analyze_workflow(Workflow.model_validate(raw))
    text = ranking_insight(tied, "waiting")
    assert "tied" in text.lower()
    assert tied.steps[1].name in text and tied.steps[5].name in text
    raw["steps"][2]["waiting_time"]["confirmed"] = False
    partial = analyze_workflow(Workflow.model_validate(raw))
    assert "confirmed steps" in ranking_insight(partial, "waiting")


def test_blockers_use_business_names_and_keep_missing_distinct_from_unconfirmed():
    from processiq.insights import blocker_labels
    result = analyze_workflow(sample(True))
    labels = blocker_labels(result.labor_cost_per_case.blocked_by, result)
    assert labels
    assert all("steps." not in label for label in labels)
    assert any("missing" in label.lower() for label in labels)
    assert any("confirm" in label.lower() for label in labels)


@pytest.mark.parametrize("waiting,expected", [("49.49", "49.5%"), ("99.49", "99.5%")])
def test_hero_percentage_rounds_only_once(waiting, expected):
    from processiq.insights import hero_insight
    result = analyze_workflow(sample()).model_copy(update={
        "total_waiting_minutes": metric(waiting),
        "total_elapsed_minutes": metric("100"),
    })
    assert hero_insight(result).title == f"{expected} of elapsed time is waiting."
