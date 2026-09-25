"""Tests for historical DCF mapping, equity bridge, lifecycle, immutability and persistence."""
from datetime import date
from decimal import Decimal
import pytest
from modules.analysis.forecast_plan import ApprovalState, ForecastAssumption, Origin
from modules.analysis.historical_backtest import require_reveal_allowed
from modules.analysis.historical_plan import (
    HistoricalForecastPlan, HistoricalPlanStatus, create_historical_draft,
    approve_historical_plan_in_place, clone_historical_draft, lock_historical_plan
)
from modules.analysis.historical_mapping import (
    map_historical_fy2026_dcf, map_historical_equity_bridge, evaluate_historical_plan_readiness
)

def _populate_full_assumptions(plan: HistoricalForecastPlan, wacc_val=Decimal("13.0"), tg_val=Decimal("4.5")):
    plan.assumptions = [
        ForecastAssumption(field="revenue_growth", value=Decimal("5.0"), unit="percentage", period_label="FY2026", operation_segment="Group", origin=Origin.ANALYST_ASSUMPTION, approval_state=ApprovalState.ACCEPTED, rationale="Guidance", created_by="analyst"),
        ForecastAssumption(field="sale_of_merchandise_growth", value=Decimal("4.5"), unit="percentage", period_label="FY2026", operation_segment="Group", origin=Origin.ANALYST_ASSUMPTION, approval_state=ApprovalState.ACCEPTED, rationale="Guidance", created_by="analyst"),
        ForecastAssumption(field="trading_margin", value=Decimal("13.5"), unit="percentage", period_label="FY2026", operation_segment="Group", origin=Origin.ANALYST_ASSUMPTION, approval_state=ApprovalState.ACCEPTED, rationale="Margin history", created_by="analyst"),
        ForecastAssumption(field="depreciation", value=Decimal("1550000000"), unit="ZAR", period_label="FY2026", operation_segment="Group", origin=Origin.ANALYST_ASSUMPTION, approval_state=ApprovalState.ACCEPTED, rationale="Slight increase", created_by="analyst"),
        ForecastAssumption(field="tax_rate", value=Decimal("25.4"), unit="percentage", period_label="FY2026", operation_segment="Group", origin=Origin.ANALYST_ASSUMPTION, approval_state=ApprovalState.ACCEPTED, rationale="AFS Note 29.2", created_by="analyst"),
        ForecastAssumption(field="total_capex", value=Decimal("700000000"), unit="ZAR", period_label="FY2026", operation_segment="Group", origin=Origin.ANALYST_ASSUMPTION, approval_state=ApprovalState.ACCEPTED, rationale="Planned capex", created_by="analyst"),
        ForecastAssumption(field="working_capital", value=Decimal("150000000"), unit="ZAR", period_label="FY2026", operation_segment="Group", origin=Origin.ANALYST_ASSUMPTION, approval_state=ApprovalState.ACCEPTED, rationale="Working capital normalization", created_by="analyst"),
        ForecastAssumption(field="other_recurring_cash", value=Decimal("0"), unit="ZAR", period_label="FY2026", operation_segment="Group", origin=Origin.ANALYST_ASSUMPTION, approval_state=ApprovalState.ACCEPTED, rationale="None expected", created_by="analyst"),
        ForecastAssumption(field="wacc", value=wacc_val, unit="percentage", period_label="FY2026", operation_segment="Group", origin=Origin.ANALYST_ASSUMPTION, approval_state=ApprovalState.ACCEPTED, rationale="Historical 2025 market inputs", created_by="analyst"),
        ForecastAssumption(field="terminal_growth", value=tg_val, unit="percentage", period_label="FY2026", operation_segment="Group", origin=Origin.ANALYST_ASSUMPTION, approval_state=ApprovalState.ACCEPTED, rationale="Long run SA inflation target", created_by="analyst"),
    ]

