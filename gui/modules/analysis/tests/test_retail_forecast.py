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
    WorkbenchRoute, aggregate_retail_revenue, build_retail_earnings_forecasts,
    build_retail_forecasts, build_sector_schedules, historical_retail_earnings,
    materialize_retail_forecast, materialize_retail_trading_profit,
    preview_retail_fcff, retail_engine_mapping, workbench_route,
)

RID = uuid4()


def assumption(field="revenue_growth", operation="Truworths Africa", *, accepted=True,
               currency="ZAR", value="2.5", fx_pair=None, unit=None):
    return ForecastAssumption(
        field=field, value=Decimal(value), unit=unit or ("multiple" if field == "fx_rate" else "percentage"),
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


def _tru_earnings_evidence():
    return [
        metric("sale_of_merchandise", None, 21339000000, currency="ZAR"),
        metric("trading_profit", None, 2774000000, currency="ZAR"),
        metric("finance_income", None, 1259000000, currency="ZAR"),
        metric("dividend_income", None, 55000000, currency="ZAR"),
        metric("segment_trading_margin", "Group", 13, currency=None),
        metric("revenue", None, 23030000000, currency="ZAR"),
        metric("retail_sales", None, 21756000000, currency="ZAR"),
        metric("operating_margin", None, Decimal("19.2"), currency=None),
    ]


def _trading_plan(*, margin_accepted=True, growth_field="sale_of_merchandise_growth"):
    growth = assumption(field=growth_field, operation="Group", value="2.5")
    margin = assumption(
        field="trading_margin", operation="Group", value="13",
        accepted=margin_accepted)
    return plan(growth, margin), growth, margin


def test_trading_margin_denominator_is_sale_of_merchandise_and_forecasts_profit():
    p, growth, margin = _trading_plan()
    evidence = _tru_earnings_evidence()
    growth_records, warnings = build_retail_forecasts(p, evidence)
    assert warnings == []
    earnings, warnings = build_retail_earnings_forecasts(
        p, evidence, records=growth_records)
    assert warnings == []
    row = earnings[0]
    assert row.forecast_sale_of_merchandise == Decimal("21872475000.000")
    assert row.forecast_trading_profit == Decimal("2843421750.00000")
    assert row.formula == "21872475000.000 * (13 / 100)"
    assert row.sale_growth_assumption_id == growth.assumption_id
    assert row.trading_margin_assumption_id == margin.assumption_id
    assert row.valuation_eligible is True


def test_operating_margin_cannot_be_applied_to_accounting_revenue():
    growth = assumption(field="revenue_growth", operation="Group")
    operating = assumption(field="operating_margin", operation="Group", value="19.2")
    p = plan(growth, operating)
    evidence = _tru_earnings_evidence()
    growth_records, _ = build_retail_forecasts(p, evidence)
    earnings, warnings = build_retail_earnings_forecasts(
        p, evidence, records=growth_records)
    assert earnings == []
    assert {item["code"] for item in warnings} == set()


@pytest.mark.parametrize("growth_field", ["retail_sales_growth", "revenue_growth"])
def test_other_growth_concepts_cannot_substitute_for_sale_of_merchandise_growth(growth_field):
    p, _, _ = _trading_plan(growth_field=growth_field)
    evidence = _tru_earnings_evidence()
    growth_records, _ = build_retail_forecasts(p, evidence)
    earnings, warnings = build_retail_earnings_forecasts(
        p, evidence, records=growth_records)
    assert earnings == []
    assert "SALE_OF_MERCHANDISE_FORECAST_MISSING" in {
        item["code"] for item in warnings}


def test_proposed_trading_margin_remains_informational_and_ineligible():
    p, _, _ = _trading_plan(margin_accepted=False)
    evidence = _tru_earnings_evidence()
    growth_records, _ = build_retail_forecasts(p, evidence)
    earnings, _ = build_retail_earnings_forecasts(
        p, evidence, records=growth_records, include_proposed=True)
    assert earnings[0].approval_state == ApprovalState.PROPOSED
    assert earnings[0].valuation_eligible is False
    accepted_only, warnings = build_retail_earnings_forecasts(
        p, evidence, records=growth_records, include_proposed=False)
    assert accepted_only == []
    assert warnings[0]["code"] == "TRADING_MARGIN_MISSING"


def test_finance_and_dividend_income_are_excluded_from_trading_profit():
    p, _, _ = _trading_plan()
    evidence = _tru_earnings_evidence()
    growth_records, _ = build_retail_forecasts(p, evidence)
    earnings, _ = build_retail_earnings_forecasts(
        p, evidence, records=growth_records)
    assert earnings[0].historical_trading_profit == Decimal("2774000000")
    assert earnings[0].historical_trading_profit != (
        Decimal("2774000000") + Decimal("1259000000") + Decimal("55000000"))


def test_trading_bridge_retains_exact_baseline_and_assumption_provenance():
    p, growth, margin = _trading_plan()
    evidence = _tru_earnings_evidence()
    sale = next(item for item in evidence if item["name"] == "sale_of_merchandise")
    profit = next(item for item in evidence if item["name"] == "trading_profit")
    growth_records, _ = build_retail_forecasts(p, evidence)
    row = build_retail_earnings_forecasts(
        p, evidence, records=growth_records)[0][0]
    assert str(row.historical_sale_metric_id) == sale["metric_id"]
    assert str(row.historical_trading_profit_metric_id) == profit["metric_id"]
    assert row.historical_sale_source_id == "file:afs"
    assert row.historical_trading_profit_source_id == "file:afs"
    assert row.sale_growth_assumption_id == growth.assumption_id
    assert row.trading_margin_assumption_id == margin.assumption_id


def test_tru_fy2026_historical_trading_margin_reconciles_with_rounding():
    rows = historical_retail_earnings(_tru_earnings_evidence())
    group = next(item for item in rows if item["operation"] == "Group")
    assert group["reported_trading_margin"] == Decimal("13")
    assert group["calculated_trading_margin"].quantize(Decimal("0.1")) == Decimal("13.0")
    disclosed_product = group["sale_of_merchandise"] * Decimal("0.13")
    assert abs(disclosed_product - group["trading_profit"]) < Decimal("1000000")
    assert group["definition"] == "trading_profit / sale_of_merchandise"


def test_tru_trading_profit_bridge_maps_explicitly_to_direct_ebit():
    p, growth, margin = _trading_plan()
    evidence = _tru_earnings_evidence()
    sales, _ = build_retail_forecasts(p, evidence, include_proposed=False)
    earnings, warnings = build_retail_earnings_forecasts(
        p, evidence, records=sales, include_proposed=False)
    assert warnings == []
    metric, selected = materialize_retail_trading_profit(earnings[0], RID)
    assert metric.name == "forecast_trading_profit"
    assert metric.intended_use == "direct_ebit"
    assert metric.value == Decimal("2843421750.00000")
    assert selected.valuation_field.value == "ebit"
    assert str(growth.assumption_id) in metric.source_id
    assert str(margin.assumption_id) in metric.source_id
    assert "Finance and dividend income excluded" in metric.notes


def test_proposed_trading_profit_cannot_materialize_as_ebit():
    p, _, _ = _trading_plan(margin_accepted=False)
    evidence = _tru_earnings_evidence()
    sales, _ = build_retail_forecasts(p, evidence)
    earnings, _ = build_retail_earnings_forecasts(
        p, evidence, records=sales, include_proposed=True)
    with pytest.raises(ValueError, match="accepted retail trading-profit"):
        materialize_retail_trading_profit(earnings[0], RID)


def _fcff_plan(*, cash_accepted=True):
    growth = assumption(
        field="sale_of_merchandise_growth", operation="Group", value="2.0")
    margin = assumption(
        field="trading_margin", operation="Group", value="13")
    p = plan(growth, margin)
    cash = [
        assumption(field="depreciation", operation="Group", value="1516000000",
                   unit="ZAR", accepted=cash_accepted),
        assumption(field="tax_rate", operation="Group", value="25.3",
                   unit="percentage", accepted=cash_accepted),
        assumption(field="total_capex", operation="Group", value="592000000",
                   unit="ZAR", accepted=cash_accepted),
        assumption(field="working_capital", operation="Group", value="188000000",
                   unit="ZAR", accepted=cash_accepted),
        assumption(field="other_recurring_cash", operation="Group", value="0",
                   unit="ZAR", accepted=cash_accepted),
    ]
    p.assumptions.extend(cash)
    return p, cash


def test_engine_mapping_shows_direct_ebit_and_cash_flow_routes():
    p, cash = _fcff_plan()
    evidence = _tru_earnings_evidence()
    records, warnings = build_retail_forecasts(p, evidence)
    earnings, earnings_warnings = build_retail_earnings_forecasts(
        p, evidence, records=records)
    previews = preview_retail_fcff(p, earnings)
    mapping = retail_engine_mapping(
        records, warnings + earnings_warnings, earnings=earnings,
        plan=p, fcff_previews=previews)
    assert "sale_of_merchandise_growth" in mapping
    assert "forecast_trading_profit" in mapping
    assert "direct EBIT (eligible)" in mapping
    assert "depreciation" in mapping and "D&A add-back (eligible)" in mapping
    assert "tax_rate" in mapping and "cash tax (eligible)" in mapping
    assert "total_capex" in mapping and "capex (eligible)" in mapping
    assert "working_capital" in mapping
    assert "change in operating working capital (eligible)" in mapping
    assert "other_recurring_cash" in mapping
    assert "recurring operating cash deduction (eligible)" in mapping
    assert "required by current YearInputSpec/preflight" in mapping
    assert "not used in direct-EBIT FCFF arithmetic" in mapping


def test_accepted_only_tru_fcff_preview_reconciles():
    p, _ = _fcff_plan()
    evidence = _tru_earnings_evidence()
    records, _ = build_retail_forecasts(p, evidence)
    earnings, _ = build_retail_earnings_forecasts(p, evidence, records=records)
    preview = preview_retail_fcff(p, earnings)[0]
    assert preview["status"] == "PASS"
    assert preview["inputs"]["ebit"] == Decimal("2829551400.000")
    assert preview["inputs"]["cash_tax"] == Decimal("715876504.200000")
    assert preview["inputs"]["unlevered_fcf"] == Decimal("2849674895.800000")


def test_proposed_cash_flow_assumptions_are_mapped_ineligible_and_not_previewed():
    p, cash = _fcff_plan(cash_accepted=False)
    evidence = _tru_earnings_evidence()
    records, warnings = build_retail_forecasts(p, evidence)
    earnings, earnings_warnings = build_retail_earnings_forecasts(
        p, evidence, records=records)
    previews = preview_retail_fcff(p, earnings)
    assert previews[0]["status"] == "NOT_CALCULABLE"
    assert set(previews[0]["missing"]) == {
        "depreciation", "tax_rate", "working_capital", "other_recurring_cash",
        "sustaining_capex", "growth_capex",
    }
    mapping = retail_engine_mapping(
        records, warnings + earnings_warnings, earnings=earnings, plan=p,
        fcff_previews=previews)
    for item in cash:
        assert f"{item.field} [{item.assumption_id}]" in mapping
    assert mapping.count("proposed / ineligible") >= 5
