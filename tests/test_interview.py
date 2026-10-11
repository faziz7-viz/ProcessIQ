from decimal import Decimal
from importlib import import_module

import pytest


def output(value="10", quote="Receiving takes 10 minutes.", unit="minutes"):
    return {
        "workflow": {
            "name": "Estimate process", "start_point": "Inquiry received", "end_point": "Estimate sent",
            "monthly_volume": {"value": None, "unit": "cases/month", "evidence": []},
            "steps": [{
                "id": "receive", "name": "Receive inquiry", "responsible_role": None,
                "active_time": {"value": value, "unit": unit, "evidence": [{"message_id": "owner-1", "quote": quote}]},
                "waiting_time": {"value": None, "unit": "minutes", "evidence": []},
                "people": {"value": None, "unit": "people", "evidence": []},
                "hourly_labor_cost": {"value": None, "unit": "currency/hour", "evidence": []},
            }],
        },
        "question": "How many cases do you handle per month?", "target": "monthly_volume",
    }


class Reply:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def extract(self, **kwargs):
        self.calls += 1
        return self.response


@pytest.fixture
def interview():
    return import_module("processiq.interview")


def test_extracts_grounded_draft_without_confirmation(interview):
    state = interview.advance_interview(interview.InterviewSession(), "Receiving takes 10 minutes.", Reply(output()))
    assert state.workflow.steps[0].active_time.value == Decimal("10")
    assert state.workflow.steps[0].active_time.confirmed is False
    assert state.workflow.source_messages[0].text == "Receiving takes 10 minutes."
    assert state.workflow.data_kind == "owner_provided"
    assert state.target == "monthly_volume"


@pytest.mark.parametrize("response", [output("50"), output(quote="Invented owner words"), output(unit="hours")])
def test_rejects_unsupported_values_quotes_and_units(interview, response):
    state = interview.InterviewSession()
    with pytest.raises(interview.InterviewError):
        interview.advance_interview(state, "Receiving takes 10 minutes.", Reply(response))
    assert state.sources == ()
    assert state.workflow is None


def test_model_cannot_supply_confirmation_or_owner_messages(interview):
    response = output()
    response["workflow"]["source_messages"] = [{"id": "fake", "text": "Fake"}]
    with pytest.raises(interview.InterviewError):
        interview.advance_interview(interview.InterviewSession(), "Receiving takes 10 minutes.", Reply(response))


def test_unknown_answer_skips_previous_target_and_selects_another(interview):
    first = interview.advance_interview(interview.InterviewSession(), "Receiving takes 10 minutes.", Reply(output()))
    second = interview.advance_interview(first, "I don't know", Reply(output()))
    assert "monthly_volume" in second.skipped
    assert second.target != "monthly_volume"
    assert second.workflow.monthly_volume.value is None


def test_vague_description_can_request_details_without_fabricating_steps(interview):
    response = {"workflow": None, "question": "What starts and ends your process, and what are the steps?", "target": "process_details"}
    state = interview.advance_interview(interview.InterviewSession(), "We do estimates.", Reply(response))
    assert state.workflow is None
    assert state.question


def test_turn_limit_stops_questions_and_blocks_additional_requests(interview):
    state = interview.InterviewSession()
    client = Reply(output())
    for index in range(interview.MAX_TURNS):
        client.response = {**output(), "question": f"Please clarify detail {index}?", "target": "process_details"}
        state = interview.advance_interview(state, "Receiving takes 10 minutes.", client)
    assert state.question is None
    with pytest.raises(interview.InterviewError):
        interview.advance_interview(state, "Another answer", client)
    assert client.calls == interview.MAX_TURNS


def test_blank_and_oversized_answers_do_not_call_provider(interview):
    client = Reply(output())
    for answer in (" ", "x" * (interview.MAX_MESSAGE_CHARS + 1)):
        with pytest.raises(interview.InterviewError):
            interview.advance_interview(interview.InterviewSession(), answer, client)
    assert client.calls == 0


def test_explicit_financial_quote_can_supply_rate_but_not_confirm_it(interview):
    response = output()
    response["workflow"]["steps"][0]["hourly_labor_cost"] = {
        "value": "30.00", "unit": "currency/hour",
        "evidence": [{"message_id": "owner-1", "quote": "Labor costs $30 per hour."}],
    }
    state = interview.advance_interview(interview.InterviewSession(),
        "Receiving takes 10 minutes. Labor costs $30 per hour.", Reply(response))
    assert state.workflow.steps[0].hourly_labor_cost.value == Decimal("30.00")
    assert state.workflow.steps[0].hourly_labor_cost.confirmed is False


def test_provider_failure_preserves_previous_state(interview):
    class Failure:
        def extract(self, **kwargs):
            raise interview.InterviewError("Service temporarily unavailable")
    state = interview.InterviewSession()
    with pytest.raises(interview.InterviewError):
        interview.advance_interview(state, "Receiving takes 10 minutes.", Failure())
    assert state.sources == ()


def test_scope_clarification_is_not_replaced_by_numeric_followup(interview):
    response = output()
    response["target"] = "process_details"
    response["question"] = "Do these steps happen sequentially or in parallel?"
    state = interview.advance_interview(interview.InterviewSession(), "Receiving takes 10 minutes.", Reply(response))
    assert state.target == "process_details"
    assert state.question == "Do these steps happen sequentially or in parallel?"


def test_known_fact_can_still_be_clarified(interview):
    response = output()
    response["target"] = "steps.receive.active_time"
    response["question"] = "Is the 10-minute duration active work or elapsed time?"
    state = interview.advance_interview(interview.InterviewSession(), "Receiving takes 10 minutes.", Reply(response))
    assert state.target == "steps.receive.active_time"
    assert state.question == response["question"]


