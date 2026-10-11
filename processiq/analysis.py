"""Pure Python calculations over confirmed facts; no AI, I/O, or global state.

Time is recorded in minutes (labor in person-minutes). Money is rounded per step
with ROUND_HALF_UP, then summed and scaled. Rankings indicate contributors to
waiting or effort; they do not establish causes or capacity constraints.
"""

from collections.abc import Callable, Iterable
from decimal import Context, Decimal, ROUND_HALF_UP, localcontext

from processiq.models import (
    AnalysisMetric,
    BlockedFact,
    BottleneckRanking,
    Fact,
    RankedContribution,
    StepAnalysis,
    Workflow,
    WorkflowAnalysis,
    WorkflowStep,
)

ZERO = Decimal("0")
CENT = Decimal("0.01")
COST_FORMULA = "active_minutes * people * hourly_labor_cost / 60; round half up to cents"


def _unique(items: Iterable) -> tuple:
    """Preserve input order while removing repeated source references or gaps."""
    return tuple(dict.fromkeys(items))


def _gap(path: str, fact: Fact) -> BlockedFact | None:
    if fact.value is None:
        return BlockedFact(path=path, reason="missing")
    if not fact.confirmed:
        return BlockedFact(path=path, reason="unconfirmed")
    return None


def _metric(
    facts: tuple[tuple[str, Fact], ...],
    unit: str,
    formula: str,
    calculate: Callable[[list[Decimal]], Decimal],
) -> AnalysisMetric:
    gaps = tuple(gap for path, fact in facts if (gap := _gap(path, fact)) is not None)
    evidence = _unique(
        item for _, fact in facts if fact.value is not None and fact.confirmed
        for item in fact.evidence
    )
    value = None if gaps else calculate([Decimal(fact.value) for _, fact in facts])
    return AnalysisMetric(
        value=value, unit=unit, formula=formula,
        input_paths=tuple(path for path, _ in facts), evidence=evidence, blocked_by=gaps,
    )


def _step_analysis(step: WorkflowStep, currency: str) -> StepAnalysis:
    active = (f"steps.{step.id}.active_time", step.active_time)
    wait = (f"steps.{step.id}.waiting_time", step.waiting_time)
    people = (f"steps.{step.id}.people", step.people)
    rate = (f"steps.{step.id}.hourly_labor_cost", step.hourly_labor_cost)
    return StepAnalysis(
        step_id=step.id, name=step.name,
        active_minutes=_metric((active,), "minutes", "active_minutes", lambda v: v[0]),
        waiting_minutes=_metric((wait,), "minutes", "waiting_minutes", lambda v: v[0]),
        elapsed_minutes=_metric(
            (active, wait), "minutes", "active_minutes + waiting_minutes", lambda v: v[0] + v[1],
        ),
        labor_minutes=_metric(
            (active, people), "person-minutes", "active_minutes * people", lambda v: v[0] * v[1],
        ),
        labor_cost=_metric(
            (active, people, rate), f"{currency}/case", COST_FORMULA,
            lambda v: (v[0] * v[1] * v[2] / Decimal(60)).quantize(CENT, rounding=ROUND_HALF_UP),
        ),
    )


def _total(metrics: tuple[AnalysisMetric, ...], unit: str, formula: str) -> AnalysisMetric:
    known_values = [metric.value for metric in metrics if metric.value is not None]
    gaps = _unique(gap for metric in metrics for gap in metric.blocked_by)
    subtotal = sum(known_values, ZERO) if known_values else None
    return AnalysisMetric(
        value=None if gaps else subtotal, unit=unit, formula=formula,
        input_paths=_unique(path for metric in metrics for path in metric.input_paths),
        evidence=_unique(item for metric in metrics for item in metric.evidence),
        blocked_by=gaps, known_subtotal=subtotal if gaps else None,
    )


