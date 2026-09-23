from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from modules.analysis.forecast_plan import (
    ApprovalState, ForecastAssumption, ForecastPeriod, ForecastPlan, Origin,
)
from modules.analysis.retail_forecast import (
    WorkbenchRoute, aggregate_retail_revenue, build_retail_forecasts,
    build_sector_schedules, materialize_retail_forecast, retail_engine_mapping, workbench_route,
)

RID = uuid4()


def assumption(field="revenue_growth", operation="Truworths Africa", *, accepted=True,
               currency="ZAR", value="2.5", fx_pair=None):
    return ForecastAssumption(
        field=field, value=Decimal(value), unit="multiple" if field == "fx_rate" else "percentage",
        currency=currency, period_label="FY2027", operation_segment=operation,
        case="base", origin=Origin.ANALYST_ASSUMPTION,
        approval_state=ApprovalState.ACCEPTED if accepted else ApprovalState.PROPOSED,
        rationale="Explicit synthetic analyst assumption", created_by="test analyst",
        confidence=Decimal("0.6"), fx_pair=fx_pair,
    )


def plan(*assumptions):
    return ForecastPlan(
        ticker="TEST.JO", created_by="test analyst", source_report_version_id=RID,
        horizon=[ForecastPeriod(label="FY2027", start=date(2026, 6, 29), end=date(2027, 6, 27))],
        assumptions=list(assumptions),
    )


def metric(name, operation, value, currency="ZAR", period="2026-06-28"):
    return {
        "metric_id": str(uuid4()), "name": name, "operation_segment": operation,
        "value": str(value), "unit": currency, "currency": currency,
        "period_end": period, "source_id": "file:afs",
    }


def test_general_retail_never_invokes_mining_builders():
    calls = []
    def forbidden(*args):
        calls.append(args)
        raise AssertionError("mining builder called for retail")
    payload = build_sector_schedules(
        "General Retail", plan(assumption(accepted=False)),
        [metric("segment_revenue", "Truworths Africa", 100)],
        mining_production_builder=forbidden, mining_cost_builder=forbidden)
    assert payload["route"] == WorkbenchRoute.RETAIL
    assert calls == []


def test_mining_route_invokes_production_and_cost_builders():
    calls = []
    def production(_plan, operation):
        calls.append(("production", operation)); return []
    def costs(_plan, operation):
        calls.append(("cost", operation)); return []
    payload = build_sector_schedules(
        "Mining & Commodities", plan(assumption(operation="Mine", accepted=False)), [],
        mining_production_builder=production, mining_cost_builder=costs)
    assert payload["route"] == WorkbenchRoute.MINING
    assert calls == [("production", "Mine"), ("cost", "Mine")]


def test_generic_retail_routing_is_not_ticker_specific():
    assert workbench_route("General Retail") == WorkbenchRoute.RETAIL
    assert workbench_route("general retail") == WorkbenchRoute.RETAIL
    assert workbench_route("Banks & Financial Services") == WorkbenchRoute.BANK
    assert workbench_route("Investment Holding Companies") == WorkbenchRoute.HOLDING_COMPANY


def test_proposed_retail_assumption_is_preview_only():
    records, warnings = build_retail_forecasts(
        plan(assumption(accepted=False)),
        [metric("segment_revenue", "Truworths Africa", 100)])
    assert not warnings
    assert records[0].derived_forecast_value == Decimal("102.500")
    assert records[0].approval_state == ApprovalState.PROPOSED
    assert records[0].valuation_eligible is False
    assert "informational / not valuation eligible" in retail_engine_mapping(records, warnings)


def test_accepted_revenue_growth_retains_baseline_provenance():
    baseline = metric("segment_revenue", "Truworths Africa", 100)
    item = assumption()
    records, warnings = build_retail_forecasts(plan(item), [baseline])
    assert not warnings
    record = records[0]
    assert record.output_metric == "forecast_revenue"
    assert record.valuation_eligible is True
    assert str(record.historical_baseline_metric_id) == baseline["metric_id"]
    assert record.historical_source_id == "file:afs"
    assert record.historical_period == date(2026, 6, 28)
    assert record.assumption_id == item.assumption_id
    assert record.formula == "100 * (1 + 2.5 / 100)"


