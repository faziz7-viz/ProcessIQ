"""Exercise real JSON fixtures through the production data contract."""

from decimal import Decimal
from pathlib import Path

import pytest

from processiq.models import Workflow

DATA = Path(__file__).resolve().parents[1] / "data"


def load(name):
    return Workflow.model_validate_json((DATA / name).read_text())


def test_complete_fixture_has_reviewed_inputs_for_every_step():
    workflow = load("contractor_estimate.json")
    assert workflow.data_kind == "synthetic"
    assert workflow.monthly_volume.value == 20
    assert workflow.monthly_volume.confirmed is True
    assert len(workflow.steps) == 6
    for step in workflow.steps:
        assert step.responsible_role is not None
        for fact in (step.active_time, step.waiting_time, step.people, step.hourly_labor_cost):
            assert fact.value is not None
            assert fact.confirmed is True
            assert fact.evidence
    # Independent known inputs protect against a structurally valid but wrong demo.
    assert [step.active_time.value for step in workflow.steps] == [
        Decimal("10"), Decimal("15"), Decimal("60"), Decimal("45"), Decimal("5"), Decimal("10")
    ]
    assert [step.waiting_time.value for step in workflow.steps] == [
        Decimal("0"), Decimal("120"), Decimal("1440"), Decimal("240"), Decimal("0"), Decimal("2880")
    ]
    assert workflow.steps[2].people.value == 2
    assert workflow.steps[2].hourly_labor_cost.value == Decimal("40.00")


def test_incomplete_fixture_preserves_gaps_and_pending_review():
    workflow = load("contractor_estimate_incomplete.json")
    assert workflow.data_kind == "synthetic"
    assert workflow.monthly_volume.value is None
    assert workflow.monthly_volume.confirmed is False
    assert len(workflow.steps) == 6
    assert workflow.steps[0].waiting_time.value == Decimal("0")
    assert workflow.steps[0].waiting_time.confirmed is True
    assert workflow.steps[2].waiting_time.value is None
    assert workflow.steps[3].active_time.value is None
    assert workflow.steps[3].hourly_labor_cost.value is None
    assert workflow.steps[5].responsible_role is None
    assert workflow.steps[5].people.value is None
    assert workflow.steps[1].active_time.value == Decimal("15")
    assert workflow.steps[1].active_time.confirmed is False


@pytest.mark.parametrize("name", ["contractor_estimate.json", "contractor_estimate_incomplete.json"])
def test_fixture_numeric_evidence_is_traceable_and_survives_serialization(name):
    workflow = load(name)
    sources = {message.id: message.text for message in workflow.source_messages}
    facts = [workflow.monthly_volume]
    for step in workflow.steps:
        facts.extend((step.active_time, step.waiting_time, step.people, step.hourly_labor_cost))
    for fact in facts:
        if fact.value is not None:
            assert fact.evidence
        for evidence in fact.evidence:
            assert evidence.quote in sources[evidence.message_id]
    restored = Workflow.model_validate_json(workflow.model_dump_json())
    assert restored == workflow
