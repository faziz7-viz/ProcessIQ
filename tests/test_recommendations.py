from pathlib import Path
from decimal import Decimal

import pytest
from pydantic import ValidationError

from processiq.assessment import apply_review, review_values
from processiq.models import Workflow
from processiq.recommendations import build_catalog, generate_plan, workflow_fingerprint

DATA = Path(__file__).resolve().parents[1] / 'data'


def workflow(incomplete=False):
    name = 'contractor_estimate_incomplete.json' if incomplete else 'contractor_estimate.json'
    return Workflow.model_validate_json((DATA / name).read_text())


class Selector:
    def __init__(self, reply):
        self.reply = reply

    def select(self, **kwargs):
        return self.reply


def selection(finding='waiting-step-follow-up', action='track_wait'):
    return {'finding_ids': [finding], 'actions': [{'finding_id': finding, 'action': action}]}


def test_complete_catalog_explanations_use_exact_engine_values_and_sources():
    catalog = {f.id: f for f in build_catalog(workflow())}
    assert catalog['labor-cost'].metric.value == Decimal('137.50')
    assert '$137.50' in catalog['labor-cost'].explanation
    assert '$2,750.00' in catalog['monthly-cost'].explanation
    wait = catalog['waiting-step-follow-up']
    assert '2,880' in wait.explanation
    assert 'rank 1' in wait.explanation
    assert wait.evidence[0].quote in workflow().source_messages[-1].text
    assert wait.input_paths == ('steps.follow-up.waiting_time',)
    assert '120' in catalog['labor-step-site-visit'].explanation
    assert 'person-minutes' in catalog['labor-step-site-visit'].explanation


def test_partial_catalog_and_offline_plan_disclose_gaps_without_cost_estimates():
    owner = workflow(True)
    catalog = {f.id: f for f in build_catalog(owner)}
    assert 'gaps' in catalog
    assert catalog['labor-cost'].metric.value is None
    assert 'Unavailable' in catalog['labor-cost'].explanation
    assert '$5.00' in catalog['labor-cost'].explanation
    assert '$2,750' not in catalog['monthly-cost'].explanation
    assert 'partial' in catalog['labor-step-receive-inquiry'].explanation.lower()
    assert 'waiting-step-follow-up' not in catalog
    plan = generate_plan(owner)
    assert plan.mode == 'offline'
    assert plan.actions[0].code == 'collect_facts'
    assert any(f.id == 'gaps' for f in plan.findings)
    assert plan.actions[0].finding.blocked_by


def test_ai_selection_cannot_change_numbers_or_supply_source_quotes():
    plan = generate_plan(workflow(), Selector(selection()))
    assert plan.mode == 'ai'
    assert plan.findings[0].metric.value == Decimal('2880')
    assert plan.actions[0].finding.id == 'waiting-step-follow-up'
    assert plan.actions[0].measure
    assert 'not established' in plan.limitations


@pytest.mark.parametrize('reply', [
    selection('invented'),
    selection(action='review_cost'),
    {'finding_ids': ['labor-step-site-visit'], 'actions': selection()['actions']},
    {'finding_ids': ['waiting-step-follow-up', 'waiting-step-follow-up'], 'actions': selection()['actions']},
    {'finding_ids': ['waiting-step-follow-up'], 'actions': selection()['actions'] * 2},
    {'finding_ids': [], 'actions': []},
    {**selection(), 'savings': '50000'},
    {**selection(), 'quote': 'Invented evidence'},
    {**selection(), 'explanation': 'Your monthly cost is $999999'},
])
def test_invalid_ai_selection_is_rejected_atomically(reply):
    with pytest.raises(ValueError):
        generate_plan(workflow(), Selector(reply))


def test_incomplete_ai_plan_must_prioritize_collecting_missing_facts():
    with pytest.raises(ValueError):
        generate_plan(workflow(True), Selector(selection('labor-step-receive-inquiry', 'observe_work')))


def test_confirmed_zero_has_no_positive_bottleneck_and_no_fake_gap():
    owner = workflow()
    values = review_values(owner)
    for path in values:
        if path.endswith(('active_time', 'waiting_time', 'hourly_labor_cost')) or path == 'monthly_volume':
            values[path] = '0'
    owner = apply_review(owner, values, confirm_all=True)
    catalog = {f.id: f for f in build_catalog(owner)}
    assert catalog['labor-cost'].metric.value == 0
    assert catalog['monthly-cost'].metric.value == 0
    assert 'gaps' not in catalog
    assert 'no-positive' in catalog
    assert all(f.step_id is None for f in catalog.values())
    assert generate_plan(owner).actions


def test_ties_keep_equal_rank_and_do_not_claim_unique_largest():
    owner = workflow()
    values = review_values(owner)
    values['steps.collect-details.waiting_time'] = '2880'
    owner = apply_review(owner, values, confirm_all=True)
    catalog = {f.id: f for f in build_catalog(owner)}
    assert 'rank 1' in catalog['waiting-step-collect-details'].explanation
    assert 'rank 1' in catalog['waiting-step-follow-up'].explanation
    assert 'tied' in catalog['waiting-step-follow-up'].explanation


def test_correction_changes_report_snapshot_and_recalculates_cost():
    owner = workflow()
    before = generate_plan(owner)
    values = review_values(owner)
    values['steps.prepare-estimate.active_time'] = '30'
    updated = apply_review(owner, values, confirm_all=True)
    after = generate_plan(updated)
    assert before.snapshot != after.snapshot
    assert after.snapshot == workflow_fingerprint(updated)
    assert next(f for f in after.summary if f.id == 'labor-cost').metric.value == Decimal('126.25')
    assert owner.steps[3].active_time.value == 45


def test_bypassed_invalid_workflow_is_revalidated_at_plan_boundary():
    owner = workflow().model_copy(update={'currency': 'EUR'})
    with pytest.raises(ValidationError):
        generate_plan(owner)


def test_step_ids_cannot_collide_with_summary_finding_ids():
    data = workflow().model_dump(mode='json')
    data['steps'][0]['id'] = 'time'
    data['steps'][1]['id'] = 'cost'
    owner = Workflow.model_validate(data)
    catalog = build_catalog(owner)
    assert len({f.id for f in catalog}) == len(catalog)
    assert next(f for f in catalog if f.id == 'labor-cost').metric.value == Decimal('137.50')
    assert next(f for f in catalog if f.id == 'waiting-time').metric.value == Decimal('4680')


def test_invalid_constructed_selection_is_revalidated():
    from processiq.llm import PlanOutput
    reply = PlanOutput.model_validate(selection()).model_copy(update={'actions': []})
    with pytest.raises(ValueError):
        generate_plan(workflow(), Selector(reply))