def test_retail_sales_does_not_use_accounting_revenue_baseline():
    records, warnings = build_retail_forecasts(
        plan(assumption(field="retail_sales_growth")),
        [metric("segment_revenue", "Truworths Africa", 100)])
    assert records == []
    assert warnings[0]["code"] == "RETAIL_BASELINE_MISSING"


def test_retail_sales_growth_forecasts_retail_sales_only():
    records, warnings = build_retail_forecasts(
        plan(assumption(field="retail_sales_growth")),
        [metric("segment_retail_sales", "Truworths Africa", 100)])
    assert not warnings
    assert records[0].output_metric == "forecast_retail_sales"
    assert records[0].valuation_eligible is False


def test_revenue_growth_forecasts_accounting_revenue_only():
    records, warnings = build_retail_forecasts(
        plan(assumption(field="revenue_growth")),
        [metric("segment_sale_of_merchandise", "Truworths Africa", 100),
         metric("segment_revenue", "Truworths Africa", 120)])
    assert not warnings
    assert records[0].historical_baseline_value == 120
    assert records[0].derived_forecast_value == Decimal("123.000")


def test_segment_revenue_aggregation():
    p = plan(assumption(operation="Africa"), assumption(operation="Other"))
    records, _ = build_retail_forecasts(
        p, [metric("segment_revenue", "Africa", 100), metric("segment_revenue", "Other", 50)])
    evidence = [metric("segment_revenue", "Africa", 100), metric("segment_revenue", "Other", 50)]
    result = aggregate_retail_revenue(
        p, records, period="FY2027", evidence_metrics=evidence)
    assert result["status"] == "PASS"
    assert result["value"] == Decimal("153.750")


def test_foreign_segment_stays_in_gbp_until_explicit_fx():
    p = plan(assumption(operation="Office UK", currency="GBP"))
    records, _ = build_retail_forecasts(
        p, [metric("segment_revenue", "Office UK", 100, currency="GBP")])
    assert records[0].currency == "GBP"
    assert records[0].derived_forecast_value == Decimal("102.500")
    blocked = aggregate_retail_revenue(
        p, records, period="FY2027",
        evidence_metrics=[metric("segment_revenue", "Office UK", 100, currency="GBP")])
    assert blocked["status"] == "NOT_CALCULABLE"
    assert blocked["reason"] == "MISSING_EXPLICIT_FX"


def test_explicit_fx_enables_foreign_segment_translation():
    growth = assumption(operation="Office UK", currency="GBP")
    fx = assumption(field="fx_rate", operation=None, currency="ZAR", value="20", fx_pair="GBP/ZAR")
    p = plan(growth, fx)
    records, _ = build_retail_forecasts(
        p, [metric("segment_revenue", "Office UK", 100, currency="GBP")])
    result = aggregate_retail_revenue(
        p, records, period="FY2027",
        evidence_metrics=[metric("segment_revenue", "Office UK", 100, currency="GBP")])
    assert result["status"] == "PASS"
    assert result["value"] == Decimal("2050.000")
    assert result["components"][0]["fx_assumption_id"] == str(fx.assumption_id)


def test_group_and_segments_are_rejected_as_double_count():
    p = plan(assumption(operation="Group"), assumption(operation="Africa"))
    records, _ = build_retail_forecasts(
        p, [metric("revenue", None, 150), metric("segment_revenue", "Africa", 100)])
    result = aggregate_retail_revenue(p, records, period="FY2027")
    assert result == {"status": "NOT_CALCULABLE", "reason": "GROUP_SEGMENT_DOUBLE_COUNT"}


def test_tru_style_incomplete_proposed_plan_remains_non_calculable():
    p = plan(assumption(field="retail_sales_growth", accepted=False))
    records, warnings = build_retail_forecasts(
        p, [metric("segment_revenue", "Truworths Africa", 15246000000)])
    assert records == []
    assert warnings[0]["code"] == "RETAIL_BASELINE_MISSING"
    assert aggregate_retail_revenue(p, records, period="FY2027")["status"] == "NOT_CALCULABLE"

