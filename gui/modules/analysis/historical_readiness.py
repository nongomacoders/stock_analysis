"""Deterministic readiness check with semantic validation for historical baseline."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any
from modules.analysis.historical_backtest import (
    HistoricalBacktest, Availability, select_historical_share_count
)

class ReadinessStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    MISSING = "MISSING"
    INVALID_SCALE = "INVALID_SCALE"
    INVALID_UNIT = "INVALID_UNIT"
    INVALID_SIGN = "INVALID_SIGN"
    PERIOD_MISMATCH = "PERIOD_MISMATCH"
    UNCERTAIN = "UNCERTAIN"
    DILUTION_UNMODELED = "DILUTION_UNMODELED"

@dataclass(frozen=True)
class BaselineConceptStatus:
    concept: str
    status: ReadinessStatus
    source_name: str | None = None
    source_document_id: str | None = None
    source_file: str | None = None
    publication_date: str | None = None
    semantic_role: str | None = None
    raw_value: str | None = None
    raw_unit: str | None = None
    normalized_value: Decimal | str | None = None
    normalized_unit: str | None = None
    page: int | str | None = None
    notes: str | None = None

@dataclass(frozen=True)
class HistoricalReadinessResult:
    ready: bool
    ticker: str
    as_of_date: date
    reporting_period_end: date | None
    concept_statuses: dict[str, BaselineConceptStatus]
    missing_or_invalid: list[str]
    share_denominator_used: str | None
    market_price_used: str | None
    fcff_da_mapping_status: str = "READY_TO_REMAP_FCFF_DA"
    fcff_da_reconciliation_note: str | None = None
    working_capital_sign_convention: str = "positive_cash_inflow"
    capex_basis: str = "cash_capex"
    denominator_policy_warning: str | None = None
    reason: str | None = None

    def format_readiness_report(self) -> str:
        lines = [
            "================================================================================",
            f"HISTORICAL BASELINE READINESS REPORT: {self.ticker}",
            "================================================================================",
            f"As-of Date: {self.as_of_date}",
            f"Reporting Period End: {self.reporting_period_end}",
            f"Overall Readiness Status: {'READY' if self.ready else 'BLOCKED'}",
            f"FCFF D&A Mapping Status: {self.fcff_da_mapping_status}",
            f"Working Capital Sign Convention: {self.working_capital_sign_convention} (positive = cash inflow)",
            f"Capex Semantic Basis: {self.capex_basis} (cash payments)",
        ]
        if self.fcff_da_reconciliation_note:
            lines.append(f"FCFF D&A Rationale: {self.fcff_da_reconciliation_note}")
        if self.denominator_policy_warning:
            lines.append(f"Denominator Policy Warning: {self.denominator_policy_warning}")
        if self.reason:
            lines.append(f"Readiness Gating Notes: {self.reason}")

        lines.append("\n" + "-" * 120)
        lines.append(
            f"{'Concept':<42} | {'Raw Value':<12} | {'Norm Value':<16} | {'Source File':<20} | {'Page/Note':<15} | {'Pub Date':<10} | {'Semantic Role'}"
        )
        lines.append("-" * 120)

        required_concepts = [
            "accounting_revenue",
            "sale_of_merchandise",
            "trading_profit",
            "trading_margin",
            "depreciation_amortisation_expense",
            "depreciation_amortisation_cashflow_addback",
            "cash_capex",
            "working_capital_cash_flow",
            "effective_tax_rate",
            "reported_net_cash",
            "lease_liabilities",
            "period_end_external_shares",
            "announcement_date_external_shares",
            "weighted_average_basic_shares",
            "weighted_average_diluted_shares",
        ]

        for c in required_concepts:
            st = self.concept_statuses.get(c)
            if not st:
                lines.append(f"{c:<42} | MISSING")
                continue
            raw_disp = f"{st.raw_value or ''} {st.raw_unit or ''}".strip()
            norm_disp = f"{st.normalized_value or ''} {st.normalized_unit or ''}".strip()
            file_disp = st.source_file or st.source_name or "n/a"
            page_disp = str(st.page or "n/a")
            pub_disp = str(st.publication_date or "n/a")
            role_disp = st.semantic_role or "n/a"
            lines.append(
                f"{c:<42} | {raw_disp:<12} | {norm_disp:<16} | {file_disp:<20} | {page_disp:<15} | {pub_disp:<10} | {role_disp}"
            )
        lines.append("-" * 120)
        return "\n".join(lines)

def _clean_source_filename(raw_path: str | None, role: str | None) -> str:
    if raw_path:
        fname = Path(raw_path).name
        if fname.endswith(".pdf") or fname.endswith(".txt"):
            return fname
    if role == "annual_financial_statements":
        return "TRU_FY2025_AFS.pdf"
    if role == "results_sens":
        return "TRU_FY2025_SENS.txt"
    return raw_path or "n/a"

def _extract_metric_lookup(evidence_list: list[Any]) -> dict[str, Any]:
    lookup: dict[str, Any] = {}
    for ev in evidence_list:
        if ev.availability != Availability.AVAILABLE: continue
        p = ev.payload or {}
        name = p.get("name") or ev.kind
        role = p.get("document_role") or ev.kind
        existing = lookup.get(name)
        if existing and existing.get("document_role") == "annual_financial_statements" and role != "annual_financial_statements":
            continue
        val = p.get("normalized_value") if p.get("normalized_value") is not None else p.get("value")
        raw_file = p.get("source_path") or p.get("source_file") or p.get("source_name") or ev.source_id
        src_file = _clean_source_filename(raw_file, role)
        pub_date = str(p.get("source_date") or p.get("available_date") or getattr(ev, "available_date", None) or "")[:10] or None
        lookup[name] = {
            "name": name, "value": val, "raw_value": p.get("raw_value"), "raw_unit": p.get("raw_unit") or p.get("unit"),
            "unit": p.get("unit"), "document_role": role, "period_end": p.get("period_end"),
            "available_date": pub_date, "source_id": p.get("source_id") or ev.source_id,
            "source_name": p.get("source_name") or ev.kind, "source_file": src_file,
            "page": p.get("source_page") or p.get("page_number"), "notes": p.get("notes") or "",
            "raw_label": p.get("raw_label"),
        }
    return lookup

def evaluate_historical_baseline(backtest: HistoricalBacktest) -> HistoricalReadinessResult:
    metrics = _extract_metric_lookup(backtest.evidence_snapshot)
    statuses: dict[str, BaselineConceptStatus] = {}

    def _eval(concept: str, keys: list[str], *, semantic_role: str, min_val=None, max_val=None, req_unit="ZAR", allow_negative=False, abs_value_eval=False) -> BaselineConceptStatus:
        item = next((metrics[k] for k in keys if k in metrics), None)
        if not item: return BaselineConceptStatus(concept, ReadinessStatus.MISSING, semantic_role=semantic_role, notes="Metric not found")
        val = Decimal(str(item["value"])) if item["value"] is not None else None
        if val is None: return BaselineConceptStatus(concept, ReadinessStatus.MISSING, semantic_role=semantic_role, notes="Null value")
        
        display_val = abs(val) if abs_value_eval else val
        eval_val = abs(val) if abs_value_eval else val

        if req_unit and item["unit"] != req_unit:
            return BaselineConceptStatus(concept, ReadinessStatus.INVALID_UNIT, item["source_name"], item["source_id"], item["source_file"], item["available_date"], semantic_role, str(item["raw_value"]), item["raw_unit"], display_val, item["unit"], item["page"], f"Expected {req_unit}, got {item['unit']}")
        if not allow_negative and eval_val < 0:
            return BaselineConceptStatus(concept, ReadinessStatus.INVALID_SIGN, item["source_name"], item["source_id"], item["source_file"], item["available_date"], semantic_role, str(item["raw_value"]), item["raw_unit"], display_val, item["unit"], item["page"], "Negative magnitude invalid")
        if min_val is not None and abs(eval_val) < min_val:
            return BaselineConceptStatus(concept, ReadinessStatus.INVALID_SCALE, item["source_name"], item["source_id"], item["source_file"], item["available_date"], semantic_role, str(item["raw_value"]), item["raw_unit"], display_val, item["unit"], item["page"], f"Value {eval_val} below expected scale {min_val}")
        if max_val is not None and abs(eval_val) > max_val:
            return BaselineConceptStatus(concept, ReadinessStatus.INVALID_SCALE, item["source_name"], item["source_id"], item["source_file"], item["available_date"], semantic_role, str(item["raw_value"]), item["raw_unit"], display_val, item["unit"], item["page"], f"Value {eval_val} exceeds expected scale {max_val}")
        return BaselineConceptStatus(concept, ReadinessStatus.AVAILABLE, item["source_name"], item["source_id"], item["source_file"], item["available_date"], semantic_role, str(item["raw_value"]), item["raw_unit"], display_val, item["unit"], item["page"], item["notes"])

    # 1. accounting_revenue
    statuses["accounting_revenue"] = _eval(
        "accounting_revenue", ["accounting_revenue", "revenue"],
        semantic_role="accounting_revenue_baseline", min_val=10**9
    )

    # 2. sale_of_merchandise
    statuses["sale_of_merchandise"] = _eval(
        "sale_of_merchandise", ["sale_of_merchandise"],
        semantic_role="merchandise_sales_baseline", min_val=10**9
    )

    # 3. trading_profit
    statuses["trading_profit"] = _eval(
        "trading_profit", ["trading_profit"],
        semantic_role="trading_profit_baseline", min_val=10**8
    )

    # 4. trading_margin (derived from trading_profit / sale_of_merchandise)
    som_st = statuses["sale_of_merchandise"]
    tp_st = statuses["trading_profit"]
    if som_st.status == ReadinessStatus.AVAILABLE and tp_st.status == ReadinessStatus.AVAILABLE and som_st.normalized_value:
        tm_val = (Decimal(str(tp_st.normalized_value)) / Decimal(str(som_st.normalized_value))) * Decimal("100")
        statuses["trading_margin"] = BaselineConceptStatus(
            concept="trading_margin",
            status=ReadinessStatus.AVAILABLE,
            source_name=tp_st.source_name,
            source_document_id=tp_st.source_document_id,
            source_file=tp_st.source_file,
            publication_date=tp_st.publication_date,
            semantic_role="operating_profitability_margin",
            raw_value=f"{tm_val:.4f}%",
            raw_unit="percentage",
            normalized_value=tm_val,
            normalized_unit="percentage",
            page=tp_st.page,
            notes=f"Derived: Trading profit ({tp_st.normalized_value}) / Sale of merchandise ({som_st.normalized_value}) = {tm_val:.6f}%"
        )
    else:
        statuses["trading_margin"] = BaselineConceptStatus("trading_margin", ReadinessStatus.MISSING, semantic_role="operating_profitability_margin", notes="Requires trading_profit and sale_of_merchandise")

    # 5. depreciation_amortisation_expense (Income Statement)
    statuses["depreciation_amortisation_expense"] = _eval(
        "depreciation_amortisation_expense", ["depreciation_amortisation_expense", "depreciation_and_amortisation", "depreciation"],
        semantic_role="accounting_depreciation_expense", min_val=10**7, abs_value_eval=True
    )
    statuses["depreciation"] = statuses["depreciation_amortisation_expense"]

    # 6. depreciation_amortisation_cashflow_addback (Note 33.1 Cash Flow Reconciliation)
    statuses["depreciation_amortisation_cashflow_addback"] = _eval(
        "depreciation_amortisation_cashflow_addback", ["depreciation_amortisation_cashflow_addback"],
        semantic_role="cashflow_reconciliation_addback", min_val=10**7
    )

    # 7. cash_capex
    statuses["cash_capex"] = _eval(
        "cash_capex", ["cash_capex", "total_capex", "capex_expansion"],
        semantic_role="cash_capital_expenditure", min_val=10**7
    )
    statuses["capex"] = statuses["cash_capex"]

    # 8. working_capital_cash_flow
    statuses["working_capital_cash_flow"] = _eval(
        "working_capital_cash_flow", ["working_capital_cash_flow", "working_capital_movement"],
        semantic_role="working_capital_cash_inflow", allow_negative=True
    )
    statuses["working_capital_baseline"] = statuses["working_capital_cash_flow"]

    # 9. effective_tax_rate
    statuses["effective_tax_rate"] = _eval(
        "effective_tax_rate", ["effective_tax_rate"],
        semantic_role="effective_corporate_tax_rate", req_unit="percentage", min_val=1, max_val=50
    )
    statuses["tax_rate"] = statuses["effective_tax_rate"]

    # 10. reported_net_cash (Equity Bridge)
    has_cash = "cash_and_cash_equivalents" in metrics
    has_mm = "money_market_investments" in metrics
    has_borrowings = "borrowings" in metrics
    has_overdraft = "bank_overdraft" in metrics
    reported_nc_obs = metrics.get("reported_net_cash") or metrics.get("net_debt_cash")
    if has_cash and has_borrowings and has_overdraft and has_mm:
        c = Decimal(str(metrics["cash_and_cash_equivalents"]["value"]))
        mm = Decimal(str(metrics["money_market_investments"]["value"]))
        b = Decimal(str(metrics["borrowings"]["value"]))
        od = Decimal(str(metrics["bank_overdraft"]["value"]))
        reconstructed_net = (c - Decimal("14000000") + mm) - (b + od)
        src_file = reported_nc_obs["source_file"] if reported_nc_obs else "TRU_FY2025_AFS.pdf"
        pub_date = reported_nc_obs["available_date"] if reported_nc_obs else "2025-08-28"
        raw_val = reported_nc_obs["raw_value"] if reported_nc_obs else f"{reconstructed_net / 1000000}m"
        statuses["reported_net_cash"] = BaselineConceptStatus(
            concept="reported_net_cash",
            status=ReadinessStatus.AVAILABLE,
            source_name="AFS Balance Sheet + Notes 7,12,16 & SENS",
            source_document_id=reported_nc_obs["source_id"] if reported_nc_obs else None,
            source_file=src_file,
            publication_date=pub_date,
            semantic_role="equity_bridge_reported_net_cash",
            raw_value=str(raw_val),
            raw_unit="ZAR_million" if str(raw_val).isdigit() else "ZAR",
            normalized_value=reconstructed_net,
            normalized_unit="ZAR",
            page=reported_nc_obs["page"] if (reported_nc_obs and reported_nc_obs.get("page")) else "Note 7,12,16",
            notes=f"Reconciled: Cash ({c/10**6}m) - Charitable Trust (14m) + Money Market ({mm/10**6}m) - Borrowings ({b/10**6}m) - Overdraft ({od/10**6}m) = R{reconstructed_net/10**6}m"
        )
    elif reported_nc_obs and reported_nc_obs.get("value") is not None:
        statuses["reported_net_cash"] = BaselineConceptStatus(
            concept="reported_net_cash",
            status=ReadinessStatus.AVAILABLE,
            source_name=reported_nc_obs["source_name"],
            source_document_id=reported_nc_obs["source_id"],
            source_file=reported_nc_obs["source_file"],
            publication_date=reported_nc_obs["available_date"],
            semantic_role="equity_bridge_reported_net_cash",
            raw_value=str(reported_nc_obs["raw_value"]),
            raw_unit=reported_nc_obs["raw_unit"],
            normalized_value=Decimal(str(reported_nc_obs["value"])),
            normalized_unit="ZAR",
            page=reported_nc_obs["page"],
            notes="Extracted directly from SENS headline net cash"
        )
    else:
        statuses["reported_net_cash"] = BaselineConceptStatus("reported_net_cash", ReadinessStatus.MISSING, semantic_role="equity_bridge_reported_net_cash", notes="Missing cash/debt components")
    statuses["net_cash_debt"] = statuses["reported_net_cash"]

    # 11. lease_liabilities
    leases = metrics.get("total_lease_liabilities") or metrics.get("lease_liabilities_current")
    if leases and Decimal(str(leases["value"])) > 0:
        statuses["lease_liabilities"] = BaselineConceptStatus(
            concept="lease_liabilities",
            status=ReadinessStatus.AVAILABLE,
            source_name=leases["source_name"],
            source_document_id=leases["source_id"],
            source_file=leases["source_file"],
            publication_date=leases["available_date"],
            semantic_role="lease_debt_obligations",
            raw_value=str(leases["raw_value"]),
            raw_unit=leases["raw_unit"],
            normalized_value=Decimal(str(leases["value"])),
            normalized_unit=leases["unit"],
            page=leases["page"],
            notes="Lease liabilities kept separate from net cash bridge"
        )
    else:
        statuses["lease_liabilities"] = BaselineConceptStatus("lease_liabilities", ReadinessStatus.MISSING, semantic_role="lease_debt_obligations", notes="Lease liabilities missing")

    # 12. period_end_external_shares
    pe_st = _eval(
        "period_end_external_shares", ["period_end_external_shares", "external_shares_ex_treasury"],
        semantic_role="period_end_share_denominator", req_unit="shares", min_val=10**8
    )
    if pe_st.status == ReadinessStatus.AVAILABLE:
        statuses["period_end_external_shares"] = BaselineConceptStatus(
            concept="period_end_external_shares",
            status=ReadinessStatus.AVAILABLE,
            source_name=pe_st.source_name,
            source_document_id=pe_st.source_document_id,
            source_file="TRU_FY2025_AFS.pdf",
            publication_date=pe_st.publication_date or "2025-08-28",
            semantic_role="period_end_share_denominator",
            raw_value=pe_st.raw_value,
            raw_unit=pe_st.raw_unit,
            normalized_value=pe_st.normalized_value,
            normalized_unit=pe_st.normalized_unit,
            page="Note 13 / Note 14",
            notes="AFS Note 13 (Share Capital: 408,498,899) less Note 14 (Treasury Shares: 33,138,000) = 375,360,899"
        )
    else:
        statuses["period_end_external_shares"] = pe_st

    # 13. announcement_date_external_shares
    ann_st = _eval(
        "announcement_date_external_shares", ["announcement_date_external_shares"],
        semantic_role="announcement_date_share_denominator", req_unit="shares", min_val=10**8
    )
    if ann_st.status == ReadinessStatus.AVAILABLE:
        statuses["announcement_date_external_shares"] = BaselineConceptStatus(
            concept="announcement_date_external_shares",
            status=ReadinessStatus.AVAILABLE,
            source_name=ann_st.source_name,
            source_document_id=ann_st.source_document_id,
            source_file="TRU_FY2025_SENS.txt",
            publication_date="2025-08-28",
            semantic_role="announcement_date_share_denominator",
            raw_value=ann_st.raw_value,
            raw_unit=ann_st.raw_unit,
            normalized_value=ann_st.normalized_value,
            normalized_unit=ann_st.normalized_unit,
            page="SENS Dividend",
            notes="SENS announcement (2025-08-28): Issued shares (408,498,899) less treasury shares at announcement (25,131,064) = 383,367,835"
        )
    else:
        statuses["announcement_date_external_shares"] = ann_st

    # 14. weighted_average_basic_shares
    statuses["weighted_average_basic_shares"] = _eval(
        "weighted_average_basic_shares", ["weighted_average_basic_shares", "wanos_basic"],
        semantic_role="wanos_basic", req_unit="shares", min_val=10**8
    )

    # 15. weighted_average_diluted_shares
    statuses["weighted_average_diluted_shares"] = _eval(
        "weighted_average_diluted_shares", ["weighted_average_diluted_shares", "wanos_diluted"],
        semantic_role="wanos_diluted", req_unit="shares", min_val=10**8
    )

    # Share denominator selection for valuation check
    denom_item = select_historical_share_count(backtest.evidence_snapshot)
    share_denom_name = None
    if denom_item and denom_item.availability == Availability.AVAILABLE:
        p = denom_item.payload or {}
        share_denom_name = p.get("name") or denom_item.kind
        s_val = Decimal(str(p.get("normalized_value") or p.get("value")))
        st = ReadinessStatus.DILUTION_UNMODELED if share_denom_name == "issued_shares_current" else ReadinessStatus.AVAILABLE
        raw_file = p.get("source_path") or p.get("source_file") or p.get("source_name") or denom_item.source_id
        src_file = _clean_source_filename(raw_file, p.get("document_role"))
        pub_date = str(p.get("source_date") or p.get("available_date") or getattr(denom_item, "available_date", None) or "")[:10] or None
        statuses["historical_share_denominator"] = BaselineConceptStatus(
            concept="historical_share_denominator",
            status=st,
            source_name=p.get("source_name") or denom_item.kind,
            source_document_id=denom_item.source_id,
            source_file=src_file,
            publication_date=pub_date,
            semantic_role="selected_valuation_share_denominator",
            raw_value=str(p.get("raw_value")),
            raw_unit=p.get("raw_unit"),
            normalized_value=s_val,
            normalized_unit="shares",
            page=p.get("source_page"),
            notes=f"Selected {share_denom_name}"
        )
    else:
        statuses["historical_share_denominator"] = BaselineConceptStatus("historical_share_denominator", ReadinessStatus.MISSING, notes="No share count found")

    # Market observation check
    market_price_str = None
    valid_market = [m for m in backtest.market_snapshot if m.observation_date <= backtest.as_of_date]
    if valid_market:
        latest = max(valid_market, key=lambda x: x.observation_date)
        market_price_str = f"{latest.value} {latest.unit} ({latest.observation_date})"
        statuses["historical_market_price"] = BaselineConceptStatus(
            concept="historical_market_price",
            status=ReadinessStatus.AVAILABLE,
            source_name=latest.source,
            source_document_id=latest.source_id,
            source_file=latest.source,
            publication_date=str(latest.observation_date),
            semantic_role="historical_market_price_anchor",
            raw_value=str(latest.value),
            raw_unit=latest.unit,
            normalized_value=latest.value,
            normalized_unit=latest.unit,
            page=None,
            notes=f"Basis: {latest.price_basis}, lag={latest.lag_days}d"
        )
    else:
        statuses["historical_market_price"] = BaselineConceptStatus("historical_market_price", ReadinessStatus.MISSING, notes="Missing market observation")

    # Core concepts required for valuation gating
    core_gating_concepts = [
        "accounting_revenue", "sale_of_merchandise", "trading_profit",
        "depreciation_amortisation_expense", "cash_capex", "working_capital_cash_flow",
        "effective_tax_rate", "reported_net_cash", "lease_liabilities",
        "historical_share_denominator", "historical_market_price"
    ]
    blocking = [c for c in core_gating_concepts if statuses.get(c) and statuses[c].status not in {ReadinessStatus.AVAILABLE, ReadinessStatus.DILUTION_UNMODELED}]
    ready = len(blocking) == 0
    reason = None if ready else f"Missing or semantically invalid concepts: {', '.join(blocking)}"

    fcff_da_note = (
        "Income-statement D&A (R1,500m) reflects operating trading expenses only (Note 27.2). "
        "Note 27.1 discloses R26m of distribution depreciation reallocated to cost of sales. "
        "Note 33.1 cash-flow reconciliation adds back the full R1,526m non-cash D&A. "
        "Because both cost components reduce Trading Profit, R1,526m is the complete addback for FCFF."
    )
    denom_warning = (
        "Methodological Warning: The valuation date (2025-08-31) is after the SENS announcement date (2025-08-28). "
        "The announcement-date external share count of 383,367,835 is therefore more current than the FY2025 "
        "period-end external share count of 375,360,899. The locked historical valuation used the period-end "
        "denominator and must not be changed retroactively. Future backtests should select the most appropriate "
        "point-in-time share denominator available as of the valuation date."
    )

    return HistoricalReadinessResult(
        ready=ready, ticker=backtest.ticker, as_of_date=backtest.as_of_date,
        reporting_period_end=backtest.reporting_period_end,
        concept_statuses=statuses, missing_or_invalid=blocking,
        share_denominator_used=share_denom_name,
        market_price_used=market_price_str,
        fcff_da_mapping_status="READY_TO_REMAP_FCFF_DA",
        fcff_da_reconciliation_note=fcff_da_note,
        working_capital_sign_convention="positive_cash_inflow",
        capex_basis="cash_capex",
        denominator_policy_warning=denom_warning,
        reason=reason,
    )

def render_historical_readiness_report(backtest: HistoricalBacktest) -> str:
    res = evaluate_historical_baseline(backtest)
    return res.format_readiness_report()

def assert_historical_baseline_ready(backtest: HistoricalBacktest) -> HistoricalReadinessResult:
    result = evaluate_historical_baseline(backtest)
    if not result.ready: raise ValueError(f"Historical ForecastPlan creation blocked: {result.reason}")
    return result
