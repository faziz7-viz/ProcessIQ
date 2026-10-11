"""Validated input contract. No financial calculations or LLM calls live here.

JSON clients send decimal quantities as strings so financial inputs never pass
through binary floating point. Owner review establishes confirmation; validation
checks structure and source traceability, not the truth of the owner's statement.
"""

from decimal import Decimal
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    StringConstraints,
    model_validator,
)


# Preserve evidence text exactly while rejecting empty or whitespace-only labels.
def _nonblank(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("must be a nonblank string")
    return value


def _exact_decimal(value: object) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError("use a decimal string or integer; floats and booleans are not accepted")
    try:
        result = Decimal(value)
    except ArithmeticError as exc:
        raise ValueError("must be a valid decimal number") from exc
    if not result.is_finite():
        raise ValueError("must be finite")
    return result


NonBlank = Annotated[str, BeforeValidator(_nonblank)]
Identifier = Annotated[
    str, StringConstraints(strict=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
]
NonNegativeDecimal = Annotated[
    Decimal,
    BeforeValidator(_exact_decimal, json_schema_input_type=str | int),
    Field(ge=0, allow_inf_nan=False)
]
NonNegativeInteger = Annotated[int, Field(strict=True, ge=0)]
PositiveInteger = Annotated[int, Field(strict=True, ge=1)]
ValueType = TypeVar("ValueType")


class ContractModel(BaseModel):
    """Reject unexpected fields and require edits to pass through validation."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class Evidence(ContractModel):
    """A verbatim substring of an owner message, not an AI-created explanation."""

    message_id: Identifier
    quote: NonBlank


class SourceMessage(ContractModel):
    """Owner input, including synthetic owner input in demo fixtures."""

    id: Identifier
    speaker: Literal["owner"] = "owner"
    text: NonBlank


class Fact(ContractModel, Generic[ValueType]):
    """A known or unknown value with independent source and review information."""

    value: ValueType | None = None
    evidence: tuple[Evidence, ...] = ()
    confirmed: StrictBool = False

    @model_validator(mode="after")
    def validate_evidence_and_confirmation(self) -> "Fact[ValueType]":
        if self.value is not None and not self.evidence:
            raise ValueError("a known value requires evidence, including explicit zero")
        if self.value is None and self.confirmed:
            raise ValueError("an unknown value cannot be confirmed")
        return self


class DurationFact(Fact[NonNegativeDecimal]):
    """Active or waiting duration for one representative case."""

    unit: Literal["minutes"] = "minutes"


class HourlyRateFact(Fact[NonNegativeDecimal]):
    """Hourly labor cost per person in the workflow's declared currency."""

    unit: Literal["currency/hour"] = "currency/hour"


class PeopleFact(Fact[PositiveInteger]):
    """People actively working on a step; zero workers is not a valid count."""

    unit: Literal["people"] = "people"


class MonthlyVolumeFact(Fact[NonNegativeInteger]):
    """Cases per month. Zero cases is a meaningful known value."""

    unit: Literal["cases/month"] = "cases/month"


class WorkflowStep(ContractModel):
    """One step on the sequential path, with unknown numeric facts by default."""

    id: Identifier
    order: PositiveInteger
    name: NonBlank
    responsible_role: NonBlank | None = None
    active_time: DurationFact = Field(default_factory=DurationFact)
    waiting_time: DurationFact = Field(
        default_factory=DurationFact,
        description="Elapsed waiting before work on this step, inside process boundaries, in minutes.",
    )
    people: PeopleFact = Field(default_factory=PeopleFact)
    hourly_labor_cost: HourlyRateFact = Field(default_factory=HourlyRateFact)


class Workflow(ContractModel):
    """A draft or reviewed sequential process; incomplete drafts are valid."""

    name: NonBlank
    start_point: NonBlank
    end_point: NonBlank
    currency: Literal["USD"] = "USD"
    data_kind: Literal["synthetic", "owner_provided"]
    source_messages: tuple[SourceMessage, ...] = Field(min_length=1)
    monthly_volume: MonthlyVolumeFact = Field(default_factory=MonthlyVolumeFact)
    steps: tuple[WorkflowStep, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_sequence_and_sources(self) -> "Workflow":
        source_by_id = {message.id: message for message in self.source_messages}
        if len(source_by_id) != len(self.source_messages):
            raise ValueError("source message IDs must be unique")
        if len({step.id for step in self.steps}) != len(self.steps):
            raise ValueError("step IDs must be unique")
        if [step.order for step in self.steps] != list(range(1, len(self.steps) + 1)):
            raise ValueError("steps must be in order starting at 1 with no gaps")

        facts = [self.monthly_volume]
        for step in self.steps:
            facts.extend((step.active_time, step.waiting_time, step.people, step.hourly_labor_cost))
        for fact in facts:
            for evidence in fact.evidence:
                source = source_by_id.get(evidence.message_id)
                if source is None or evidence.quote not in source.text:
                    raise ValueError(
                        f"evidence must quote an existing owner message: {evidence.message_id}"
                    )
        return self


class BlockedFact(ContractModel):
    """An input that prevents a calculation, located by stable step ID."""

    path: NonBlank
    reason: Literal["missing", "unconfirmed"]


class AnalysisMetric(ContractModel):
    """A calculated quantity, or an unavailable total with explicit blockers.

    known_subtotal covers fully calculable steps only, never an estimated total.
    A complete metric has no subtotal because its value already is the total.
    """

    value: NonNegativeDecimal | None
    unit: NonBlank
    formula: NonBlank
    input_paths: tuple[str, ...]
    evidence: tuple[Evidence, ...] = ()
    blocked_by: tuple[BlockedFact, ...] = ()
    known_subtotal: NonNegativeDecimal | None = None


class StepAnalysis(ContractModel):
    step_id: Identifier
    name: NonBlank
    active_minutes: AnalysisMetric
    waiting_minutes: AnalysisMetric
    elapsed_minutes: AnalysisMetric
    labor_minutes: AnalysisMetric
    labor_cost: AnalysisMetric


class RankedContribution(ContractModel):
    """One positive contributor; tied values have the same dense rank."""

    step_id: Identifier
    rank: PositiveInteger
    value: NonNegativeDecimal
    input_paths: tuple[str, ...]
    evidence: tuple[Evidence, ...]


class BottleneckRanking(ContractModel):
    """An indicator of potential bottlenecks, not proof of a capacity limit."""

    description: NonBlank
    unit: NonBlank
    complete: StrictBool
    entries: tuple[RankedContribution, ...]
    blocked_by: tuple[BlockedFact, ...]


class WorkflowAnalysis(ContractModel):
    workflow_name: NonBlank
    currency: Literal["USD"]
    data_kind: Literal["synthetic", "owner_provided"]
    steps: tuple[StepAnalysis, ...]
    total_active_minutes: AnalysisMetric
    total_waiting_minutes: AnalysisMetric
    total_elapsed_minutes: AnalysisMetric
    total_labor_minutes: AnalysisMetric
    labor_cost_per_case: AnalysisMetric
    monthly_labor_cost: AnalysisMetric
    waiting_ranking: BottleneckRanking
    labor_ranking: BottleneckRanking