def test_accepted_revenue_forecast_materializes_for_existing_dcf_input():
    p = plan(assumption())
    records, _ = build_retail_forecasts(
        p, [metric('segment_revenue', 'Truworths Africa', 100)])
    derived, candidate = materialize_retail_forecast(records[0], RID)
    assert derived.metric_id == records[0].derived_metric_id
    assert derived.name == 'forecast_revenue'
    assert derived.source_id == f'retail_forecast:{records[0].assumption_id}'
    assert candidate.valuation_field.value == 'revenue'
    assert candidate.case_type.value == 'base'


def test_proposed_retail_forecast_cannot_materialize_for_valuation():
    p = plan(assumption(accepted=False))
    records, _ = build_retail_forecasts(
        p, [metric('segment_revenue', 'Truworths Africa', 100)])
    with pytest.raises(ValueError, match='Only accepted forecast revenue'):
        materialize_retail_forecast(records[0], RID)


def test_foreign_segment_rejects_presentation_currency_baseline_for_native_forecast():
    p = plan(assumption(operation='Office UK', currency='GBP'))
    records, warnings = build_retail_forecasts(
        p, [metric('segment_revenue', 'Office UK', 100, currency='ZAR')])
    assert records == []
    assert warnings[0]['code'] == 'NATIVE_CURRENCY_BASELINE_MISSING'



def test_native_currency_baseline_is_preferred_without_historical_fx_reconstruction():
    p = plan(assumption(operation="Office UK", currency="GBP"))
    evidence = [
        metric("segment_revenue", "Office UK", 2200, currency="ZAR"),
        metric("segment_revenue", "Office UK", 100, currency="GBP"),
    ]
    records, warnings = build_retail_forecasts(p, evidence)
    assert warnings == []
    assert records[0].historical_baseline_value == Decimal("100")
    assert records[0].currency == "GBP"


def test_segment_aggregation_fails_closed_without_completeness_evidence():
    p = plan(assumption(operation="Truworths Africa"))
    evidence = [metric("segment_revenue", "Truworths Africa", 100)]
    records, _ = build_retail_forecasts(p, evidence)
    result = aggregate_retail_revenue(p, records, period="FY2027")
    assert result["status"] == "NOT_CALCULABLE"
    assert result["reason"] == "REQUIRED_SEGMENT_EVIDENCE_MISSING"

def test_one_of_two_known_revenue_segments_is_partial():
    growth = assumption(operation='Truworths Africa')
    p = plan(growth)
    evidence = [
        metric('segment_revenue', 'Truworths Africa', 100, currency='ZAR'),
        metric('segment_revenue', 'Office UK', 50, currency='GBP'),
    ]
    records, _ = build_retail_forecasts(p, evidence)
    result = aggregate_retail_revenue(
        p, records, period='FY2027', evidence_metrics=evidence)
    assert result['status'] == 'PARTIAL'
    assert result['reason'] == 'MISSING_REQUIRED_SEGMENTS'
    assert result['missing_segments'] == ['Office UK']
    assert result['present_segments'] == ['Truworths Africa']


def test_both_known_segments_with_explicit_fx_pass_completeness():
    africa = assumption(operation='Truworths Africa')
    office = assumption(operation='Office UK', currency='GBP')
    fx = assumption(field='fx_rate', operation=None, currency='ZAR', value='20', fx_pair='GBP/ZAR')
    p = plan(africa, office, fx)
    evidence = [
        metric('segment_revenue', 'Truworths Africa', 100, currency='ZAR'),
        metric('segment_revenue', 'Office UK', 50, currency='GBP'),
    ]
    records, _ = build_retail_forecasts(p, evidence)
    result = aggregate_retail_revenue(
        p, records, period='FY2027', evidence_metrics=evidence)
    assert result['status'] == 'PASS'
    assert result['required_segments'] == ['Office UK', 'Truworths Africa']
    assert result['missing_segments'] == []
    assert result['value'] == Decimal('1127.500')


