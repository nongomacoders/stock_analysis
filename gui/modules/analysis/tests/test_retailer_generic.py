"""Synthetic retailer integration. Values are invented test inputs, never Mr Price facts."""
from datetime import date
from decimal import Decimal
from pathlib import Path
import sys
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from modules.analysis.financial_metrics import (AssumptionType, FinancialMetric, ShareCountType,
    SourceType, Unit)
from modules.analysis.forecast_plan import (ApprovalState, ForecastAssumption, ForecastPeriod,
    ForecastPlan, Origin, approve_plan, compile_plan_inputs, preview_valuation)
from modules.analysis.valuation.engine import (CasePlan, DcfSpec, EquitySpec, ValuationPlan,
    WaccSpec, YearInputSpec)
from modules.analysis.valuation.models import Basis, InputRef, TerminalMethod
from modules.analysis.valuation.reconciliation import recalculate_target
from modules.analysis.valuation_preflight import candidate, validate_candidate

D = lambda x: Decimal(str(x))
RID = uuid4()
TICKER = "RETAIL_SYNTHETIC.JO"


def retailer_fixture(*, capex_add=0, working_capital_add=0, omit_wacc=False):
    periods = [ForecastPeriod(label=f"FY{year}", start=date(year-1, 7, 1),
                              end=date(year, 6, 30)) for year in range(2027, 2032)]
    assumptions = []
    def add(field, value, unit="ZAR", *, period=None, currency=None, cost_definition=None):
        a = ForecastAssumption(field=field, value=D(value), unit=unit,
            currency=currency if currency is not None else ("ZAR" if unit == "ZAR" else None),
            period_label=period, origin=Origin.ANALYST_ASSUMPTION,
            approval_state=ApprovalState.ACCEPTED,
            rationale="SYNTHETIC RETAILER TEST INPUT; not a company fact",
            created_by="test fixture", cost_definition=cost_definition)
        assumptions.append(a)
        return InputRef(metric_id=a.assumption_id, field=field)
    years = []
    for i, p in enumerate(periods):
        numbers = {"revenue": 1000 + 100*i, "operating_cost": 600 + 60*i,
            "corporate_cost": 50, "depreciation": 50, "net_finance_cost": 0,
            "tax_rate": 25, "sustaining_capex": 40 + capex_add,
            "growth_capex": 20, "working_capital": 10 + working_capital_add,
            "other_recurring_cash": 0}
        inputs = {field: add(field, value,
                    "percentage" if field == "tax_rate" else "ZAR", period=p.label,
                    cost_definition="operating_cost" if field == "operating_cost" else None)
                  for field, value in numbers.items()}
        years.append(YearInputSpec(period_end=p.end, inputs=inputs))
    wacc_values = {"risk_free_rate": 5, "equity_risk_premium": 6, "beta": 1,
                   "country_risk_premium": 2, "cost_of_debt": 8, "tax_rate": 25,
                   "debt_weight": 20, "equity_weight": 80}
    wacc = {field: add(field, value, "multiple" if field == "beta" else "percentage",
                       currency="ZAR" if field in {"risk_free_rate", "cost_of_debt"} else None)
            for field, value in wacc_values.items() if not (omit_wacc and field == "beta")}
    growth = add("terminal_growth", 3, "percentage")
    shares = add("forecast_diluted_shares", 100, "shares")
    adjustments = {field: add(field, value) for field, value in {
        "non_operating_assets": 0, "net_debt": 80,
        "lease_adjustments": 0, "minorities": 0,
        "other_equity_adjustments": 0}.items()}
    dcf = DcfSpec(valuation_date=date(2026, 6, 30), years=years,
        cash_flow_currency="ZAR", cash_flow_basis=Basis.NOMINAL,
        inflation_basis="ZAR_CPI",
        wacc=WaccSpec(currency="ZAR", basis=Basis.NOMINAL,
                      inflation_basis="ZAR_CPI", components=wacc),
        terminal_method=TerminalMethod.PERPETUITY_GROWTH, terminal_growth=growth)
    mapping = ValuationPlan(ticker=TICKER, report_version_id=RID,
        valuation_date=date(2026, 6, 30),
        cases={"base": CasePlan(rationale="SYNTHETIC direct-revenue retailer DCF",
            primary_method="DCF", dcf=dcf,
            equity=EquitySpec(adjustments=adjustments, shares=shares))})
    draft = ForecastPlan(ticker=TICKER, created_by="test fixture",
        source_report_version_id=RID, horizon=periods, assumptions=assumptions,
        engine_plan=mapping, notes="SYNTHETIC; not Mr Price evidence")
    return approve_plan(draft, "test reviewer")


def value(plan):
    metrics, candidates = compile_plan_inputs(plan, [])
    return preview_valuation(plan, metrics, candidates)