def test_source_hours_cannot_be_relabeled_as_minutes(interview):
    with pytest.raises(interview.InterviewError):
        interview.advance_interview(interview.InterviewSession(), "Receiving takes 10 hours.",
                                    Reply(output(quote="Receiving takes 10 hours.")))


def test_invalid_extraction_preserves_populated_draft(interview):
    state = interview.advance_interview(interview.InterviewSession(), "Receiving takes 10 minutes.", Reply(output()))
    before = state.workflow.model_dump_json()
    with pytest.raises(interview.InterviewError):
        interview.advance_interview(state, "I don't know", Reply(output("999")))
    assert state.workflow.model_dump_json() == before
    assert len(state.sources) == 1


def test_null_workflow_preserves_existing_partial_draft(interview):
    state = interview.advance_interview(interview.InterviewSession(), "Receiving takes 10 minutes.", Reply(output()))
    updated = interview.advance_interview(state, "I don't know", Reply({
        "workflow": None, "question": "What is the waiting time?", "target": "steps.receive.waiting_time",
    }))
    assert updated.workflow.steps[0].active_time.value == Decimal("10")
    assert len(updated.workflow.source_messages) == 2


def test_explicit_latest_correction_uses_new_source_and_remains_unconfirmed(interview):
    state = interview.advance_interview(interview.InterviewSession(), "Receiving takes 10 minutes.", Reply(output()))
    response = output("15", "Correction: receiving takes 15 minutes.")
    response["workflow"]["steps"][0]["active_time"]["evidence"][0]["message_id"] = "owner-2"
    updated = interview.advance_interview(state, "Correction: receiving takes 15 minutes.", Reply(response))
    assert updated.workflow.steps[0].active_time.value == Decimal("15")
    assert updated.workflow.steps[0].active_time.confirmed is False
    assert updated.workflow.steps[0].active_time.evidence[0].message_id == "owner-2"


def test_complete_numeric_draft_can_still_ask_scope_question(interview):
    response = output()
    step = response["workflow"]["steps"][0]
    for field, value, unit, quote in [
        ("waiting_time", "0", "minutes", "Waiting is 0 minutes."),
        ("people", 1, "people", "There is 1 person working."),
        ("hourly_labor_cost", "30", "currency/hour", "Labor costs USD 30 per hour."),
    ]:
        step[field] = {"value": value, "unit": unit, "evidence": [{"message_id": "owner-1", "quote": quote}]}
    response["workflow"]["monthly_volume"] = {
        "value": 20, "unit": "cases/month", "evidence": [{"message_id": "owner-1", "quote": "We handle 20 cases per month."}],
    }
    response["question"] = "Does the waiting occur inside the process boundaries?"
    response["target"] = "process_details"
    answer = "Receiving takes 10 minutes. Waiting is 0 minutes. There is 1 person working. Labor costs USD 30 per hour. We handle 20 cases per month."
    result = interview.advance_interview(interview.InterviewSession(), answer, Reply(response))
    assert interview.missing_fields(result.workflow) == []
    assert result.target == "process_details"
    assert result.question == response["question"]


@pytest.mark.parametrize("quote", ["Labor costs USD 30 per day.", "Labor costs EUR 30 per hour."])
def test_rate_quote_must_support_usd_hourly_units(interview, quote):
    response = output()
    response["workflow"]["steps"][0]["hourly_labor_cost"] = {
        "value": "30", "unit": "currency/hour", "evidence": [{"message_id": "owner-1", "quote": quote}],
    }
    with pytest.raises(interview.InterviewError):
        interview.advance_interview(interview.InterviewSession(), "Receiving takes 10 minutes. " + quote, Reply(response))


def test_number_followed_by_sentence_period_is_supported():
    response = output()
    response['workflow']['steps'][0]['people'] = {
        'value': 1, 'unit': 'people',
        'evidence': [{'message_id': 'owner-1', 'quote': 'The number of people actively working is 1.'}],
    }
    from processiq.interview import InterviewSession, advance_interview
    state = advance_interview(InterviewSession(),
        'Receiving takes 10 minutes. The number of people actively working is 1.', Reply(response))
    assert state.workflow.steps[0].people.value == 1
    assert state.workflow.steps[0].people.confirmed is False


def test_decimal_fraction_cannot_support_a_truncated_integer():
    response = output()
    response['workflow']['steps'][0]['people'] = {
        'value': 1, 'unit': 'people',
        'evidence': [{'message_id': 'owner-1', 'quote': 'Staffing is 1.5 people.'}],
    }
    from processiq.interview import InterviewSession, advance_interview, InterviewError
    with pytest.raises(InterviewError):
        advance_interview(InterviewSession(), 'Receiving takes 10 minutes. Staffing is 1.5 people.', Reply(response))


@pytest.mark.parametrize('field,value,unit,quote,source', [
    ('hourly_labor_cost', '30', 'currency/hour', 'USD hourly labor cost is 30.', 'USD hourly labor cost is 30.50.'),
    ('people', 1, 'people', 'The people count is 1.', 'The people count is 1.5.'),
    ('people', 1, 'people', '1 people', 'Staffing is 21 people.'),
])
def test_quote_cannot_truncate_a_source_number(field, value, unit, quote, source):
    response = output()
    response['workflow']['steps'][0][field] = {
        'value': value, 'unit': unit,
        'evidence': [{'message_id': 'owner-1', 'quote': quote}],
    }
    from processiq.interview import InterviewSession, advance_interview, InterviewError
    with pytest.raises(InterviewError):
        advance_interview(InterviewSession(), 'Receiving takes 10 minutes. ' + source, Reply(response))
