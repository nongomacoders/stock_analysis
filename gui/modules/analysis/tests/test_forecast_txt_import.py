from decimal import Decimal
from pathlib import Path
from uuid import uuid4
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from modules.analysis.forecast_plan import (
    ApprovalState, ForecastPlan, Origin, PlanStatus, approve_plan, new_version)
from modules.analysis.forecast_txt_import import (
    ForecastTxtImportError, parse_forecast_txt, resolve_import_assumptions,
)

RID = uuid4()
OPERATIONS = {"Group", "Truworths Africa", "Office UK"}


def empty_plan():
    return ForecastPlan(ticker="TRU.JO", created_by="analyst", source_report_version_id=RID)


EXAMPLE = """
  FORECAST_PLAN
  ticker = TRU.JO
  case = base

  ASSUMPTION
  period = FY2027
  start = 2026-06-29
  end = 2027-06-27
  operation = Truworths Africa
  field = retail_sales_growth
  value = 2.5
  unit = percentage
  currency = ZAR
  confidence = 0.6
  analyst = Dion
  rationale = Modest recovery after weak FY2026 trading.
  commodity =
  price_type =
  project_start =
  cost_definition =
  fx_pair =

  ASSUMPTION
  period = FY2028
  start = 2027-06-28
  end = 2028-06-25
  operation = Truworths Africa
  field = revenue_growth
  value = 3.0
  unit = percentage
  currency = ZAR
  confidence = 0.55
  analyst = Dion
  rationale = Independently approved accounting revenue assumption with UTF-8: naÃ¯ve cafÃ©.
"""


def parse(text=EXAMPLE, plan=None, ticker="TRU.JO", category="General Retail"):
    return parse_forecast_txt(
        text, current_plan=plan or empty_plan(), current_ticker=ticker,
        category=category, source_name="forecast.txt", allowed_operations=OPERATIONS)


def test_imports_multiple_utf8_assumptions_and_periods_as_proposed():
    preview = parse()
    assert [period.label for period in preview.horizon] == ["FY2027", "FY2028"]
    assert [item.field for item in preview.assumptions] == [
        "retail_sales_growth", "revenue_growth"]
    assert all(item.origin == Origin.ANALYST_ASSUMPTION for item in preview.assumptions)
    assert all(item.approval_state == ApprovalState.PROPOSED for item in preview.assumptions)
    assert preview.assumptions[0].commodity is None
    assert preview.assumptions[0].effective_date is None
    assert "naÃ¯ve cafÃ©" in preview.assumptions[1].rationale
    assert "approval=proposed" in preview.render()


def test_import_does_not_mutate_current_plan():
    current = empty_plan()
    original = current.model_dump()
    preview = parse(plan=current)
    assert current.model_dump() == original
    assert len(preview.assumptions) == 2


def test_existing_period_can_be_reused_without_dates():
    first = parse()
    plan = ForecastPlan.model_validate({
        **empty_plan().model_dump(), "horizon": first.horizon,
    })
    text = """FORECAST_PLAN
ticker=TRU.JO
case=base
ASSUMPTION
period=FY2027
operation=Group
field=revenue_growth
value=2
unit=percentage
currency=ZAR
confidence=0.5
analyst=Dion
rationale=Explicit group accounting revenue view.
"""
    preview = parse(text, plan=plan)
    assert preview.horizon == plan.horizon


def test_ticker_mismatch_is_blocked():
    with pytest.raises(ForecastTxtImportError, match="IMPORT BLOCKED â€” ticker mismatch"):
        parse(EXAMPLE.replace("ticker = TRU.JO", "ticker = MRP.JO"))


def test_invalid_controlled_unit_is_not_corrected():
    with pytest.raises(ForecastTxtImportError, match="Unknown controlled unit: %"):
        parse(EXAMPLE.replace("unit = percentage", "unit = %", 1))


def test_invalid_case_uses_existing_model_validator():
    with pytest.raises(ForecastTxtImportError, match="Unknown forecast case"):
        parse(EXAMPLE.replace("case = base", "case = upside", 1))


