"""Append-only deterministic valuation storage; never edits the legacy report."""
from modules.data.report_versions import json_text


async def insert_valuation_result(connection, result, forecast_plan_id=None):
    from modules.analysis.valuation.models import ValuationStatus
    from modules.analysis.valuation.reconciliation import recalculate_target
    publishable = result.status in {ValuationStatus.PASS, ValuationStatus.PASS_WITH_WARNINGS}
    if publishable:
        if result.target_price is None:
            raise ValueError("Publishable valuation has no reconciled target")
        recalculate_target(result)
    elif result.target_price is not None:
        raise ValueError("FAIL/NOT_CALCULABLE valuation cannot publish a target")
    await connection.execute("""
        INSERT INTO deterministic_valuations
          (valuation_id, ticker, report_version_id, valuation_engine_version,
           generated_at, valuation_date, status, input_ids, calculation_inputs, preflight, result, published_at, forecast_plan_id, publication_state)
        VALUES ($1::uuid,$2,$3::uuid,$4,$5,$6,$7,$8::uuid[],$9::jsonb,$10::jsonb,$11::jsonb,
                NULL, $12::uuid, 'draft')
    """, result.valuation_id, result.ticker, result.report_version_id,
        result.valuation_engine_version, result.generated_at, result.valuation_date,
        result.status.value, result.input_ids, json_text(result.calculation_inputs),
        json_text(result.preflight), json_text(result.model_dump(mode="json")), forecast_plan_id)


async def save_valuation_result(result):
    from core.db.engine import DBEngine
    await insert_valuation_result(DBEngine, result)
