"""Deterministic Historical DCF execution, validation, equity bridge and results."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4
from modules.analysis.forecast_plan import ApprovalState
from modules.analysis.historical_backtest import (
    BacktestStatus, HistoricalBacktest, backtest_input_hash
)
from modules.analysis.historical_plan import (
    HistoricalForecastPlan, HistoricalPlanStatus, historical_plan_input_hash
)
from modules.analysis.historical_retail_bridge import (
    derive_historical_retail_forecasts, get_fy2025_baseline_values
)
from modules.analysis.valuation.dcf import DcfInputs, ForecastYear, calculate_dcf
from modules.analysis.valuation.models import Basis, TerminalMethod
from modules.analysis.valuation.reconciliation import reconcile_equity

@dataclass
class HistoricalValuationResult:
    historical_result_id: UUID
    backtest_id: UUID
    historical_plan_id: UUID
    ticker: str
    valuation_date: date
    status: str
    forecast_revenue: Decimal
    forecast_sale_of_merchandise: Decimal
    forecast_trading_profit: Decimal
    forecast_fcf: Decimal
    wacc: Decimal
    terminal_growth: Decimal
    pv_explicit: Decimal
    terminal_value_undiscounted: Decimal
    terminal_value_pv: Decimal
    terminal_value_percentage_of_ev: Decimal
    enterprise_value: Decimal
    net_cash: Decimal
    contractual_debt_for_wacc: Decimal
    lease_adjustment: Decimal
    minorities: Decimal
    non_operating_assets: Decimal
    other_equity_adjustments: Decimal
    equity_value: Decimal
    shares: Decimal
    historical_fair_value: Decimal
    historical_market_price: Decimal
    implied_upside_downside_pct: Decimal
    warnings: list[str] = field(default_factory=list)
    plan_version: int = 1
    locked_input_hash: str = ""
    schedule: list[dict[str, Any]] = field(default_factory=list)

def validate_historical_execution_prerequisites(plan: HistoricalForecastPlan, backtest: HistoricalBacktest) -> list[str]:
    issues = []
    if backtest.status != BacktestStatus.LOCKED:
        issues.append("Backtest must be locked before execution")
    if not plan.is_locked or plan.status != HistoricalPlanStatus.LOCKED:
        issues.append("Historical ForecastPlan must be locked before execution")
    if not plan.input_hash:
        issues.append("Historical ForecastPlan must have a frozen input hash")
    wacc_a = next((a for a in plan.assumptions if a.field == "wacc" and a.approval_state == ApprovalState.ACCEPTED), None)
    tg_a = next((a for a in plan.assumptions if a.field == "terminal_growth" and a.approval_state == ApprovalState.ACCEPTED), None)
    if not wacc_a or not tg_a:
        issues.append("WACC and terminal growth must be accepted")
    elif tg_a.value >= wacc_a.value:
        issues.append(f"Perpetuity growth ({tg_a.value}%) must be strictly less than WACC ({wacc_a.value}%)")
    for ev in backtest.evidence_snapshot:
        if ev.available_date and ev.available_date > backtest.as_of_date:
            issues.append(f"FY2026 actual leakage detected: evidence {ev.evidence_id} available {ev.available_date} > {backtest.as_of_date}")
        if ev.period_end and backtest.reporting_period_end and ev.period_end > backtest.reporting_period_end:
            issues.append(f"Future period leakage: evidence {ev.evidence_id} period {ev.period_end} > {backtest.reporting_period_end}")
    if backtest.metadata.get("current_forecast_plans_used"):
        issues.append("Live ForecastPlan isolation violated")
    return issues

def execute_historical_dcf(plan: HistoricalForecastPlan, backtest: HistoricalBacktest) -> HistoricalValuationResult:
    issues = validate_historical_execution_prerequisites(plan, backtest)
    if issues:
        raise ValueError(f"Historical DCF execution blocked: {'; '.join(issues)}")
    b = get_fy2025_baseline_values(backtest)
    bridge = derive_historical_retail_forecasts(plan, backtest)
    if bridge["status"] != "READY":
        raise ValueError(f"Retail forecast bridge not ready: {bridge['missing']}")
    d = bridge["derived"]
    f_rev = d["forecast_revenue"]["value"]
    f_sale = d["forecast_sale_of_merchandise"]["value"]
    f_ebit = d["forecast_trading_profit"]["value"]
    
    acc = {a.field: a.value for a in plan.assumptions if a.approval_state == ApprovalState.ACCEPTED and a.value is not None}
    depr = acc.get("depreciation", Decimal("1500000000"))
    tax_rate = acc.get("tax_rate", Decimal("25.4")) / Decimal("100")
    capex = acc.get("total_capex", Decimal("674000000"))
    wc = acc.get("working_capital", Decimal("0"))
    orc = acc.get("other_recurring_cash", Decimal("0"))
    wacc_pct = acc.get("wacc", Decimal("14.86"))
    tg_pct = acc.get("terminal_growth", Decimal("4.5"))
    wacc_dec = wacc_pct / Decimal("100")
    tg_dec = tg_pct / Decimal("100")
    
    tax_amt = f_ebit * tax_rate
    fcf = f_ebit - tax_amt + depr - capex - wc - orc
    period_end = date(2026, 6, 28)
    
    fy = ForecastYear(
        period_end=period_end, revenue=f_rev, ebitda=f_ebit + depr, ebit=f_ebit,
        tax=tax_amt, depreciation_addback=depr, total_capex=capex,
        working_capital_change=wc, other_recurring_cash=orc, fcf=fcf
    )
    dcf_in = DcfInputs(
        valuation_date=plan.as_of_date, forecast=[fy], wacc=wacc_dec,
        cash_flow_currency="ZAR", discount_rate_currency="ZAR",
        cash_flow_basis=Basis.NOMINAL, discount_rate_basis=Basis.NOMINAL,
        cash_flow_inflation_basis="ZAR_CPI", discount_rate_inflation_basis="ZAR_CPI",
        terminal_method=TerminalMethod.PERPETUITY_GROWTH, terminal_growth=tg_dec
    )
    dcf_res = calculate_dcf(dcf_in)
    ev = Decimal(str(dcf_res.value))
    
    explicit_row = dcf_res.schedule[0]
    terminal_row = dcf_res.schedule[1]
    pv_explicit = Decimal(str(explicit_row["present_value"]))
    tv_undisc = Decimal(str(terminal_row["undiscounted_terminal_value"]))
    pv_tv = Decimal(str(terminal_row["present_value"]))
    tv_pct = (pv_tv / ev * Decimal("100")).quantize(Decimal("0.01"))
    
    net_cash = b["net_cash"]
    lease_adj = b["lease_liabilities"]
    min_adj = acc.get("minorities", Decimal("0"))
    noa_adj = acc.get("non_operating_assets", Decimal("0"))
    oea_adj = acc.get("other_equity_adjustments", Decimal("0"))
    shares = b["share_denominator"]
    
    recon = reconcile_equity(
        enterprise_or_operating_value=ev, non_operating_assets=noa_adj,
        receivables=Decimal("0"), cash=net_cash, debt=Decimal("0"),
        lease_adjustments=lease_adj, minorities=min_adj,
        other_equity_adjustments=oea_adj, forward_shares=shares,
        shares_metric_id=uuid4()
    )
    mkt_price = b["market_price"]
    fv_share = recon.rounded_target_zar
    upside = ((recon.unrounded_target_zar - mkt_price) / mkt_price * Decimal("100")).quantize(Decimal("0.01"))
    
    warnings = [
        "SHORT_EXPLICIT_FORECAST_HORIZON",
        "TERMINAL_VALUE_CONCENTRATION",
        "METHODOLOGICAL_LIMITATION: R2030 bond tenor 4.42Y duration mismatch for long-term DCF"
    ]
    return HistoricalValuationResult(
        historical_result_id=uuid4(), backtest_id=backtest.backtest_id,
        historical_plan_id=plan.historical_plan_id, ticker=plan.ticker,
        valuation_date=plan.as_of_date, status="PASS_WITH_WARNINGS",
        forecast_revenue=f_rev, forecast_sale_of_merchandise=f_sale,
        forecast_trading_profit=f_ebit, forecast_fcf=fcf, wacc=wacc_pct,
        terminal_growth=tg_pct, pv_explicit=pv_explicit,
        terminal_value_undiscounted=tv_undisc, terminal_value_pv=pv_tv,
        terminal_value_percentage_of_ev=tv_pct, enterprise_value=ev,
        net_cash=net_cash, contractual_debt_for_wacc=Decimal("2443000000"),
        lease_adjustment=lease_adj, minorities=min_adj,
        non_operating_assets=noa_adj, other_equity_adjustments=oea_adj,
        equity_value=recon.equity_value, shares=shares,
        historical_fair_value=fv_share, historical_market_price=mkt_price,
        implied_upside_downside_pct=upside, warnings=warnings,
        plan_version=plan.plan_version, locked_input_hash=backtest.input_hash or plan.input_hash,
        schedule=dcf_res.schedule
    )
