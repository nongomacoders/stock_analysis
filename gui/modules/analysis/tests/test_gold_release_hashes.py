"""Tests for hardened benchmark-release identity, dual hash semantics, and population isolation.

Verifies:
1. Source sentence change:
   - changes source_hash
   - changes release_hash
   - does not change label_hash
2. Detected numeric tokens change:
   - changes source_hash
   - changes release_hash
3. Reviewer notes change:
   - does not change source_hash
   - does not change label_hash
   - does not change release_hash
   - changes audit_hash
4. Included gold-label change:
   - changes label_hash
   - changes release_hash
5. Label change on a SKIP row:
   - does NOT change label_hash
   - does NOT change release_hash
   - DOES change audit_hash
6. SKIP -> included:
   - changes label_hash
   - changes release_hash
7. Row ordering:
   - cannot affect any canonical hash
8. Timestamps:
   - cannot affect release identity
9. DB GOLD-001 hashes:
   - source_hash, label_hash, release_hash, audit_hash match canonical constants
10. Evaluation run linkage:
   - BASELINE-SEED-GOLD-001 links to release_hash, source_hash, label_hash
11. Population leakage regression guard:
   - Simulates a reviewed BATCH-002 row and proves GOLD-001 evaluation strictly isolates to 281 rows
12. BATCH-002 / BATCH-003 remain completely untouched
"""
from __future__ import annotations

import copy
import json
import random
from typing import Any, Dict, List

import pytest

from modules.analysis.gold_release_hashes import (
    AUDIT_COLUMNS,
    GOLD001_ANNOTATION_SCHEMA_VERSION,
    GOLD001_AUDIT_HASH,
    GOLD001_INITIAL_AUDIT_HASH,
    GOLD001_LABEL_HASH,
    GOLD001_RELEASE_HASH,
    GOLD001_RELEASE_ID,
    GOLD001_RELEASE_SCHEMA_VERSION,
    GOLD001_SCHEMA_VERSION,
    GOLD001_SEMANTIC_HASH,
    GOLD001_SOURCE_HASH,
    RELEASE_IDENTITY_SCHEMA_VERSION,
    SOURCE_COLUMNS,
    compute_audit_hash,
    compute_label_hash,
    compute_release_hash,
    compute_semantic_hash,
    compute_source_hash,
)


