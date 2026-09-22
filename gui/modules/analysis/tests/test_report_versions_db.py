"""Opt-in real PostgreSQL test: all schema/data changes roll back.

RUN_PROVENANCE_DB_TESTS=1 python -m pytest .../test_report_versions_db.py
"""
import asyncio
import os
import sys
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from core.config import DB_CONFIG
from core.db.engine import DBEngine
from modules.analysis.financial_metrics import FinancialMetric, Unit
from modules.data.report_versions import (
    EvidenceArchive, register_generation, finish_generation, save_manual_report,
)

pytestmark = pytest.mark.skipif(os.getenv("RUN_PROVENANCE_DB_TESTS") != "1", reason="Explicit opt-in for rollback-only DB test")


def test_migration_versions_manual_edits_and_failed_attempts(monkeypatch, tmp_path):
    async def scenario():
        import asyncpg
        connection = await asyncpg.connect(host=DB_CONFIG["host"], database=DB_CONFIG["dbname"],
                                          user=DB_CONFIG["user"], password=DB_CONFIG["password"])
        transaction = connection.transaction()
        await transaction.start()
        try:
            schema = "provenance_test_" + uuid4().hex
            await connection.execute(f'CREATE SCHEMA "{schema}"')
            await connection.execute(f'SET LOCAL search_path TO "{schema}"')
            await connection.execute("CREATE TABLE stock_analysis (ticker text PRIMARY KEY, deepresearch text, deepresearch_date date)")
            await connection.execute("INSERT INTO stock_analysis VALUES ('TEST.JO', 'Original legacy report', '2026-09-18')")
            migration = Path(__file__).resolve().parents[3] / "core/db/migrations/add_deepresearch_versions.sql"
            await connection.execute(migration.read_text(encoding="utf-8"))
            await connection.execute(migration.read_text(encoding="utf-8"))
            metrics_migration = Path(__file__).resolve().parents[3] / "core/db/migrations/add_financial_metrics.sql"
            await connection.execute(metrics_migration.read_text(encoding="utf-8"))
            await connection.execute(metrics_migration.read_text(encoding="utf-8"))
            valuation_migration = Path(__file__).resolve().parents[3] / "core/db/migrations/add_deterministic_valuations.sql"
            await connection.execute(valuation_migration.read_text(encoding="utf-8"))
            await connection.execute(valuation_migration.read_text(encoding="utf-8"))
            old_id = await connection.fetchval("SELECT current_report_id FROM stock_analysis")
            assert old_id
            assert await connection.fetchval("SELECT count(*) FROM deepresearch_versions") == 1
            assert await connection.fetchval("SELECT deepresearch_date FROM stock_analysis") == date(2026, 9, 18)

            class Pool:
                @asynccontextmanager
                async def acquire(self):
                    yield connection

            async def pool():
                return Pool()

            monkeypatch.setattr(DBEngine, "get_pool", pool)
            monkeypatch.setattr(DBEngine, "fetch", connection.fetch)
            monkeypatch.setattr(DBEngine, "execute", connection.execute)
            monkeypatch.setattr("modules.data.report_versions.ARCHIVE_ROOT", tmp_path)
            archive = EvidenceArchive("TEST.JO")
            inputs = archive.save_inputs({"prompt": "complete prompt", "previous_report_id": str(old_id),
                                          "previous_report": "Original legacy report"})
            await register_generation(archive, inputs)
            candidate = FinancialMetric(ticker="TEST.JO", report_id=archive.report_id,
                                        name="target_price", value=1.70, unit=Unit.ZAR)
            from modules.analysis.valuation.models import ValuationResult, ValuationStatus
            from modules.data.valuation_results import save_valuation_result
            atomic_result = ValuationResult(ticker="TEST.JO", report_version_id=archive.report_id,
                                            valuation_date=date(2026, 9, 18),
                                            status=ValuationStatus.NOT_CALCULABLE)
            await finish_generation(archive, {"response_text": "New report", "raw_response": {"text": "New report"},
                                             "audit": {"warnings": ["advisory"]}}, report_content="New report",
                                    publish=True, metrics=[candidate], valuation_result=atomic_result)
            assert await connection.fetchval("SELECT count(*) FROM deterministic_valuations WHERE valuation_id=$1::uuid", atomic_result.valuation_id) == 1
            assert await connection.fetchval("SELECT count(*) FROM financial_metrics WHERE report_id=$1::uuid", archive.report_id) == 1
            no_target = ValuationResult(ticker="TEST.JO", report_version_id=archive.report_id,
                                        valuation_date=date(2026, 9, 18), status=ValuationStatus.NOT_CALCULABLE,
                                        legacy_gemini_target=1.70)
            await save_valuation_result(no_target)
            assert await connection.fetchval("SELECT count(*) FROM deterministic_valuations WHERE report_version_id=$1::uuid", archive.report_id) == 2
            assert await connection.fetchval("SELECT published_at FROM deterministic_valuations WHERE valuation_id=$1::uuid", no_target.valuation_id) is None
            from decimal import Decimal
            from modules.analysis.valuation.reconciliation import reconcile_equity
            reconciled = reconcile_equity(enterprise_or_operating_value=Decimal(100),
                non_operating_assets=Decimal(0), receivables=Decimal(0), cash=Decimal(0),
                debt=Decimal(0), lease_adjustments=Decimal(0), minorities=Decimal(0),
                other_equity_adjustments=Decimal(0), forward_shares=Decimal(10),
                shares_metric_id=candidate.metric_id)
            calculated = ValuationResult(ticker="TEST.JO", report_version_id=archive.report_id,
                valuation_date=date(2026, 9, 18), status=ValuationStatus.PASS,
                target_price=Decimal(10), reconciliation=reconciled)
            await save_valuation_result(calculated)
            assert await connection.fetchval("SELECT published_at IS NOT NULL FROM deterministic_valuations WHERE valuation_id=$1::uuid", calculated.valuation_id)
            assert await connection.fetchval("SELECT deepresearch FROM stock_analysis") == "New report"
            assert str(await connection.fetchval("SELECT current_report_id FROM stock_analysis")) == archive.report_id
            assert await connection.fetchval("SELECT report_content FROM deepresearch_versions WHERE report_id=$1", old_id) == "Original legacy report"
            assert await connection.fetchval("SELECT previous_report_id FROM deepresearch_versions WHERE report_id=$1::uuid", archive.report_id) == old_id
            with pytest.raises(ValueError, match="cannot be overwritten"):
                await finish_generation(archive, {}, report_content="Overwrite", publish=True)
            assert await connection.fetchval("SELECT deepresearch FROM stock_analysis") == "New report"
            bad_archive = EvidenceArchive("TEST.JO")
            await register_generation(bad_archive, bad_archive.save_inputs({"prompt": "bad plan"}))
            with pytest.raises(ValueError, match="must reference this report version"):
                await finish_generation(bad_archive, {"raw_response": {"text": "bad"}},
                                        report_content="Bad report", publish=True,
                                        valuation_result=atomic_result)
            assert await connection.fetchval("SELECT deepresearch FROM stock_analysis") == "New report"
            assert await connection.fetchval("SELECT status FROM deepresearch_versions WHERE report_id=$1::uuid", bad_archive.report_id) == "pending"
            manual_id = await save_manual_report("TEST.JO", "Manual edit")
            assert str(await connection.fetchval("SELECT current_report_id FROM stock_analysis")) == manual_id
            assert await connection.fetchval("SELECT report_content FROM deepresearch_versions WHERE report_id=$1::uuid", archive.report_id) == "New report"
            failed = EvidenceArchive("TEST.JO")
            await register_generation(failed, failed.save_inputs({"prompt": "failure prompt", "previous_report_id": manual_id}))
            await finish_generation(failed, {"status": "failed", "error": "provider error"})
            assert await connection.fetchval("SELECT deepresearch FROM stock_analysis") == "Manual edit"
            assert await connection.fetchval("SELECT status FROM deepresearch_versions WHERE report_id=$1::uuid", failed.report_id) == "failed"
        finally:
            await transaction.rollback()
            await connection.close()
    asyncio.run(scenario())