def test_retailer_direct_revenue_five_year_dcf_and_reconciliation():
    result = value(retailer_fixture())
    assert result.status.value in {"PASS", "PASS_WITH_WARNINGS"}
    assert result.target_price == D("31.10")
    assert recalculate_target(result) == result.target_price
    assert result.methods["DCF"].status.value == "PASS"
    assert result.methods["SOTP"].status.value == "NOT_CALCULABLE"
    first = result.methods["DCF"].schedule[0]
    assert D(first["revenue"]) == 1000
    assert D(first["ebitda"]) == 350
    assert D(first["ebit"]) == 300
    assert D(first["fcf"]) == 205
    assert first["operational_schedule"] is None
    assert result.reconciliation.shares == 100
    assert any(str(result.reconciliation.shares_metric_id) == a["assumption_id"] and a["field"] == "forecast_diluted_shares"
               for a in result.calculation_inputs["forecast_plan"]["assumptions"])
    assert not any("commodity" in str(x).lower() or "production" in str(x).lower()
                   for x in result.warnings)


def test_retailer_capex_and_working_capital_change_fcf_and_target():
    base = value(retailer_fixture())
    capex = value(retailer_fixture(capex_add=10))
    wc = value(retailer_fixture(working_capital_add=10))
    for changed in (capex, wc):
        assert D(changed.methods["DCF"].schedule[0]["fcf"]) == 195
        assert changed.target_price < base.target_price


def test_missing_wacc_is_not_calculable_without_mining_warning():
    result = value(retailer_fixture(omit_wacc=True))
    assert result.status.value == "NOT_CALCULABLE"
    assert result.target_price is None
    assert any("WACC missing beta" in x for x in result.methods["DCF"].missing_inputs)
    assert not any("commodity" in str(x).lower() or "production" in str(x).lower()
                   for x in result.warnings)


def test_generic_preflight_rejects_unsourced_revenue_and_warns_on_current_shares():
    missing = FinancialMetric(ticker=TICKER, report_id=RID, name="revenue",
        value=100, unit=Unit.ZAR, currency="ZAR", assumption_type=AssumptionType.UNRESOLVED)
    bad, _ = validate_candidate(candidate(missing, RID, "revenue", "base", "unsourced"), [missing])
    assert bad.validation_status.value == "unresolved"
    shares = FinancialMetric(ticker=TICKER, report_id=RID, name="issued_shares_current",
        value=100, unit=Unit.SHARES, share_count_type=ShareCountType.ISSUED_SHARES_CURRENT,
        source="SYNTHETIC disclosure", source_type=SourceType.COMPANY_DISCLOSURE,
        assumption_type=AssumptionType.HISTORICAL_ACTUAL,
        source_date=date(2026, 6, 1), source_id="synthetic:shares",
        evidence_quote="Synthetic share count", evidence_verified=True)
    reviewed, _ = validate_candidate(candidate(shares, RID, "current_issued_shares", "base", "test"), [shares])
    assert reviewed.validation_status.value == "eligible_with_warning"
    assert {w.code for w in reviewed.warnings} == {"DILUTION_UNMODELED"}


def test_direct_revenue_rejects_historical_actual_as_future_forecast():
    from modules.analysis.valuation.engine import run_valuation
    plan = retailer_fixture()
    metrics, candidates = compile_plan_inputs(plan, [])
    old = next(c for c in candidates if c.valuation_field.value == "revenue" and
               c.source_metric.period_end == date(2027, 6, 30))
    historical = FinancialMetric(metric_id=old.metric_id, ticker=TICKER, report_id=RID,
        name="revenue", value=old.selected_value, unit=Unit.ZAR, currency="ZAR",
        period_start=date(2025, 7, 1), period_end=date(2026, 6, 30),
        source_date=date(2026, 7, 1), source="SYNTHETIC prior-year report",
        source_type=SourceType.COMPANY_DISCLOSURE,
        assumption_type=AssumptionType.HISTORICAL_ACTUAL,
        source_id="synthetic:old_revenue", evidence_verified=True,
        evidence_quote="Synthetic historical revenue")
    historical_candidate = candidate(historical, RID, "revenue", "base", "Synthetic stale value")
    metrics = [historical if m.metric_id == old.metric_id else m for m in metrics]
    candidates = [historical_candidate if c.metric_id == old.metric_id else c for c in candidates]
    result = run_valuation(ticker=TICKER, report_version_id=RID, metrics=metrics,
                           candidates=candidates, plan=plan.engine_plan)
    assert result.status.value == "FAIL"
    assert result.target_price is None
    assert any(w["code"] == "HISTORICAL_FORWARD_ASSUMPTION"
               for w in result.preflight["warnings"])


