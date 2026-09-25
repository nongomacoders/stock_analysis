"""Comprehensive integration test for TRU first historical backtest: accept, map, lock and run."""
from datetime import date
from decimal import Decimal
import pytest
from modules.analysis.forecast_plan import ApprovalState, ForecastAssumption, Origin
from modules.analysis.historical_backtest import (
    BacktestStatus, lock_backtest, backtest_input_hash
)
from modules.analysis.historical_plan import (
    HistoricalPlanStatus, create_historical_draft,
    approve_historical_plan_in_place, lock_historical_plan, historical_plan_input_hash
)
from modules.analysis.historical_mapping import (
    map_historical_fy2026_dcf, map_historical_equity_bridge, evaluate_historical_plan_readiness
)
from modules.analysis.historical_dcf_execution import execute_historical_dcf

def _build_tru_reviewed_assumptions():
    return [
        ForecastAssumption(
            field="revenue_growth", value=Decimal("5.0"), unit="percentage",
            period_label="FY2026", operation_segment="Group", origin=Origin.ANALYST_ASSUMPTION,
            approval_state=ApprovalState.ACCEPTED,
            rationale="FY25 baseline 4.9% anchored; modest inflation expansion",
            source_document_id="AFS_2025_REV", created_by="analyst"
        ),
        ForecastAssumption(
            field="sale_of_merchandise_growth", value=Decimal("4.0"), unit="percentage",
            period_label="FY2026", operation_segment="Group", origin=Origin.ANALYST_ASSUMPTION,
            approval_state=ApprovalState.ACCEPTED,
            rationale="FY25 baseline 3.9% merchandise sales growth trend",
            source_document_id="AFS_2025_SALES", created_by="analyst"
        ),
        ForecastAssumption(
            field="trading_margin", value=Decimal("13.56"), unit="percentage",
            period_label="FY2026", operation_segment="Group", origin=Origin.ANALYST_ASSUMPTION,
            approval_state=ApprovalState.ACCEPTED,
            rationale="FY25 baseline trading margin (2.892bn / 21.323bn = 13.56%) sustained",
            source_document_id="AFS_2025_MARGIN", created_by="analyst"
        ),
        ForecastAssumption(
            field="depreciation", value=Decimal("1500000000"), unit="ZAR",
            period_label="FY2026", operation_segment="Group", origin=Origin.ANALYST_ASSUMPTION,
            approval_state=ApprovalState.ACCEPTED,
            rationale="FY25 baseline D&A of R1.480bn with slight store renewal step-up",
            source_document_id="AFS_2025_DEP", created_by="analyst"
        ),
        ForecastAssumption(
            field="tax_rate", value=Decimal("25.4"), unit="percentage",
            period_label="FY2026", operation_segment="Group", origin=Origin.ANALYST_ASSUMPTION,
            approval_state=ApprovalState.ACCEPTED,
            rationale="Statutory and effective tax rate (AFS Note 29.2)",
            source_document_id="AFS_2025_TAX", created_by="analyst"
        ),
        ForecastAssumption(
            field="total_capex", value=Decimal("674000000"), unit="ZAR",
            period_label="FY2026", operation_segment="Group", origin=Origin.ANALYST_ASSUMPTION,
            approval_state=ApprovalState.ACCEPTED,
            rationale="FY25 baseline capex R674m maintained",
            source_document_id="AFS_2025_CAPEX", created_by="analyst"
        ),
        ForecastAssumption(
            field="working_capital", value=Decimal("0"), unit="ZAR",
            period_label="FY2026", operation_segment="Group", origin=Origin.ANALYST_ASSUMPTION,
            approval_state=ApprovalState.ACCEPTED,
            rationale="Working capital variation normalized to zero",
            created_by="analyst"
        ),
        ForecastAssumption(
            field="other_recurring_cash", value=Decimal("0"), unit="ZAR",
            period_label="FY2026", operation_segment="Group", origin=Origin.ANALYST_ASSUMPTION,
            approval_state=ApprovalState.ACCEPTED,
            rationale="No non-operational recurring cash items",
            created_by="analyst"
        ),
        ForecastAssumption(
            field="wacc", value=Decimal("14.86"), unit="percentage",
            period_label="FY2026", operation_segment="Group", origin=Origin.ANALYST_ASSUMPTION,
            approval_state=ApprovalState.ACCEPTED,
            rationale="Dated market inputs 2025-08-31: Rf=10.25%, beta=0.92, ERP=6.00%, pre-tax Kd=8.59%, Wd=9.75%",
            created_by="analyst"
        ),
        ForecastAssumption(
            field="terminal_growth", value=Decimal("4.5"), unit="percentage",
            period_label="FY2026", operation_segment="Group", origin=Origin.ANALYST_ASSUMPTION,
            approval_state=ApprovalState.ACCEPTED,
            rationale="Long-run SA inflation midpoint as of 2025-08-31",
            created_by="analyst"
        ),
        ForecastAssumption(
            field="lease_adjustments", value=Decimal("3742000000"), unit="ZAR",
            period_label="FY2026", operation_segment="Group", origin=Origin.ANALYST_ASSUMPTION,
            approval_state=ApprovalState.ACCEPTED,
            rationale="FY25 baseline lease liabilities (Note 17)",
            source_document_id="AFS_2025_LEASE", created_by="analyst"
        ),
        ForecastAssumption(
            field="minorities", value=Decimal("0"), unit="ZAR",
            period_label="FY2026", operation_segment="Group", origin=Origin.ANALYST_ASSUMPTION,
            approval_state=ApprovalState.ACCEPTED,
            rationale="No non-controlling interests",
            created_by="analyst"
        ),
        ForecastAssumption(
            field="non_operating_assets", value=Decimal("0"), unit="ZAR",
            period_label="FY2026", operation_segment="Group", origin=Origin.ANALYST_ASSUMPTION,
            approval_state=ApprovalState.ACCEPTED,
            rationale="No separate non-operating assets",
            created_by="analyst"
        ),
        ForecastAssumption(
            field="other_equity_adjustments", value=Decimal("0"), unit="ZAR",
            period_label="FY2026", operation_segment="Group", origin=Origin.ANALYST_ASSUMPTION,
            approval_state=ApprovalState.ACCEPTED,
            rationale="No other equity adjustments",
            created_by="analyst"
        ),
    ]

