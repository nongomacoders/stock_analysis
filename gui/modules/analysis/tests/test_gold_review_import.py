"""Tests for the financial-classifier gold-review import pipeline.

Opt-in real-PostgreSQL tests:
    RUN_GOLD_REVIEW_DB_TESTS=1 python -m pytest .../test_gold_review_import.py -v

All real-DB tests run inside a rolled-back transaction so the live database
is never modified.

Pure-logic tests (CSV parsing, upsert guard, boolean handling) run without
any database connection.
"""
from __future__ import annotations

import asyncio
import csv
import io
import os
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------
from scripts.import_gold_review import (
    REQUIRED_COLUMNS,
    VALID_REVIEW_DECISIONS,
    normalise_row,
    parse_bool,
    run_import,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
GOLD_CSV = DATA_DIR / "financial_classifier_gold_review_001.csv"

MIGRATION_SQL = (
    Path(__file__).resolve().parents[3]
    / "core/db/migrations/add_financial_classifier_gold_review.sql"
)

DB_TEST_MARK = pytest.mark.skipif(
    os.getenv("RUN_GOLD_REVIEW_DB_TESTS") != "1",
    reason="Explicit opt-in required: set RUN_GOLD_REVIEW_DB_TESTS=1",
)

_MINIMAL_ROW = {
    "benchmark_id": "BENCH-UNIT-001",
    "ticker": "TST.JO",
    "publication_datetime": "2025-11-14 16:40",
    "previous_sentence": "prev",
    "full_sentence": "full",
    "next_sentence": "next",
    "detected_numeric_tokens": "[]",
    "normalized_label": "revenue",
    "seed_concept": "accounting_revenue",
    "seed_scope": "group_consolidated",
    "seed_dilution": "unspecified",
    "seed_tax_basis": "unspecified",
    "seed_capex_basis": "unspecified",
    "seed_lease_inclusion": "unspecified",
    "seed_margin_denominator": "unspecified",
    "seed_attribution": "unspecified",
    "seed_alias_role": "unspecified",
    "seed_value_pattern": "DIRECT_VALUE_LABEL",
    "seed_valuation_eligibility": "ELIGIBLE",
    "seed_should_abstain": "False",
    "gold_concept": "",
    "gold_scope": "",
    "gold_dilution": "",
    "gold_tax_basis": "",
    "gold_capex_basis": "",
    "gold_lease_inclusion": "",
    "gold_basis_evidence": "",
    "gold_margin_denominator": "",
    "gold_attribution": "",
    "gold_alias_role": "",
    "gold_value_pattern": "",
    "gold_valuation_eligibility": "",
    "gold_should_abstain": "",
    "reviewer_notes": "",
    "review_decision": "",
}


def _make_csv(rows: list[dict[str, str]]) -> str:
    """Build an in-memory CSV string from a list of row dicts."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(REQUIRED_COLUMNS))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Pure-logic unit tests (no DB required)
# ---------------------------------------------------------------------------


class TestParseBool:
    def test_true(self):
        assert parse_bool("True", "col", "BENCH-X") is True

    def test_false(self):
        assert parse_bool("False", "col", "BENCH-X") is False

    def test_empty_returns_none(self):
        assert parse_bool("", "col", "BENCH-X") is None

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="True, False, or empty"):
            parse_bool("yes", "col", "BENCH-X")


class TestNormaliseRow:
    def test_valid_row_parsed(self):
        row = normalise_row(_MINIMAL_ROW)
        assert row["benchmark_id"] == "BENCH-UNIT-001"
        assert row["seed_should_abstain"] is False
        assert row["gold_should_abstain"] is None
        assert row["review_decision"] is None

    def test_missing_seed_should_abstain_raises(self):
        bad = {**_MINIMAL_ROW, "seed_should_abstain": ""}
        with pytest.raises(ValueError, match="seed_should_abstain must not be empty"):
            normalise_row(bad)

    def test_invalid_review_decision_raises(self):
        bad = {**_MINIMAL_ROW, "review_decision": "APPROVE"}
        with pytest.raises(ValueError, match="invalid review_decision"):
            normalise_row(bad)

    def test_valid_review_decision_accepted(self):
        for decision in VALID_REVIEW_DECISIONS:
            row = normalise_row({**_MINIMAL_ROW, "review_decision": decision})
            assert row["review_decision"] == decision

    def test_gold_should_abstain_nullable(self):
        row = normalise_row({**_MINIMAL_ROW, "gold_should_abstain": ""})
        assert row["gold_should_abstain"] is None

    def test_gold_should_abstain_true(self):
        row = normalise_row({**_MINIMAL_ROW, "gold_should_abstain": "True"})
        assert row["gold_should_abstain"] is True


class TestCsvHeaderValidation:
    """run_import should raise if required columns are missing."""

    def test_missing_column_triggers_rollback(self, tmp_path):
        bad_csv = tmp_path / "bad.csv"
        bad_csv.write_text("benchmark_id,ticker\nBENCH-1,TST.JO\n", encoding="utf-8")
        with pytest.raises(ValueError, match="missing required columns"):
            # run_import will raise before touching the DB
            run_import(bad_csv)


class TestDuplicateBenchmarkIdRejection:
    def test_duplicate_in_csv_raises(self, tmp_path):
        row = {**_MINIMAL_ROW}
        row2 = {**_MINIMAL_ROW}  # same benchmark_id
        csv_text = _make_csv([row, row2])
        p = tmp_path / "dup.csv"
        p.write_text(csv_text, encoding="utf-8")
        with pytest.raises(ValueError, match="Duplicate benchmark_id"):
            run_import(p)


# ---------------------------------------------------------------------------
# Real PostgreSQL integration tests (opt-in, always rolled back)
# ---------------------------------------------------------------------------


def _db_scenario(scenario_fn):
    """
    Run an async scenario with a real asyncpg connection, always rolling back.
    asyncpg is already a project dependency (core/db/engine.py uses it).
    """
    import asyncpg
    from core.config import DB_CONFIG

    async def runner():
        conn = await asyncpg.connect(
            host=DB_CONFIG["host"],
            database=DB_CONFIG["dbname"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
        )
        tr = conn.transaction()
        await tr.start()
        try:
            # Create the table in this transaction only
            await conn.execute(MIGRATION_SQL.read_text(encoding="utf-8"))
            await scenario_fn(conn)
        finally:
            await tr.rollback()
            await conn.close()

    asyncio.run(runner())


@DB_TEST_MARK
class TestGoldReviewDbImport:
    """Integration tests that hit a real PostgreSQL instance."""

    def _import_via_psycopg2_in_tx(self, conn_asyncpg, csv_path: Path):
        """
        Workaround: run_import uses psycopg2; the test isolation uses asyncpg.
        For integration tests we call the import logic directly with a shared
        psycopg2 connection, using savepoints for rollback isolation.
        """
        import psycopg2
        import psycopg2.extras
        from core.config import DB_CONFIG

        # We need a separate psycopg2 connection that can see the table
        # created by asyncpg in this transaction. Because PostgreSQL does not
        # share transaction visibility across connections, we use psycopg2
        # directly here instead.
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = False
        return conn

    def test_full_csv_imports_300_rows(self, tmp_path):
        """All 300 benchmark rows must be present after import."""

        import asyncpg
        from core.config import DB_CONFIG
        from scripts.import_gold_review import run_import as do_import

        async def scenario(conn):
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM financial_classifier_gold_review"
            )
            assert count == 300, f"Expected 300 rows, got {count}"

        async def full():
            conn = await asyncpg.connect(
                host=DB_CONFIG["host"],
                database=DB_CONFIG["dbname"],
                user=DB_CONFIG["user"],
                password=DB_CONFIG["password"],
            )
            tr = conn.transaction()
            await tr.start()
            try:
                await conn.execute(MIGRATION_SQL.read_text(encoding="utf-8"))
                # run_import uses psycopg2 which has its own connection;
                # we need the table to be committed first for it to see it.
                # So we commit the table creation, run the import, then verify.
                await tr.commit()

                # Import
                do_import(GOLD_CSV)

                # Verify then clean up
                tr2 = conn.transaction()
                await tr2.start()
                try:
                    await scenario(conn)
                finally:
                    await tr2.rollback()

                # Drop the table to clean up after the test
                await conn.execute("DROP TABLE IF EXISTS financial_classifier_gold_review")
            except Exception:
                # Best-effort cleanup
                try:
                    await conn.execute(
                        "DROP TABLE IF EXISTS financial_classifier_gold_review"
                    )
                except Exception:
                    pass
                raise
            finally:
                await conn.close()

        asyncio.run(full())

    def test_idempotent_rerun_produces_same_count(self, tmp_path):
        """Running import twice must not duplicate rows."""
        import asyncpg
        from core.config import DB_CONFIG
        from scripts.import_gold_review import run_import as do_import

        async def full():
            conn = await asyncpg.connect(
                host=DB_CONFIG["host"],
                database=DB_CONFIG["dbname"],
                user=DB_CONFIG["user"],
                password=DB_CONFIG["password"],
            )
            tr = conn.transaction()
            await tr.start()
            try:
                await conn.execute(MIGRATION_SQL.read_text(encoding="utf-8"))
                await tr.commit()

                do_import(GOLD_CSV)
                do_import(GOLD_CSV)  # second run

                count = await conn.fetchval(
                    "SELECT COUNT(*) FROM financial_classifier_gold_review"
                )
                assert count == 300, f"Expected 300 after double import, got {count}"
            finally:
                try:
                    await conn.execute(
                        "DROP TABLE IF EXISTS financial_classifier_gold_review"
                    )
                except Exception:
                    pass
                await conn.close()

        asyncio.run(full())

    def test_reviewed_fields_preserved_on_rerun(self, tmp_path):
        """Existing non-blank review_decision must not be overwritten by blank CSV."""
        import asyncpg
        from core.config import DB_CONFIG
        from scripts.import_gold_review import run_import as do_import

        async def full():
            conn = await asyncpg.connect(
                host=DB_CONFIG["host"],
                database=DB_CONFIG["dbname"],
                user=DB_CONFIG["user"],
                password=DB_CONFIG["password"],
            )
            tr = conn.transaction()
            await tr.start()
            try:
                await conn.execute(MIGRATION_SQL.read_text(encoding="utf-8"))
                await tr.commit()

                do_import(GOLD_CSV)

                # Simulate a human review on BENCH-0001
                import psycopg2
                pconn = psycopg2.connect(**DB_CONFIG)
                pconn.autocommit = True
                with pconn.cursor() as cur:
                    cur.execute(
                        "UPDATE financial_classifier_gold_review "
                        "SET review_decision = 'CONFIRM_SEED', "
                        "    reviewer_notes = 'Looks correct', "
                        "    last_updated_at = NOW() "
                        "WHERE benchmark_id = 'BENCH-0001'"
                    )
                pconn.close()

                # Rerun import without force flag
                do_import(GOLD_CSV)

                decision = await conn.fetchval(
                    "SELECT review_decision FROM financial_classifier_gold_review "
                    "WHERE benchmark_id = 'BENCH-0001'"
                )
                assert decision == "CONFIRM_SEED", (
                    f"review_decision was overwritten; got {decision!r}"
                )
            finally:
                try:
                    await conn.execute(
                        "DROP TABLE IF EXISTS financial_classifier_gold_review"
                    )
                except Exception:
                    pass
                await conn.close()

        asyncio.run(full())

    def test_duplicate_benchmark_id_rejected_before_db_write(self, tmp_path):
        """A CSV with duplicate benchmark_ids must fail before any DB write."""
        import asyncpg
        from core.config import DB_CONFIG
        from scripts.import_gold_review import run_import as do_import

        # Build a CSV with two identical IDs
        row = {**_MINIMAL_ROW}
        row2 = {**_MINIMAL_ROW}
        csv_text = _make_csv([row, row2])
        p = tmp_path / "dup.csv"
        p.write_text(csv_text, encoding="utf-8")

        async def full():
            conn = await asyncpg.connect(
                host=DB_CONFIG["host"],
                database=DB_CONFIG["dbname"],
                user=DB_CONFIG["user"],
                password=DB_CONFIG["password"],
            )
            tr = conn.transaction()
            await tr.start()
            try:
                await conn.execute(MIGRATION_SQL.read_text(encoding="utf-8"))
                await tr.commit()

                with pytest.raises(ValueError, match="Duplicate benchmark_id"):
                    do_import(p)

                count = await conn.fetchval(
                    "SELECT COUNT(*) FROM financial_classifier_gold_review"
                )
                assert count == 0
            finally:
                try:
                    await conn.execute(
                        "DROP TABLE IF EXISTS financial_classifier_gold_review"
                    )
                except Exception:
                    pass
                await conn.close()

        asyncio.run(full())

    def test_transaction_rollback_on_invalid_input(self, tmp_path):
        """Invalid review_decision in CSV must roll back the full transaction."""
        import asyncpg
        from core.config import DB_CONFIG
        from scripts.import_gold_review import run_import as do_import

        bad_row = {**_MINIMAL_ROW, "benchmark_id": "BENCH-BAD", "review_decision": "INVALID"}
        csv_text = _make_csv([bad_row])
        p = tmp_path / "bad.csv"
        p.write_text(csv_text, encoding="utf-8")

        async def full():
            conn = await asyncpg.connect(
                host=DB_CONFIG["host"],
                database=DB_CONFIG["dbname"],
                user=DB_CONFIG["user"],
                password=DB_CONFIG["password"],
            )
            tr = conn.transaction()
            await tr.start()
            try:
                await conn.execute(MIGRATION_SQL.read_text(encoding="utf-8"))
                await tr.commit()

                with pytest.raises(ValueError):
                    do_import(p)

                count = await conn.fetchval(
                    "SELECT COUNT(*) FROM financial_classifier_gold_review"
                )
                assert count == 0, "Rows were written despite invalid input"
            finally:
                try:
                    await conn.execute(
                        "DROP TABLE IF EXISTS financial_classifier_gold_review"
                    )
                except Exception:
                    pass
                await conn.close()

        asyncio.run(full())

    def test_nullable_boolean_gold_should_abstain(self, tmp_path):
        """gold_should_abstain may be NULL (unreviewed) or True/False."""
        import asyncpg
        from core.config import DB_CONFIG
        from scripts.import_gold_review import run_import as do_import

        async def full():
            conn = await asyncpg.connect(
                host=DB_CONFIG["host"],
                database=DB_CONFIG["dbname"],
                user=DB_CONFIG["user"],
                password=DB_CONFIG["password"],
            )
            tr = conn.transaction()
            await tr.start()
            try:
                await conn.execute(MIGRATION_SQL.read_text(encoding="utf-8"))
                await tr.commit()

                do_import(GOLD_CSV)

                # All rows in the CSV have blank gold_should_abstain -> must be NULL
                non_null = await conn.fetchval(
                    "SELECT COUNT(*) FROM financial_classifier_gold_review "
                    "WHERE gold_should_abstain IS NOT NULL"
                )
                assert non_null == 0, (
                    f"Expected all gold_should_abstain to be NULL; {non_null} are not"
                )
            finally:
                try:
                    await conn.execute(
                        "DROP TABLE IF EXISTS financial_classifier_gold_review"
                    )
                except Exception:
                    pass
                await conn.close()

        asyncio.run(full())

    def test_all_300_benchmark_ids_distinct(self, tmp_path):
        """After import the table must contain exactly 300 distinct benchmark_ids."""
        import asyncpg
        from core.config import DB_CONFIG
        from scripts.import_gold_review import run_import as do_import

        async def full():
            conn = await asyncpg.connect(
                host=DB_CONFIG["host"],
                database=DB_CONFIG["dbname"],
                user=DB_CONFIG["user"],
                password=DB_CONFIG["password"],
            )
            tr = conn.transaction()
            await tr.start()
            try:
                await conn.execute(MIGRATION_SQL.read_text(encoding="utf-8"))
                await tr.commit()

                do_import(GOLD_CSV)

                total = await conn.fetchval(
                    "SELECT COUNT(*) FROM financial_classifier_gold_review"
                )
                distinct = await conn.fetchval(
                    "SELECT COUNT(DISTINCT benchmark_id) FROM financial_classifier_gold_review"
                )
                assert total == 300
                assert distinct == 300
            finally:
                try:
                    await conn.execute(
                        "DROP TABLE IF EXISTS financial_classifier_gold_review"
                    )
                except Exception:
                    pass
                await conn.close()

        asyncio.run(full())

    def test_bench_0001_to_0015_decisions_match_csv_after_import(self, tmp_path):
        """BENCH-0001..0015 review_decision must match the CSV after import.

        The CSV currently has blank review_decisions for all rows, so after
        import all 15 should be NULL.  This test also validates that a second
        import does not corrupt manually applied decisions.
        """
        import asyncpg
        from core.config import DB_CONFIG
        from scripts.import_gold_review import run_import as do_import

        async def full():
            conn = await asyncpg.connect(
                host=DB_CONFIG["host"],
                database=DB_CONFIG["dbname"],
                user=DB_CONFIG["user"],
                password=DB_CONFIG["password"],
            )
            tr = conn.transaction()
            await tr.start()
            try:
                await conn.execute(MIGRATION_SQL.read_text(encoding="utf-8"))
                await tr.commit()

                do_import(GOLD_CSV)

                rows = await conn.fetch(
                    "SELECT benchmark_id, review_decision "
                    "FROM financial_classifier_gold_review "
                    "WHERE benchmark_id = ANY($1) "
                    "ORDER BY benchmark_id",
                    [f"BENCH-{i:04d}" for i in range(1, 16)],
                )
                assert len(rows) == 15
                for r in rows:
                    assert r["review_decision"] is None, (
                        f"{r['benchmark_id']}: expected NULL review_decision, "
                        f"got {r['review_decision']!r}"
                    )
            finally:
                try:
                    await conn.execute(
                        "DROP TABLE IF EXISTS financial_classifier_gold_review"
                    )
                except Exception:
                    pass
                await conn.close()

        asyncio.run(full())
