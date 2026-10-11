"""Contract tests: each case protects a user-visible validation boundary."""

from decimal import Decimal
import importlib
import json

import pytest
from pydantic import ValidationError


@pytest.fixture
def models():
    # A runtime import lets the initial RED run report missing-contract failures.
    return importlib.import_module("processiq.models")


def known(value, unit, quote="Work takes 30 minutes.", confirmed=False):
    return {
        "value": value,
        "unit": unit,
        "confirmed": confirmed,
        "evidence": [{"message_id": "owner-1", "quote": quote}],
    }


def draft_payload():
    return {
        "name": "Prepare an estimate",
        "start_point": "Inquiry received",
        "end_point": "Estimate sent",
        "currency": "USD",
        "data_kind": "owner_provided",
        "source_messages": [
            {"id": "owner-1", "text": "Work takes 30 minutes.", "speaker": "owner"}
        ],
        "steps": [
            {
                "id": "prepare",
                "order": 1,
                "name": "Prepare estimate",
                "responsible_role": None,
                "active_time": known("30", "minutes"),
            }
        ],
    }


def test_numeric_facts_default_to_unknown_without_evidence(models):
    workflow = models.Workflow.model_validate(draft_payload())
    assert workflow.monthly_volume.value is None
    assert workflow.monthly_volume.confirmed is False
    step = workflow.steps[0]
    assert step.waiting_time.value is None
    assert step.people.value is None
    assert step.hourly_labor_cost.value is None
    assert step.waiting_time.evidence == ()
    assert step.responsible_role is None


@pytest.mark.parametrize(
    "model_name,unit,value,expected",
    [
        ("DurationFact", "minutes", "0", Decimal("0")),
        ("HourlyRateFact", "currency/hour", "0.00", Decimal("0.00")),
        ("MonthlyVolumeFact", "cases/month", 0, 0),
    ],
)
def test_explicit_zero_is_known_not_missing(models, model_name, unit, value, expected):
    fact = getattr(models, model_name).model_validate(known(value, unit))
    assert fact.value == expected
    assert fact.value is not None


@pytest.mark.parametrize(
    "model_name,unit,value",
    [
        ("DurationFact", "minutes", "-1"),
        ("HourlyRateFact", "currency/hour", "-0.01"),
        ("MonthlyVolumeFact", "cases/month", -1),
        ("PeopleFact", "people", -1),
        ("PeopleFact", "people", 0),
    ],
)
def test_rejects_negative_inputs_and_zero_workers(models, model_name, unit, value):
    with pytest.raises(ValidationError):
        getattr(models, model_name).model_validate(known(value, unit))


@pytest.mark.parametrize(
    "model_name,unit,value",
    [
        ("DurationFact", "hours", "1"),
        ("HourlyRateFact", "USD", "25"),
        ("MonthlyVolumeFact", "cases/week", 10),
        ("PeopleFact", "workers", 1),
    ],
)
def test_rejects_wrong_units_instead_of_silent_conversion(models, model_name, unit, value):
    with pytest.raises(ValidationError):
        getattr(models, model_name).model_validate(known(value, unit))


@pytest.mark.parametrize("value", [True, False, 0.1, "NaN", "Infinity", "-Infinity", ""])
def test_rejects_unsafe_decimal_inputs(models, value):
    with pytest.raises(ValidationError):
        models.HourlyRateFact.model_validate(known(value, "currency/hour"))


@pytest.mark.parametrize("value", [True, 1.5, "2"])
def test_counts_require_real_integers(models, value):
    with pytest.raises(ValidationError):
        models.PeopleFact.model_validate(known(value, "people"))


@pytest.mark.parametrize("value", ["19.95", Decimal("19.95"), 20])
def test_money_accepts_exact_decimal_strings_decimals_and_integers(models, value):
    fact = models.HourlyRateFact.model_validate(known(value, "currency/hour"))
    assert isinstance(fact.value, Decimal)
    assert fact.value == Decimal(str(value))


@pytest.mark.parametrize("value", ["30", "0"])
def test_known_values_including_zero_require_evidence(models, value):
    with pytest.raises(ValidationError, match="evidence"):
        models.DurationFact.model_validate({"value": value, "unit": "minutes"})


def test_unknown_fact_can_record_an_owner_admitting_a_gap(models):
    fact = models.DurationFact.model_validate(known(None, "minutes", "I do not know."))
    assert fact.value is None
    assert fact.evidence[0].quote == "I do not know."


def test_unknown_fact_cannot_be_confirmed(models):
    with pytest.raises(ValidationError, match="confirmed"):
        models.DurationFact.model_validate({"value": None, "confirmed": True})


def test_confirmation_requires_a_boolean(models):
    payload = known("30", "minutes")
    payload["confirmed"] = "true"
    with pytest.raises(ValidationError):
        models.DurationFact.model_validate(payload)


@pytest.mark.parametrize("field", ["message_id", "quote"])
def test_evidence_cannot_be_blank(models, field):
    evidence = {"message_id": "owner-1", "quote": "Work takes 30 minutes."}
    evidence[field] = "   "
    with pytest.raises(ValidationError):
        models.Evidence.model_validate(evidence)


@pytest.mark.parametrize("field,value", [("message_id", "missing"), ("quote", "Invented quote")])
def test_workflow_rejects_untraceable_evidence(models, field, value):
    payload = draft_payload()
    payload["steps"][0]["active_time"]["evidence"][0][field] = value
    with pytest.raises(ValidationError, match="evidence"):
        models.Workflow.model_validate(payload)


def test_monthly_volume_evidence_is_checked_too(models):
    payload = draft_payload()
    payload["monthly_volume"] = known(10, "cases/month", "Invented volume")
    with pytest.raises(ValidationError, match="evidence"):
        models.Workflow.model_validate(payload)


