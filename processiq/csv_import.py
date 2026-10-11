"""Import one sequential workflow from CSV, without AI or inferred numbers."""

import csv
import io
from pathlib import PurePath
import re

from pydantic import ValidationError

from processiq.models import (
    DurationFact, Evidence, HourlyRateFact, MonthlyVolumeFact, PeopleFact,
    SourceMessage, Workflow, WorkflowStep,
)

MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_STEPS = 200
FACT_COLUMNS = {
    "active_minutes": ("active_time", DurationFact),
    "waiting_minutes": ("waiting_time", DurationFact),
    "people": ("people", PeopleFact),
    "hourly_rate_usd": ("hourly_labor_cost", HourlyRateFact),
}
METADATA = {"process_name", "start_point", "end_point", "monthly_volume", "currency"}
COLUMNS = {"step_name", "responsible_role", *FACT_COLUMNS, *METADATA}
ALIASES = {
    "task": "step_name", "step": "step_name",
    "role": "responsible_role", "team_members": "people",
    "cases_per_month": "monthly_volume", "hourly_rate": "hourly_rate_usd",
    "active_minutes_per_case": "active_minutes",
    "waiting_minutes_per_case": "waiting_minutes",
}


class CsvImportError(ValueError):
    """A file or cell that the owner needs to correct before importing."""


def _fact(column, raw, source_id, quote, row):
    fact_type = MonthlyVolumeFact if column == "monthly_volume" else FACT_COLUMNS[column][1]
    if not raw:
        return fact_type()
    try:
        if column in {"people", "monthly_volume"}:
            if not re.fullmatch(r"[0-9]+", raw):
                raise ValueError("use a whole number (no decimals or units)")
            value = int(raw)
        else:
            value = raw
        return fact_type(value=value, evidence=(Evidence(message_id=source_id, quote=quote),))
    except (ValidationError, ValueError) as exc:
        detail = exc.errors(include_url=False)[0]["msg"] if isinstance(exc, ValidationError) else str(exc)
        raise CsvImportError(f"CSV row {row}, {column}: {detail}.") from exc


def parse_workflow_csv(data: bytes, *, filename: str = "workflow.csv") -> Workflow:
    """Blank cells are unknown. Every known numeric fact retains its source row."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise CsvImportError("Upload a CSV no larger than 2 MB.")
    try:
        contents = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvImportError("Save the file as CSV UTF-8, then upload it again.") from exc
    if not contents.strip():
        raise CsvImportError("The CSV is empty. Add a header and at least one step.")
    reader = csv.reader(io.StringIO(contents, newline=""), strict=True)
    try:
        headers = next(reader)
        normalized = [re.sub(r"[^a-z0-9]+", "_", header.strip().lower()).strip("_") for header in headers]
        columns = [ALIASES.get(name, name) for name in normalized]
        if len(set(columns)) != len(columns):
            raise CsvImportError("Duplicate CSV columns. Keep one column for each field.")
        if "step_name" not in columns:
            raise CsvImportError("Include a step_name column (Task and Step name also work).")
        unsupported = set(columns) - COLUMNS
        if unsupported:
            raise CsvImportError(f"Unsupported CSV columns: {', '.join(sorted(unsupported))}. Use the template headers; units are minutes, USD per hour, and cases per month.")

        sources, steps, metadata = [], [], {}
        monthly_volume = MonthlyVolumeFact()
        display_name = PurePath(filename).name
        while True:
            row_number = reader.line_num + 1
            row = next(reader, None)
            if row is None:
                break
            if not any(cell.strip() for cell in row):
                continue
            if len(row) != len(columns):
                raise CsvImportError(f"CSV row {row_number}: expected {len(columns)} cells, found {len(row)}. Quote text containing commas.")
            if len(steps) >= MAX_STEPS:
                raise CsvImportError("Upload one workflow with no more than 200 steps.")
            cells = dict(zip(columns, (cell.strip() for cell in row), strict=True))
            if not cells["step_name"]:
                raise CsvImportError(f"CSV row {row_number}, step_name: enter a step name.")
            source_id = f"csv-row-{row_number}"
            quotes = {column: f"{header}: {raw}" for column, header, raw in zip(columns, headers, row, strict=True)}
            sources.append(SourceMessage(id=source_id, text=f"CSV row {row_number}, file {display_name}:\n" + "\n".join(quotes.values())))
            facts = {
                field: _fact(column, cells.get(column, ""), source_id, quotes.get(column, ""), row_number)
                for column, (field, _) in FACT_COLUMNS.items()
            }
            for column in METADATA:
                value = cells.get(column, "")
                if not value:
                    continue
                if column == "currency" and value != "USD":
                    raise CsvImportError(f"CSV row {row_number}, currency: only USD is supported.")
                if column == "monthly_volume":
                    candidate = _fact(column, value, source_id, quotes[column], row_number)
                    value = candidate.value
                if column in metadata and metadata[column] != value:
                    raise CsvImportError(f"CSV row {row_number}, {column}: use the same value for the whole workflow, or leave later rows blank.")
                if column == "monthly_volume" and column not in metadata:
                    monthly_volume = candidate
                metadata[column] = value
            steps.append(WorkflowStep(
                id=f"csv-step-{len(steps) + 1}", order=len(steps) + 1,
                name=cells["step_name"], responsible_role=cells.get("responsible_role") or None,
                **facts,
            ))
    except csv.Error as exc:
        raise CsvImportError(f"Invalid CSV near row {reader.line_num}: check quotes and comma separators.") from exc
    if not steps:
        raise CsvImportError("Add at least one step below the CSV header.")
    # These editable scope labels describe row order, never invented business facts.
    return Workflow(
        name=metadata.get("process_name") or re.sub(r"[_-]+", " ", PurePath(display_name).stem).strip() or "Uploaded workflow",
        start_point=metadata.get("start_point") or f"Start of {steps[0].name}",
        end_point=metadata.get("end_point") or f"Completion of {steps[-1].name}",
        data_kind="owner_provided", source_messages=tuple(sources),
        monthly_volume=monthly_volume, steps=tuple(steps),
    )