# ---------------------------------------------------------------------------
# Fixture: Sample 4-row review batch
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_rows() -> List[Dict[str, Any]]:
    """Synthetic review batch with CONFIRM_SEED, OVERRIDE, ABSTAIN, and SKIP."""
    return [
        {
            "benchmark_id": "BENCH-0001",
            "ticker": "ABC.JO",
            "publication_datetime": "2025-11-14T16:40:00",
            "previous_sentence": "Previous context sentence.",
            "full_sentence": "Full text sentence with taxation context.",
            "next_sentence": "Next context sentence.",
            "detected_numeric_tokens": "[]",
            "normalized_label": "taxation",
            "review_decision": "CONFIRM_SEED",
            "seed_concept": "taxation",
            "seed_scope": "group_consolidated",
            "seed_dilution": "unspecified",
            "seed_tax_basis": "unspecified",
            "seed_capex_basis": "unspecified",
            "seed_lease_inclusion": "unspecified",
            "seed_margin_denominator": "unspecified",
            "seed_attribution": "unspecified",
            "seed_alias_role": "CONCEPT_MENTION_ONLY",
            "seed_value_pattern": "UNKNOWN",
            "seed_valuation_eligibility": "INFORMATIONAL_ONLY",
            "seed_should_abstain": True,
            "gold_concept": None,
            "gold_scope": None,
            "gold_dilution": None,
            "gold_tax_basis": None,
            "gold_capex_basis": None,
            "gold_lease_inclusion": None,
            "gold_basis_evidence": None,
            "gold_margin_denominator": None,
            "gold_attribution": None,
            "gold_alias_role": None,
            "gold_value_pattern": None,
            "gold_valuation_eligibility": None,
            "gold_should_abstain": None,
            "gold_concept_is_override": False,
            "gold_scope_is_override": False,
            "gold_dilution_is_override": False,
            "gold_tax_basis_is_override": False,
            "gold_capex_basis_is_override": False,
            "gold_lease_inclusion_is_override": False,
            "gold_basis_evidence_is_override": False,
            "gold_margin_denominator_is_override": False,
            "gold_attribution_is_override": False,
            "gold_alias_role_is_override": False,
            "gold_value_pattern_is_override": False,
            "gold_valuation_eligibility_is_override": False,
            "gold_should_abstain_is_override": False,
            "reviewer_notes": "CONFIRM_SEED: looks correct.",
            "imported_at": "2026-09-25T18:00:00Z",
            "last_updated_at": "2026-09-25T18:00:00Z",
        },
        {
            "benchmark_id": "BENCH-0002",
            "ticker": "DEF.JO",
            "publication_datetime": "2025-11-14T15:30:00",
            "previous_sentence": "Group operating overview.",
            "full_sentence": "Operating profit was 746 million.",
            "next_sentence": "Subsequent lines follow.",
            "detected_numeric_tokens": '["746 000 000"]',
            "normalized_label": "operating_profit",
            "review_decision": "OVERRIDE",
            "seed_concept": "operating_profit",
            "seed_scope": "group_consolidated",
            "seed_dilution": "unspecified",
            "seed_tax_basis": "unspecified",
            "seed_capex_basis": "unspecified",
            "seed_lease_inclusion": "unspecified",
            "seed_margin_denominator": "unspecified",
            "seed_attribution": "unspecified",
            "seed_alias_role": "DIRECT_VALUE_LABEL",
            "seed_value_pattern": "DIRECT_LEVEL",
            "seed_valuation_eligibility": "ELIGIBLE",
            "seed_should_abstain": False,
            "gold_concept": "ebitda",
            "gold_scope": None,
            "gold_dilution": None,
            "gold_tax_basis": None,
            "gold_capex_basis": None,
            "gold_lease_inclusion": None,
            "gold_basis_evidence": None,
            "gold_margin_denominator": None,
            "gold_attribution": None,
            "gold_alias_role": None,
            "gold_value_pattern": None,
            "gold_valuation_eligibility": None,
            "gold_should_abstain": None,
            "gold_concept_is_override": True,
            "gold_scope_is_override": False,
            "gold_dilution_is_override": False,
            "gold_tax_basis_is_override": False,
            "gold_capex_basis_is_override": False,
            "gold_lease_inclusion_is_override": False,
            "gold_basis_evidence_is_override": False,
            "gold_margin_denominator_is_override": False,
            "gold_attribution_is_override": False,
            "gold_alias_role_is_override": False,
            "gold_value_pattern_is_override": False,
            "gold_valuation_eligibility_is_override": False,
            "gold_should_abstain_is_override": False,
            "reviewer_notes": "Corrected concept from operating_profit to ebitda.",
            "imported_at": "2026-09-25T18:00:00Z",
            "last_updated_at": "2026-09-25T18:05:00Z",
        },
        {
            "benchmark_id": "BENCH-0003",
            "ticker": "GHI.JO",
            "publication_datetime": "2025-11-14T14:45:00",
            "previous_sentence": "Disposal context statement.",
            "full_sentence": "Revenue was not stated separately.",
            "next_sentence": "End of note.",
            "detected_numeric_tokens": "[]",
            "normalized_label": "revenue",
            "review_decision": "ABSTAIN",
            "seed_concept": "accounting_revenue",
            "seed_scope": "unspecified",
            "seed_dilution": "unspecified",
            "seed_tax_basis": "unspecified",
            "seed_capex_basis": "unspecified",
            "seed_lease_inclusion": "unspecified",
            "seed_margin_denominator": "unspecified",
            "seed_attribution": "unspecified",
            "seed_alias_role": "CONCEPT_MENTION_ONLY",
            "seed_value_pattern": "UNKNOWN",
            "seed_valuation_eligibility": "INFORMATIONAL_ONLY",
            "seed_should_abstain": False,
            "gold_concept": None,
            "gold_scope": None,
            "gold_dilution": None,
            "gold_tax_basis": None,
            "gold_capex_basis": None,
            "gold_lease_inclusion": None,
            "gold_basis_evidence": None,
            "gold_margin_denominator": None,
            "gold_attribution": None,
            "gold_alias_role": None,
            "gold_value_pattern": None,
            "gold_valuation_eligibility": None,
            "gold_should_abstain": True,
            "gold_concept_is_override": False,
            "gold_scope_is_override": False,
            "gold_dilution_is_override": False,
            "gold_tax_basis_is_override": False,
            "gold_capex_basis_is_override": False,
            "gold_lease_inclusion_is_override": False,
            "gold_basis_evidence_is_override": False,
            "gold_margin_denominator_is_override": False,
            "gold_attribution_is_override": False,
            "gold_alias_role_is_override": False,
            "gold_value_pattern_is_override": False,
            "gold_valuation_eligibility_is_override": False,
            "gold_should_abstain_is_override": True,
            "reviewer_notes": "Mention only; no numeric metric.",
            "imported_at": "2026-09-25T18:00:00Z",
            "last_updated_at": "2026-09-25T18:10:00Z",
        },
        {
            "benchmark_id": "BENCH-0004",
            "ticker": "JKL.JO",
            "publication_datetime": "2025-11-14T12:00:00",
            "previous_sentence": "Disposal note 4.",
            "full_sentence": "Unusable noisy text segment.",
            "next_sentence": "Following segment.",
            "detected_numeric_tokens": "[]",
            "normalized_label": "headline_earnings",
            "review_decision": "SKIP",
            "seed_concept": "headline_earnings",
            "seed_scope": "group_consolidated",
            "seed_dilution": "unspecified",
            "seed_tax_basis": "unspecified",
            "seed_capex_basis": "unspecified",
            "seed_lease_inclusion": "unspecified",
            "seed_margin_denominator": "unspecified",
            "seed_attribution": "unspecified",
            "seed_alias_role": "CONCEPT_MENTION_ONLY",
            "seed_value_pattern": "UNKNOWN",
            "seed_valuation_eligibility": "INFORMATIONAL_ONLY",
            "seed_should_abstain": True,
            "gold_concept": None,
            "gold_scope": None,
            "gold_dilution": None,
            "gold_tax_basis": None,
            "gold_capex_basis": None,
            "gold_lease_inclusion": None,
            "gold_basis_evidence": None,
            "gold_margin_denominator": None,
            "gold_attribution": None,
            "gold_alias_role": None,
            "gold_value_pattern": None,
            "gold_valuation_eligibility": None,
            "gold_should_abstain": None,
            "gold_concept_is_override": False,
            "gold_scope_is_override": False,
            "gold_dilution_is_override": False,
            "gold_tax_basis_is_override": False,
            "gold_capex_basis_is_override": False,
            "gold_lease_inclusion_is_override": False,
            "gold_basis_evidence_is_override": False,
            "gold_margin_denominator_is_override": False,
            "gold_attribution_is_override": False,
            "gold_alias_role_is_override": False,
            "gold_value_pattern_is_override": False,
            "gold_valuation_eligibility_is_override": False,
            "gold_should_abstain_is_override": False,
            "reviewer_notes": "Garbled OCR text - excluded from evaluation.",
            "imported_at": "2026-09-25T18:00:00Z",
            "last_updated_at": "2026-09-25T18:15:00Z",
        },
    ]