def test_tru_first_historical_backtest_full_run(cached_tru_backtest):
    bt = cached_tru_backtest
    assert bt.as_of_date == date(2025, 8, 31)
    
    # 1. Create draft plan and apply reviewed assumptions
    plan = create_historical_draft(bt)
    plan.assumptions = _build_tru_reviewed_assumptions()
    
    # 2. Map DCF and Equity Bridge
    plan, dcf_preview = map_historical_fy2026_dcf(plan, bt)
    plan, eq_preview = map_historical_equity_bridge(plan, bt)
    
    # 3. Check readiness
    readiness = evaluate_historical_plan_readiness(plan, bt)
    assert readiness["baseline"] == "READY"
    assert readiness["assumptions"] == "READY"
    assert readiness["dcf_mapping"] == "READY"
    assert readiness["equity_bridge"] == "READY"
    assert readiness["all_mappings_complete"] is True
    
    # 4. Approve plan in place
    approved = approve_historical_plan_in_place(plan, reviewer="Dion")
    assert approved.status == HistoricalPlanStatus.APPROVED
    assert approved.approved_by == "Dion"
    
    # 5. Lock plan and lock backtest
    locked_plan = lock_historical_plan(approved, bt)
    assert locked_plan.is_locked is True
    assert locked_plan.status == HistoricalPlanStatus.LOCKED
    
    frozen_plan_hash = historical_plan_input_hash(locked_plan)
    assert locked_plan.input_hash == frozen_plan_hash
    
    locked_bt = lock_backtest(bt, locked_plan, engine_version="historical_dcf_v1")
    assert locked_bt.status == BacktestStatus.LOCKED
    assert locked_bt.input_hash != ""
    
    # 6. Execute deterministic historical DCF
    val = execute_historical_dcf(locked_plan, locked_bt)
    
    # 7. Verify outputs
    assert val.forecast_revenue == Decimal("24224550000.00")
    assert val.forecast_sale_of_merchandise == Decimal("22175920000.00")
    assert val.forecast_trading_profit == Decimal("3007054752.000000")
    assert val.forecast_fcf == Decimal("3069262844.992000000")
    assert val.wacc == Decimal("14.86")
    assert val.terminal_growth == Decimal("4.5")
    
    # Explicit PV and TV
    assert val.pv_explicit.quantize(Decimal("1")) == Decimal("2738100472")
    assert val.terminal_value_undiscounted.quantize(Decimal("1")) == Decimal("30959263253")
    assert val.terminal_value_pv.quantize(Decimal("1")) == Decimal("27618870589")
    assert val.terminal_value_percentage_of_ev == Decimal("90.98")
    assert val.enterprise_value.quantize(Decimal("1")) == Decimal("30356971061")
    
    # Equity Bridge
    assert val.net_cash == Decimal("720000000")
    assert val.lease_adjustment == Decimal("3742000000")
    assert val.contractual_debt_for_wacc == Decimal("2443000000")
    assert val.equity_value.quantize(Decimal("1")) == Decimal("27334971061")
    assert val.shares == Decimal("375360899")
    
    # Fair Value and Upside
    assert val.historical_fair_value == Decimal("72.82")
    assert val.historical_market_price == Decimal("60.22")
    assert val.implied_upside_downside_pct == Decimal("20.93")
    
    # Warnings
    assert "SHORT_EXPLICIT_FORECAST_HORIZON" in val.warnings
    assert "TERMINAL_VALUE_CONCENTRATION" in val.warnings
    assert any("R2030" in w for w in val.warnings)
