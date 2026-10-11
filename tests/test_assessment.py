from decimal import Decimal
from importlib import import_module
from pathlib import Path

import pytest
from pydantic import ValidationError

from processiq.models import Workflow

DATA = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture
def review():
    return import_module("processiq.assessment")


def demo(incomplete=False):
    name = "contractor_estimate_incomplete.json" if incomplete else "contractor_estimate.json"
    return Workflow.model_validate_json((DATA / name).read_text())


def test_correction_records_owner_evidence_and_requires_new_confirmation(review):
    workflow = demo()
    updated = review.apply_review(workflow, {"steps.prepare-estimate.active_time": "30"})
    fact = updated.steps[3].active_time
    assert fact.value == Decimal("30")
    assert fact.confirmed is False
    assert fact.evidence[0].message_id != workflow.steps[3].active_time.evidence[0].message_id
    assert fact.evidence[0].quote in updated.source_messages[-1].text
    assert updated.source_messages[-1].speaker == "owner"
    assert workflow.steps[3].active_time.value == Decimal("45")


def test_unchanged_fact_preserves_evidence_and_confirmation(review):
    workflow = demo()
    updated = review.apply_review(workflow, review.review_values(workflow))
    assert updated == workflow
    assert updated.steps[0].active_time.evidence == workflow.steps[0].active_time.evidence


def test_blank_is_unknown_and_zero_remains_known(review):
    updated = review.apply_review(demo(), {
        "steps.prepare-estimate.active_time": "", "steps.follow-up.waiting_time": "0",
    }, confirm_all=True)
    assert updated.steps[3].active_time.value is None
    assert updated.steps[3].active_time.confirmed is False
    assert updated.steps[5].waiting_time.value == Decimal("0")
    assert updated.steps[5].waiting_time.confirmed is True


@pytest.mark.parametrize("value", ["-1", "NaN", "Infinity", "abc"])
def test_invalid_decimal_correction_is_rejected(review, value):
    with pytest.raises((ValidationError, ValueError)):
        review.apply_review(demo(), {"steps.receive-inquiry.active_time": value})


@pytest.mark.parametrize("value", ["1.5", "1.0", "true", "0", "-1"])
def test_staffing_count_is_a_positive_integer(review, value):
    with pytest.raises((ValidationError, ValueError)):
        review.apply_review(demo(), {"steps.site-visit.people": value})


def test_individual_and_bulk_confirmation_never_fill_gaps(review):
    workflow = demo(True)
    individual = review.apply_review(workflow, {}, {"steps.collect-details.active_time": True})
    assert individual.steps[1].active_time.confirmed is True
    assert individual.steps[1].hourly_labor_cost.confirmed is False
    bulk = review.apply_review(workflow, {}, confirm_all=True)
    assert bulk.steps[1].hourly_labor_cost.confirmed is True
    assert bulk.monthly_volume.value is None
    assert bulk.monthly_volume.confirmed is False


def test_review_can_fill_missing_volume_and_role(review):
    updated = review.apply_review(demo(True), {
        "monthly_volume": "0", "steps.follow-up.responsible_role": "Office administrator",
    }, {"monthly_volume": True})
    assert updated.monthly_volume.value == 0
    assert updated.monthly_volume.confirmed is True
    assert updated.steps[5].responsible_role == "Office administrator"


def test_new_evidence_ids_do_not_collide_after_multiple_saves(review):
    first = review.apply_review(demo(), {"monthly_volume": "15"})
    second = review.apply_review(first, {"monthly_volume": "16"})
    assert len({message.id for message in second.source_messages}) == len(second.source_messages)
    assert second.monthly_volume.evidence != first.monthly_volume.evidence


def test_unknown_review_field_is_rejected(review):
    with pytest.raises(ValueError):
        review.apply_review(demo(), {"invented_revenue": "500"})
