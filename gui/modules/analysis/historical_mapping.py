"""Historical DCF and equity bridge deterministic mapping and readiness evaluation."""
from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Any
from modules.analysis.forecast_plan import ApprovalState, Origin
from modules.analysis.historical_backtest import HistoricalBacktest
from modules.analysis.historical_readiness import evaluate_historical_baseline
from modules.analysis.historical_plan import HistoricalForecastPlan, historical_plan_input_hash
from modules.analysis.historical_retail_bridge import derive_historical_retail_forecasts, get_fy2025_baseline_values
from modules.analysis.valuation.models import InputRef, TerminalMethod

def _find_accepted(plan: HistoricalForecastPlan, field: str):
    matches = [a for a in plan.assumptions if a.field == field and a.approval_state == ApprovalState.ACCEPTED and a.value is not None]
    return matches[0] if matches else None

def map_historical_fy2026_dcf(plan: HistoricalForecastPlan, backtest: HistoricalBacktest) -> tuple[HistoricalForecastPlan, dict[str, Any]]:
    bridge = derive_historical_retail_forecasts(plan, backtest)
    if bridge["status"] != "READY":
        raise ValueError(f"Historical DCF mapping blocked by missing forecast bridge: {bridge['missing']}")
    d = bridge["derived"]
    missing = []
    depr = _find_accepted(plan, "depreciation")
    if not depr: missing.append("depreciation")
    tax = _find_accepted(plan, "tax_rate")
    if not tax: missing.append("tax_rate")
    capex = _find_accepted(plan, "total_capex")
    if not capex: missing.append("total_capex")
    wc = _find_accepted(plan, "working_capital")
    if not wc: missing.append("working_capital")
    orc = _find_accepted(plan, "other_recurring_cash")
    wacc = _find_accepted(plan, "wacc")
    if not wacc: missing.append("wacc")
    tg = _find_accepted(plan, "terminal_growth")
    if not tg: missing.append("terminal_growth")
    if missing:
        raise ValueError(f"DCF mapping blocked by missing accepted assumptions: {', '.join(missing)}")
    if tg.value >= wacc.value:
        raise ValueError(f"Terminal growth ({tg.value}%) must be less than WACC ({wacc.value}%)")
    inputs = {
        "revenue": {"metric_id": str(d["forecast_revenue"]["derived_id"]), "field": "revenue", "case": "base"},
        "ebit": {"metric_id": str(d["forecast_trading_profit"]["derived_id"]), "field": "ebit", "case": "base"},
        "depreciation": {"metric_id": str(depr.assumption_id), "field": "depreciation", "case": "base"},
        "tax_rate": {"metric_id": str(tax.assumption_id), "field": "tax_rate", "case": "base"},
        "total_capex": {"metric_id": str(capex.assumption_id), "field": "total_capex", "case": "base"},
        "working_capital": {"metric_id": str(wc.assumption_id), "field": "working_capital", "case": "base"},
    }
    if orc:
        inputs["other_recurring_cash"] = {"metric_id": str(orc.assumption_id), "field": "other_recurring_cash", "case": "base"}
    period_end = date(2026, 6, 28)
    year_spec = {"period_end": period_end.isoformat(), "inputs": inputs}
    wacc_spec = {"currency": "ZAR", "basis": "nominal", "inflation_basis": "ZAR_CPI", "supported_wacc": {"metric_id": str(wacc.assumption_id), "field": "wacc", "case": "base"}}
    dcf_spec = {
        "valuation_date": plan.as_of_date.isoformat(), "years": [year_spec], "cash_flow_currency": "ZAR",
        "cash_flow_basis": "nominal", "inflation_basis": "ZAR_CPI", "wacc": wacc_spec,
        "terminal_method": "perpetuity_growth", "terminal_growth": {"metric_id": str(tg.assumption_id), "field": "terminal_growth", "case": "base"},
        "warnings": ["SHORT_EXPLICIT_FORECAST_HORIZON", "TERMINAL_VALUE_CONCENTRATION"]
    }
    cases = dict(plan.engine_plan.get("cases", {}))
    prior_case = cases.get("base", {})
    cases["base"] = {**prior_case, "primary_method": "DCF", "dcf": dcf_spec, "rationale": "Historical retailer direct-EBIT DCF"}
    new_engine = {"ticker": plan.ticker, "valuation_date": plan.as_of_date.isoformat(), "currency": "ZAR", "sector": "retail", "cases": cases}
    updated = plan.model_copy(update={"engine_plan": new_engine})
    return updated.model_copy(update={"input_hash": historical_plan_input_hash(updated)}), {
        "status": "MAPPED", "period_end": period_end, "inputs": inputs, "wacc": wacc.value, "terminal_growth": tg.value
    }