# ---------------------------------------------------------------------------
# Unit tests: Hash properties and mutation responses
# ---------------------------------------------------------------------------

def test_source_sentence_change_affects_source_and_release_not_label(sample_rows):
    """A source sentence change:
    - changes source_hash
    - changes release_hash
    - does not change label_hash
    """
    base_src = compute_source_hash(sample_rows)
    base_lbl = compute_label_hash(sample_rows)
    base_rel = compute_release_hash("TEST-REL", "1.0.0", base_src, base_lbl)

    mutated = copy.deepcopy(sample_rows)
    mutated[0]["full_sentence"] = "Modified sentence text with different phrasing."

    new_src = compute_source_hash(mutated)
    new_lbl = compute_label_hash(mutated)
    new_rel = compute_release_hash("TEST-REL", "1.0.0", new_src, new_lbl)

    assert new_src != base_src, "source_hash failed to detect sentence change!"
    assert new_rel != base_rel, "release_hash failed to detect sentence change!"
    assert new_lbl == base_lbl, "label_hash was corrupted by source sentence change!"


def test_detected_numeric_tokens_change_affects_source_and_release(sample_rows):
    """A detected_numeric_tokens change:
    - changes source_hash
    - changes release_hash
    """
    base_src = compute_source_hash(sample_rows)
    base_lbl = compute_label_hash(sample_rows)
    base_rel = compute_release_hash("TEST-REL", "1.0.0", base_src, base_lbl)

    mutated = copy.deepcopy(sample_rows)
    mutated[1]["detected_numeric_tokens"] = '["800 000 000"]'

    new_src = compute_source_hash(mutated)
    new_rel = compute_release_hash("TEST-REL", "1.0.0", new_src, base_lbl)

    assert new_src != base_src
    assert new_rel != base_rel