def test_explicit_accepted_group_revenue_forecast_bypasses_segment_completeness():
    group = assumption(operation='Group')
    p = plan(group)
    evidence = [
        metric('revenue', None, 150, currency='ZAR'),
        metric('segment_revenue', 'Truworths Africa', 100, currency='ZAR'),
        metric('segment_revenue', 'Office UK', 50, currency='GBP'),
    ]
    records, _ = build_retail_forecasts(p, evidence)
    result = aggregate_retail_revenue(
        p, records, period='FY2027', evidence_metrics=evidence)
    assert result['status'] == 'PASS'
    assert result['value'] == Decimal('153.750')
    assert [item['operation'] for item in result['components']] == ['Group']


def test_group_plus_segments_still_fails_before_completeness_aggregation():
    group = assumption(operation='Group')
    africa = assumption(operation='Truworths Africa')
    office = assumption(operation='Office UK', currency='GBP')
    p = plan(group, africa, office)
    evidence = [
        metric('revenue', None, 150, currency='ZAR'),
        metric('segment_revenue', 'Truworths Africa', 100, currency='ZAR'),
        metric('segment_revenue', 'Office UK', 50, currency='GBP'),
    ]
    records, _ = build_retail_forecasts(p, evidence)
    result = aggregate_retail_revenue(
        p, records, period='FY2027', evidence_metrics=evidence)
    assert result == {'status': 'NOT_CALCULABLE', 'reason': 'GROUP_SEGMENT_DOUBLE_COUNT'}


def test_all_segments_present_but_missing_fx_remains_not_calculable():
    africa = assumption(operation='Truworths Africa')
    office = assumption(operation='Office UK', currency='GBP')
    p = plan(africa, office)
    evidence = [
        metric('segment_revenue', 'Truworths Africa', 100, currency='ZAR'),
        metric('segment_revenue', 'Office UK', 50, currency='GBP'),
    ]
    records, _ = build_retail_forecasts(p, evidence)
    result = aggregate_retail_revenue(
        p, records, period='FY2027', evidence_metrics=evidence)
    assert result['status'] == 'NOT_CALCULABLE'
    assert result['reason'] == 'MISSING_EXPLICIT_FX'
    assert result['operation'] == 'Office UK'
    assert result['missing_segments'] == []



def test_tru_actual_segment_evidence_cannot_pass_with_africa_only():
    evidence = [
        metric("segment_revenue", "Truworths Africa", 15246000000, currency="ZAR"),
        metric("segment_revenue", "Office UK", 7784000000, currency="ZAR"),
        metric("segment_revenue", "Group", 23030000000, currency="ZAR"),
    ]
    p = plan(assumption(operation="Truworths Africa", currency="ZAR"))
    records, warnings = build_retail_forecasts(p, evidence)
    assert warnings == []
    result = aggregate_retail_revenue(
        p, records, period="FY2027", evidence_metrics=evidence)
    assert result["status"] == "PARTIAL"
    assert result["required_segments"] == ["Office UK", "Truworths Africa"]
    assert result["present_segments"] == ["Truworths Africa"]
    assert result["missing_segments"] == ["Office UK"]


def test_proposed_fx_does_not_make_foreign_aggregation_calculable():
    evidence = [
        metric("segment_revenue", "Truworths Africa", 100, currency="ZAR"),
        metric("segment_revenue", "Office UK", 50, currency="GBP"),
    ]
    p = plan(
        assumption(operation="Truworths Africa"),
        assumption(operation="Office UK", currency="GBP"),
        assumption(field="fx_rate", operation="Group", currency="ZAR",
                   value="21.6", fx_pair="GBP/ZAR", accepted=False),
    )
    records, _ = build_retail_forecasts(p, evidence)
    result = aggregate_retail_revenue(
        p, records, period="FY2027", evidence_metrics=evidence)
    assert result["status"] == "NOT_CALCULABLE"
    assert result["reason"] == "MISSING_EXPLICIT_FX"
