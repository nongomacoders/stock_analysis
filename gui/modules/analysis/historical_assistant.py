"""Controlled Historical Assumption Assistant models and leakage-controlled resolver."""
from __future__ import annotations
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID, uuid4
from pydantic import BaseModel, Field
from modules.analysis.forecast_plan import ApprovalState
from modules.analysis.historical_backtest import (
    HistoricalBacktest, HistoricalEvidence, canonical_hash
)

class AssumptionType(str, Enum):
    MANAGEMENT_GUIDANCE = "management_guidance"
    HISTORICAL_RUN_RATE = "historical_run_rate"
    NORMALIZED_ASSUMPTION = "normalized_assumption"
    HISTORICAL_MARKET_INPUT = "historical_market_input"
    ANALYST_JUDGMENT = "analyst_judgment"
    VALUATION_POLICY_CHOICE = "valuation_policy_choice"

class QualityLabel(str, Enum):
    SOURCE_BACKED = "source_backed"
    HISTORICALLY_ANCHORED_ANALYST_JUDGMENT = "historically_anchored_analyst_judgment"
    ANALYST_NORMALIZATION_TO_ZERO = "analyst_normalization_to_zero"
    NO_MATERIAL_ITEM_IDENTIFIED = "no_material_item_identified"
    EXPLICITLY_SOURCE_BACKED_ZERO = "explicitly_source_backed_zero"
    ANALYST_JUDGMENT = "analyst_judgment"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"

class HistoricalAssumptionProposal(BaseModel):
    proposal_id: UUID = Field(default_factory=uuid4)
    field: str
    historical_anchor: str = ""
    proposed_value: Decimal | str | None
    unit: str
    case: str = "base"
    rationale: str
    assumption_type: AssumptionType
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_dates: list[date] = Field(default_factory=list)
    quality: QualityLabel
    reviewable: bool = True
    required_for_valuation: bool = True
    approval_state: ApprovalState = ApprovalState.PROPOSED
    missing_components: list[str] = Field(default_factory=list)

class HistoricalAssistantAudit(BaseModel):
    eligible_source_count: int
    excluded_later_source_count: int
    unknown_date_exclusions: int
    market_observations_used: int
    snapshot_hash: str
    as_of_date: date
    ticker: str

def resolve_historical_assistant_inputs(backtest: HistoricalBacktest) -> tuple[dict[str, Any], HistoricalAssistantAudit]:
    cutoff = backtest.as_of_date
    eligible_ev: list[HistoricalEvidence] = []
    excluded_later = 0
    unknown_exclusions = 0

    for ev in backtest.evidence_snapshot:
        av = ev.available_date
        if av is None:
            unknown_exclusions += 1; continue
        if av > cutoff:
            excluded_later += 1; continue
        p = ev.payload or {}
        p_label = str(p.get("period_label") or p.get("period") or "").upper()
        if "FY2026" in p_label or "FY26" in p_label:
            excluded_later += 1; continue
        eligible_ev.append(ev)

    valid_mkt = [m for m in backtest.market_snapshot if m.observation_date <= cutoff]
    hash_payload = {
        "ticker": backtest.ticker, "as_of_date": str(cutoff),
        "evidence_ids": sorted(e.evidence_id for e in eligible_ev),
        "market_ids": sorted(m.snapshot_id for m in valid_mkt),
    }
    snap_hash = canonical_hash(hash_payload)

    lookup: dict[str, Any] = {}
    for ev in eligible_ev:
        p = ev.payload or {}
        name = p.get("name") or ev.kind
        role = p.get("document_role") or ev.kind
        existing = lookup.get(name)
        if existing and existing.get("document_role") == "annual_financial_statements" and role != "annual_financial_statements":
            continue
        val = p.get("normalized_value") if p.get("normalized_value") is not None else p.get("value")
        lookup[name] = {
            "name": name, "value": val, "unit": p.get("unit"),
            "evidence_id": ev.evidence_id, "available_date": ev.available_date,
            "source_id": ev.source_id, "document_role": role,
        }

    audit = HistoricalAssistantAudit(
        eligible_source_count=len(eligible_ev), excluded_later_source_count=excluded_later,
        unknown_date_exclusions=unknown_exclusions, market_observations_used=len(valid_mkt),
        snapshot_hash=snap_hash, as_of_date=cutoff, ticker=backtest.ticker,
    )
    return lookup, audit

def generate_historical_assumptions(backtest: HistoricalBacktest) -> tuple[list[HistoricalAssumptionProposal], HistoricalAssistantAudit]:
    from modules.analysis.historical_assistant_proposals import generate_historical_assumptions as _gen
    return _gen(backtest)