def test_confidence_uses_existing_range_validator():
    with pytest.raises(ForecastTxtImportError, match="less than or equal to 1"):
        parse(EXAMPLE.replace("confidence = 0.6", "confidence = 1.2", 1))


def test_unknown_operation_is_blocked():
    with pytest.raises(ForecastTxtImportError, match="unknown operation 'Unknown Division'"):
        parse(EXAMPLE.replace("operation = Truworths Africa", "operation = Unknown Division", 1))


def test_retail_sector_rejects_mining_field():
    changed = (EXAMPLE.replace("field = retail_sales_growth", "field = recovery", 1)
               .replace("value = 2.5", "value = 85", 1))
    with pytest.raises(ForecastTxtImportError, match="mining field"):
        parse(changed)


def test_field_specific_fx_requirement_uses_existing_acceptance_validator():
    text = """FORECAST_PLAN
ticker=TRU.JO
case=base
ASSUMPTION
period=FY2027
start=2026-06-29
end=2027-06-27
operation=Group
field=fx_rate
value=20
unit=multiple
currency=ZAR
confidence=0.6
analyst=Dion
rationale=Explicit GBP translation assumption.
fx_pair=
"""
    with pytest.raises(ForecastTxtImportError, match="FX forecast needs fiscal period and explicit pair"):
        parse(text)


@pytest.mark.parametrize("bad_line, message", [
    ("mystery=value", "unknown assumption field 'mystery'"),
    ("field=revenue_growth\nfield=retail_sales_growth", "duplicate field 'field'"),
    ("field=revenue_growth", "period is required"),
])
def test_structural_errors_are_clear(bad_line, message):
    text = f"""FORECAST_PLAN
ticker=TRU.JO
case=base
ASSUMPTION
{bad_line}
"""
    with pytest.raises(ForecastTxtImportError, match=message):
        parse(text)


def test_compact_file_without_section_markers_is_supported():
    compact = """ticker=TRU.JO
case=base

period=FY2027
start=2026-06-29
end=2027-06-27
operation=Truworths Africa
field=retail_sales_growth
value=2.5
unit=percentage
currency=ZAR
confidence=0.6
analyst=Dion
rationale=Modest recovery.
"""
    preview = parse(compact)
    assert len(preview.assumptions) == 1
    assert preview.assumptions[0].field == 'retail_sales_growth'
    assert preview.horizon[0].label == 'FY2027'


def test_compact_file_can_start_another_assumption_with_period_key():
    compact = EXAMPLE.replace('  FORECAST_PLAN\n', '', 1).replace('  ASSUMPTION\n', '')
    preview = parse(compact)
    assert len(preview.assumptions) == 2


def _plan_with_first_example_assumption():
    initial = parse(EXAMPLE)
    return ForecastPlan.model_validate({
        **empty_plan().model_dump(),
        'horizon': [initial.horizon[0]],
        'assumptions': [initial.assumptions[0]],
    })


def test_duplicate_against_current_in_memory_draft_keeps_existing_by_default():
    current = _plan_with_first_example_assumption()
    existing_id = current.assumptions[0].assumption_id
    preview = parse(EXAMPLE, plan=current)
    assert len(preview.identical_duplicates) == 1
    assert preview.identical_duplicates[0].status == 'DUPLICATE_IDENTICAL'
    assert preview.identical_duplicates[0].against == 'current in-memory draft'
    assert [item.field for item in preview.assumptions] == ['revenue_growth']
    resolved = resolve_import_assumptions(current, preview, 'keep_existing')
    retail = [item for item in resolved if item.field == 'retail_sales_growth']
    assert len(retail) == 1
    assert retail[0].assumption_id == existing_id


def test_duplicate_against_persisted_reloaded_draft_is_detected():
    reloaded = ForecastPlan.model_validate_json(_plan_with_first_example_assumption().model_dump_json())
    preview = parse(EXAMPLE, plan=reloaded)
    assert len(preview.identical_duplicates) == 1
    assert preview.identical_duplicates[0].existing.assumption_id == reloaded.assumptions[0].assumption_id