def test_reviewer_notes_change_only_affects_audit_hash(sample_rows):
    """A reviewer_notes change:
    - does not change source_hash
    - does not change label_hash
    - does not change release_hash
    - changes audit_hash
    """
    base_src = compute_source_hash(sample_rows)
    base_lbl = compute_label_hash(sample_rows)
    base_rel = compute_release_hash("TEST-REL", "1.0.0", base_src, base_lbl)
    base_aud = compute_audit_hash(sample_rows)

    mutated = copy.deepcopy(sample_rows)
    mutated[0]["reviewer_notes"] = "Completely rewritten rationale note."
    mutated[1]["reviewer_notes"] = "Typo fixed in audit note."

    new_src = compute_source_hash(mutated)
    new_lbl = compute_label_hash(mutated)
    new_rel = compute_release_hash("TEST-REL", "1.0.0", new_src, new_lbl)
    new_aud = compute_audit_hash(mutated)

    assert new_src == base_src, "source_hash must not change on notes edit!"
    assert new_lbl == base_lbl, "label_hash must not change on notes edit!"
    assert new_rel == base_rel, "release_hash must not change on notes edit!"
    assert new_aud != base_aud, "audit_hash failed to capture notes edit!"


def test_included_gold_label_change_affects_label_and_release(sample_rows):
    """An included gold-label change:
    - changes label_hash
    - changes release_hash
    """
    base_src = compute_source_hash(sample_rows)
    base_lbl = compute_label_hash(sample_rows)
    base_rel = compute_release_hash("TEST-REL", "1.0.0", base_src, base_lbl)

    mutated = copy.deepcopy(sample_rows)
    # Row 1 is included (OVERRIDE). Change gold_concept:
    mutated[1]["gold_concept"] = "gross_profit"

    new_lbl = compute_label_hash(mutated)
    new_rel = compute_release_hash("TEST-REL", "1.0.0", base_src, new_lbl)

    assert new_lbl != base_lbl, "label_hash failed to capture included gold label edit!"
    assert new_rel != base_rel, "release_hash failed to capture included gold label edit!"


def test_label_change_on_skip_row_does_not_affect_label_or_release_hash(sample_rows):
    """A label change on a SKIP row:
    - does NOT change label_hash
    - does NOT change release_hash
    - DOES change audit_hash
    """
    base_src = compute_source_hash(sample_rows)
    base_lbl = compute_label_hash(sample_rows)
    base_rel = compute_release_hash("TEST-REL", "1.0.0", base_src, base_lbl)
    base_aud = compute_audit_hash(sample_rows)

    mutated = copy.deepcopy(sample_rows)
    # Row 3 is SKIP. Mutate its seed and gold annotations:
    mutated[3]["seed_concept"] = "operating_profit"
    mutated[3]["gold_concept"] = "revenue"
    mutated[3]["gold_concept_is_override"] = True

    new_lbl = compute_label_hash(mutated)
    new_rel = compute_release_hash("TEST-REL", "1.0.0", base_src, new_lbl)
    new_aud = compute_audit_hash(mutated)

    assert new_lbl == base_lbl, "label_hash was improperly altered by annotation on a SKIP row!"
    assert new_rel == base_rel, "release_hash was improperly altered by annotation on a SKIP row!"
    assert new_aud != base_aud, "audit_hash failed to capture annotation change on SKIP row!"


