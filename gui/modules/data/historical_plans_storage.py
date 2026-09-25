"""Persistence layer for versioned Historical ForecastPlans."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from uuid import UUID
from core.db.engine import DBEngine
from modules.analysis.historical_plan import (
    HistoricalForecastPlan, HistoricalPlanStatus, approve_historical_plan_in_place,
    lock_historical_plan, historical_plan_input_hash
)

async def save_historical_plan_db(plan: HistoricalForecastPlan, db=DBEngine) -> HistoricalForecastPlan:
    digest = historical_plan_input_hash(plan)
    updated = plan.model_copy(update={"input_hash": digest, "updated_at": datetime.now(timezone.utc)})
    snapshot_json = updated.model_dump_json()
    status_str = "draft" if updated.status == HistoricalPlanStatus.DRAFT else "approved"
    await db.execute("""INSERT INTO historical_backtest_plans
      (historical_plan_id, backtest_id, plan_version, previous_historical_plan_id, status, forecast_plan_snapshot, input_hash, created_by, created_at, approved_by, approved_at)
      VALUES($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9, $10, $11)
      ON CONFLICT (backtest_id, plan_version) DO UPDATE SET
        forecast_plan_snapshot = EXCLUDED.forecast_plan_snapshot,
        input_hash = EXCLUDED.input_hash,
        status = EXCLUDED.status,
        approved_by = EXCLUDED.approved_by,
        approved_at = EXCLUDED.approved_at""",
      updated.historical_plan_id, updated.backtest_id, updated.plan_version,
      updated.previous_historical_plan_id, status_str,
      snapshot_json, digest, updated.created_by, updated.created_at,
      updated.approved_by, updated.approved_at)
    return updated

async def approve_historical_plan_db(plan: HistoricalForecastPlan, reviewer: str, db=DBEngine) -> HistoricalForecastPlan:
    approved = approve_historical_plan_in_place(plan, reviewer)
    digest = approved.input_hash
    snapshot_json = approved.model_dump_json()
    rows = await db.fetch("SELECT status FROM historical_backtest_plans WHERE historical_plan_id=$1 AND backtest_id=$2", approved.historical_plan_id, approved.backtest_id)
    if rows and rows[0]["status"] == "approved":
        return approved
    await db.execute("""UPDATE historical_backtest_plans SET
      status='approved', approved_by=$3, approved_at=$4, forecast_plan_snapshot=$5::jsonb, input_hash=$6
      WHERE historical_plan_id=$1 AND backtest_id=$2 AND status='draft'""",
      approved.historical_plan_id, approved.backtest_id, approved.approved_by,
      approved.approved_at, snapshot_json, digest)
    return approved

async def get_historical_plan_db(historical_plan_id: UUID, db=DBEngine) -> HistoricalForecastPlan | None:
    rows = await db.fetch("SELECT forecast_plan_snapshot FROM historical_backtest_plans WHERE historical_plan_id=$1", historical_plan_id)
    if not rows: return None
    raw = rows[0]["forecast_plan_snapshot"]
    data = json.loads(raw) if isinstance(raw, str) else raw
    return HistoricalForecastPlan.model_validate(data)

async def list_historical_plans_db(backtest_id: UUID, db=DBEngine) -> list[HistoricalForecastPlan]:
    rows = await db.fetch("SELECT forecast_plan_snapshot FROM historical_backtest_plans WHERE backtest_id=$1 ORDER BY plan_version DESC", backtest_id)
    plans = []
    for r in rows:
        raw = r["forecast_plan_snapshot"]
        data = json.loads(raw) if isinstance(raw, str) else raw
        plans.append(HistoricalForecastPlan.model_validate(data))
    return plans

async def lock_historical_backtest_and_plan_db(plan: HistoricalForecastPlan, backtest, db=DBEngine) -> HistoricalForecastPlan:
    locked = lock_historical_plan(plan, backtest)
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("UPDATE historical_backtests SET status='locked', locked_at=$2, input_hash=$3 WHERE backtest_id=$1 AND status='draft'",
                               plan.backtest_id, datetime.now(timezone.utc), locked.input_hash)
            await conn.execute("UPDATE historical_backtest_plans SET forecast_plan_snapshot=$2::jsonb, input_hash=$3 WHERE historical_plan_id=$1",
                               plan.historical_plan_id, locked.model_dump_json(), locked.input_hash)
    return locked
