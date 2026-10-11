"""Evidence-backed explanations and bounded action selection; no AI arithmetic."""

from collections import Counter
import hashlib
from typing import Literal

from processiq.analysis import analyze_workflow
from processiq.dashboard import format_metric
from processiq.llm import ActionCode, PlanOutput
from processiq.models import AnalysisMetric, BlockedFact, ContractModel, Evidence, Workflow


class Finding(ContractModel):
    id: str
    title: str
    explanation: str
    step_id: str | None = None
    metric: AnalysisMetric | None = None
    input_paths: tuple[str, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    blocked_by: tuple[BlockedFact, ...] = ()
    allowed_actions: tuple[ActionCode, ...] = ()


class ActionTemplate(ContractModel):
    title: str
    instruction: str
    measure: str
    effort: Literal['Small trial', 'Team review'] = 'Small trial'


ACTIONS = {
    'collect_facts': ActionTemplate(
        effort='Team review',
        title='Complete and confirm the missing facts',
        instruction='Ask the responsible people for the listed unknown values, review existing estimates, and confirm only what you know. Save the reviewed facts and calculate again.',
        measure='Check whether the listed missing or unconfirmed inputs have been resolved before comparing full totals.'),
    'track_wait': ActionTemplate(
        title='Track the wait before this step',
        instruction='Record when each case is ready for this step and when work actually begins. Ask what is preventing an earlier start before choosing a change.',
        measure='Compare waiting minutes per case before and after a small trial. Keep the same process boundaries and include nights and weekends.'),
    'check_handoff': ActionTemplate(
        title='Try a clearer handoff',
        instruction='Agree who hands over each case, what information must be ready, and how the next person knows it is ready. Test a simple handoff checklist on upcoming cases.',
        measure='Compare waiting minutes and missed handoffs before and after the trial; check whether service quality stays acceptable.'),
    'observe_work': ActionTemplate(
        effort='Team review',
        title='Observe the work before changing it',
        instruction='Walk through this step with the people doing it. Identify repeat work, missing information, and required quality or safety checks before considering a change.',
        measure='Compare active minutes, staffing, and person-minutes per case; also track errors and service quality.'),
    'standardize_work': ActionTemplate(
        title='Try a reusable work checklist',
        instruction='With the people doing this step, create a short checklist or reusable document for repeated work. Test it while preserving required quality and safety checks.',
        measure='Compare person-minutes and rework before and after the trial. Confirm that the checklist improves the actual work.'),
    'review_cost': ActionTemplate(
        effort='Team review',
        title='Review the labor-cost baseline',
        instruction='Verify active time, people working, and per-person labor cost against the way work is actually performed. Keep materials, overhead, and customer billing rates separate.',
        measure='Recalculate reviewed inputs and compare the labor-cost baseline with actual labor records when available.'),
    'monitor_process': ActionTemplate(
        title='Keep a consistent process baseline',
        instruction='Record upcoming cases using the same process boundaries and units. Review unusual delays or repeat work with the people involved before making a change.',
        measure='Compare confirmed active time, waiting time, labor effort, and quality across cases.'),
}

LIMITATIONS = (
    'Potential bottleneck indicators are contributions, not proof of a capacity constraint. '
    'The cause of a delay is not established by these numbers. Actions are experiments for the owner to review; '
    'benefits and savings are not established. Waiting is elapsed time, including nights and weekends, '
    'and is not charged as labor. Labor costs exclude materials and overhead. '
    'Monthly cost is a projection from a representative case, not observed spending.'
)


class PlannedAction(ContractModel):
    code: ActionCode
    finding: Finding
    title: str
    instruction: str
    measure: str
    suggested_owner: str
    effort: Literal['Small trial', 'Team review'] = 'Small trial'


class ImprovementPlan(ContractModel):
    snapshot: str
    mode: Literal['ai', 'offline']
    summary: tuple[Finding, ...]
    findings: tuple[Finding, ...]
    actions: tuple[PlannedAction, ...]
    limitations: str = LIMITATIONS


def workflow_fingerprint(workflow: Workflow) -> str:
    return hashlib.sha256(workflow.model_dump_json().encode()).hexdigest()


def build_catalog(workflow: Workflow) -> tuple[Finding, ...]:
    """Recompute from the reviewed contract; never trust an old supplied analysis."""
    workflow = Workflow.model_validate(workflow.model_dump(mode='json'))
    result = analyze_workflow(workflow)
    findings = []
    summaries = (
        ('active-time', 'Active time per case', result.total_active_minutes),
        ('waiting-time', 'Waiting time per case', result.total_waiting_minutes),
        ('elapsed-time', 'Sequential elapsed time per case', result.total_elapsed_minutes),
        ('labor-effort', 'Labor effort per case', result.total_labor_minutes),
        ('labor-cost', 'Labor cost per case', result.labor_cost_per_case),
        ('monthly-cost', 'Projected labor cost per month', result.monthly_labor_cost),
    )
    for key, title, metric in summaries:
        explanation = f'{title}: {format_metric(metric)} {metric.unit}.'
        if metric.value is None:
            explanation += ' Required inputs are missing or unconfirmed; this is not zero.'
            if metric.known_subtotal is not None:
                subtotal_metric = AnalysisMetric(
                    value=metric.known_subtotal, unit=metric.unit, formula=metric.formula,
                    input_paths=metric.input_paths)
                explanation += f' Known subtotal only: {format_metric(subtotal_metric)} {metric.unit}; not a complete total.'
        actions = ('review_cost',) if key in ('labor-cost', 'monthly-cost') and metric.value is not None else ('monitor_process',)
        findings.append(Finding(id=key, title=title, explanation=explanation, metric=metric,
                                input_paths=metric.input_paths, evidence=metric.evidence,
                                blocked_by=metric.blocked_by, allowed_actions=actions))
    gaps = {gap.path: gap for _, _, metric in summaries for gap in metric.blocked_by}
    if gaps:
        findings.append(Finding(
            id='gaps', title='Complete the evidence before deciding',
            explanation='Some totals and comparisons are unavailable or partial. Missing values and unconfirmed estimates must be reviewed before a complete assessment.',
            input_paths=tuple(gaps), blocked_by=tuple(gaps.values()), allowed_actions=('collect_facts',)))
    steps = {s.id: s for s in workflow.steps}
    analyzed_steps = {s.step_id: s for s in result.steps}
    for category, ranking, field, allowed in (
        ('waiting', result.waiting_ranking, 'waiting_minutes', ('track_wait', 'check_handoff')),
        ('labor', result.labor_ranking, 'labor_minutes', ('observe_work', 'standardize_work')),
    ):
        tied_ranks = Counter(entry.rank for entry in ranking.entries)
        for entry in ranking.entries:
            step = steps[entry.step_id]
            metric = getattr(analyzed_steps[entry.step_id], field)
            comparison = 'complete comparison' if ranking.complete else 'partial comparison of confirmed contributors'
            tie = ' (tied)' if tied_ranks[entry.rank] > 1 else ''
            title = f'{"Waiting" if category == "waiting" else "Labor effort"} at step {step.order}: {step.name}'
            explanation = (
                f'{title}: {format_metric(metric)} {metric.unit}, rank {entry.rank}{tie} in a {comparison}. '
                'This is a potential bottleneck indicator; it does not establish the cause or prove the step is inefficient.'
            )
            findings.append(Finding(id=f'{category}-step-{entry.step_id}', title=title,
                                    explanation=explanation, step_id=entry.step_id, metric=metric,
                                    input_paths=entry.input_paths, evidence=entry.evidence,
                                    blocked_by=ranking.blocked_by, allowed_actions=allowed))
    if not gaps and not result.waiting_ranking.entries and not result.labor_ranking.entries:
        findings.append(Finding(id='no-positive', title='No positive time contributors in this assessment',
                                explanation='Confirmed waiting time and labor effort have no positive contributors. This does not prove the process has no other problems.',
                                allowed_actions=('monitor_process',)))
    return tuple(findings)


def _offline_selection(catalog: tuple[Finding, ...]) -> PlanOutput:
    selected = []
    gaps = next((f for f in catalog if f.id == 'gaps'), None)
    if gaps:
        selected.append(gaps)
    for prefix in ('waiting-', 'labor-'):
        candidate = next((f for f in catalog if f.step_id and f.id.startswith(prefix)), None)
        if candidate:
            selected.append(candidate)
    if not selected:
        selected.append(next((f for f in catalog if f.id == 'no-positive'), catalog[0]))
    return PlanOutput(finding_ids=[f.id for f in selected],
                      actions=[{'finding_id': f.id, 'action': f.allowed_actions[0]} for f in selected])


def generate_plan(workflow: Workflow, planner=None) -> ImprovementPlan:
    workflow = Workflow.model_validate(workflow.model_dump(mode='json'))
    catalog = build_catalog(workflow)
    raw = _offline_selection(catalog) if planner is None else planner.select(catalog=catalog)
    output = PlanOutput.model_validate(raw.model_dump() if isinstance(raw, PlanOutput) else raw)
    by_id = {f.id: f for f in catalog}
    if len(set(output.finding_ids)) != len(output.finding_ids) or any(key not in by_id for key in output.finding_ids):
        raise ValueError('The plan references an unknown or duplicate finding.')
    pairs = [(a.finding_id, a.action) for a in output.actions]
    if len(set(pairs)) != len(pairs):
        raise ValueError('The plan contains duplicate actions.')
    if 'gaps' in by_id and (not output.actions or pairs[0] != ('gaps', 'collect_facts')):
        raise ValueError('An incomplete assessment must first collect and confirm missing facts.')
    planned = []
    steps = {s.id: s for s in workflow.steps}
    for choice in output.actions:
        if choice.finding_id not in output.finding_ids:
            raise ValueError('Each action must cite a selected finding.')
        finding = by_id[choice.finding_id]
        if choice.action not in finding.allowed_actions:
            raise ValueError('The action does not apply to its cited finding.')
        template = ACTIONS[choice.action]
        role = steps[finding.step_id].responsible_role if finding.step_id else None
        planned.append(PlannedAction(code=choice.action, finding=finding,
                                     suggested_owner=role or 'Business owner', **template.model_dump()))
    return ImprovementPlan(snapshot=workflow_fingerprint(workflow), mode='offline' if planner is None else 'ai',
                           summary=catalog[:6], findings=tuple(by_id[key] for key in output.finding_ids),
                           actions=tuple(planned))