def test_historical_dcf_mapping_and_terminal_growth_consistency(cached_tru_backtest):
    bt = cached_tru_backtest
    plan = create_historical_draft(bt)
    _populate_full_assumptions(plan, wacc_val=Decimal("13.0"), tg_val=Decimal("4.5"))
    mapped, preview = map_historical_fy2026_dcf(plan, bt)
    assert preview["status"] == "MAPPED"
    assert preview["wacc"] == Decimal("13.0")
    assert preview["terminal_growth"] == Decimal("4.5")
    dcf = mapped.engine_plan["cases"]["base"]["dcf"]
    assert dcf["terminal_method"] == "perpetuity_growth"
    assert "revenue" in dcf["years"][0]["inputs"]
    assert "ebit" in dcf["years"][0]["inputs"]
    bad_plan = create_historical_draft(bt)
    _populate_full_assumptions(bad_plan, wacc_val=Decimal("10.0"), tg_val=Decimal("12.0"))
    with pytest.raises(ValueError, match="must be less than WACC"):
        map_historical_fy2026_dcf(bad_plan, bt)

def test_historical_equity_bridge_maps_fy2025_baseline_without_fy2026_leakage(cached_tru_backtest):
    bt = cached_tru_backtest
    plan = create_historical_draft(bt)
    mapped, preview = map_historical_equity_bridge(plan, bt)
    assert preview["status"] == "MAPPED"
    assert preview["lease_treatment"] == "lease_debt_adjustment"
    eq = mapped.equity_spec
    assert eq["adjustments"]["net_cash"]["value"] == "720000000"
    assert eq["adjustments"]["lease_adjustments"]["value"] == "3742000000"
    assert eq["shares"]["value"] == "375360899"

def test_approval_in_place_and_lock_immutability(cached_tru_backtest):
    bt = cached_tru_backtest
    plan = create_historical_draft(bt)
    _populate_full_assumptions(plan)
    map_historical_fy2026_dcf(plan, bt)
    map_historical_equity_bridge(plan, bt)
    initial_id = plan.historical_plan_id
    initial_version = plan.plan_version
    approved = approve_historical_plan_in_place(plan, reviewer="Dion")
    assert approved.status == HistoricalPlanStatus.APPROVED
    assert approved.historical_plan_id == initial_id
    assert approved.plan_version == initial_version
    assert approved.approved_by == "Dion"
    assert approved.approved_at is not None
    with pytest.raises(ValueError, match="Reveal next-period actuals requires a locked historical plan"):
        require_reveal_allowed(bt)
    locked = lock_historical_plan(approved, bt)
    assert locked.status == HistoricalPlanStatus.LOCKED
    assert locked.is_locked is True
    with pytest.raises(ValueError, match="locked"):
        approve_historical_plan_in_place(locked, reviewer="Dion")

def test_clone_approved_plan_increments_version_and_resets_draft(cached_tru_backtest):
    bt = cached_tru_backtest
    plan = create_historical_draft(bt)
    _populate_full_assumptions(plan)
    approved = approve_historical_plan_in_place(plan, reviewer="Dion")
    cloned = clone_historical_draft(approved, changed_by="analyst_2")
    assert cloned.plan_version == 2
    assert cloned.status == HistoricalPlanStatus.DRAFT
    assert cloned.historical_plan_id != approved.historical_plan_id
    assert cloned.previous_historical_plan_id == approved.historical_plan_id
    assert cloned.approved_at is None
    assert cloned.created_by == "analyst_2"

def test_deterministic_readiness_status(cached_tru_backtest):
    bt = cached_tru_backtest
    plan = create_historical_draft(bt)
    r_initial = evaluate_historical_plan_readiness(plan, bt)
    assert r_initial["baseline"] == "READY"
    assert "MISSING" in r_initial["assumptions"]
    assert r_initial["dcf_mapping"] == "NOT MAPPED"
    assert r_initial["valuation_execution"] == "NOT READY"
    _populate_full_assumptions(plan)
    plan_dcf, _ = map_historical_fy2026_dcf(plan, bt)
    plan_full, _ = map_historical_equity_bridge(plan_dcf, bt)
    r_full = evaluate_historical_plan_readiness(plan_full, bt)
    assert r_full["assumptions"] == "READY"
    assert r_full["dcf_mapping"] == "READY"
    assert r_full["equity_bridge"] == "READY"
    assert "READY" in r_full["wacc"]
    assert "READY" in r_full["terminal"]
    assert r_full["all_mappings_complete"] is True
