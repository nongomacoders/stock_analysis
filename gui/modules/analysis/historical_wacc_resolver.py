"""Dedicated resolver and calculator for historical WACC and macro inputs."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any
from modules.analysis.historical_market_inputs import (
    HistoricalMarketInput, InputScope, MarketConcept, ProvenanceQuality,
    check_bond_remaining_maturity, propagate_calculation_provenance
)
from modules.data.historical_market_storage import list_historical_market_inputs
from modules.analysis.valuation.models import Basis
from modules.analysis.valuation.wacc import WaccInputs, calculate_wacc

@dataclass(frozen=True)
class ResolvedMarketComponent:
    concept: str
    observation: HistoricalMarketInput
    value: Decimal
    unit: str
    observation_date: date
    available_date: date
    lag_days: int
    source: str
    methodology: str | None = None
    provenance: str = "analyst_entered"

@dataclass
class HistoricalWaccResolution:
    status: str  # "READY" or "NOT_CALCULABLE"
    ticker: str
    as_of_date: date
    components: dict[str, ResolvedMarketComponent] = field(default_factory=dict)
    missing_components: list[str] = field(default_factory=list)
    beta_candidates: list[HistoricalMarketInput] = field(default_factory=list)
    calculated_wacc: Decimal | None = None
    cost_of_equity: Decimal | None = None
    cost_of_debt_after_tax: Decimal | None = None
    debt_weight: Decimal | None = None
    equity_weight: Decimal | None = None
    notes: list[str] = field(default_factory=list)
    evidence_quality: str = "INSUFFICIENT"
    methodological_status: str = "BLOCKED"
    cost_of_equity_provenance: str = "historically_anchored_analyst_calculation"
    cost_of_debt_provenance: str = "derived_from_source_document"
    wacc_provenance: str = "historically_anchored_analyst_calculation"
    capital_weights_provenance: str = "derived_from_source_document"
    provenance_summary: dict[str, int] = field(default_factory=dict)
    market_input_tokens: list[str] = field(default_factory=list)

@dataclass
class HistoricalMacroResolution:
    status: str  # "READY" or "INCOMPLETE"
    as_of_date: date
    inflation_long_run: ResolvedMarketComponent | None = None
    nominal_gdp_growth_long_run: ResolvedMarketComponent | None = None
    missing_components: list[str] = field(default_factory=list)
    evidence_quality: str = "INSUFFICIENT"
    market_input_tokens: list[str] = field(default_factory=list)

def _select_latest(items: list[HistoricalMarketInput], as_of_date: date) -> HistoricalMarketInput | None:
    valid = [x for x in items if x.available_date <= as_of_date and x.is_active]
    return max(valid, key=lambda x: (x.available_date, x.revision, x.observation_date)) if valid else None

def derive_historical_capital_weights(backtest) -> tuple[Decimal, Decimal, str]:
    from modules.analysis.historical_retail_bridge import get_fy2025_baseline_values
    b = get_fy2025_baseline_values(backtest)
    shares = b.get("external_shares") or Decimal("375360899")
    price = b.get("market_price") or Decimal("60.22")
    mkt_equity = shares * price
    # Contractual debt principal: RCF R1,200m + Green loan R268m + Overdraft R975m = R2,443m
    debt_principal = Decimal("2443000000")
    total_cap = mkt_equity + debt_principal
    if total_cap > 0:
        d_weight = (debt_principal / total_cap).quantize(Decimal("0.0001"))
        note = (
            f"Derived from FY25 baseline: Mkt Equity R{mkt_equity/1000000000:.3f}bn, "
            f"Contractual Debt Principal R{debt_principal/1000000000:.3f}bn (reconciles with Kd components; "
            f"excludes R11m accrued interest Note 16 p. 56; carrying debt was R2.454bn)."
        )
        return d_weight, Decimal("1.0") - d_weight, note
    return Decimal("0.0975"), Decimal("0.9025"), "Default capital weights fallback"

def _assess_quality(components: list[ResolvedMarketComponent]) -> tuple[str, str, dict[str, int]]:
    summary: dict[str, int] = {}
    for c in components:
        q = c.observation.provenance_quality.value; summary[q] = summary.get(q, 0) + 1
    has_src = summary.get("raw_source_fact", 0) + summary.get("derived_from_source_document", 0) + summary.get("source_document_backed", 0) + summary.get("provider_record_backed", 0)
    has_man = summary.get("analyst_entered_historical_observation", 0) + summary.get("analyst_valuation_assumption", 0) + summary.get("historically_anchored_analyst_calculation", 0) + summary.get("analyst_entered", 0) + summary.get("manually_transcribed", 0)
    if not components: return "INSUFFICIENT", "BLOCKED", summary
    eq = "MIXED" if (has_src and has_man) else ("VERIFIED" if has_src else "MANUAL")
    return eq, ("READY_WITH_MANUAL_INPUTS" if has_man else "READY"), summary

def _make_comp(concept: str, item: HistoricalMarketInput, as_of: date) -> ResolvedMarketComponent:
    return ResolvedMarketComponent(
        concept, item, item.value, item.unit, item.observation_date, item.available_date,
        (as_of - item.observation_date).days, item.provider, item.source_methodology,
        item.provenance_quality.value
    )

def resolve_historical_wacc(backtest, tax_rate_override: Decimal | None = None) -> HistoricalWaccResolution:
    as_of = backtest.as_of_date; ticker = backtest.ticker
    res = HistoricalWaccResolution(status="NOT_CALCULABLE", ticker=ticker, as_of_date=as_of)
    all_inputs = list_historical_market_inputs(max_available_date=as_of)
    
    # 1. Beta
    betas = [x for x in all_inputs if x.scope == InputScope.COMPANY and x.ticker == ticker.upper() and x.concept == MarketConcept.BETA]
    res.beta_candidates = sorted(betas, key=lambda x: (x.available_date, x.revision), reverse=True)
    latest_beta = _select_latest(betas, as_of)
    if latest_beta: res.components["beta"] = _make_comp("beta", latest_beta, as_of)
    else: res.missing_components.append("beta")
    # 2. Risk-free rate
    rfr_list = [x for x in all_inputs if x.scope == InputScope.MARKET and x.concept == MarketConcept.RISK_FREE_RATE]
    latest_rfr = _select_latest(rfr_list, as_of)
    if latest_rfr:
        res.components["risk_free_rate"] = _make_comp("risk_free_rate", latest_rfr, as_of)
        if "R2030" in (latest_rfr.source_methodology or "") or "R2030" in (latest_rfr.notes or ""):
            b_chk = check_bond_remaining_maturity("R2030", date(2030, 1, 31), as_of)
            res.notes.append(f"Risk-free proxy R2030 has {b_chk['remaining_years']}Y remaining tenor; short of standard 10Y DCF convention")
    else: res.missing_components.append("risk_free_rate")
    # 3. Equity Risk Premium
    erp_list = [x for x in all_inputs if x.scope == InputScope.MARKET and x.concept == MarketConcept.EQUITY_RISK_PREMIUM]
    latest_erp = _select_latest(erp_list, as_of)
    if latest_erp: res.components["equity_risk_premium"] = _make_comp("equity_risk_premium", latest_erp, as_of)
    else: res.missing_components.append("equity_risk_premium")
    # 4. Cost of debt
    cod_list = [x for x in all_inputs if x.scope == InputScope.COMPANY and x.ticker == ticker.upper() and x.concept == MarketConcept.COST_OF_DEBT]
    latest_cod = _select_latest(cod_list, as_of)
    if latest_cod:
        res.components["cost_of_debt"] = _make_comp("cost_of_debt", latest_cod, as_of)
        if latest_cod.value == Decimal("9.80"):
            res.notes.append("Cost of debt 9.80% corresponds to FY2024 prior-year overdraft rate in Note 25.3.2; FY2025 derived rate is 8.59%")
    else: res.missing_components.append("cost_of_debt")

    # 5. Capital weights & tax
    d_wt, e_wt, wt_note = derive_historical_capital_weights(backtest)
    res.debt_weight = d_wt; res.equity_weight = e_wt; res.notes.append(wt_note)
    tax = tax_rate_override or Decimal("0.254")

    if not res.missing_components:
        c = res.components
        to_dec = lambda x: x / (100 if x > 1 else 1)
        inputs = WaccInputs(
            risk_free_rate=to_dec(c["risk_free_rate"].value), equity_risk_premium=to_dec(c["equity_risk_premium"].value),
            beta=c["beta"].value, country_risk_premium=Decimal("0"), cost_of_debt=to_dec(c["cost_of_debt"].value),
            tax_rate=tax, debt_weight=d_wt, equity_weight=e_wt, currency="ZAR", basis=Basis.NOMINAL, inflation_basis="ZAR_CPI"
        )
        out = calculate_wacc(inputs)
        res.status = "READY"
        res.calculated_wacc = (Decimal(str(out["wacc"])) * 100).quantize(Decimal("0.01"))
        res.cost_of_equity = (Decimal(str(out["cost_of_equity"])) * 100).quantize(Decimal("0.01"))
        res.cost_of_debt_after_tax = (Decimal(str(out["cost_of_debt_after_tax"])) * 100).quantize(Decimal("0.01"))
        
        # Provenance propagation
        ke_prov = propagate_calculation_provenance([
            res.components["risk_free_rate"].observation.provenance_quality,
            res.components["beta"].observation.provenance_quality,
            res.components["equity_risk_premium"].observation.provenance_quality
        ])
        kd_prov = res.components["cost_of_debt"].observation.provenance_quality
        wacc_prov = propagate_calculation_provenance([
            ke_prov, kd_prov, ProvenanceQuality.RAW_SOURCE_FACT, ProvenanceQuality.DERIVED_FROM_SOURCE_DOCUMENT
        ])
        res.cost_of_equity_provenance = ke_prov.value
        res.cost_of_debt_provenance = kd_prov.value
        res.wacc_provenance = wacc_prov.value
        res.evidence_quality, res.methodological_status, res.provenance_summary = _assess_quality(list(res.components.values()))
        res.market_input_tokens = [
            f"{c.observation.input_id}:r{c.observation.revision}:{c.observation.input_hash}:{c.observation.evidence_hash or ''}"
            for c in res.components.values()
        ]
    return res

def resolve_historical_macro(as_of_date: date) -> HistoricalMacroResolution:
    res = HistoricalMacroResolution(status="INCOMPLETE", as_of_date=as_of_date)
    all_inputs = list_historical_market_inputs(max_available_date=as_of_date)
    inf_list = [x for x in all_inputs if x.scope == InputScope.MARKET and x.concept == MarketConcept.INFLATION_LONG_RUN]
    latest_inf = _select_latest(inf_list, as_of_date)
    if latest_inf: res.inflation_long_run = _make_comp("inflation_long_run", latest_inf, as_of_date)
    else: res.missing_components.append("inflation_long_run")
    gdp_list = [x for x in all_inputs if x.scope == InputScope.MARKET and x.concept == MarketConcept.NOMINAL_GDP_GROWTH_LONG_RUN]
    latest_gdp = _select_latest(gdp_list, as_of_date)
    if latest_gdp: res.nominal_gdp_growth_long_run = _make_comp("nominal_gdp_growth_long_run", latest_gdp, as_of_date)
    if res.inflation_long_run:
        res.status = "READY"
        comps = [res.inflation_long_run] + ([res.nominal_gdp_growth_long_run] if res.nominal_gdp_growth_long_run else [])
        q, _, _ = _assess_quality(comps)
        res.evidence_quality = q
        res.market_input_tokens = [
            f"{c.observation.input_id}:r{c.observation.revision}:{c.observation.input_hash}:{c.observation.evidence_hash or ''}"
            for c in comps
        ]
    return res

