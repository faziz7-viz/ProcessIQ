"""Isolated hypothetical reductions over reviewed analysis, never saved facts.

Evidence on a hypothetical metric describes its baseline inputs. Scenario
assumptions live separately in ScenarioResult and in calculation formulas; they
are never represented as owner statements or confirmations.
"""

from dataclasses import dataclass, fields
from decimal import Context, Decimal, ROUND_HALF_UP, localcontext

from processiq.analysis import CENT, _monthly_cost, _total, _working_precision, analyze_workflow
from processiq.models import AnalysisMetric, StepAnalysis, Workflow, WorkflowAnalysis, WorkflowStep


@dataclass(frozen=True)
class ScenarioMetrics:
    steps: tuple[StepAnalysis, ...]
    total_active_minutes: AnalysisMetric
    total_waiting_minutes: AnalysisMetric
    total_elapsed_minutes: AnalysisMetric
    total_labor_minutes: AnalysisMetric
    labor_cost_per_case: AnalysisMetric
    monthly_labor_cost: AnalysisMetric


@dataclass(frozen=True)
class ScenarioDelta:
    """Baseline minus hypothetical; None means a complete comparison is blocked."""

    total_active_minutes: Decimal | None
    total_waiting_minutes: Decimal | None
    total_elapsed_minutes: Decimal | None
    total_labor_minutes: Decimal | None
    labor_cost_per_case: Decimal | None
    monthly_labor_cost: Decimal | None


@dataclass(frozen=True)
class ScenarioResult:
    step_id: str
    active_reduction_pct: Decimal
    waiting_reduction_pct: Decimal
    baseline: WorkflowAnalysis
    hypothetical: ScenarioMetrics
    delta: ScenarioDelta


def _percentage(value: object) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError("A reduction percentage must be a decimal string, integer, or Decimal from 0 to 100.")
    try:
        percentage = Decimal(value)
    except ArithmeticError as exc:
        raise ValueError("A reduction percentage must be a valid number from 0 to 100.") from exc
    if not percentage.is_finite() or not Decimal(0) <= percentage <= Decimal(100):
        raise ValueError("A reduction percentage must be finite and from 0 to 100.")
    return percentage


def _reduce(metric: AnalysisMetric, percent: Decimal) -> AnalysisMetric:
    value = None if metric.value is None else metric.value * (1 - percent / 100)
    return metric.model_copy(update={
        "value": value,
        "formula": f"Hypothetical: ({metric.formula}) * (1 - {percent}/100)",
    })


def _changed_step(
    baseline: StepAnalysis, source: WorkflowStep, active_pct: Decimal, waiting_pct: Decimal,
) -> StepAnalysis:
    active = _reduce(baseline.active_minutes, active_pct)
    waiting = _reduce(baseline.waiting_minutes, waiting_pct)
    elapsed_value = None
    if baseline.elapsed_minutes.value is not None:
        elapsed_value = active.value + waiting.value
    cost_value = None
    if baseline.labor_cost.value is not None:
        # Recalculate the unrounded cost: scaling the rounded baseline is wrong
        # at cent boundaries. An unavailable input stays unavailable, even at 100%.
        cost_value = (
            active.value * Decimal(source.people.value) * source.hourly_labor_cost.value / 60
        ).quantize(CENT, rounding=ROUND_HALF_UP)
    return StepAnalysis(
        step_id=baseline.step_id, name=baseline.name,
        active_minutes=active, waiting_minutes=waiting,
        elapsed_minutes=baseline.elapsed_minutes.model_copy(update={
            "value": elapsed_value,
            "formula": "Hypothetical active minutes + hypothetical waiting minutes",
        }),
        labor_minutes=_reduce(baseline.labor_minutes, active_pct),
        labor_cost=baseline.labor_cost.model_copy(update={
            "value": cost_value,
            "formula": f"Hypothetical: active_minutes * (1 - {active_pct}/100) * people * hourly_labor_cost / 60; round half up to cents",
        }),
    )


def calculate_scenario(
    workflow: Workflow,
    step_id: str,
    *,
    active_reduction_pct: Decimal | str | int = 0,
    waiting_reduction_pct: Decimal | str | int = 0,
) -> ScenarioResult:
    """Compare one step's assumed reductions with the unchanged reviewed baseline.

    Complete totals and deltas require all their original inputs. Partial known
    subtotals may change, but are never extrapolated into a monthly projection.
    """
    active_pct = _percentage(active_reduction_pct)
    waiting_pct = _percentage(waiting_reduction_pct)
    workflow = Workflow.model_validate(workflow.model_dump(mode="python"))
    source = next((step for step in workflow.steps if step.id == step_id), None)
    if source is None:
        raise ValueError(f"Unknown workflow step: {step_id}")
    extra_digits = sum(len(value.as_tuple().digits) + abs(value.as_tuple().exponent) for value in (active_pct, waiting_pct))
    context = Context(prec=_working_precision(workflow) + extra_digits + 4, rounding=ROUND_HALF_UP)
    with localcontext(context):
        baseline = analyze_workflow(workflow)
        steps = tuple(
            _changed_step(step, source, active_pct, waiting_pct) if step.step_id == step_id else step
            for step in baseline.steps
        )
        total_specs = (
            ("total_active_minutes", "active_minutes", "minutes"),
            ("total_waiting_minutes", "waiting_minutes", "minutes"),
            ("total_elapsed_minutes", "elapsed_minutes", "minutes"),
            ("total_labor_minutes", "labor_minutes", "person-minutes"),
            ("labor_cost_per_case", "labor_cost", f"{workflow.currency}/case"),
        )
        totals = {
            name: _total(tuple(getattr(step, attribute) for step in steps), unit,
                         f"Hypothetical: sum(step {attribute}) after selected-step reduction")
            for name, attribute, unit in total_specs
        }
        monthly = _monthly_cost(totals["labor_cost_per_case"], workflow)
        totals["monthly_labor_cost"] = monthly.model_copy(update={
            "formula": "Hypothetical: sum(rounded hypothetical step labor costs) * unchanged confirmed monthly case volume",
        })
        hypothetical = ScenarioMetrics(steps=steps, **totals)
        deltas = {}
        for field in fields(ScenarioDelta):
            before = getattr(baseline, field.name).value
            after = getattr(hypothetical, field.name).value
            deltas[field.name] = None if before is None or after is None else before - after
        return ScenarioResult(
            step_id=step_id, active_reduction_pct=active_pct, waiting_reduction_pct=waiting_pct,
            baseline=baseline, hypothetical=hypothetical, delta=ScenarioDelta(**deltas),
        )