def test_skip_to_included_change_affects_label_and_release_hash(sample_rows):
    """Changing a row's decision from SKIP to included:
    - changes label_hash
    - changes release_hash
    """
    base_src = compute_source_hash(sample_rows)
    base_lbl = compute_label_hash(sample_rows)
    base_rel = compute_release_hash("TEST-REL", "1.0.0", base_src, base_lbl)

    mutated = copy.deepcopy(sample_rows)
    # Change row 3 from SKIP to CONFIRM_SEED
    mutated[3]["review_decision"] = "CONFIRM_SEED"

    new_lbl = compute_label_hash(mutated)
    new_rel = compute_release_hash("TEST-REL", "1.0.0", base_src, new_lbl)

    assert new_lbl != base_lbl, "label_hash failed to capture SKIP -> included transition!"
    assert new_rel != base_rel, "release_hash failed to capture SKIP -> included transition!"


def test_row_ordering_cannot_affect_any_canonical_hash(sample_rows):
    """Row permutation cannot affect source_hash, label_hash, release_hash, or audit_hash."""
    base_src = compute_source_hash(sample_rows)
    base_lbl = compute_label_hash(sample_rows)
    base_rel = compute_release_hash("TEST-REL", "1.0.0", base_src, base_lbl)
    base_aud = compute_audit_hash(sample_rows)

    shuffled = copy.deepcopy(sample_rows)
    for _ in range(5):
        random.shuffle(shuffled)
        s_src = compute_source_hash(shuffled)
        s_lbl = compute_label_hash(shuffled)
        s_rel = compute_release_hash("TEST-REL", "1.0.0", s_src, s_lbl)
        s_aud = compute_audit_hash(shuffled)

        assert s_src == base_src
        assert s_lbl == base_lbl
        assert s_rel == base_rel
        assert s_aud == base_aud


def test_timestamps_cannot_affect_release_identity(sample_rows):
    """Volatile timestamps cannot affect source_hash, label_hash, or release_hash."""
    base_src = compute_source_hash(sample_rows)
    base_lbl = compute_label_hash(sample_rows)
    base_rel = compute_release_hash("TEST-REL", "1.0.0", base_src, base_lbl)

    mutated = copy.deepcopy(sample_rows)
    for r in mutated:
        r["imported_at"] = "2029-01-01T00:00:00Z"
        r["last_updated_at"] = "2029-01-01T00:00:00Z"

    assert compute_source_hash(mutated) == base_src
    assert compute_label_hash(mutated) == base_lbl
    assert compute_release_hash("TEST-REL", "1.0.0", base_src, base_lbl) == base_rel


# ---------------------------------------------------------------------------
# Database integration tests (PostgreSQL)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def db_conn():
    """Optional database fixture; skips gracefully if DB unavailable."""
    try:
        import psycopg2
        from core.config import DB_CONFIG
        conn = psycopg2.connect(**DB_CONFIG)
        yield conn
        conn.close()
    except Exception as exc:
        pytest.skip(f"PostgreSQL not accessible: {exc}")


