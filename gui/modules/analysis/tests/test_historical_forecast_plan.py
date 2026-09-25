"""Tests for Historical ForecastPlan creation, TXT import, baseline display, and derived bridge."""
from datetime import date
from decimal import Decimal
import pytest
from modules.analysis.forecast_plan import ApprovalState, ForecastAssumption, Origin
from modules.analysis.historical_readiness import evaluate_historical_baseline
from modules.analysis.historical_plan import (
    HistoricalPlanStatus, create_historical_draft
)
from modules.analysis.historical_retail_bridge import (
    get_fy2025_baseline_values, render_historical_baseline_display,
    derive_historical_retail_forecasts, make_stable_derived_id
)
from modules.analysis.historical_forecast_txt import parse_historical_forecast_txt

def test_create_historical_draft_from_passed_baseline(cached_tru_backtest):
    bt = cached_tru_backtest
    assert evaluate_historical_baseline(bt).ready is True
    plan = create_historical_draft(bt, created_by="analyst")
    assert plan.status == HistoricalPlanStatus.DRAFT
    assert plan.plan_version == 1
    assert plan.ticker == "TRU.JO"
    assert plan.as_of_date == date(2025, 8, 31)
    assert plan.reporting_period == "FY2025"
    assert plan.reporting_period_end == date(2025, 6, 29)
    assert len(plan.assumptions) == 0
    assert len(plan.horizon) == 1
    assert plan.horizon[0].label == "FY2026"
    assert plan.audit_metadata["no_fy2026_actuals_revealed"] is True

def test_baseline_display_contains_exact_fy2025_figures_and_derived_margin(cached_tru_backtest):
    bt = cached_tru_backtest
    b = get_fy2025_baseline_values(bt)
    assert b["accounting_revenue"] == Decimal("23071000000")
    assert b["sale_of_merchandise"] == Decimal("21323000000")
    assert b["trading_profit"] == Decimal("2892000000")
    assert round(b["trading_margin"], 2) == Decimal("13.56")
    assert b["market_price"] == Decimal("60.22")
    rendered = render_historical_baseline_display(bt)
    assert "Accounting revenue       R23.071bn" in rendered
    assert "Sale of merchandise      R21.323bn" in rendered
    assert "Trading profit           R2.892bn" in rendered
    assert "Trading margin           13.56%" in rendered
    assert "D&A                      R1.500bn" in rendered
    assert "Capex                    R674m" in rendered
    assert "Net cash                 R720m" in rendered
    assert "Lease liabilities        R3.742bn" in rendered
    assert "Historical share price   R60.22" in rendered

def test_historical_txt_import_requires_backtest_header_and_starts_proposed(cached_tru_backtest):
    bt = cached_tru_backtest
    plan = create_historical_draft(bt)
    txt_content = """BACKTEST\nticker=TRU.JO\nas_of_date=2025-08-31\nforecast_period=FY2026\n\nASSUMPTION\nfield=revenue_growth\nvalue=5.0\nunit=percentage\nrationale=FY2025 SENS commentary\nanalyst=analyst\n\nASSUMPTION\nfield=trading_margin\nvalue=13.5\nunit=percentage\nrationale=Stable retail margin forecast\nanalyst=analyst\n"""
    assumptions = parse_historical_forecast_txt(txt_content, plan)
    assert len(assumptions) == 2
    for a in assumptions:
        assert a.origin == Origin.ANALYST_ASSUMPTION
        assert a.approval_state == ApprovalState.PROPOSED
        assert a.rationale != ""
    with pytest.raises(ValueError, match="ticker mismatch"):
        bad_txt = txt_content.replace("ticker=TRU.JO", "ticker=WHL.JO")
        parse_historical_forecast_txt(bad_txt, plan)

def test_derived_retail_forecast_bridge_and_stable_ids(cached_tru_backtest):
    bt = cached_tru_backtest
    plan = create_historical_draft(bt)
    plan.assumptions = [
        ForecastAssumption(field="revenue_growth", value=Decimal("5.0"), unit="percentage", period_label="FY2026", operation_segment="Group", origin=Origin.ANALYST_ASSUMPTION, approval_state=ApprovalState.ACCEPTED, rationale="Guidance", created_by="analyst"),
        ForecastAssumption(field="sale_of_merchandise_growth", value=Decimal("4.5"), unit="percentage", period_label="FY2026", operation_segment="Group", origin=Origin.ANALYST_ASSUMPTION, approval_state=ApprovalState.ACCEPTED, rationale="Guidance", created_by="analyst"),
        ForecastAssumption(field="trading_margin", value=Decimal("13.5"), unit="percentage", period_label="FY2026", operation_segment="Group", origin=Origin.ANALYST_ASSUMPTION, approval_state=ApprovalState.ACCEPTED, rationale="Margin history", created_by="analyst"),
    ]
    derived = derive_historical_retail_forecasts(plan, bt)
    assert derived["status"] == "READY"
    rev = derived["derived"]["forecast_revenue"]["value"]
    sale = derived["derived"]["forecast_sale_of_merchandise"]["value"]
    profit = derived["derived"]["forecast_trading_profit"]["value"]
    assert rev == Decimal("23071000000") * Decimal("1.05")
    assert sale == Decimal("21323000000") * Decimal("1.045")
    assert profit == sale * Decimal("0.135")
    id1 = make_stable_derived_id("TRU.JO", "2025-08-31", "FY2026", "revenue", Decimal("23071000000"), Decimal("5.0"))
    id2 = make_stable_derived_id("TRU.JO", "2025-08-31", "FY2026", "revenue", Decimal("23071000000"), Decimal("5.0"))
    assert id1 == id2
    assert derived["derived"]["forecast_revenue"]["derived_id"] == id1
