"""Deterministic Historical ForecastPlan contract, lifecycle, and immutability controls."""
from __future__ import annotations
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID, uuid4
from pydantic import BaseModel, Field, model_validator
from modules.analysis.forecast_plan import (
    ApprovalState, ForecastAssumption, ForecastPeriod, Origin
)
from modules.analysis.historical_backtest import (
    HistoricalBacktest, canonical_hash
)
from modules.analysis.historical_readiness import assert_historical_baseline_ready

class HistoricalPlanStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    SUPERSEDED = "superseded"
    LOCKED = "locked"

MATERIAL_FIELDS = frozenset({
    "revenue_growth", "sale_of_merchandise_growth", "trading_margin",
    "wacc", "terminal_growth"
})

class HistoricalForecastPlan(BaseModel):
    historical_plan_id: UUID = Field(default_factory=uuid4)
    backtest_id: UUID
    ticker: str
    plan_version: int = Field(default=1, ge=1)
    status: HistoricalPlanStatus = HistoricalPlanStatus.DRAFT
    previous_historical_plan_id: UUID | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    approved_at: datetime | None = None
    approved_by: str | None = None
    created_by: str = "analyst"
    as_of_date: date
    reporting_period: str
    reporting_period_end: date
    evidence_snapshot_hash: str
    market_snapshot_hash: str
    engine_plan: dict[str, Any] = Field(default_factory=dict)
    assumptions: list[ForecastAssumption] = Field(default_factory=list)
    horizon: list[ForecastPeriod] = Field(default_factory=list)
    equity_spec: dict[str, Any] = Field(default_factory=dict)
    valuation_currency: str = "ZAR"
    audit_metadata: dict[str, Any] = Field(default_factory=dict)
    input_hash: str = ""
    is_locked: bool = False

    @model_validator(mode="after")
    def validate_plan(self):
        if self.status == HistoricalPlanStatus.APPROVED and (not self.approved_by or not self.approved_at):
            raise ValueError("Approved historical plan requires reviewer and approval timestamp")
        if self.is_locked and self.status not in (HistoricalPlanStatus.APPROVED, HistoricalPlanStatus.LOCKED):
            raise ValueError("Only approved historical plans may be locked")
        return self

def historical_plan_input_hash(plan: HistoricalForecastPlan) -> str:
    return canonical_hash({
        "historical_plan_id": str(plan.historical_plan_id),
        "backtest_id": str(plan.backtest_id),
        "ticker": plan.ticker,
        "plan_version": plan.plan_version,
        "as_of_date": str(plan.as_of_date),
        "evidence_snapshot_hash": plan.evidence_snapshot_hash,
        "market_snapshot_hash": plan.market_snapshot_hash,
        "assumptions": [a.model_dump(mode="json") for a in plan.assumptions],
        "horizon": [h.model_dump(mode="json") for h in plan.horizon],
        "engine_plan": plan.engine_plan,
        "equity_spec": plan.equity_spec,
    })

def create_historical_draft(backtest: HistoricalBacktest, created_by: str = "analyst") -> HistoricalForecastPlan:
    assert_historical_baseline_ready(backtest)
    ev_hash = canonical_hash([e.model_dump(mode="json") for e in backtest.evidence_snapshot])
    mkt_hash = canonical_hash([m.model_dump(mode="json") for m in backtest.market_snapshot])
    p_end = backtest.reporting_period_end or date(2025, 6, 29)
    fy26_start = date(p_end.year, p_end.month, p_end.day + 1) if p_end.day < 28 else date(2025, 6, 30)
    fy26_end = date(2026, 6, 28)
    horizon = [ForecastPeriod(label="FY2026", start=fy26_start, end=fy26_end)]
    plan = HistoricalForecastPlan(
        backtest_id=backtest.backtest_id,
        ticker=backtest.ticker,
        plan_version=1,
        status=HistoricalPlanStatus.DRAFT,
        created_by=created_by,
        as_of_date=backtest.as_of_date,
        reporting_period=backtest.reporting_period_label or "FY2025",
        reporting_period_end=p_end,
        evidence_snapshot_hash=ev_hash,
        market_snapshot_hash=mkt_hash,
        horizon=horizon,
        assumptions=[],
        audit_metadata={
            "baseline_readiness": "PASSED",
            "as_of_date": str(backtest.as_of_date),
            "no_fy2026_actuals_revealed": True,
            "live_forecast_plan_isolated": True,
        }
    )
    return plan.model_copy(update={"input_hash": historical_plan_input_hash(plan)})

