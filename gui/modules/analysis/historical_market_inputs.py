"""Provenance-backed data models for historical market and macro inputs."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID, uuid4
from pydantic import BaseModel, Field
from modules.analysis.historical_backtest import canonical_hash

class InputScope(str, Enum):
    MARKET = "market"
    COMPANY = "company"

class MarketConcept(str, Enum):
    RISK_FREE_RATE = "risk_free_rate"
    EQUITY_RISK_PREMIUM = "equity_risk_premium"
    BETA = "beta"
    COUNTRY_RISK_PREMIUM = "country_risk_premium"
    COST_OF_DEBT = "cost_of_debt"
    DEBT_WEIGHT = "debt_weight"
    EQUITY_WEIGHT = "equity_weight"
    INFLATION_LONG_RUN = "inflation_long_run"
    NOMINAL_GDP_GROWTH_LONG_RUN = "nominal_gdp_growth_long_run"

class ProvenanceQuality(str, Enum):
    RAW_SOURCE_FACT = "raw_source_fact"
    DERIVED_FROM_SOURCE_DOCUMENT = "derived_from_source_document"
    HISTORICALLY_ANCHORED_ANALYST_CALCULATION = "historically_anchored_analyst_calculation"
    ANALYST_ENTERED_HISTORICAL_OBSERVATION = "analyst_entered_historical_observation"
    ANALYST_VALUATION_ASSUMPTION = "analyst_valuation_assumption"
    SOURCE_DOCUMENT_BACKED = "source_document_backed"
    PROVIDER_RECORD_BACKED = "provider_record_backed"
    ANALYST_ENTERED = "analyst_entered"
    MANUALLY_TRANSCRIBED = "manually_transcribed"
    INSUFFICIENT_PROVENANCE = "insufficient_provenance"

COMPANY_SCOPED_CONCEPTS = frozenset({
    MarketConcept.BETA, MarketConcept.COST_OF_DEBT,
    MarketConcept.DEBT_WEIGHT, MarketConcept.EQUITY_WEIGHT
})

_PROVENANCE_RANKS = {
    ProvenanceQuality.INSUFFICIENT_PROVENANCE: 0,
    ProvenanceQuality.ANALYST_VALUATION_ASSUMPTION: 1,
    ProvenanceQuality.ANALYST_ENTERED: 2,
    ProvenanceQuality.MANUALLY_TRANSCRIBED: 2,
    ProvenanceQuality.ANALYST_ENTERED_HISTORICAL_OBSERVATION: 2,
    ProvenanceQuality.HISTORICALLY_ANCHORED_ANALYST_CALCULATION: 3,
    ProvenanceQuality.DERIVED_FROM_SOURCE_DOCUMENT: 4,
    ProvenanceQuality.SOURCE_DOCUMENT_BACKED: 4,
    ProvenanceQuality.PROVIDER_RECORD_BACKED: 4,
    ProvenanceQuality.RAW_SOURCE_FACT: 5,
}

def propagate_calculation_provenance(upstream_qualities: list[ProvenanceQuality]) -> ProvenanceQuality:
    """A downstream calculation may never receive a stronger provenance classification than its weakest material input."""
    if not upstream_qualities: return ProvenanceQuality.INSUFFICIENT_PROVENANCE
    min_q = min(upstream_qualities, key=lambda q: _PROVENANCE_RANKS.get(q, 0))
    rank = _PROVENANCE_RANKS.get(min_q, 0)
    if rank >= 4: return ProvenanceQuality.DERIVED_FROM_SOURCE_DOCUMENT
    if rank >= 2: return ProvenanceQuality.HISTORICALLY_ANCHORED_ANALYST_CALCULATION
    if rank == 1: return ProvenanceQuality.ANALYST_VALUATION_ASSUMPTION
    return ProvenanceQuality.INSUFFICIENT_PROVENANCE

class HistoricalMarketInput(BaseModel):
    input_id: UUID = Field(default_factory=uuid4)
    scope: InputScope
    ticker: str | None = None
    market_scope: str = "ZA"
    concept: MarketConcept
    value: Decimal
    unit: str = "percentage"
    observation_date: date
    available_date: date
    provider: str
    source_url: str | None = None
    retrieval_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_methodology: str | None = None
    notes: str | None = None
    batch_id: str | None = None
    lookback_period: str | None = None
    frequency: str | None = None
    levered: bool | None = None
    debt_method: str | None = None
    provenance_quality: ProvenanceQuality = ProvenanceQuality.ANALYST_ENTERED_HISTORICAL_OBSERVATION
    source_document_id: str | None = None
    evidence_uri: str | None = None
    evidence_hash: str | None = None
    revision: int = 1
    supersedes_input_id: UUID | None = None
    is_active: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)
    input_hash: str = ""

    def compute_hash(self) -> str:
        payload = {
            "scope": self.scope.value, "ticker": self.ticker.upper() if self.ticker else None,
            "market_scope": self.market_scope.upper(), "concept": self.concept.value,
            "value": str(self.value), "unit": self.unit, "observation_date": str(self.observation_date),
            "available_date": str(self.available_date), "provider": self.provider,
            "source_methodology": self.source_methodology, "provenance_quality": self.provenance_quality.value,
            "source_document_id": self.source_document_id, "evidence_hash": self.evidence_hash,
            "revision": self.revision, "supersedes_input_id": str(self.supersedes_input_id) if self.supersedes_input_id else None,
        }
        return canonical_hash(payload)

def make_historical_market_input(
    concept: MarketConcept, value: Decimal, observation_date: date, available_date: date, provider: str,
    ticker: str | None = None, market_scope: str = "ZA", unit: str = "percentage",
    source_methodology: str | None = None, notes: str | None = None, batch_id: str | None = None,
    provenance_quality: ProvenanceQuality = ProvenanceQuality.ANALYST_ENTERED_HISTORICAL_OBSERVATION,
    source_document_id: str | None = None, evidence_uri: str | None = None, evidence_hash: str | None = None,
    revision: int = 1, supersedes_input_id: UUID | None = None, is_active: bool = True, **kwargs: Any
) -> HistoricalMarketInput:
    if available_date < observation_date: raise ValueError("available_date cannot be earlier than observation_date")
    scope = InputScope.COMPANY if (ticker or concept in COMPANY_SCOPED_CONCEPTS) else InputScope.MARKET
    if scope == InputScope.COMPANY and not ticker: raise ValueError(f"Company-scoped concept {concept.value} requires a ticker")
    item = HistoricalMarketInput(
        scope=scope, ticker=ticker.strip().upper() if ticker else None, market_scope=market_scope.strip().upper(),
        concept=concept, value=value, unit=unit, observation_date=observation_date, available_date=available_date,
        provider=provider.strip(), source_methodology=source_methodology, notes=notes, batch_id=batch_id,
        provenance_quality=provenance_quality, source_document_id=source_document_id, evidence_uri=evidence_uri,
        evidence_hash=evidence_hash, revision=revision, supersedes_input_id=supersedes_input_id, is_active=is_active, **kwargs
    )
    return item.model_copy(update={"input_hash": item.compute_hash()})

def check_bond_remaining_maturity(bond_name: str, maturity_date: date, as_of_date: date) -> dict[str, Any]:
    rem_days = (maturity_date - as_of_date).days
    rem_years = round(rem_days / 365.25, 2)
    is_10y = 9.0 <= rem_years <= 11.0
    return {
        "bond": bond_name, "maturity_date": maturity_date, "as_of_date": as_of_date,
        "remaining_years": rem_years, "is_10y_benchmark": is_10y,
        "classification": "10Y_BENCHMARK" if is_10y else f"{rem_years}Y_TENOR_LIMITATION"
    }

@dataclass(frozen=True)
class DebtComponent:
    name: str
    balance: Decimal
    rate: Decimal
    source_reference: str
    is_source_backed: bool

def calculate_weighted_cost_of_debt(components: list[DebtComponent]) -> tuple[Decimal, bool, dict[str, Any]]:
    total_bal = sum(c.balance for c in components)
    if total_bal <= 0: return Decimal("0"), False, {"status": "NO_DEBT"}
    weighted_sum = sum(c.balance * c.rate for c in components)
    kd = (weighted_sum / total_bal).quantize(Decimal("0.0001"))
    all_backed = all(c.is_source_backed for c in components)
    return kd, all_backed, {
        "total_debt": total_bal, "weighted_kd": kd, "all_source_backed": all_backed,
        "status": "DERIVED_FROM_SOURCE_DOCUMENT" if all_backed else "NOT_FULLY_SOURCE_BACKED",
        "components": [{"name": c.name, "balance": c.balance, "rate": c.rate, "backed": c.is_source_backed} for c in components]
    }
