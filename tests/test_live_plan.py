"""Opt-in single synthetic request; ordinary pytest never uses paid API calls."""

import os
from decimal import Decimal

import pytest

from processiq.llm import OpenAIPlanner, load_api_configuration
from processiq.recommendations import generate_plan
from test_recommendations import workflow


@pytest.mark.live
def test_live_synthetic_improvement_plan():
    if os.getenv('PROCESSIQ_LIVE_PLAN_TEST') != '1':
        pytest.skip('Set PROCESSIQ_LIVE_PLAN_TEST=1 to opt into a live synthetic plan test')
    if not load_api_configuration()['api_key']:
        pytest.fail('Configure OPENAI_API_KEY in ProcessIQ/.env before the live plan test')
    owner = workflow()
    plan = generate_plan(owner, OpenAIPlanner())
    assert plan.mode == 'ai'
    assert 1 <= len(plan.actions) <= 3
    assert next(f for f in plan.summary if f.id == 'labor-cost').metric.value == Decimal('137.50')
    for finding in plan.findings:
        for evidence in finding.evidence:
            assert evidence.quote in next(s.text for s in owner.source_messages if s.id == evidence.message_id)
    for action in plan.actions:
        assert action.code in action.finding.allowed_actions