def approve_historical_plan_in_place(plan: HistoricalForecastPlan, reviewer: str) -> HistoricalForecastPlan:
    if plan.is_locked:
        raise ValueError("Cannot edit or approve a locked historical plan")
    if plan.status != HistoricalPlanStatus.DRAFT:
        raise ValueError("Only draft historical plans can be approved")
    if not reviewer.strip():
        raise ValueError("Reviewer identity required for approval")
    for a in plan.assumptions:
        if a.approval_state == ApprovalState.PROPOSED:
            raise ValueError(f"Unreviewed proposed assumption blocks approval: {a.field}")
        if a.field in MATERIAL_FIELDS and (not a.rationale or not a.rationale.strip()):
            raise ValueError(f"Material assumption {a.field} requires historical rationale")
    wacc_a = next((a for a in plan.assumptions if a.field == "wacc" and a.approval_state == ApprovalState.ACCEPTED), None)
    tg_a = next((a for a in plan.assumptions if a.field == "terminal_growth" and a.approval_state == ApprovalState.ACCEPTED), None)
    if wacc_a and tg_a and tg_a.value is not None and wacc_a.value is not None:
        if tg_a.value >= wacc_a.value:
            raise ValueError(f"Consistency check failed: terminal growth ({tg_a.value}%) must be strictly less than WACC ({wacc_a.value}%)")
    now = datetime.now(timezone.utc)
    updated = plan.model_copy(update={
        "status": HistoricalPlanStatus.APPROVED,
        "approved_by": reviewer.strip(),
        "approved_at": now,
        "updated_at": now,
    })
    return updated.model_copy(update={"input_hash": historical_plan_input_hash(updated)})

def clone_historical_draft(plan: HistoricalForecastPlan, changed_by: str = "analyst") -> HistoricalForecastPlan:
    now = datetime.now(timezone.utc)
    cloned = HistoricalForecastPlan(
        historical_plan_id=uuid4(),
        backtest_id=plan.backtest_id,
        ticker=plan.ticker,
        plan_version=plan.plan_version + 1,
        status=HistoricalPlanStatus.DRAFT,
        previous_historical_plan_id=plan.historical_plan_id,
        created_at=now,
        updated_at=now,
        created_by=changed_by.strip() or "analyst",
        as_of_date=plan.as_of_date,
        reporting_period=plan.reporting_period,
        reporting_period_end=plan.reporting_period_end,
        evidence_snapshot_hash=plan.evidence_snapshot_hash,
        market_snapshot_hash=plan.market_snapshot_hash,
        engine_plan=dict(plan.engine_plan),
        assumptions=[a.model_copy() for a in plan.assumptions],
        horizon=[h.model_copy() for h in plan.horizon],
        equity_spec=dict(plan.equity_spec),
        valuation_currency=plan.valuation_currency,
        audit_metadata={**plan.audit_metadata, "cloned_from": str(plan.historical_plan_id)},
        is_locked=False,
    )
    return cloned.model_copy(update={"input_hash": historical_plan_input_hash(cloned)})

def lock_historical_plan(plan: HistoricalForecastPlan, backtest: HistoricalBacktest) -> HistoricalForecastPlan:
    if plan.is_locked:
        return plan
    if plan.status != HistoricalPlanStatus.APPROVED:
        raise ValueError("Historical ForecastPlan must be approved before locking")
    frozen_hash = historical_plan_input_hash(plan)
    return plan.model_copy(update={
        "status": HistoricalPlanStatus.LOCKED,
        "is_locked": True,
        "input_hash": frozen_hash,
        "updated_at": datetime.now(timezone.utc),
    })