def test_conflicting_duplicate_requires_explicit_resolution():
    current = _plan_with_first_example_assumption()
    conflict_text = EXAMPLE.replace('value = 2.5', 'value = 4.0', 1)
    preview = parse(conflict_text, plan=current)
    assert len(preview.conflicts) == 1
    duplicate = preview.conflicts[0]
    assert duplicate.status == 'DUPLICATE_CONFLICT'
    assert duplicate.existing.value == 2.5
    assert duplicate.imported.value == 4
    with pytest.raises(ForecastTxtImportError, match='require Keep Existing or Replace'):
        resolve_import_assumptions(current, preview, 'cancel')
    kept = resolve_import_assumptions(current, preview, 'keep_existing')
    assert next(item for item in kept if item.field == 'retail_sales_growth').value == Decimal('2.5')
    replaced = resolve_import_assumptions(current, preview, 'replace_as_proposed')
    replacement = next(item for item in replaced if item.field == 'retail_sales_growth')
    assert replacement.value == 4
    assert replacement.approval_state == ApprovalState.PROPOSED
    assert current.assumptions[0].value == Decimal('2.5')


def test_duplicate_within_txt_is_detected():
    block = """period=FY2027
start=2026-06-29
end=2027-06-27
operation=Truworths Africa
field=retail_sales_growth
value=2.5
unit=percentage
currency=ZAR
confidence=0.6
analyst=Dion
rationale=Modest recovery.
"""
    text = 'ticker=TRU.JO\ncase=base\n\n' + block + '\n' + block
    preview = parse(text)
    assert len(preview.assumptions) == 1
    assert len(preview.identical_duplicates) == 1
    assert preview.identical_duplicates[0].against == 'earlier TXT entry'


def test_different_field_same_period_operation_is_not_duplicate():
    second = EXAMPLE.replace('period = FY2028', 'period = FY2027').replace(
        'start = 2027-06-28\n  end = 2028-06-25',
        'start = 2026-06-29\n  end = 2027-06-27')
    preview = parse(second)
    assert {item.field for item in preview.assumptions} == {
        'retail_sales_growth', 'revenue_growth'}
    assert preview.duplicates == []


def test_duplicate_import_and_resolution_are_atomic():
    current = _plan_with_first_example_assumption()
    before = current.model_dump()
    preview = parse(EXAMPLE.replace('value = 2.5', 'value = 4.0', 1), plan=current)
    resolved = resolve_import_assumptions(current, preview, 'replace_as_proposed')
    assert current.model_dump() == before
    changed = new_version(current, changed_by='Dion', horizon=preview.horizon, assumptions=resolved)
    assert current.model_dump() == before
    assert changed.previous_plan_id == current.forecast_plan_id
    assert changed.plan_version == current.plan_version + 1


def test_replacement_creates_new_draft_without_mutating_approved_history():
    base = _plan_with_first_example_assumption()
    accepted = base.assumptions[0].model_copy(update={'approval_state': ApprovalState.ACCEPTED})
    accepted_plan = ForecastPlan.model_validate({
        **base.model_dump(), 'assumptions': [accepted]})
    approved = approve_plan(accepted_plan, 'Reviewer')
    approved_snapshot = approved.model_dump()
    preview = parse(EXAMPLE.replace('value = 2.5', 'value = 4.0', 1), plan=approved)
    resolved = resolve_import_assumptions(approved, preview, 'replace_as_proposed')
    replacement = new_version(
        approved, changed_by='Dion', horizon=preview.horizon, assumptions=resolved)
    assert approved.model_dump() == approved_snapshot
    assert approved.status == PlanStatus.APPROVED
    assert replacement.status == PlanStatus.DRAFT
    changed = next(item for item in replacement.assumptions if item.field == 'retail_sales_growth')
    assert changed.value == 4
    assert changed.approval_state == ApprovalState.PROPOSED