def test_db_gold001_hashes_match_constants(db_conn):
    """Verify GOLD-001 release in DB matches all canonical constants."""
    import psycopg2.extras
    cur = db_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT *
        FROM financial_classifier_gold_review
        WHERE review_batch = 'BATCH-001'
        ORDER BY benchmark_id;
    """)
    rows = cur.fetchall()
    assert len(rows) == 300

    calc_src = compute_source_hash(rows)
    calc_lbl = compute_label_hash(rows)
    calc_rel = compute_release_hash(GOLD001_RELEASE_ID, GOLD001_SCHEMA_VERSION, calc_src, calc_lbl)
    calc_aud = compute_audit_hash(rows)
    calc_sem = compute_semantic_hash(rows)

    assert calc_src == GOLD001_SOURCE_HASH
    assert calc_lbl == GOLD001_LABEL_HASH
    assert calc_rel == GOLD001_RELEASE_HASH
    assert calc_aud == GOLD001_AUDIT_HASH
    assert calc_sem == GOLD001_SEMANTIC_HASH

    # Check release table record
    cur.execute("""
        SELECT release_id, schema_version, source_hash, label_hash, release_hash,
               semantic_hash, audit_hash, dataset_hash, review_row_count, evaluation_row_count
        FROM financial_classifier_gold_releases
        WHERE release_id = 'GOLD-001';
    """)
    rel = cur.fetchone()
    assert rel is not None
    assert rel["schema_version"] == GOLD001_RELEASE_SCHEMA_VERSION == "1.1.0"
    assert rel["source_hash"] == GOLD001_SOURCE_HASH
    assert rel["label_hash"] == GOLD001_LABEL_HASH
    assert rel["release_hash"] == GOLD001_RELEASE_HASH
    assert rel["semantic_hash"] == GOLD001_SEMANTIC_HASH
    assert rel["audit_hash"] == GOLD001_AUDIT_HASH
    assert rel["dataset_hash"] == GOLD001_AUDIT_HASH
    assert rel["review_row_count"] == 300
    assert rel["evaluation_row_count"] == 281


def test_schema_version_semantics():
    """Verify distinct schema version semantics:
    - annotation_schema_version: 1.1.0 (sparse override flags)
    - release_schema_version: 1.1.0 (financial_classifier_gold_releases.schema_version)
    - release_identity_schema_version: 1.0 (format of canonical manifest template)
    - compute_release_hash binds release_schema_version '1.1.0' into GOLD001_RELEASE_HASH
    """
    assert GOLD001_ANNOTATION_SCHEMA_VERSION == "1.1.0"
    assert GOLD001_RELEASE_SCHEMA_VERSION == "1.1.0"
    assert GOLD001_SCHEMA_VERSION == "1.1.0"
    assert RELEASE_IDENTITY_SCHEMA_VERSION == "1.0"

    # Prove release_hash binds 1.1.0
    calc_rel = compute_release_hash(
        GOLD001_RELEASE_ID,
        GOLD001_RELEASE_SCHEMA_VERSION,
        GOLD001_SOURCE_HASH,
        GOLD001_LABEL_HASH,
    )
    assert calc_rel == GOLD001_RELEASE_HASH


def test_db_evaluation_run_linkage(db_conn):
    """Verify BASELINE-SEED-GOLD-001 evaluation run links to authoritative release_hash."""
    import psycopg2.extras
    cur = db_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT run_id, release_id, release_hash, source_hash, label_hash, semantic_hash, status
        FROM financial_classifier_evaluation_runs
        WHERE run_id = 'BASELINE-SEED-GOLD-001';
    """)
    run = cur.fetchone()
    assert run is not None
    assert run["release_id"] == "GOLD-001"
    assert run["release_hash"] == GOLD001_RELEASE_HASH
    assert run["source_hash"] == GOLD001_SOURCE_HASH
    assert run["label_hash"] == GOLD001_LABEL_HASH
    assert run["semantic_hash"] == GOLD001_SEMANTIC_HASH
    assert run["status"] == "completed"