def test_source_message_cannot_claim_to_be_an_assistant(models):
    payload = draft_payload()
    payload["source_messages"][0]["speaker"] = "assistant"
    with pytest.raises(ValidationError):
        models.Workflow.model_validate(payload)


@pytest.mark.parametrize("field", ["name", "start_point", "end_point"])
def test_process_labels_cannot_be_blank(models, field):
    payload = draft_payload()
    payload[field] = "  "
    with pytest.raises(ValidationError):
        models.Workflow.model_validate(payload)


def test_unknown_fields_are_not_silently_dropped(models):
    payload = draft_payload()
    payload["steps"][0]["invented_cost"] = "500"
    with pytest.raises(ValidationError):
        models.Workflow.model_validate(payload)


@pytest.mark.parametrize("field", ["source_messages", "steps"])
def test_workflow_needs_a_source_and_at_least_one_step(models, field):
    payload = draft_payload()
    payload[field] = []
    with pytest.raises(ValidationError):
        models.Workflow.model_validate(payload)


def test_source_message_ids_must_be_unique(models):
    payload = draft_payload()
    payload["source_messages"].append(dict(payload["source_messages"][0]))
    with pytest.raises(ValidationError, match="unique"):
        models.Workflow.model_validate(payload)


def test_step_ids_must_be_unique(models):
    payload = draft_payload()
    second = dict(payload["steps"][0], order=2)
    payload["steps"].append(second)
    with pytest.raises(ValidationError, match="unique"):
        models.Workflow.model_validate(payload)


@pytest.mark.parametrize("order", [0, 2, True])
def test_step_sequence_starts_at_one_and_has_no_gaps(models, order):
    payload = draft_payload()
    payload["steps"][0]["order"] = order
    with pytest.raises(ValidationError):
        models.Workflow.model_validate(payload)


def test_steps_must_be_stored_in_sequence_order(models):
    payload = draft_payload()
    payload["steps"].append(dict(payload["steps"][0], id="send", order=2))
    payload["steps"].reverse()
    with pytest.raises(ValidationError, match="order"):
        models.Workflow.model_validate(payload)


def test_json_round_trip_preserves_exact_money_unknowns_and_confirmation(models):
    payload = draft_payload()
    payload["source_messages"][0]["text"] += " Labor costs 19.95 per hour."
    payload["steps"][0]["hourly_labor_cost"] = known(
        "19.95", "currency/hour", "Labor costs 19.95 per hour.", confirmed=True
    )
    workflow = models.Workflow.model_validate(payload)
    serialized = workflow.model_dump_json()
    raw = json.loads(serialized)
    assert raw["steps"][0]["hourly_labor_cost"]["value"] == "19.95"
    assert raw["steps"][0]["waiting_time"]["value"] is None
    restored = models.Workflow.model_validate_json(serialized)
    assert restored.steps[0].hourly_labor_cost.value == Decimal("19.95")
    assert restored.steps[0].hourly_labor_cost.confirmed is True


def test_corrections_can_be_revalidated_without_changing_original(models):
    original = models.Workflow.model_validate(draft_payload())
    corrected = original.model_dump(mode="json")
    corrected["source_messages"].append(
        {"id": "owner-2", "speaker": "owner", "text": "Correction: it takes 20 minutes."}
    )
    corrected["steps"][0]["active_time"] = {
        "value": "20", "unit": "minutes", "confirmed": True,
        "evidence": [{"message_id": "owner-2", "quote": "Correction: it takes 20 minutes."}],
    }
    updated = models.Workflow.model_validate(corrected)
    assert original.steps[0].active_time.value == Decimal("30")
    assert updated.steps[0].active_time.value == Decimal("20")
    assert updated.steps[0].active_time.confirmed is True
    assert updated.steps[0].id == original.steps[0].id


def test_models_prevent_unvalidated_in_place_edits(models):
    workflow = models.Workflow.model_validate(draft_payload())
    with pytest.raises(ValidationError):
        workflow.steps[0].active_time.value = Decimal("-10")
    assert isinstance(workflow.steps, tuple)
    assert isinstance(workflow.steps[0].active_time.evidence, tuple)


def test_decimal_json_schema_does_not_invite_binary_float_input(models):
    schema = models.HourlyRateFact.model_json_schema()
    choices = [schema["properties"]["value"]]
    types = set()
    while choices:
        choice = choices.pop()
        choices.extend(choice.get("anyOf", []))
        if "type" in choice:
            types.add(choice["type"])
    assert types == {"string", "integer", "null"}


@pytest.mark.parametrize("value", ["EUR", "usd", ""])
def test_workflow_requires_the_supported_explicit_currency(models, value):
    payload = draft_payload()
    payload["currency"] = value
    with pytest.raises(ValidationError):
        models.Workflow.model_validate(payload)


def test_evidence_preserves_exact_source_spacing(models):
    payload = draft_payload()
    payload["source_messages"][0]["text"] = "Owner said:  Work takes 30 minutes.  End."
    payload["steps"][0]["active_time"]["evidence"][0]["quote"] = "  Work takes 30 minutes.  "
    workflow = models.Workflow.model_validate(payload)
    assert workflow.steps[0].active_time.evidence[0].quote == "  Work takes 30 minutes.  "


def test_invalid_correction_is_rejected_on_revalidation(models):
    workflow = models.Workflow.model_validate(draft_payload())
    corrected = workflow.model_dump(mode="json")
    corrected["steps"][0]["active_time"]["value"] = "-20"
    with pytest.raises(ValidationError):
        models.Workflow.model_validate(corrected)
    assert workflow.steps[0].active_time.value == Decimal("30")
