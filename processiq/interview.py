"""Controlled interview loop with application-owned sources and unconfirmed drafts."""

from dataclasses import dataclass
from decimal import Decimal
import re
from typing import Protocol

from pydantic import ValidationError

from processiq.llm import InterviewError, InterviewOutput
from processiq.models import SourceMessage, Workflow

MAX_TURNS = 30
FIRST_QUESTION = "Walk me through your typical workday."
MAX_MESSAGE_CHARS = 12000
FACT_FIELDS = ("active_time", "people", "hourly_labor_cost", "waiting_time")


class InterviewClient(Protocol):
    def extract(self, *, sources, previous, missing, skipped): ...


@dataclass(frozen=True)
class InterviewSession:
    sources: tuple[SourceMessage, ...] = ()
    questions: tuple[str | None, ...] = ()
    workflow: Workflow | None = None
    question: str | None = None
    target: str | None = None
    skipped: tuple[str, ...] = ()
    checkpoints: tuple["InterviewSession", ...] = ()


def missing_fields(workflow: Workflow | None) -> list[str]:
    if workflow is None:
        return ["process_details"]
    missing = []
    for step in workflow.steps:
        for field in FACT_FIELDS:
            if getattr(step, field).value is None:
                missing.append(f"steps.{step.id}.{field}")
    if workflow.monthly_volume.value is None:
        missing.append("monthly_volume")
    return missing


def _quoted_numbers(quote: str, source: str) -> list[Decimal]:
    """Only complete numeric tokens inside an actual occurrence of the quote."""
    numbers = []
    offset = source.find(quote)
    while offset >= 0:
        for match in re.finditer(r"(?<![\w.])-?\d+(?:,\d{3})*(?:\.\d+)?(?!\w|\.\d)", source):
            if offset <= match.start() and match.end() <= offset + len(quote):
                numbers.append(Decimal(match.group().replace(",", "")))
        offset = source.find(quote, offset + 1)
    return numbers


def _supported_number(value, evidence, source_by_id, unit):
    """Conservative lexical support; semantic accuracy remains owner-reviewed."""
    for item in evidence:
        source = source_by_id.get(item["message_id"])
        if source is None or not item["quote"].strip() or item["quote"] not in source.text:
            raise ValueError("Source quote is not present in the owner's recorded messages")
    if value is None:
        return
    numeric = Decimal(str(value))
    numbers = [number for item in evidence
               for number in _quoted_numbers(item["quote"], source_by_id[item["message_id"]].text)]
    if not numeric.is_finite() or numeric not in numbers:
        raise ValueError("Extracted number is not explicitly supported by its owner quote")
    quotes = [item["quote"] for item in evidence]
    if unit == "minutes":
        tokens = [match for quote in quotes for match in re.findall(
            r"(-?\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:(?:active|elapsed|waiting|working)\s+)?(?:minutes?|mins?)\b",
            quote, flags=re.IGNORECASE,
        )]
        supported = numeric in [Decimal(token.replace(",", "")) for token in tokens]
    elif unit == "currency/hour":
        supported = any(re.search(r"\b(?:hours?|hourly)\b|/hr?\b", quote, re.IGNORECASE)
                        and re.search(r"\bUSD\b|\bdollars?\b|\$", quote, re.IGNORECASE)
                        and not re.search(r"[€£¥]|\b(?:EUR|GBP|CAD|AUD|INR)\b", quote, re.IGNORECASE)
                        for quote in quotes)
    elif unit == "people":
        supported = any(re.search(r"\b(?:people|persons?|workers?|staff|employees?|crew)\b", quote, re.IGNORECASE) for quote in quotes)
    else:
        supported = any(re.search(r"\bmonths?\b", quote, re.IGNORECASE) for quote in quotes)
    if not supported:
        raise ValueError("Owner quotes do not explicitly support the required units")


def _workflow(extracted, sources) -> Workflow:
    raw = extracted.model_dump()
    source_by_id = {source.id: source for source in sources}
    facts = [raw["monthly_volume"]]
    for order, step in enumerate(raw["steps"], start=1):
        step["order"] = order
        facts.extend(step[field] for field in FACT_FIELDS)
    for fact in facts:
        _supported_number(fact["value"], fact["evidence"], source_by_id, fact["unit"])
        fact["confirmed"] = False
    raw.update(currency="USD", data_kind="owner_provided", source_messages=sources)
    return Workflow.model_validate(raw)