def test_db_population_leakage_guard():
    """LEAKAGE REGRESSION TEST:
    Simulates a human-reviewed BATCH-002 row inside a rolled-back transaction.
    Proves that GOLD-001 evaluation population strictly selects 281 rows,
    and cannot be contaminated by active BATCH-002 reviews.
    """
    import psycopg2
    import psycopg2.extras
    from core.config import DB_CONFIG

    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        # Simulate human review on BENCH-0301 (first row of BATCH-002)
        cur.execute("""
            UPDATE financial_classifier_gold_review
            SET
                review_decision = 'OVERRIDE',
                gold_concept = 'accounting_revenue',
                gold_concept_is_override = TRUE,
                reviewer_notes = 'Simulated human review during BATCH-002 pass.'
            WHERE benchmark_id = 'BENCH-0301';
        """)
        assert cur.rowcount == 1

        # Check unconstrained query (the bad pattern to prevent):
        cur.execute("SELECT COUNT(*) AS cnt FROM financial_classifier_gold_review WHERE review_decision <> 'SKIP';")
        leaked_count = cur.fetchone()["cnt"]
        assert leaked_count == 282, f"Expected 282 under unconstrained query, got {leaked_count}"

        # 1. Check isolated GOLD-001 query with explicit review_batch:
        cur.execute("""
            SELECT COUNT(*) AS cnt
            FROM financial_classifier_gold_review
            WHERE review_batch = 'BATCH-001'
              AND review_decision <> 'SKIP';
        """)
        isolated_count = cur.fetchone()["cnt"]
        assert isolated_count == 281, f"GOLD-001 leaked! Expected 281 rows, got {isolated_count}"

        # 2. Check dedicated view financial_classifier_gold_001_effective:
        cur.execute("SELECT COUNT(*) AS cnt FROM financial_classifier_gold_001_effective;")
        view_count = cur.fetchone()["cnt"]
        assert view_count == 281, f"View leaked! Expected 281 rows, got {view_count}"

    finally:
        conn.rollback()
        conn.close()


def test_db_batch002_and_003_remain_untouched(db_conn):
    """Verify BATCH-002 and BATCH-003 remain completely unreviewed and clean in DB."""
    import psycopg2.extras
    cur = db_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    for batch in ["BATCH-002", "BATCH-003"]:
        cur.execute("""
            SELECT
                COUNT(*) AS total,
                COUNT(review_decision) AS reviewed,
                SUM(CASE WHEN review_decision IS NULL THEN 1 ELSE 0 END) AS unreviewed,
                SUM(CASE WHEN reviewer_notes IS NOT NULL THEN 1 ELSE 0 END) AS notes_count,
                SUM(CASE WHEN (
                    gold_concept IS NOT NULL OR gold_scope IS NOT NULL OR
                    gold_dilution IS NOT NULL OR gold_tax_basis IS NOT NULL OR
                    gold_capex_basis IS NOT NULL OR gold_lease_inclusion IS NOT NULL OR
                    gold_basis_evidence IS NOT NULL OR gold_margin_denominator IS NOT NULL OR
                    gold_attribution IS NOT NULL OR gold_alias_role IS NOT NULL OR
                    gold_value_pattern IS NOT NULL OR gold_valuation_eligibility IS NOT NULL OR
                    gold_should_abstain IS NOT NULL
                ) THEN 1 ELSE 0 END) AS dirty_gold_count,
                SUM(CASE WHEN (
                    gold_concept_is_override OR gold_scope_is_override OR
                    gold_dilution_is_override OR gold_tax_basis_is_override OR
                    gold_capex_basis_is_override OR gold_lease_inclusion_is_override OR
                    gold_basis_evidence_is_override OR gold_margin_denominator_is_override OR
                    gold_attribution_is_override OR gold_alias_role_is_override OR
                    gold_value_pattern_is_override OR gold_valuation_eligibility_is_override OR
                    gold_should_abstain_is_override
                ) THEN 1 ELSE 0 END) AS dirty_flag_count
            FROM financial_classifier_gold_review
            WHERE review_batch = %s;
        """, (batch,))
        stats = cur.fetchone()

        assert stats["total"] == 260
        assert stats["reviewed"] == 0
        assert stats["unreviewed"] == 260
        assert stats["notes_count"] == 0
        assert stats["dirty_gold_count"] == 0
        assert stats["dirty_flag_count"] == 0

    # Verify no GOLD-002 or GOLD-003 exists
    cur.execute("SELECT release_id FROM financial_classifier_gold_releases ORDER BY release_id;")
    releases = [r["release_id"] for r in cur.fetchall()]
    assert "GOLD-002" not in releases
    assert "GOLD-003" not in releases
    assert releases == ["GOLD-001"]
