"""CSV input must keep exact values, missingness, and row-level evidence."""

from decimal import Decimal
from importlib import import_module

import pytest

from processiq.analysis import analyze_workflow
from processiq.assessment import apply_review

CSV = b"""step_name,responsible_role,active_minutes,waiting_minutes,people,hourly_rate_usd,monthly_volume
Review request,Coordinator,10,0,1,30,20
Prepare quote,Estimator,30,60,1,60,20
Email quote,Coordinator,5,0,1,30,20
"""


def parse(data=CSV, filename="painting_quotes.csv"):
    return import_module("processiq.csv_import").parse_workflow_csv(data, filename=filename)


def test_upload_produces_unconfirmed_exact_facts_with_csv_evidence():
    workflow = parse()
    assert workflow.name == "painting quotes"
    assert [step.name for step in workflow.steps] == ["Review request", "Prepare quote", "Email quote"]
    assert workflow.steps[0].active_time.value == Decimal("10")
    assert workflow.steps[0].waiting_time.value == Decimal("0")
    assert workflow.monthly_volume.value == 20
    assert workflow.data_kind == "owner_provided"
    assert analyze_workflow(workflow).labor_cost_per_case.value is None
    for fact in [workflow.monthly_volume, *(getattr(step, field) for step in workflow.steps
                 for field in ("active_time", "waiting_time", "people", "hourly_labor_cost"))]:
        assert not fact.confirmed
        for evidence in fact.evidence:
            source = next(source for source in workflow.source_messages if source.id == evidence.message_id)
            assert evidence.quote in source.text
            assert "CSV row" in source.text
    confirmed = apply_review(workflow, {}, confirm_all=True)
    analysis = analyze_workflow(confirmed)
    assert analysis.labor_cost_per_case.value == Decimal("37.50")
    assert analysis.monthly_labor_cost.value == Decimal("750.00")
    assert analysis.total_elapsed_minutes.value == Decimal("105")


def test_blank_and_omitted_columns_stay_unknown_but_explicit_zero_is_preserved():
    workflow = parse(b"step_name,active_minutes,waiting_minutes,hourly_rate_usd,monthly_volume\nReceive,,0,0,0\n")
    step = workflow.steps[0]
    assert step.active_time.value is None
    assert step.people.value is None
    assert step.waiting_time.value == Decimal("0")
    assert step.hourly_labor_cost.value == Decimal("0")
    assert workflow.monthly_volume.value == 0
    assert step.waiting_time.evidence


def test_familiar_headers_bom_quoted_names_and_exact_decimals():
    data = '\ufeffTask,Active minutes,Waiting minutes,Team members,Hourly rate (USD),Cases per month\r\n"Review, then log",10.25,0,1,30.10,20\r\n'.encode()
    step = parse(data).steps[0]
    assert step.name == "Review, then log"
    assert step.active_time.value == Decimal("10.25")
    assert step.hourly_labor_cost.value == Decimal("30.10")


def test_optional_process_metadata_is_read_and_volume_need_only_appear_once():
    workflow = parse(b"step_name,process_name,start_point,end_point,monthly_volume,currency\nReceive,Quoting,Email arrives,Quote sent,20,USD\nSend,,,,,\n")
    assert (workflow.name, workflow.start_point, workflow.end_point) == ("Quoting", "Email arrives", "Quote sent")
    assert workflow.monthly_volume.value == 20


@pytest.mark.parametrize("column,value", [
    ("active_minutes", "-1"), ("active_minutes", "NaN"), ("active_minutes", "Infinity"),
    ("waiting_minutes", "2 hours"), ("people", "0"), ("people", "1.5"),
    ("hourly_rate_usd", "-30"), ("hourly_rate_usd", "$30"), ("monthly_volume", "-1"),
    ("monthly_volume", "2.5"), ("currency", "EUR"),
])
def test_invalid_values_identify_the_csv_row_and_column(column, value):
    module = import_module("processiq.csv_import")
    with pytest.raises(module.CsvImportError, match=f"row 2.*{column}"):
        parse(f"step_name,{column}\nReceive,{value}\n".encode())


@pytest.mark.parametrize("data,match", [
    (b"", "empty"), (b"step_name\n", "step"),
    (b"active_minutes\n10\n", "step_name"),
    (b"step_name,Step name\nReceive,Receive\n", "Duplicate"),
    (b"step_name,frequency_per_week\nReceive,10\n", "frequency_per_week"),
    (b"step_name,people\n,1\n", "row 2.*step_name"),
    (b"step_name,people\nReceive,1,extra\n", "row 2"),
    (b'step_name\n"unfinished', "CSV"),
    (b"step_name\n\xff", "UTF-8"),
    (b"step_name,monthly_volume\nReceive,20\nSend,30\n", "monthly_volume.*same"),
    (b"step_name,process_name\nReceive,A\nSend,B\n", "process_name.*same"),
])
def test_bad_files_fail_clearly_instead_of_silently_dropping_data(data, match):
    module = import_module("processiq.csv_import")
    with pytest.raises(module.CsvImportError, match=match):
        parse(data)


def test_blank_rows_are_ignored_without_breaking_sequence_or_source_row_numbers():
    workflow = parse(b"step_name,people\n\nReceive,1\n,\nSend,1\n")
    assert [step.order for step in workflow.steps] == [1, 2]
    assert "CSV row 3" in workflow.source_messages[0].text
    assert "CSV row 5" in workflow.source_messages[1].text


def test_upload_limits_are_checked():
    module = import_module("processiq.csv_import")
    with pytest.raises(module.CsvImportError, match="2 MB"):
        parse(b"x" * (module.MAX_UPLOAD_BYTES + 1))
    with pytest.raises(module.CsvImportError, match="200"):
        parse(b"step_name\n" + b"Receive\n" * 201)


def test_downloadable_template_is_valid_and_matches_documented_results():
    from pathlib import Path
    data = (Path(__file__).resolve().parents[1] / "data/workflow_template.csv").read_bytes()
    workflow = parse(data)
    assert workflow.name == "Synthetic painting quotes"
    assert all(not step.active_time.confirmed for step in workflow.steps)
    analysis = analyze_workflow(apply_review(workflow, {}, confirm_all=True))
    assert analysis.labor_cost_per_case.value == Decimal("37.50")
    assert analysis.monthly_labor_cost.value == Decimal("750.00")