def rewind_interview(state: InterviewSession) -> InterviewSession:
    """Restore the state before the latest answer; dependent facts disappear."""
    if not state.checkpoints:
        return InterviewSession()
    return state.checkpoints[-1]


def _question_key(question: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", question.lower()).strip()


def advance_interview(state: InterviewSession, answer: str, client: InterviewClient) -> InterviewSession:
    """Apply one successful turn atomically. Failed requests leave state untouched."""
    if len(state.sources) >= MAX_TURNS:
        raise InterviewError("The interview turn limit has been reached. Review the draft or start a new interview.")
    if not answer.strip() or len(answer) > MAX_MESSAGE_CHARS:
        raise InterviewError(f"Enter an answer between 1 and {MAX_MESSAGE_CHARS} characters.")
    sources = state.sources + (SourceMessage(id=f"owner-{len(state.sources) + 1}", text=answer),)
    skipped = state.skipped
    normalized = answer.strip().lower().replace("’", "'").rstrip(".!?")
    if normalized in {"i don't know", "i dont know", "unknown", "skip", "not sure"} and state.target and state.target != "process_details":
        skipped = tuple(dict.fromkeys((*skipped, state.target)))
    try:
        kwargs = dict(sources=sources, previous=state.workflow,
                      missing=missing_fields(state.workflow), skipped=skipped)
        if hasattr(client, "extract_with_context"):
            result = client.extract_with_context(**kwargs, questions=(FIRST_QUESTION, *state.questions))
        else:
            result = client.extract(**kwargs)
        if not isinstance(result, InterviewOutput):
            result = InterviewOutput.model_validate(result)
        workflow = _workflow(result.workflow, sources) if result.workflow else None
        if workflow is None and state.workflow is not None:
            # A vague answer must not erase a valid partial assessment.
            workflow = Workflow.model_validate({**state.workflow.model_dump(mode="python"), "source_messages": sources})
        proposed_target = result.target
        # Models sometimes use a JSON array path instead of the stable step ID.
        # Resolve only a valid zero-based position, then apply all normal guards.
        indexed = re.fullmatch(r"steps\[(\d+)\]\.(active_time|waiting_time|people|hourly_labor_cost)", proposed_target or "")
        if indexed and workflow and int(indexed[1]) < len(workflow.steps):
            proposed_target = f"steps.{workflow.steps[int(indexed[1])].id}.{indexed[2]}"
        valid_targets = {"process_details", "monthly_volume"}
        if workflow:
            valid_targets.update(f"steps.{step.id}.{field}" for step in workflow.steps for field in FACT_FIELDS)
        proposed = result.question.strip() if result.question else ""
        if proposed.count("?") + proposed.count("？") > 1 or len(proposed) > 240:
            raise InterviewError("The AI asked too much at once. Your answer is still here; try again or review your draft.")
        asked = {_question_key(q) for q in (FIRST_QUESTION, *state.questions) if q}
        known_unchanged = False
        if workflow and proposed_target in valid_targets and proposed_target.startswith("steps."):
            _, step_id, field = proposed_target.split(".", 2)
            step = next((step for step in workflow.steps if step.id == step_id), None)
            if step and field in FACT_FIELDS:
                known_unchanged = getattr(step, field).value is not None
        if workflow and proposed_target == "monthly_volume":
            known_unchanged = workflow.monthly_volume.value is not None
        # Clarifying a fact's meaning is distinct from requesting its value again.
        meaning_check = bool(re.search(r"\b(?:or|mean|meaning|includes?|inside|outside|billing|currency)\b", proposed, re.IGNORECASE))
        known_unchanged = known_unchanged and not meaning_check
        clarification = (proposed and proposed_target in valid_targets
                         and proposed_target not in skipped and _question_key(proposed) not in asked
                         and not known_unchanged)
        if not clarification and workflow is None and len(sources) < MAX_TURNS:
            raise InterviewError("The AI did not find a useful next question. Your answer is still here; try again or go back to revise it.")
        target, question = None, None
        if len(sources) < MAX_TURNS and clarification:
            target, question = proposed_target, proposed
        return InterviewSession(sources=sources, questions=state.questions + (question,),
                                workflow=workflow, question=question, target=target, skipped=skipped,
                                checkpoints=(*state.checkpoints, state))
    except InterviewError:
        raise
    except (ValidationError, ValueError, TypeError, ArithmeticError):
        raise InterviewError("The AI draft contained invalid or unsupported facts. Your previous draft was preserved; try again or review it.") from None
