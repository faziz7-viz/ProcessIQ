"""Apply owner review to the input contract without inventing or calculating facts."""

from decimal import Decimal, InvalidOperation
import re

from processiq.models import Workflow

FACT_FIELDS = ("active_time", "waiting_time", "people", "hourly_labor_cost")


def review_values(workflow: Workflow) -> dict[str, str]:
    values = {field: getattr(workflow, field) for field in ("name", "start_point", "end_point")}
    values["monthly_volume"] = "" if workflow.monthly_volume.value is None else str(workflow.monthly_volume.value)
    for step in workflow.steps:
        prefix = f"steps.{step.id}."
        values[prefix + "name"] = step.name
        values[prefix + "responsible_role"] = step.responsible_role or ""
        for field in FACT_FIELDS:
            value = getattr(step, field).value
            values[prefix + field] = "" if value is None else str(value)
    return values


def review_confirmations(workflow: Workflow) -> dict[str, bool]:
    flags = {"monthly_volume": workflow.monthly_volume.confirmed}
    for step in workflow.steps:
        for field in FACT_FIELDS:
            flags[f"steps.{step.id}.{field}"] = getattr(step, field).confirmed
    return flags


def _parse(text: str, integer: bool):
    text = text.strip()
    if not text:
        return None
    if integer:
        if not re.fullmatch(r"-?[0-9]+", text):
            raise ValueError("Counts must be whole integers (for example 2); leave unknown values blank.")
        return int(text)
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("Enter a decimal number (for example 30.00), or leave unknown values blank.") from exc
    if not value.is_finite():
        raise ValueError("Numbers must be finite; NaN and infinity are not allowed.")
    return value


def apply_review(
    workflow: Workflow,
    values: dict[str, str],
    confirmations: dict[str, bool] | None = None,
    *,
    confirm_all: bool = False,
) -> Workflow:
    """Apply edits atomically and validate before replacing the stored draft.

    New numeric values get genuine owner-review evidence. Unchanged values keep
    their original evidence. A changed value defaults to unconfirmed unless the
    owner explicitly confirms it in this review action.
    """
    confirmations = confirmations or {}
    allowed = review_values(workflow)
    if values.keys() - allowed.keys() or confirmations.keys() - review_confirmations(workflow).keys():
        raise ValueError("Review contains an unknown field.")
    raw = workflow.model_dump(mode="python")
    for field in ("name", "start_point", "end_point"):
        if field in values:
            raw[field] = values[field].strip()
    ids = {message.id for message in workflow.source_messages}
    number = len(ids) + 1
    while f"owner-review-{number}" in ids:
        number += 1
    message_id = f"owner-review-{number}"
    quotes = []

    def update_fact(path, old, target, integer=False):
        value = _parse(values[path], integer) if path in values else old.value
        changed = value != old.value
        target["value"] = value
        confirmed = confirmations.get(path, False if changed else old.confirmed)
        target["confirmed"] = (value is not None) if confirm_all else confirmed
        if changed:
            display = "not provided" if value is None else f"{value} {old.unit}"
            quote = f"Owner review of {path}: {display}."
            quotes.append(quote)
            target["evidence"] = ({"message_id": message_id, "quote": quote},)

    update_fact("monthly_volume", workflow.monthly_volume, raw["monthly_volume"], integer=True)
    for index, step in enumerate(workflow.steps):
        target = raw["steps"][index]
        for field in ("name", "responsible_role"):
            path = f"steps.{step.id}.{field}"
            if path in values:
                text = values[path].strip()
                target[field] = (text or None) if field == "responsible_role" else text
        for field in FACT_FIELDS:
            update_fact(f"steps.{step.id}.{field}", getattr(step, field), target[field], integer=field == "people")
    if quotes:
        raw["source_messages"] += ({"id": message_id, "speaker": "owner", "text": "\n".join(quotes)},)
    return Workflow.model_validate(raw)
