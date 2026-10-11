"""Follow-up paths from live model output must not prematurely end a draft."""

from copy import deepcopy

import pytest

from processiq.interview import InterviewSession, advance_interview
from test_interview import Reply, output


def indexed_followup(target="steps[1].active_time"):
    reply = output()
    prepare = deepcopy(reply["workflow"]["steps"][0])
    prepare.update(id="prepare", name="Prepare quote")
    prepare["active_time"] = {"value": None, "unit": "minutes", "evidence": []}
    reply["workflow"]["steps"].append(prepare)
    reply.update(question="How many minutes does preparing the quote take?", target=target)
    return reply


def test_indexed_followup_continues_interview_for_the_correct_step():
    state = advance_interview(InterviewSession(), "Receiving takes 10 minutes.",
                              Reply(indexed_followup()))
    assert state.question == "How many minutes does preparing the quote take?"
    assert state.target == "steps.prepare.active_time"
    assert state.workflow.steps[0].active_time.value == 10
    assert state.workflow.steps[1].active_time.value is None


def test_indexed_unknown_answer_skips_the_same_fact_by_id():
    first = advance_interview(InterviewSession(), "Receiving takes 10 minutes.",
                              Reply(indexed_followup()))
    second = advance_interview(first, "Not sure", Reply(indexed_followup()))
    assert "steps.prepare.active_time" in second.skipped
    assert second.question is None
    assert second.workflow.steps[1].active_time.value is None


@pytest.mark.parametrize("target", ["steps[0].active_time", "steps[99].active_time", "steps[-1].active_time"])
def test_indexed_target_cannot_repeat_known_values_or_reference_absent_steps(target):
    state = advance_interview(InterviewSession(), "Receiving takes 10 minutes.",
                              Reply(indexed_followup(target)))
    assert state.question is None