def _monthly_cost(cost: AnalysisMetric, workflow: Workflow) -> AnalysisMetric:
    volume = workflow.monthly_volume
    volume_gap = _gap("monthly_volume", volume)
    gaps = cost.blocked_by + ((volume_gap,) if volume_gap else ())
    value = None
    if not gaps:
        value = (cost.value * Decimal(volume.value)).quantize(CENT, rounding=ROUND_HALF_UP)
    volume_evidence = volume.evidence if volume_gap is None else ()
    return AnalysisMetric(
        value=value, unit=f"{workflow.currency}/month",
        formula="sum(rounded step labor costs) * confirmed monthly case volume",
        input_paths=cost.input_paths + ("monthly_volume",),
        evidence=_unique((*cost.evidence, *volume_evidence)), blocked_by=gaps,
    )


def _ranking(steps: tuple[StepAnalysis, ...], attribute: str, unit: str) -> BottleneckRanking:
    metrics = [(step.step_id, getattr(step, attribute)) for step in steps]
    gaps = _unique(gap for _, metric in metrics for gap in metric.blocked_by)
    available = [(step_id, metric) for step_id, metric in metrics
                 if metric.value is not None and metric.value > ZERO]
    # Python's stable sort preserves process order when values tie.
    available.sort(key=lambda pair: pair[1].value, reverse=True)
    entries = []
    previous = None
    rank = 0
    for step_id, metric in available:
        if metric.value != previous:
            rank += 1
        entries.append(RankedContribution(
            step_id=step_id, rank=rank, value=metric.value,
            input_paths=metric.input_paths, evidence=metric.evidence,
        ))
        previous = metric.value
    basis = "waiting time" if attribute == "waiting_minutes" else "labor effort"
    scope = "Partial comparison of confirmed steps." if gaps else "All steps have confirmed inputs."
    return BottleneckRanking(
        description=f"Potential bottleneck contributors ranked by {basis}. {scope} "
                    "This does not prove a capacity constraint or its cause.",
        unit=unit, complete=not gaps, entries=tuple(entries), blocked_by=gaps,
    )


def _working_precision(workflow: Workflow) -> int:
    """Allow exact products/sums even when inputs exceed normal decimal precision.

    Reserve the digits and decimal places of all inputs plus headroom for division
    and cent rounding. This avoids inheriting the caller's arithmetic context.
    """
    digits = 0
    for step in workflow.steps:
        for fact in (step.active_time, step.waiting_time, step.people, step.hourly_labor_cost):
            if fact.value is not None:
                value = Decimal(fact.value)
                parts = value.as_tuple()
                digits += len(parts.digits) + abs(parts.exponent)
    if workflow.monthly_volume.value is not None:
        digits += len(str(workflow.monthly_volume.value))
    return max(28, digits + len(str(len(workflow.steps))) + 10)


def analyze_workflow(workflow: Workflow) -> WorkflowAnalysis:
    """Return fresh deterministic results, using only reviewed numeric inputs.

    Revalidation catches invalid edits made through unvalidated model_copy calls.
    The sequential elapsed-time model includes recorded waits before each step.
    """
    workflow = Workflow.model_validate(workflow.model_dump(mode="python"))
    context = Context(prec=_working_precision(workflow), rounding=ROUND_HALF_UP)
    with localcontext(context):
        steps = tuple(_step_analysis(step, workflow.currency) for step in workflow.steps)
        active = _total(tuple(s.active_minutes for s in steps), "minutes", "sum(step active_minutes)")
        waiting = _total(tuple(s.waiting_minutes for s in steps), "minutes", "sum(step waiting_minutes)")
        elapsed = _total(tuple(s.elapsed_minutes for s in steps), "minutes", "sum(step elapsed_minutes)")
        labor = _total(tuple(s.labor_minutes for s in steps), "person-minutes", "sum(step labor_minutes)")
        cost = _total(tuple(s.labor_cost for s in steps), f"{workflow.currency}/case", "sum(rounded step labor costs)")
        return WorkflowAnalysis(
            workflow_name=workflow.name, currency=workflow.currency, data_kind=workflow.data_kind,
            steps=steps, total_active_minutes=active, total_waiting_minutes=waiting,
            total_elapsed_minutes=elapsed, total_labor_minutes=labor, labor_cost_per_case=cost,
            monthly_labor_cost=_monthly_cost(cost, workflow),
            waiting_ranking=_ranking(steps, "waiting_minutes", "minutes"),
            labor_ranking=_ranking(steps, "labor_minutes", "person-minutes"),
        )