def map_historical_equity_bridge(plan: HistoricalForecastPlan, backtest: HistoricalBacktest) -> tuple[HistoricalForecastPlan, dict[str, Any]]:
    b = get_fy2025_baseline_values(backtest)
    gate = evaluate_historical_baseline(backtest)
    net_cash_id = gate.concept_statuses["net_cash_debt"].source_document_id or "net_cash_fy2025"
    lease_id = gate.concept_statuses["lease_liabilities"].source_document_id or "lease_liabilities_fy2025"
    share_id = gate.concept_statuses["historical_share_denominator"].source_document_id or "share_count_fy2025"
    min_a = _find_accepted(plan, "minorities")
    noa_a = _find_accepted(plan, "non_operating_assets")
    oea_a = _find_accepted(plan, "other_equity_adjustments")
    adjustments = {
        "net_cash": {"metric_id": net_cash_id, "field": "net_cash", "case": "base", "value": str(b["net_cash"])},
        "lease_adjustments": {"metric_id": lease_id, "field": "lease_adjustments", "case": "base", "value": str(b["lease_liabilities"])},
        "minorities": {"metric_id": str(min_a.assumption_id) if min_a else "min_default_0", "field": "minorities", "case": "base", "value": str(min_a.value if min_a else Decimal("0"))},
        "non_operating_assets": {"metric_id": str(noa_a.assumption_id) if noa_a else "noa_default_0", "field": "non_operating_assets", "case": "base", "value": str(noa_a.value if noa_a else Decimal("0"))},
        "other_equity_adjustments": {"metric_id": str(oea_a.assumption_id) if oea_a else "oea_default_0", "field": "other_equity_adjustments", "case": "base", "value": str(oea_a.value if oea_a else Decimal("0"))},
    }
    eq_spec = {
        "adjustments": adjustments,
        "shares": {"metric_id": share_id, "field": "shares", "case": "base", "value": str(b["share_denominator"])},
        "lease_treatment": "lease_debt_adjustment",
        "non_operating_asset_rationale": "FY2025 baseline evidence",
    }
    cases = dict(plan.engine_plan.get("cases", {}))
    prior_case = cases.get("base", {})
    cases["base"] = {**prior_case, "equity": eq_spec}
    new_engine = {**plan.engine_plan, "cases": cases}
    updated = plan.model_copy(update={"equity_spec": eq_spec, "engine_plan": new_engine})
    return updated.model_copy(update={"input_hash": historical_plan_input_hash(updated)}), {
        "status": "MAPPED", "adjustments": adjustments, "shares": b["share_denominator"], "lease_treatment": "lease_debt_adjustment"
    }

def evaluate_historical_plan_readiness(plan: HistoricalForecastPlan, backtest: HistoricalBacktest) -> dict[str, Any]:
    from modules.analysis.historical_wacc_resolver import resolve_historical_wacc, resolve_historical_macro
    b_ready = evaluate_historical_baseline(backtest).ready
    bridge = derive_historical_retail_forecasts(plan, backtest)
    assumptions_ready = bridge["status"] == "READY"
    dcf = plan.engine_plan.get("cases", {}).get("base", {}).get("dcf")
    dcf_ready = dcf is not None and "years" in dcf and len(dcf["years"]) > 0
    eq = plan.equity_spec or plan.engine_plan.get("cases", {}).get("base", {}).get("equity")
    eq_ready = eq is not None and "adjustments" in eq and "shares" in eq
    wacc_res = resolve_historical_wacc(backtest)
    macro_res = resolve_historical_macro(backtest.as_of_date)
    wacc_a = _find_accepted(plan, "wacc")
    tg_a = _find_accepted(plan, "terminal_growth")
    wacc_ready = wacc_a is not None
    tg_ready = tg_a is not None and (not wacc_a or tg_a.value < wacc_a.value)
    lock_status = plan.status.value.upper()
    all_ready = b_ready and assumptions_ready and dcf_ready and eq_ready and wacc_ready and tg_ready
    return {
        "baseline": "READY" if b_ready else "BLOCKED",
        "market_price": "READY",
        "wacc_inputs": "COMPLETE" if wacc_res.status == "READY" else f"INCOMPLETE ({', '.join(wacc_res.missing_components)})",
        "historical_wacc": f"READY ({wacc_res.calculated_wacc}%)" if wacc_res.status == "READY" else "NOT CALCULABLE",
        "historical_wacc_methodological_status": wacc_res.methodological_status,
        "macro_evidence": "COMPLETE" if macro_res.status == "READY" else f"INCOMPLETE ({', '.join(macro_res.missing_components)})",
        "assumptions": "READY" if assumptions_ready else f"MISSING ({', '.join(bridge.get('missing', []))})",
        "dcf_mapping": "READY" if dcf_ready else "NOT MAPPED",
        "equity_bridge": "READY" if eq_ready else "NOT MAPPED",
        "wacc_accepted": f"ACCEPTED ({wacc_a.value}%)" if wacc_ready else "NOT ACCEPTED",
        "terminal_accepted": f"ACCEPTED ({tg_a.value}%)" if tg_ready else ("INVALID (g >= WACC)" if (tg_a and wacc_a and tg_a.value >= wacc_a.value) else "NOT ACCEPTED"),
        "wacc": f"READY ({wacc_a.value}%)" if wacc_ready else "MISSING",
        "terminal": f"READY ({tg_a.value}%)" if tg_ready else ("INVALID (g >= WACC)" if (tg_a and wacc_a and tg_a.value >= wacc_a.value) else "MISSING"),
        "lock_status": lock_status,
        "plan_status": lock_status,
        "actuals": "HIDDEN",
        "valuation_execution": "READY (WAITING FOR LOCK)" if (all_ready and not plan.is_locked) else ("READY FOR EXECUTION" if (all_ready and plan.is_locked) else "NOT READY"),
        "all_mappings_complete": all_ready,
    }

def render_historical_plan_readiness(r: dict[str, Any]) -> str:
    lines = [
        "Historical Readiness",
        f"Historical baseline:       {r['baseline']}",
        f"Historical market price:   {r['market_price']}",
        f"Historical WACC inputs:    {r['wacc_inputs']}",
        f"Historical WACC:           {r['historical_wacc']}",
        f"Historical WACC method:    {r.get('historical_wacc_methodological_status', 'READY_WITH_MANUAL_INPUTS')}",
        f"Terminal-growth evidence:  {r['macro_evidence']}",
        f"Historical ForecastPlan:   {r['plan_status']}",
        f"FY2026 actuals:            {r['actuals']}",
        f"DCF execution:             {r['valuation_execution']}",
    ]
    return "\n".join(lines)
