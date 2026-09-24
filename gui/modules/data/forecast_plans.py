"""Versioned forecast plans and explicit publication workflow."""
from __future__ import annotations
from uuid import UUID
import json
from modules.analysis.forecast_plan import ForecastPlan, PlanStatus, approve_plan
from modules.analysis.valuation.models import ValuationResult, ValuationStatus
from modules.analysis.valuation.reconciliation import recalculate_target

async def save_plan(plan: ForecastPlan, db=None):
    from core.db.engine import DBEngine
    db = db or DBEngine
    await db.execute("""INSERT INTO forecast_plans
        (forecast_plan_id,ticker,plan_version,previous_plan_id,source_report_version_id,
         valuation_engine_version,status,approval_status,created_by,created_at,updated_at,
         approved_by,approved_at,plan)
        VALUES ($1::uuid,$2,$3,$4::uuid,$5::uuid,$6,$7,$8,$9,$10,$11,$12,$13,$14::jsonb)""",
        plan.forecast_plan_id,plan.ticker,plan.plan_version,plan.previous_plan_id,
        plan.source_report_version_id,plan.valuation_engine_version,plan.status.value,
        plan.approval_status,plan.created_by,plan.created_at,plan.updated_at,
        plan.approved_by,plan.approved_at,plan.model_dump_json())

async def list_plans(ticker: str):
    from core.db.engine import DBEngine
    rows = await DBEngine.fetch("SELECT plan FROM forecast_plans WHERE ticker=$1 ORDER BY plan_version DESC",ticker)
    return [ForecastPlan.model_validate(json.loads(r['plan']) if isinstance(r['plan'], str) else r['plan']) for r in rows]

async def get_plan(plan_id: UUID):
    from core.db.engine import DBEngine
    rows = await DBEngine.fetch("SELECT plan FROM forecast_plans WHERE forecast_plan_id=$1::uuid",plan_id)
    return ForecastPlan.model_validate(json.loads(rows[0]['plan']) if isinstance(rows[0]['plan'], str) else rows[0]['plan']) if rows else None

async def approve_saved_plan(plan_id: UUID, reviewer: str, db=None):
    """Approve one persisted draft in place without creating another version."""
    from core.db.engine import DBEngine
    db = db or DBEngine
    rows = await db.fetch(
        "SELECT plan FROM forecast_plans WHERE forecast_plan_id=$1::uuid", plan_id)
    if not rows:
        raise ValueError("ForecastPlan was not found")
    raw = rows[0]['plan']
    current = ForecastPlan.model_validate(
        json.loads(raw) if isinstance(raw, str) else raw)
    approved = approve_plan(current, reviewer)
    result = await db.execute("""UPDATE forecast_plans SET
        status=$2,approval_status=$3,updated_at=$4,approved_by=$5,approved_at=$6,
        plan=$7::jsonb
        WHERE forecast_plan_id=$1::uuid AND status='draft'""",
        approved.forecast_plan_id, approved.status.value, approved.approval_status,
        approved.updated_at, approved.approved_by, approved.approved_at,
        approved.model_dump_json())
    if isinstance(result, str) and not result.endswith(' 1'):
        raise ValueError("ForecastPlan approval did not update the persisted draft")
    return approved
async def save_plan_valuation(plan: ForecastPlan, result: ValuationResult, db=None):
    if plan.status != PlanStatus.APPROVED or result.calculation_inputs.get('forecast_plan',{}).get('forecast_plan_id') != str(plan.forecast_plan_id):
        raise ValueError('Valuation requires the exact approved plan snapshot')
    if result.status not in {ValuationStatus.PASS,ValuationStatus.PASS_WITH_WARNINGS}:
        raise ValueError('Only a calculable deterministic valuation may be stored for a ForecastPlan')
    from core.db.engine import DBEngine
    from modules.data.valuation_results import insert_valuation_result
    await insert_valuation_result(db or DBEngine,result,forecast_plan_id=plan.forecast_plan_id)