def test_historical_margin_needs_forward_assumption_and_unsupported_wacc_fails():
    historical_margin = FinancialMetric(ticker=TICKER, report_id=RID,
        name="operating_margin", value=15, unit=Unit.PERCENTAGE,
        period_start=date(2025, 7, 1), period_end=date(2026, 6, 30),
        source="SYNTHETIC annual results", source_date=date(2026, 7, 1),
        source_type=SourceType.COMPANY_DISCLOSURE,
        assumption_type=AssumptionType.HISTORICAL_ACTUAL,
        source_id="synthetic:margin", evidence_verified=True,
        evidence_quote="Synthetic historical margin")
    margin, _ = validate_candidate(candidate(historical_margin, RID,
        "operating_margin", "base", "Unapproved forward extrapolation"), [historical_margin])
    assert margin.validation_status.value == "ineligible"
    unsupported = FinancialMetric(ticker=TICKER, report_id=RID, name="wacc",
        value=12, unit=Unit.PERCENTAGE, currency="ZAR",
        source="SYNTHETIC unsupported number", source_type=SourceType.MODEL,
        assumption_type=AssumptionType.MODEL_ASSUMPTION)
    reviewed, _ = validate_candidate(candidate(unsupported, RID, "wacc", "base", "No derivation"), [unsupported])
    assert reviewed.validation_status.value == "ineligible"
    assert "WACC_UNSUPPORTED" in {w.code for w in reviewed.warnings}


def test_direct_cash_flow_field_uses_forecast_boundary():
    from modules.analysis.valuation.engine import run_valuation
    plan = retailer_fixture()
    metrics, candidates = compile_plan_inputs(plan, [])
    old = next(c for c in candidates if c.valuation_field.value == "corporate_cost" and
               c.source_metric.period_end == date(2027, 6, 30))
    historical = FinancialMetric(metric_id=old.metric_id, ticker=TICKER, report_id=RID,
        name="corporate_cost", value=old.selected_value, unit=Unit.ZAR, currency="ZAR",
        period_start=date(2025, 7, 1), period_end=date(2026, 6, 30),
        source_date=date(2026, 7, 1), source="SYNTHETIC prior-year report",
        source_type=SourceType.COMPANY_DISCLOSURE,
        assumption_type=AssumptionType.HISTORICAL_ACTUAL,
        source_id="synthetic:old_corporate", evidence_verified=True,
        evidence_quote="Synthetic historical corporate cost")
    old_candidate = candidate(historical, RID, "corporate_cost", "base", "Synthetic stale value")
    metrics = [historical if m.metric_id == old.metric_id else m for m in metrics]
    candidates = [old_candidate if c.metric_id == old.metric_id else c for c in candidates]
    result = run_valuation(ticker=TICKER, report_version_id=RID, metrics=metrics,
                           candidates=candidates, plan=plan.engine_plan)
    assert result.status.value == "FAIL" and result.target_price is None
    assert any("historical actual cannot silently become a forecast input" in x
               for x in result.methods["DCF"].warnings)


def test_retailer_driver_storage_is_optional_and_not_a_dcf_requirement():
    for name, unit in {"gross_profit": Unit.ZAR, "gross_margin": Unit.PERCENTAGE,
                       "operating_profit": Unit.ZAR, "ebitda": Unit.ZAR,
                       "inventory": Unit.ZAR, "operating_cash_flow": Unit.ZAR,
                       "free_cash_flow": Unit.ZAR}.items():
        metric = FinancialMetric(ticker=TICKER, report_id=RID, name=name,
            value=1, unit=unit, source="SYNTHETIC test",
            source_type=SourceType.MODEL, assumption_type=AssumptionType.MODEL_ASSUMPTION)
        assert metric.name == name
    drivers = [ForecastAssumption(field=field, value=D(value), unit=unit,
        period_label="FY2027", origin=Origin.ANALYST_ASSUMPTION,
        approval_state=ApprovalState.PROPOSED, rationale="SYNTHETIC retailer driver",
        created_by="test fixture") for field,value,unit in
        (("store_count", 100, "stores"), ("new_store_openings", 5, "stores"),
         ("like_for_like_growth", 3, "percentage"), ("inventory_days", 60, "days"),
         ("online_sales", 50, "ZAR"), ("capex_per_store", 2, "ZAR"))]
    draft = ForecastPlan(ticker=TICKER, created_by="test fixture", source_report_version_id=RID,
        horizon=[ForecastPeriod(label="FY2027", start=date(2026, 7, 1), end=date(2027, 6, 30))],
        assumptions=drivers)
    assert len(draft.assumptions) == 6 and draft.engine_plan is None
    assert value(retailer_fixture()).methods["DCF"].status.value == "PASS"

