"""OpenAI structured-output transport; no owner confirmation or calculations."""

import json
import os
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI
from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError

from processiq.prompts import INTERVIEW_INSTRUCTIONS, PLAN_INSTRUCTIONS

ENV_PATH = Path(__file__).resolve().parents[1] / ".env"


class InterviewError(ValueError):
    """Safe owner-facing error, never provider credentials or raw request details."""


class TransportModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Quote(TransportModel):
    message_id: str
    quote: str


class ExtractedDecimal(TransportModel):
    value: str | None
    unit: Literal["minutes", "currency/hour"]
    evidence: list[Quote]


class ExtractedCount(TransportModel):
    value: StrictInt | None
    unit: Literal["people", "cases/month"]
    evidence: list[Quote]


class ExtractedStep(TransportModel):
    id: str
    name: str
    responsible_role: str | None
    active_time: ExtractedDecimal
    waiting_time: ExtractedDecimal
    people: ExtractedCount
    hourly_labor_cost: ExtractedDecimal


class ExtractedWorkflow(TransportModel):
    name: str
    start_point: str
    end_point: str
    monthly_volume: ExtractedCount
    steps: list[ExtractedStep]


class InterviewOutput(TransportModel):
    workflow: ExtractedWorkflow | None
    question: str | None
    target: str | None


ActionCode = Literal["collect_facts", "track_wait", "check_handoff", "observe_work", "standardize_work", "review_cost", "monitor_process"]


class ActionSelection(TransportModel):
    finding_id: str
    action: ActionCode


class PlanOutput(TransportModel):
    finding_ids: list[str] = Field(min_length=1, max_length=5)
    actions: list[ActionSelection] = Field(min_length=1, max_length=3)


def load_api_configuration() -> dict[str, str]:
    """Read only this project's file without caching credentials in os.environ."""
    values = dotenv_values(ENV_PATH, interpolate=False)
    return {
        "api_key": (os.getenv("OPENAI_API_KEY") or values.get("OPENAI_API_KEY") or "").strip(),
        "model": (os.getenv("OPENAI_MODEL") or values.get("OPENAI_MODEL") or "gpt-5-mini").strip(),
    }


class StructuredOpenAI:
    def __init__(self, *, client=None, model: str | None = None):
        configuration = load_api_configuration() or {}
        self.client = client
        self.api_key = configuration.get("api_key", "")
        self.model = model or configuration.get("model") or "gpt-5-mini"

    def _parse(self, kwargs):
        try:
            if self.client is not None:
                response = self.client.responses.parse(**kwargs)
            else:
                key = self.api_key
                if not key:
                    raise InterviewError("Add OPENAI_API_KEY to ProcessIQ/.env to use the live AI interview. Synthetic demos still work.")
                with OpenAI(api_key=key, base_url="https://api.openai.com/v1", timeout=30, max_retries=1) as client:
                    response = client.responses.parse(**kwargs)
            if response.status != "completed" or response.output_parsed is None:
                raise InterviewError("The AI response was refused or incomplete. Your draft was preserved; try again or review existing facts.")
            return response.output_parsed
        except InterviewError:
            raise
        except (APITimeoutError, APIConnectionError):
            raise InterviewError("The AI service could not be reached in time. Your draft was preserved; try again.") from None
        except APIStatusError as exc:
            if exc.status_code in (401, 403):
                message = "The API key or model access was rejected. Check the project's API configuration."
            elif exc.status_code == 429:
                message = "The API usage limit was reached. Check your quota or try again later."
            else:
                message = "The AI service rejected the request. Check the model configuration or try again."
            raise InterviewError(message) from None
        except (ValidationError, ValueError, TypeError):
            raise InterviewError("The AI returned an invalid structured response. Your draft was preserved; try again.") from None


class OpenAIInterviewer(StructuredOpenAI):
    def extract_with_context(self, *, sources, previous, missing, skipped, questions):
        return self.extract(sources=sources, previous=previous, missing=missing,
                            skipped=skipped, questions=questions)

    def extract(self, *, sources, previous, missing, skipped, questions=()):
        payload = {
            "owner_messages": [source.model_dump(mode="json") for source in sources],
            "previous_draft": previous.model_dump(mode="json") if previous else None,
            "missing_fields": missing, "skipped_fields": list(skipped),
            "conversation": [{"question": questions[index] if index < len(questions) else None,
                              "answer": source.text, "message_id": source.id}
                             for index, source in enumerate(sources)],
            "asked_questions": [question for question in questions if question],
        }
        kwargs = dict(
            model=self.model,
            input=[{"role": "system", "content": INTERVIEW_INSTRUCTIONS},
                   {"role": "user", "content": json.dumps(payload)}],
            text_format=InterviewOutput, max_output_tokens=6000, store=False,
        )
        if self.model.startswith("gpt-5"):
            kwargs["reasoning"] = {"effort": "low"}
        return self._parse(kwargs)


class OpenAIPlanner(StructuredOpenAI):
    def select(self, *, catalog):
        # Import here to keep the transport schema independent of domain models.
        from processiq.recommendations import ACTIONS, LIMITATIONS

        payload = {
            "catalog": [finding.model_dump(mode="json") for finding in catalog],
            "action_templates": {code: template.model_dump() for code, template in ACTIONS.items()},
            "limitations": LIMITATIONS,
        }
        kwargs = dict(
            model=self.model,
            input=[{"role": "system", "content": PLAN_INSTRUCTIONS},
                   {"role": "user", "content": json.dumps(payload)}],
            text_format=PlanOutput, max_output_tokens=3000, store=False,
        )
        if self.model.startswith("gpt-5"):
            kwargs["reasoning"] = {"effort": "low"}
        try:
            return self._parse(kwargs)
        except InterviewError as exc:
            message = str(exc).replace("live AI interview", "live AI plan").replace("draft", "assessment")
            raise InterviewError(message) from None
