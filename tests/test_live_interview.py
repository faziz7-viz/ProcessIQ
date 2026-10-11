"""Opt-in real API smoke test; never spends API usage during ordinary pytest."""

import os
from decimal import Decimal

import pytest

from processiq.interview import InterviewSession, advance_interview
from processiq.llm import OpenAIInterviewer, load_api_configuration


@pytest.mark.live
def test_live_synthetic_interview():
    if os.getenv("PROCESSIQ_LIVE_TEST") != "1":
        pytest.skip("Set PROCESSIQ_LIVE_TEST=1 to explicitly opt into a live API smoke test")
    if not load_api_configuration()["api_key"]:
        pytest.fail("Configure OPENAI_API_KEY in ProcessIQ/.env before the live smoke test")
    description = (
        "This is synthetic course data for a contractor. The process is Receive an inquiry. "
        "It starts when a customer inquiry arrives and ends when its details are recorded. "
        "There is one sequential step, Receive inquiry, handled by the office administrator. "
        "Receiving takes 10 active minutes per case. Waiting before this step is 0 minutes. "
        "There is 1 person working. Labor cost is USD 30 per person per hour. "
        "We handle 20 cases per month."
    )
    result = advance_interview(InterviewSession(), description, OpenAIInterviewer())
    assert result.workflow is not None
    assert result.workflow.monthly_volume.value == 20
    assert result.workflow.monthly_volume.confirmed is False
    assert len(result.workflow.steps) == 1
    step = result.workflow.steps[0]
    assert step.active_time.value == Decimal("10")
    assert step.waiting_time.value == Decimal("0")
    assert step.people.value == 1
    assert step.hourly_labor_cost.value == Decimal("30")
    assert step.hourly_labor_cost.confirmed is False
