"""
Tests for the three-batch gold review structure.

Covers:
- Total 820 benchmark items
- Exact batch sizes (300 / 260 / 260)
- No duplicate benchmark IDs
- No benchmark item in more than one batch
- Union of all batches = full 820-item benchmark
- BATCH-002/003 gold fields null initially
- BATCH-002/003 review_decision null initially
- BATCH-002/003 override flags false initially
- GOLD-001 hash unchanged
- Release roles correct
- BATCH-003 (HOLDOUT) rows absent from DEVELOPMENT-only query

Run with:
    $env:RUN_GOLD_BATCH_DB_TESTS = "1"
    & "C:\\...\\python.exe" -m pytest gui/modules/analysis/tests/test_gold_review_batches.py -v
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

# -------------------------------------------------------------------------
# Path setup
# -------------------------------------------------------------------------
GUI_ROOT = Path(__file__).resolve().parents[3]   # gui/
sys.path.insert(0, str(GUI_ROOT))
from core.config import DB_CONFIG

BENCHMARK_JSON = GUI_ROOT / "modules/analysis/data/financial_classifier_benchmark.json"

EXPECTED_GOLD001_HASH = (
    "7f95fc104c59dfcdc42a7ced35ea102884c95b9829f15d1c1960895dcd7b1d43"
)

HASH_COLUMNS = [
    "benchmark_id", "ticker", "normalized_label", "review_decision",
    "seed_concept", "seed_scope", "seed_dilution", "seed_tax_basis",
    "seed_capex_basis", "seed_lease_inclusion", "seed_margin_denominator",
    "seed_attribution", "seed_alias_role", "seed_value_pattern",
    "seed_valuation_eligibility", "seed_should_abstain",
    "gold_concept", "gold_scope", "gold_dilution", "gold_tax_basis",
    "gold_capex_basis", "gold_lease_inclusion", "gold_basis_evidence",
    "gold_margin_denominator", "gold_attribution", "gold_alias_role",
    "gold_value_pattern", "gold_valuation_eligibility", "gold_should_abstain",
    "gold_concept_is_override", "gold_scope_is_override",
    "gold_dilution_is_override", "gold_tax_basis_is_override",
    "gold_capex_basis_is_override", "gold_lease_inclusion_is_override",
    "gold_basis_evidence_is_override", "gold_margin_denominator_is_override",
    "gold_attribution_is_override", "gold_alias_role_is_override",
    "gold_value_pattern_is_override", "gold_valuation_eligibility_is_override",
    "gold_should_abstain_is_override",
    "reviewer_notes",
]

SKIP_DB = pytest.mark.skipif(
    os.environ.get("RUN_GOLD_BATCH_DB_TESTS") != "1",
    reason="Set RUN_GOLD_BATCH_DB_TESTS=1 to run DB tests",
)


def canonical_val(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    return str(v)


# =========================================================================
# Pure-logic tests (no DB)
# =========================================================================

class TestBenchmarkFile:
    """Tests against the canonical benchmark JSON — no DB required."""

    @pytest.fixture(scope="class")
    def benchmark_items(self):
        with open(BENCHMARK_JSON, encoding="utf-8") as f:
            data = json.load(f)
        return data["items"]

    def test_total_benchmark_items(self, benchmark_items):
        assert len(benchmark_items) == 820

    def test_no_duplicate_benchmark_ids(self, benchmark_items):
        ids = [i["benchmark_id"] for i in benchmark_items]
        assert len(ids) == len(set(ids))

    def test_ids_are_sequential(self, benchmark_items):
        ids = sorted(i["benchmark_id"] for i in benchmark_items)
        assert ids[0] == "BENCH-0001"
        assert ids[-1] == "BENCH-0820"

    def test_batch001_ids(self, benchmark_items):
        b001 = [i for i in benchmark_items
                if "BENCH-0001" <= i["benchmark_id"] <= "BENCH-0300"]
        assert len(b001) == 300

    def test_batch002_ids(self, benchmark_items):
        b002 = [i for i in benchmark_items
                if "BENCH-0301" <= i["benchmark_id"] <= "BENCH-0560"]
        assert len(b002) == 260

    def test_batch003_ids(self, benchmark_items):
        b003 = [i for i in benchmark_items
                if "BENCH-0561" <= i["benchmark_id"] <= "BENCH-0820"]
        assert len(b003) == 260

    def test_batches_are_disjoint(self, benchmark_items):
        b001 = {i["benchmark_id"] for i in benchmark_items
                if "BENCH-0001" <= i["benchmark_id"] <= "BENCH-0300"}
        b002 = {i["benchmark_id"] for i in benchmark_items
                if "BENCH-0301" <= i["benchmark_id"] <= "BENCH-0560"}
        b003 = {i["benchmark_id"] for i in benchmark_items
                if "BENCH-0561" <= i["benchmark_id"] <= "BENCH-0820"}
        assert b001 & b002 == set()
        assert b001 & b003 == set()
        assert b002 & b003 == set()

    def test_union_equals_full_benchmark(self, benchmark_items):
        all_ids = {i["benchmark_id"] for i in benchmark_items}
        b001 = {i["benchmark_id"] for i in benchmark_items
                if "BENCH-0001" <= i["benchmark_id"] <= "BENCH-0300"}
        b002 = {i["benchmark_id"] for i in benchmark_items
                if "BENCH-0301" <= i["benchmark_id"] <= "BENCH-0560"}
        b003 = {i["benchmark_id"] for i in benchmark_items
                if "BENCH-0561" <= i["benchmark_id"] <= "BENCH-0820"}
        assert b001 | b002 | b003 == all_ids


# =========================================================================
# DB tests
# =========================================================================

@SKIP_DB
class TestGoldReviewBatchesDb:
    """Tests against the live PostgreSQL database."""

    @pytest.fixture(scope="class")
    def conn(self):
        import psycopg2
        c = psycopg2.connect(**DB_CONFIG)
        yield c
        c.close()

    @pytest.fixture(scope="class")
    def cur(self, conn):
        import psycopg2.extras
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            yield c

    def test_total_db_rows_820(self, cur):
        cur.execute("SELECT COUNT(*) AS cnt FROM financial_classifier_gold_review")
        assert cur.fetchone()["cnt"] == 820

    def test_batch001_row_count(self, cur):
        cur.execute("""
            SELECT COUNT(*) AS cnt FROM financial_classifier_gold_review
            WHERE review_batch = 'BATCH-001'
        """)
        assert cur.fetchone()["cnt"] == 300

    def test_batch002_row_count(self, cur):
        cur.execute("""
            SELECT COUNT(*) AS cnt FROM financial_classifier_gold_review
            WHERE review_batch = 'BATCH-002'
        """)
        assert cur.fetchone()["cnt"] == 260

    def test_batch003_row_count(self, cur):
        cur.execute("""
            SELECT COUNT(*) AS cnt FROM financial_classifier_gold_review
            WHERE review_batch = 'BATCH-003'
        """)
        assert cur.fetchone()["cnt"] == 260

    def test_no_duplicate_benchmark_ids(self, cur):
        cur.execute("""
            SELECT COUNT(*) AS cnt FROM (
                SELECT benchmark_id FROM financial_classifier_gold_review
                GROUP BY benchmark_id HAVING COUNT(*) > 1
            ) AS dups
        """)
        assert cur.fetchone()["cnt"] == 0

    def test_no_benchmark_id_in_multiple_batches(self, cur):
        cur.execute("""
            SELECT COUNT(*) AS cnt FROM (
                SELECT benchmark_id FROM financial_classifier_gold_review
                GROUP BY benchmark_id HAVING COUNT(DISTINCT review_batch) > 1
            ) AS multi
        """)
        assert cur.fetchone()["cnt"] == 0

    def test_union_equals_820(self, cur):
        cur.execute("""
            SELECT COUNT(DISTINCT benchmark_id) AS cnt
            FROM financial_classifier_gold_review
            WHERE review_batch IN ('BATCH-001','BATCH-002','BATCH-003')
        """)
        assert cur.fetchone()["cnt"] == 820

    def test_batch002_gold_fields_null(self, cur):
        cur.execute("""
            SELECT COUNT(*) AS cnt
            FROM financial_classifier_gold_review
            WHERE review_batch = 'BATCH-002'
              AND (
                gold_concept IS NOT NULL OR gold_scope IS NOT NULL OR
                gold_dilution IS NOT NULL OR gold_tax_basis IS NOT NULL OR
                gold_capex_basis IS NOT NULL OR gold_lease_inclusion IS NOT NULL OR
                gold_basis_evidence IS NOT NULL OR gold_margin_denominator IS NOT NULL OR
                gold_attribution IS NOT NULL OR gold_alias_role IS NOT NULL OR
                gold_value_pattern IS NOT NULL OR gold_valuation_eligibility IS NOT NULL OR
                gold_should_abstain IS NOT NULL
              )
        """)
        assert cur.fetchone()["cnt"] == 0

    def test_batch003_gold_fields_null(self, cur):
        cur.execute("""
            SELECT COUNT(*) AS cnt
            FROM financial_classifier_gold_review
            WHERE review_batch = 'BATCH-003'
              AND (
                gold_concept IS NOT NULL OR gold_scope IS NOT NULL OR
                gold_dilution IS NOT NULL OR gold_tax_basis IS NOT NULL OR
                gold_capex_basis IS NOT NULL OR gold_lease_inclusion IS NOT NULL OR
                gold_basis_evidence IS NOT NULL OR gold_margin_denominator IS NOT NULL OR
                gold_attribution IS NOT NULL OR gold_alias_role IS NOT NULL OR
                gold_value_pattern IS NOT NULL OR gold_valuation_eligibility IS NOT NULL OR
                gold_should_abstain IS NOT NULL
              )
        """)
        assert cur.fetchone()["cnt"] == 0

    def test_batch002_review_decision_null(self, cur):
        cur.execute("""
            SELECT COUNT(*) AS cnt FROM financial_classifier_gold_review
            WHERE review_batch = 'BATCH-002' AND review_decision IS NOT NULL
        """)
        assert cur.fetchone()["cnt"] == 0

    def test_batch003_review_decision_null(self, cur):
        cur.execute("""
            SELECT COUNT(*) AS cnt FROM financial_classifier_gold_review
            WHERE review_batch = 'BATCH-003' AND review_decision IS NOT NULL
        """)
        assert cur.fetchone()["cnt"] == 0

    def test_batch002_override_flags_false(self, cur):
        cur.execute("""
            SELECT COUNT(*) AS cnt
            FROM financial_classifier_gold_review
            WHERE review_batch = 'BATCH-002'
              AND (
                gold_concept_is_override OR gold_scope_is_override OR
                gold_dilution_is_override OR gold_tax_basis_is_override OR
                gold_capex_basis_is_override OR gold_lease_inclusion_is_override OR
                gold_basis_evidence_is_override OR gold_margin_denominator_is_override OR
                gold_attribution_is_override OR gold_alias_role_is_override OR
                gold_value_pattern_is_override OR gold_valuation_eligibility_is_override OR
                gold_should_abstain_is_override
              )
        """)
        assert cur.fetchone()["cnt"] == 0

    def test_batch003_override_flags_false(self, cur):
        cur.execute("""
            SELECT COUNT(*) AS cnt
            FROM financial_classifier_gold_review
            WHERE review_batch = 'BATCH-003'
              AND (
                gold_concept_is_override OR gold_scope_is_override OR
                gold_dilution_is_override OR gold_tax_basis_is_override OR
                gold_capex_basis_is_override OR gold_lease_inclusion_is_override OR
                gold_basis_evidence_is_override OR gold_margin_denominator_is_override OR
                gold_attribution_is_override OR gold_alias_role_is_override OR
                gold_value_pattern_is_override OR gold_valuation_eligibility_is_override OR
                gold_should_abstain_is_override
              )
        """)
        assert cur.fetchone()["cnt"] == 0

    def test_gold001_hash_unchanged(self, cur):
        cols_sql = ", ".join(HASH_COLUMNS)
        cur.execute(f"""
            SELECT {cols_sql}
            FROM financial_classifier_gold_review
            WHERE review_batch = 'BATCH-001'
            ORDER BY benchmark_id
        """)
        rows = cur.fetchall()
        assert len(rows) == 300
        hasher = hashlib.sha256()
        for row in rows:
            line = "|".join(f"{col}={canonical_val(row[col])}" for col in HASH_COLUMNS) + "\n"
            hasher.update(line.encode("utf-8"))
        assert hasher.hexdigest() == EXPECTED_GOLD001_HASH

    def test_dataset_roles_correct(self, cur):
        cur.execute("""
            SELECT review_batch, dataset_role
            FROM financial_classifier_gold_review
            GROUP BY review_batch, dataset_role
        """)
        roles = {r["review_batch"]: r["dataset_role"] for r in cur.fetchall()}
        assert roles["BATCH-001"] == "DEVELOPMENT"
        assert roles["BATCH-002"] == "VALIDATION"
        assert roles["BATCH-003"] == "HOLDOUT"

    def test_no_gold002_or_gold003_release(self, cur):
        cur.execute("SELECT release_id FROM financial_classifier_gold_releases")
        ids = [r["release_id"] for r in cur.fetchall()]
        assert "GOLD-002" not in ids
        assert "GOLD-003" not in ids

    def test_holdout_absent_from_development_query(self, cur):
        """
        A query filtering to DEVELOPMENT/VALIDATION rows must not return HOLDOUT rows.
        This simulates a threshold-tuning workflow that must not touch GOLD-003.
        """
        cur.execute("""
            SELECT COUNT(*) AS cnt
            FROM financial_classifier_gold_review
            WHERE dataset_role IN ('DEVELOPMENT', 'VALIDATION')
              AND review_batch = 'BATCH-003'
        """)
        assert cur.fetchone()["cnt"] == 0

    def test_holdout_absent_from_batch001_query(self, cur):
        cur.execute("""
            SELECT COUNT(*) AS cnt
            FROM financial_classifier_gold_review
            WHERE review_batch = 'BATCH-001'
              AND dataset_role = 'HOLDOUT'
        """)
        assert cur.fetchone()["cnt"] == 0

    def test_batch001_fully_reviewed(self, cur):
        cur.execute("""
            SELECT COUNT(*) AS cnt FROM financial_classifier_gold_review
            WHERE review_batch = 'BATCH-001' AND review_decision IS NULL
        """)
        assert cur.fetchone()["cnt"] == 0

    def test_batch002_id_range(self, cur):
        cur.execute("""
            SELECT MIN(benchmark_id) AS mn, MAX(benchmark_id) AS mx
            FROM financial_classifier_gold_review
            WHERE review_batch = 'BATCH-002'
        """)
        row = cur.fetchone()
        assert row["mn"] == "BENCH-0301"
        assert row["mx"] == "BENCH-0560"

    def test_batch003_id_range(self, cur):
        cur.execute("""
            SELECT MIN(benchmark_id) AS mn, MAX(benchmark_id) AS mx
            FROM financial_classifier_gold_review
            WHERE review_batch = 'BATCH-003'
        """)
        row = cur.fetchone()
        assert row["mn"] == "BENCH-0561"
        assert row["mx"] == "BENCH-0820"
