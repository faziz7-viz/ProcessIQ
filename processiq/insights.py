"""Small, deterministic presentation insights derived from calculated facts."""

from dataclasses import dataclass
from decimal import Context, Decimal, ROUND_HALF_UP, localcontext
from typing import Iterable, Literal

from processiq.models import AnalysisMetric, BlockedFact, WorkflowAnalysis


def decimal_text(value: Decimal) -> str:
    text = format(value, ",f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _precision(*values: Decimal) -> int:
    return max(28, sum(len(v.as_tuple().digits) + abs(v.as_tuple().exponent) for v in values) + 10)


def metric_share(numerator: AnalysisMetric, denominator: AnalysisMetric) -> Decimal | None:
    """A one-decimal percentage, only for complete, nonzero whole totals."""
    if (numerator.value is None or denominator.value is None or numerator.blocked_by
            or denominator.blocked_by or denominator.value <= 0
            or numerator.value > denominator.value):
        return None
    with localcontext(Context(prec=_precision(numerator.value, denominator.value), rounding=ROUND_HALF_UP)):
        return (numerator.value / denominator.value * 100).quantize(Decimal("0.1"))


def human_duration(minutes: Decimal | None) -> str:
    """Compact exact elapsed duration; a day is 24 hours, never a workday."""
    if minutes is None:
        return "Unavailable"
    with localcontext(Context(prec=_precision(minutes), rounding=ROUND_HALF_UP)):
        days, remainder = divmod(minutes, Decimal(1440))
        hours, remainder = divmod(remainder, Decimal(60))
        parts = []
        if days:
            parts.append(f"{decimal_text(days)}d")
        if hours:
            parts.append(f"{decimal_text(hours)}h")
        if remainder or not parts:
            parts.append(f"{decimal_text(remainder)}m")
        return " ".join(parts)


@dataclass(frozen=True)
class HeroInsight:
    title: str
    description: str


def hero_insight(analysis: WorkflowAnalysis) -> HeroInsight:
    share = metric_share(analysis.total_waiting_minutes, analysis.total_elapsed_minutes)
    if share is not None:
        if analysis.total_waiting_minutes.value == 0:
            title = "Every recorded minute is active work."
        else:
            title = f"{share.quantize(Decimal('1'), rounding=ROUND_HALF_UP)}% of elapsed time is waiting."
        return HeroInsight(
            title,
            f"{decimal_text(analysis.total_waiting_minutes.value)} of "
            f"{decimal_text(analysis.total_elapsed_minutes.value)} elapsed minutes are waiting before work "
            "on a step. Recorded waits can include nights and weekends.",
        )
    if analysis.total_elapsed_minutes.value == 0:
        return HeroInsight("No elapsed time is recorded.",
                           "All step durations are confirmed at zero. Check that this represents a typical case.")
    return HeroInsight(
        "Your process picture is taking shape.",
        "Some time inputs still need attention. Explore the confirmed steps below, then complete "
        "the missing facts to compare the whole process.",
    )


def ranking_insight(analysis: WorkflowAnalysis, lens: Literal["waiting", "labor"]) -> str:
    ranking = analysis.waiting_ranking if lens == "waiting" else analysis.labor_ranking
    basis = "waiting time" if lens == "waiting" else "labor effort"
    scope = " among confirmed steps" if not ranking.complete else ""
    if not ranking.entries:
        if ranking.complete:
            return f"No positive {basis} is recorded."
        return f"No positive {basis} is available among confirmed steps yet."
    top = [entry for entry in ranking.entries if entry.rank == 1]
    names = {step.step_id: step.name for step in analysis.steps}
    displayed = [names[entry.step_id] for entry in top[:3]]
    subject = ", ".join(displayed)
    if len(top) > 3:
        subject += f" and {len(top) - 3} more steps"
    value = decimal_text(top[0].value)
    unit = "minutes" if lens == "waiting" else "person-minutes"
    if len(top) > 1:
        return f"{subject} are tied for the most {basis}{scope}: {value} {unit} each."
    return f"{subject} has the most {basis}{scope}: {value} {unit}."


def blocker_labels(blockers: Iterable[BlockedFact], analysis: WorkflowAnalysis) -> list[str]:
    """Translate engine paths without hiding the distinction between gap types."""
    names = {step.step_id: f"{number}. {step.name}" for number, step in enumerate(analysis.steps, 1)}
    fields = {"active_time": "Active time", "waiting_time": "Waiting time", "people": "People working",
              "hourly_labor_cost": "Hourly labor cost", "monthly_volume": "Monthly case volume"}
    labels = []
    for blocker in dict.fromkeys(blockers):
        parts = blocker.path.split(".")
        field = fields.get(parts[-1], parts[-1].replace("_", " ").capitalize())
        step = f"{names.get(parts[1], 'Step')} · " if len(parts) == 3 and parts[0] == "steps" else ""
        status = "Missing" if blocker.reason == "missing" else "Needs confirmation"
        labels.append(f"{step}{field} — {status}")
    return labels
