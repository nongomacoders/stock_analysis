"""Deterministic retailer forecast bridge and baseline display from historical evidence."""
from __future__ import annotations
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid5, NAMESPACE_URL
from modules.analysis.forecast_plan import ApprovalState, ForecastAssumption
from modules.analysis.historical_backtest import HistoricalBacktest
from modules.analysis.historical_readiness import evaluate_historical_baseline
from modules.analysis.historical_plan import HistoricalForecastPlan

def get_fy2025_baseline_values(backtest: HistoricalBacktest) -> dict[str, Any]:
    gate = evaluate_historical_baseline(backtest)
    statuses = gate.concept_statuses
    rev = statuses["accounting_revenue"].normalized_value or Decimal("0")
    sale = statuses["sale_of_merchandise"].normalized_value or Decimal("0")
    profit = statuses["trading_profit"].normalized_value or Decimal("0")
    margin = (profit / sale * Decimal("100")) if sale else Decimal("0")
    return {
        "accounting_revenue": rev,
        "sale_of_merchandise": sale,
        "trading_profit": profit,
        "trading_margin": margin,
        "depreciation": statuses["depreciation"].normalized_value or Decimal("0"),
        "capex": statuses["capex"].normalized_value or Decimal("0"),
        "working_capital": statuses["working_capital_baseline"].normalized_value or Decimal("0"),
        "tax_rate": statuses["tax_rate"].normalized_value or Decimal("0"),
        "net_cash": statuses["net_cash_debt"].normalized_value or Decimal("0"),
        "lease_liabilities": statuses["lease_liabilities"].normalized_value or Decimal("0"),
        "share_denominator": statuses["historical_share_denominator"].normalized_value or Decimal("0"),
        "market_price": (statuses["historical_market_price"].normalized_value or Decimal("0")) / Decimal("100"),
    }

def render_historical_baseline_display(backtest: HistoricalBacktest) -> str:
    b = get_fy2025_baseline_values(backtest)
    def fmt_r(val: Decimal, is_rate=False) -> str:
        if is_rate: return f"{val:.1f}%"
        if abs(val) >= 1_000_000_000: return f"R{val / 1_000_000_000:.3f}bn"
        if abs(val) >= 1_000_000: return f"R{val / 1_000_000:.0f}m"
        return f"R{val:,.2f}"
    margin_str = f"{b['trading_margin']:.2f}%"
    shares_m = f"{b['share_denominator'] / 1_000_000:.3f}m"
    lines = [
        "FY2025 baseline",
        "",
        f"Accounting revenue       {fmt_r(b['accounting_revenue']):<15}",
        f"Sale of merchandise      {fmt_r(b['sale_of_merchandise']):<15}",
        f"Trading profit           {fmt_r(b['trading_profit']):<15}",
        f"Trading margin           {margin_str:<15} (derived historical baseline: 2.892 / 21.323)",
        f"D&A                      {fmt_r(b['depreciation']):<15}",
        f"Capex                    {fmt_r(b['capex']):<15}",
        f"Working capital          {fmt_r(b['working_capital']):<15}",
        f"Tax rate                 {fmt_r(b['tax_rate'], is_rate=True):<15}",
        f"Net cash                 {fmt_r(b['net_cash']):<15}",
        f"Lease liabilities        {fmt_r(b['lease_liabilities']):<15}",
        f"Share denominator        {shares_m:<15}",
        f"Historical share price   R{b['market_price']:.2f}",
    ]
    return "\n".join(lines)

def make_stable_derived_id(ticker: str, as_of_date: str, period: str, field: str, base_val: Decimal, param: Decimal) -> UUID:
    name = f"historical:{ticker}:{as_of_date}:{period}:{field}:{base_val:.4f}:{param:.4f}"
    return uuid5(NAMESPACE_URL, name)

def derive_historical_retail_forecasts(plan: HistoricalForecastPlan, backtest: HistoricalBacktest) -> dict[str, Any]:
    b = get_fy2025_baseline_values(backtest)
    acc = {a.field: a for a in plan.assumptions if a.approval_state == ApprovalState.ACCEPTED and a.value is not None}
    rev_g = acc.get("revenue_growth")
    sale_g = acc.get("sale_of_merchandise_growth")
    margin_a = acc.get("trading_margin")
    ready = rev_g is not None and sale_g is not None and margin_a is not None
    if not ready:
        missing = [f for f, v in [("revenue_growth", rev_g), ("sale_of_merchandise_growth", sale_g), ("trading_margin", margin_a)] if v is None]
        return {"status": "INCOMPLETE", "missing": missing, "derived": {}}
    f_rev = b["accounting_revenue"] * (Decimal("1") + rev_g.value / Decimal("100"))
    f_sale = b["sale_of_merchandise"] * (Decimal("1") + sale_g.value / Decimal("100"))
    f_trading_profit = f_sale * (margin_a.value / Decimal("100"))
    as_of = str(plan.as_of_date)
    rev_id = make_stable_derived_id(plan.ticker, as_of, "FY2026", "revenue", b["accounting_revenue"], rev_g.value)
    sale_id = make_stable_derived_id(plan.ticker, as_of, "FY2026", "sale_of_merchandise", b["sale_of_merchandise"], sale_g.value)
    profit_id = make_stable_derived_id(plan.ticker, as_of, "FY2026", "trading_profit", f_sale, margin_a.value)
    return {
        "status": "READY",
        "derived": {
            "forecast_revenue": {"value": f_rev, "derived_id": rev_id, "formula": f"{b['accounting_revenue']} * (1 + {rev_g.value}/100)", "baseline": b["accounting_revenue"]},
            "forecast_sale_of_merchandise": {"value": f_sale, "derived_id": sale_id, "formula": f"{b['sale_of_merchandise']} * (1 + {sale_g.value}/100)", "baseline": b["sale_of_merchandise"]},
            "forecast_trading_profit": {"value": f_trading_profit, "derived_id": profit_id, "formula": f"{f_sale:.0f} * {margin_a.value}/100", "baseline_margin": b["trading_margin"]},
        }
    }