async def get_idempotent_plan_valuation(plan: ForecastPlan, input_hash: str, db=None):
    """Return the prior result for the exact plan/engine/input hash, if present."""
    from core.db.engine import DBEngine
    db = db or DBEngine
    rows = await db.fetch("""SELECT result FROM deterministic_valuations
        WHERE forecast_plan_id=$1::uuid AND valuation_engine_version=$2
          AND status IN ('PASS','PASS_WITH_WARNINGS')
          AND calculation_inputs->>'input_hash'=$3
        ORDER BY generated_at DESC LIMIT 1""",
        plan.forecast_plan_id, plan.valuation_engine_version, input_hash)
    if not rows:
        return None
    raw=rows[0]['result']
    return ValuationResult.model_validate(json.loads(raw) if isinstance(raw,str) else raw)

async def approve_valuation(valuation_id: UUID, reviewer: str, db=None):
    if not reviewer.strip(): raise ValueError('Reviewer required')
    from core.db.engine import DBEngine
    db = db or DBEngine
    rows = await db.fetch("""SELECT d.result,d.publication_state,d.forecast_plan_id,p.status AS plan_status
        FROM deterministic_valuations d LEFT JOIN forecast_plans p ON p.forecast_plan_id=d.forecast_plan_id
        WHERE d.valuation_id=$1::uuid""",valuation_id)
    if not rows or rows[0]['publication_state'] != 'draft' or not rows[0]['forecast_plan_id'] or rows[0]['plan_status'] != 'approved':
        raise ValueError('Only a plan-linked draft valuation can be approved')
    result = ValuationResult.model_validate(json.loads(rows[0]['result']) if isinstance(rows[0]['result'], str) else rows[0]['result'])
    if result.status not in {ValuationStatus.PASS,ValuationStatus.PASS_WITH_WARNINGS}:
        raise ValueError('Only calculable valuations may be approved')
    recalculate_target(result)
    await db.execute("UPDATE deterministic_valuations SET publication_state='approved',valuation_approved_by=$2,valuation_approved_at=NOW() WHERE valuation_id=$1::uuid AND publication_state='draft'",valuation_id,reviewer)

async def publish_valuation(valuation_id: UUID, publisher: str, db=None):
    if not publisher.strip(): raise ValueError('Publisher required')
    from core.db.engine import DBEngine
    db = db or DBEngine
    rows = await db.fetch("SELECT result,publication_state FROM deterministic_valuations WHERE valuation_id=$1::uuid",valuation_id)
    if not rows or rows[0]['publication_state'] != 'approved':
        raise ValueError('Explicit valuation approval required')
    recalculate_target(ValuationResult.model_validate(json.loads(rows[0]['result']) if isinstance(rows[0]['result'], str) else rows[0]['result']))
    await db.execute("UPDATE deterministic_valuations SET publication_state='published',published_at=NOW(),published_by=$2 WHERE valuation_id=$1::uuid AND publication_state='approved'",valuation_id,publisher)

async def valuation_history(ticker: str):
    from core.db.engine import DBEngine
    return await DBEngine.fetch("""SELECT d.valuation_id,d.generated_at,d.status,d.publication_state,
        d.valuation_engine_version,d.result->>'target_price' AS target_price,
        d.result->>'legacy_gemini_target' AS legacy_target,p.plan_version,p.forecast_plan_id
        FROM deterministic_valuations d LEFT JOIN forecast_plans p ON p.forecast_plan_id=d.forecast_plan_id
        WHERE d.ticker=$1 ORDER BY d.generated_at DESC""",ticker)


async def current_published_valuation(ticker: str):
    """The active deterministic target is the latest explicitly published valuation."""
    from core.db.engine import DBEngine
    rows = await DBEngine.fetch("""SELECT valuation_id,result,published_at,forecast_plan_id
        FROM deterministic_valuations WHERE ticker=$1 AND publication_state='published'
          AND published_at IS NOT NULL ORDER BY published_at DESC,generated_at DESC LIMIT 1""",ticker)
    if not rows:
        return None
    raw=rows[0]['result']
    return ValuationResult.model_validate(json.loads(raw) if isinstance(raw,str) else raw)

