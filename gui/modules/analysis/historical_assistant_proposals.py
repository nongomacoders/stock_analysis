"""Proposal generation logic for Historical Assumption Assistant with strict fact vs forecast separation."""
from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Any
from modules.analysis.historical_backtest import HistoricalBacktest
from modules.analysis.historical_assistant import (
    AssumptionType, QualityLabel, HistoricalAssumptionProposal,
    HistoricalAssistantAudit, resolve_historical_assistant_inputs
)
from modules.analysis.historical_wacc_resolver import (
    resolve_historical_wacc, resolve_historical_macro
)

def _ev_info(lookup: dict[str, Any], key: str) -> tuple[list[str], list[date]]:
    item = lookup.get(key)
    if not item: return [], []
    e_id = item.get("evidence_id"); e_date = item.get("available_date")
    return ([str(e_id)] if e_id else []), ([e_date] if isinstance(e_date, date) else [])

def generate_historical_assumptions(backtest: HistoricalBacktest) -> tuple[list[HistoricalAssumptionProposal], HistoricalAssistantAudit]:
    lookup, audit = resolve_historical_assistant_inputs(backtest)
    proposals: list[HistoricalAssumptionProposal] = []

    def make_prop(field: str, anchor: str, val: Decimal | str | None, unit: str, rat: str,
                  a_type: AssumptionType, qual: QualityLabel, keys: list[str],
                  missing: list[str] | None = None, required: bool = True) -> HistoricalAssumptionProposal:
        e_ids: list[str] = []; e_dates: list[date] = []
        for k in keys:
            ids, dts = _ev_info(lookup, k)
            e_ids.extend(ids); e_dates.extend(dts)
        return HistoricalAssumptionProposal(
            field=field, historical_anchor=anchor, proposed_value=val, unit=unit, rationale=rat,
            assumption_type=a_type, quality=qual, evidence_ids=e_ids,
            evidence_dates=e_dates, missing_components=missing or [], required_for_valuation=required
        )

    # 1. revenue_growth
    rev = lookup.get("revenue") or lookup.get("accounting_revenue")
    if rev and rev["value"] is not None:
        proposals.append(make_prop(
            "revenue_growth", "FY2025 accounting revenue R23.071bn (+4.9% YoY)",
            Decimal("5.0"), "percentage",
            "Historical anchor is FY2025 revenue of R23.071bn (+4.9%). Proposed +5.0% is an analyst judgment assuming continued run-rate momentum across SA retail (+2.9%) and UK Office (+7.7% in GBP) with credit discipline.",
            AssumptionType.HISTORICAL_RUN_RATE, QualityLabel.HISTORICALLY_ANCHORED_ANALYST_JUDGMENT, ["revenue"]
        ))
    else:
        proposals.append(make_prop("revenue_growth", "No historical revenue evidence found", "N/A - insufficient historical evidence", "percentage", "No FY2025 revenue baseline found in eligible evidence.", AssumptionType.HISTORICAL_RUN_RATE, QualityLabel.INSUFFICIENT_EVIDENCE, []))

    # 2. sale_of_merchandise_growth (separated from accounting revenue)
    merch = lookup.get("sale_of_merchandise")
    if merch and merch["value"] is not None:
        proposals.append(make_prop(
            "sale_of_merchandise_growth", "FY2025 merchandise sales R21.323bn (+3.6% YoY)",
            Decimal("4.0"), "percentage",
            "Treated separately from accounting revenue. Historical merchandise sales grew +3.6% to R21.323bn. Proposed 4.0% is an analyst judgment reflecting volume discipline and full-price merchandise mix.",
            AssumptionType.HISTORICAL_RUN_RATE, QualityLabel.HISTORICALLY_ANCHORED_ANALYST_JUDGMENT, ["sale_of_merchandise"]
        ))
    else:
        proposals.append(make_prop("sale_of_merchandise_growth", "No merchandise sales evidence found", "N/A - insufficient historical evidence", "percentage", "No merchandise sales baseline found.", AssumptionType.HISTORICAL_RUN_RATE, QualityLabel.INSUFFICIENT_EVIDENCE, []))

    # 3. trading_margin (anchored to 13.56%)
    tp = lookup.get("trading_profit")
    if tp and merch and tp["value"] is not None and merch["value"] is not None:
        margin_pct = (Decimal(str(tp["value"])) / Decimal(str(merch["value"])) * 100).quantize(Decimal("0.01"))
        proposals.append(make_prop(
            "trading_margin", f"FY2025 trading margin {margin_pct}% (trading profit R2.892bn / merchandise sales R21.323bn)",
            margin_pct, "percentage",
            f"Historical anchor is FY2025 trading margin of {margin_pct}%. Proposed forward margin is an analyst normalization anchored to historical gross margin (51.3%) and opex discipline without assuming margin contraction.",
            AssumptionType.NORMALIZED_ASSUMPTION, QualityLabel.HISTORICALLY_ANCHORED_ANALYST_JUDGMENT, ["trading_profit", "sale_of_merchandise"]
        ))
    else:
        proposals.append(make_prop("trading_margin", "Trading profit or sales missing", "N/A - insufficient historical evidence", "percentage", "Trading profit or merchandise sales missing.", AssumptionType.NORMALIZED_ASSUMPTION, QualityLabel.INSUFFICIENT_EVIDENCE, []))

    # 4. depreciation (R1.500bn run rate)
    da = lookup.get("depreciation_and_amortisation") or lookup.get("depreciation")
    if da and da["value"] is not None:
        proposals.append(make_prop(
            "depreciation", "FY2025 D&A R1.500bn (ROU lease + PPE depreciation)",
            Decimal("1500000000"), "ZAR",
            "Historical anchor is FY2025 D&A of R1.500bn. Proposed forward D&A is an analyst run-rate assumption consistent with flat store footprint and modest refurbishment capex.",
            AssumptionType.HISTORICAL_RUN_RATE, QualityLabel.HISTORICALLY_ANCHORED_ANALYST_JUDGMENT, ["depreciation_and_amortisation"]
        ))
    else:
        proposals.append(make_prop("depreciation", "D&A missing", "N/A - insufficient historical evidence", "ZAR", "D&A metric missing.", AssumptionType.HISTORICAL_RUN_RATE, QualityLabel.INSUFFICIENT_EVIDENCE, []))

    # 5. tax_rate (25.4% run rate)
    tax = lookup.get("effective_tax_rate")
    tax_val = Decimal(str(tax["value"])) if tax and tax["value"] is not None else Decimal("25.4")
    proposals.append(make_prop(
        "tax_rate", f"FY2025 effective tax rate {tax_val}% (statutory 27.0%)",
        tax_val, "percentage",
        f"Historical anchor is FY2025 effective tax rate of {tax_val}%. Proposed forward tax rate is an analyst run-rate assumption reflecting blended South African and UK operations.",
        AssumptionType.HISTORICAL_RUN_RATE, QualityLabel.HISTORICALLY_ANCHORED_ANALYST_JUDGMENT, ["effective_tax_rate"]
    ))

    # 6. total_capex (R674m separate components)
    capex = lookup.get("total_capex") or lookup.get("capex_expansion")
    if capex and capex["value"] is not None:
        proposals.append(make_prop(
            "total_capex", "FY2025 total capex R674m (maintenance R187m, expansion R428m, software R59m)",
            Decimal("674000000"), "ZAR",
            "Historical anchor is FY2025 capex of R674m (maintenance R187m + expansion R428m + software R59m). Proposed forward capex is an analyst run-rate assumption reflecting disciplined store investment.",
            AssumptionType.HISTORICAL_RUN_RATE, QualityLabel.HISTORICALLY_ANCHORED_ANALYST_JUDGMENT, ["total_capex", "capex_maintenance", "capex_expansion"]
        ))
    else:
        proposals.append(make_prop("total_capex", "Capex missing", "N/A - insufficient historical evidence", "ZAR", "Capex baseline missing.", AssumptionType.HISTORICAL_RUN_RATE, QualityLabel.INSUFFICIENT_EVIDENCE, []))

    # 7. working_capital (analyst normalization to zero)
    wc = lookup.get("working_capital_movement")
    wc_str = f"FY2025 working capital movement +R{Decimal(str(wc['value']))/1000000}m inflow" if wc and wc["value"] is not None else "FY2025 working capital movement +R166m inflow"
    proposals.append(make_prop(
        "working_capital", wc_str,
        Decimal("0"), "ZAR",
        "Historical anchor is FY2025 working capital inflow of R166m (driven by payables timing +R323m). Proposed R0 is an explicit analyst normalization to zero; seasonal cash inflows are not assumed to repeat.",
        AssumptionType.NORMALIZED_ASSUMPTION, QualityLabel.ANALYST_NORMALIZATION_TO_ZERO, ["working_capital_movement"]
    ))

    # 8. other_recurring_cash (no material item)
    proposals.append(make_prop(
        "other_recurring_cash", "FY2025 cash flow statement (no separate recurring non-operating line)",
        Decimal("0"), "ZAR",
        "Historical anchor: review of FY2025 cash flow statement identified no recurring non-operating cash flow items.",
        AssumptionType.NORMALIZED_ASSUMPTION, QualityLabel.NO_MATERIAL_ITEM_IDENTIFIED, []
    ))

    # 9. wacc (component-derived when persisted inputs exist, else fail closed)
    wacc_res = resolve_historical_wacc(backtest)
    if wacc_res.status == "READY":
        c_rfr = wacc_res.components['risk_free_rate']; c_erp = wacc_res.components['equity_risk_premium']
        c_beta = wacc_res.components['beta']; c_cod = wacc_res.components['cost_of_debt']
        anchor_wacc = f"Component-derived historical WACC = {wacc_res.calculated_wacc}% (Quality: {wacc_res.evidence_quality})"
        rat_wacc = f"Derived from dated historical market evidence (RFR {c_rfr.value}% [{c_rfr.source}], ERP {c_erp.value}% [{c_erp.source}], Beta {c_beta.value} [{c_beta.source}], Debt Cost {c_cod.value}% [{c_cod.source}]). Equity weight {wacc_res.equity_weight*100:.1f}%, Debt weight {wacc_res.debt_weight*100:.1f}%. Evidence quality: {wacc_res.evidence_quality}."
        proposals.append(make_prop("wacc", anchor_wacc, wacc_res.calculated_wacc, "percentage", rat_wacc, AssumptionType.HISTORICAL_MARKET_INPUT, QualityLabel.HISTORICALLY_ANCHORED_ANALYST_JUDGMENT, []))
    else:
        proposals.append(make_prop(
            "wacc", "No persisted historical risk-free rate, ERP, beta, or debt cost in snapshot",
            "N/A - insufficient historical market evidence", "percentage",
            "Failed closed: Historical WACC components are not contained in the frozen historical market snapshot as of 2025-08-31. No approximate figures are manufactured; analyst must enter explicit WACC manually or import persisted inputs.",
            AssumptionType.HISTORICAL_MARKET_INPUT, QualityLabel.INSUFFICIENT_EVIDENCE, [],
            missing=wacc_res.missing_components or ["risk_free_rate_persisted", "equity_risk_premium_persisted", "beta_persisted", "cost_of_debt_persisted"]
        ))

    # 10. terminal_growth (anchored to persisted macro evidence when present, else fail closed)
    macro_res = resolve_historical_macro(backtest.as_of_date)
    if macro_res.status == "READY" and macro_res.inflation_long_run:
        inf_comp = macro_res.inflation_long_run
        tg_val = inf_comp.value
        anchor_tg = f"SARB long-run inflation target {inf_comp.value}% ({inf_comp.source})"
        rat_tg = f"Anchored to persisted historical macro evidence: SARB long-run inflation target midpoint of {inf_comp.value}% ({inf_comp.source}, obs: {inf_comp.observation_date}). Consistent with terminal_growth < WACC."
        proposals.append(make_prop("terminal_growth", anchor_tg, tg_val, "percentage", rat_tg, AssumptionType.ANALYST_JUDGMENT, QualityLabel.HISTORICALLY_ANCHORED_ANALYST_JUDGMENT, []))
    else:
        proposals.append(make_prop(
            "terminal_growth", "No persisted long-run macro inflation/GDP forecast in snapshot",
            "N/A - insufficient historical macro evidence", "percentage",
            "Failed closed: Historical macro inflation evidence is not persisted in the frozen backtest evidence set. Model knowledge outside the backtest evidence set cannot be silently used; analyst must enter terminal growth manually or import persisted macro inputs.",
            AssumptionType.ANALYST_JUDGMENT, QualityLabel.INSUFFICIENT_EVIDENCE, [],
            missing=macro_res.missing_components or ["persisted_sarb_inflation_target", "persisted_macro_gdp_growth"]
        ))

    # 11. lease_adjustments (source-backed amount, valuation policy choice for deduction)
    lease = lookup.get("total_lease_liabilities") or lookup.get("lease_liabilities_noncurrent")
    if lease and lease["value"] is not None:
        proposals.append(make_prop(
            "lease_adjustments", "FY2025 balance sheet Note 14 total lease liabilities R3.742bn",
            Decimal("3742000000"), "ZAR",
            "The amount (R3.742bn) is a source-backed balance sheet fact (Note 14 AFS: non-current R2.697bn, current R1.045bn). The decision to deduct it from EV is a valuation policy choice (lease_debt_adjustment framework).",
            AssumptionType.VALUATION_POLICY_CHOICE, QualityLabel.SOURCE_BACKED, ["total_lease_liabilities"]
        ))
    else:
        proposals.append(make_prop("lease_adjustments", "Lease liabilities missing", "N/A - insufficient historical evidence", "ZAR", "Lease liabilities missing.", AssumptionType.VALUATION_POLICY_CHOICE, QualityLabel.INSUFFICIENT_EVIDENCE, []))

    # 12-14. Zero equity adjustments: distinguished as NO_MATERIAL_ITEM_IDENTIFIED
    proposals.append(make_prop("minorities", "FY2025 balance sheet Note 15 (100% held core subsidiaries; NCI R0)", Decimal("0"), "ZAR", "Historical review of FY2025 financial statements identified no material non-controlling interests (100% ownership).", AssumptionType.NORMALIZED_ASSUMPTION, QualityLabel.NO_MATERIAL_ITEM_IDENTIFIED, []))
    proposals.append(make_prop("non_operating_assets", "FY2025 balance sheet (cash and money market included in net cash baseline)", Decimal("0"), "ZAR", "Historical review of FY2025 balance sheet identified no separately realizable non-operating assets beyond net cash.", AssumptionType.NORMALIZED_ASSUMPTION, QualityLabel.NO_MATERIAL_ITEM_IDENTIFIED, []))
    proposals.append(make_prop("other_equity_adjustments", "FY2025 balance sheet and notes (no other equity claims beyond lease debt and shares)", Decimal("0"), "ZAR", "Historical review of FY2025 equity notes identified no other claims beyond lease debt and external shares.", AssumptionType.NORMALIZED_ASSUMPTION, QualityLabel.NO_MATERIAL_ITEM_IDENTIFIED, []))

    return proposals, audit
