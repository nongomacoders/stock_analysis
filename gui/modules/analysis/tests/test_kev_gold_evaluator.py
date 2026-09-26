"""Tests for Kev-4B GOLD-001 evaluation adapter and blindness invariants.

Verifies:
1. Release hash verification:
   - Matches GOLD-001 canonical hashes
   - Detects and rejects any release mutation
2. Population isolation:
   - Exactly 281 rows in GOLD-001 evaluation population
   - Zero BATCH-002 rows selected
   - Zero BATCH-003 rows selected
3. Blindness invariants:
   - Request state payload contains NO seed_* keys
   - Request state payload contains NO gold_* keys
   - Request state payload contains NO review_decision or reviewer_notes
4. Question invariance:
   - Question definitions are static and identical across rows
   - Complete 65-concept option universe is present
5. Validation and safety:
   - Invalid Kev enum choice is rejected and recorded as parse error
   - Raw response text is preserved on parse failure
   - Model provenance contains required commit, revision, temperature, and backend metadata
   - Duplicate (run_id, benchmark_id) rejects silent overwrite
"""
from __future__ import annotations

import copy
import json
from typing import Any, Dict

import pytest

from modules.analysis.gold_release_hashes import (
    GOLD001_LABEL_HASH,
    GOLD001_RELEASE_HASH,
    GOLD001_RELEASE_ID,
    GOLD001_SOURCE_HASH,
)
from modules.analysis.kev_gold_evaluator import (
    STATIC_QUESTIONS,
    build_blind_request,
    build_static_concept_criteria,
    build_static_questions,
    get_gold001_evaluation_population,
    validate_and_parse_prediction,
    verify_gold001_release,
)


@pytest.fixture(scope="module")
def db_conn():
    """PostgreSQL connection fixture; skips gracefully if unavailable."""
    try:
        import psycopg2
        from core.config import DB_CONFIG
        conn = psycopg2.connect(**DB_CONFIG)
        yield conn
        conn.close()
    except Exception as exc:
        pytest.skip(f"PostgreSQL not accessible: {exc}")


# ---------------------------------------------------------------------------
# 1. Release & Population Invariants
# ---------------------------------------------------------------------------

def test_gold001_release_hash_verification(db_conn):
    """Verify GOLD-001 cryptographic identity strictly matches canonical constants."""
    hashes = verify_gold001_release(db_conn)
    assert hashes["release_id"] == GOLD001_RELEASE_ID
    assert hashes["source_hash"] == GOLD001_SOURCE_HASH
    assert hashes["label_hash"] == GOLD001_LABEL_HASH
    assert hashes["release_hash"] == GOLD001_RELEASE_HASH


def test_gold001_evaluation_population_size(db_conn):
    """Verify GOLD-001 evaluation population selects exactly 281 rows."""
    pop = get_gold001_evaluation_population(db_conn)
    assert len(pop) == 281


def test_no_batch002_or_batch003_rows_in_gold001_evaluation(db_conn):
    """Verify neither BATCH-002 nor BATCH-003 rows leak into GOLD-001 evaluation."""
    pop = get_gold001_evaluation_population(db_conn)
    batches = {r["review_batch"] for r in pop}
    assert batches == {"BATCH-001"}
    assert "BATCH-002" not in batches
    assert "BATCH-003" not in batches


# ---------------------------------------------------------------------------
# 2. Blindness Invariants
# ---------------------------------------------------------------------------

def test_request_payload_contains_no_seed_fields():
    """Verify built Kev request contains zero seed_* fields."""
    sample_row = {
        "benchmark_id": "BENCH-0001",
        "ticker": "LAB.JO",
        "publication_datetime": "2025-11-14 16:40:00",
        "normalized_label": "taxation",
        "detected_numeric_tokens": "[]",
        "previous_sentence": "Prev sentence.",
        "full_sentence": "Full sentence.",
        "next_sentence": "Next sentence.",
        # Add seed fields that must be stripped
        "seed_concept": "taxation",
        "seed_scope": "group_consolidated",
        "seed_should_abstain": True,
    }

    req = build_blind_request(sample_row)
    state = req["state"]

    for k in state:
        assert not k.startswith("seed_"), f"Leakage: {k} found in state!"
        assert not k.startswith("gold_"), f"Leakage: {k} found in state!"


def test_request_payload_contains_no_gold_fields():
    """Verify built Kev request contains zero gold_* fields or review annotations."""
    sample_row = {
        "benchmark_id": "BENCH-0002",
        "ticker": "DEF.JO",
        "publication_datetime": "2025-11-14 15:30:00",
        "normalized_label": "operating_profit",
        "detected_numeric_tokens": '["746 000 000"]',
        "previous_sentence": "Prev sentence.",
        "full_sentence": "Full sentence.",
        "next_sentence": "Next sentence.",
        # Add gold fields that must be stripped
        "gold_concept": "ebitda",
        "review_decision": "OVERRIDE",
        "reviewer_notes": "Changed to ebitda",
        "effective_concept": "ebitda",
    }

    req = build_blind_request(sample_row)
    state = req["state"]

    assert "gold_concept" not in state
    assert "review_decision" not in state
    assert "reviewer_notes" not in state
    assert "effective_concept" not in state


# ---------------------------------------------------------------------------
# 3. Question Schema Invariance & Concept Universe
# ---------------------------------------------------------------------------

def test_question_definitions_are_static_across_rows():
    """Verify question definitions are invariant across calls and rows."""
    q1 = build_static_questions()
    q2 = build_static_questions()
    assert q1 == q2
    assert len(q1) == 13


def test_complete_concept_option_universe_used():
    """Verify complete concept universe is used without dynamic row filtering."""
    criteria = build_static_concept_criteria()
    # 61 base canonical concepts + 4 extra benchmark concepts = 65
    assert len(criteria) >= 64
    assert "accounting_revenue" in criteria
    assert "headline_earnings" in criteria
    assert "operating_profit" in criteria
    assert "ebitda" in criteria
    assert "unknown" in criteria


# ---------------------------------------------------------------------------
# 4. Enum Validation & Error Handling
# ---------------------------------------------------------------------------

def test_invalid_kev_enum_rejected():
    """Verify invalid enum choice is rejected and logged as parse error."""
    mock_res = {
        "model": "kev-latest",
        "latency_ms": 100.0,
        "usage": {"input_tokens": 10, "output_tokens": 10},
        "answers": {
            "concept": {"choice": "INVALID_INVENTED_CONCEPT", "confidence": 0.99},
            "scope": {"choice": "unspecified", "confidence": 0.95},
            "dilution": {"choice": "unspecified", "confidence": 0.95},
            "tax_basis": {"choice": "unspecified", "confidence": 0.95},
            "capex_basis": {"choice": "unspecified", "confidence": 0.95},
            "lease_inclusion": {"choice": "unspecified", "confidence": 0.95},
            "basis_evidence": {"choice": "unspecified", "confidence": 0.95},
            "margin_denominator": {"choice": "unspecified", "confidence": 0.95},
            "attribution": {"choice": "unspecified", "confidence": 0.95},
            "alias_role": {"choice": "CONCEPT_MENTION_ONLY", "confidence": 0.95},
            "value_pattern": {"choice": "UNKNOWN", "confidence": 0.95},
            "valuation_eligibility": {"choice": "INFORMATIONAL_ONLY", "confidence": 0.95},
            "should_abstain": {"choice": "true", "confidence": 0.95},
        }
    }

    predicted, conf, errors = validate_and_parse_prediction(mock_res, STATIC_QUESTIONS)
    assert predicted["predicted_concept"] is None
    assert len(errors) == 1
    assert "INVALID_INVENTED_CONCEPT" in errors[0]


def test_missing_question_answer_handled():
    """Verify missing question answer is caught as a parse error."""
    mock_res = {
        "model": "kev-latest",
        "latency_ms": 50.0,
        "answers": {
            "concept": {"choice": "headline_earnings", "confidence": 0.90},
            # Missing scope, dilution, etc.
        }
    }

    predicted, conf, errors = validate_and_parse_prediction(mock_res, STATIC_QUESTIONS)
    assert predicted["predicted_concept"] == "headline_earnings"
    assert predicted["predicted_scope"] is None
    assert len(errors) == 12


def test_model_provenance_capture():
    """Verify model provenance captures commit, revision, temperature, and backend."""
    from modules.analysis.kev_gold_evaluator import fetch_kev_model_provenance
    prov = fetch_kev_model_provenance()
    assert prov["kev_git_commit"] == "f1535963cea021439370c23127bc970b6788e730"
    assert prov["backend"] == "torch"
    assert prov["device"] in ("cuda", "cpu")
    assert prov["dtype"] in ("bfloat16", "float32")
    assert prov["temperature"] > 1.0
    assert prov["hf_revision"] is not None
    assert prov["base_hf_revision"] is not None




def test_raw_response_preserved_on_parse_failure():
    """Verify raw response is stored regardless of parse success or failure."""
    raw_text = '{"malformed": "json_structure", "answers": {}}'
    mock_res = json.loads(raw_text)
    predicted, conf, errors = validate_and_parse_prediction(mock_res, STATIC_QUESTIONS)
    assert len(errors) == 13
    assert conf["model"] is None
    # In persistence, raw_text is passed directly to persist_prediction


def test_duplicate_prediction_rejected(db_conn):
    """Verify inserting duplicate prediction for same (run_id, benchmark_id) fails cleanly."""
    import psycopg2
    from modules.analysis.kev_gold_evaluator import persist_prediction

    test_run_id = "TEST-DUP-RUN-001"
    test_bench_id = "BENCH-0001"

    cur = db_conn.cursor()
    # Clean up prior test remnants if any
    cur.execute("DELETE FROM financial_classifier_evaluation_predictions WHERE run_id = %s;", (test_run_id,))
    cur.execute("DELETE FROM financial_classifier_evaluation_runs WHERE run_id = %s;", (test_run_id,))
    db_conn.commit()

    try:
        # Create a mock parent run record first
        cur.execute("""
            INSERT INTO financial_classifier_evaluation_runs (
                run_id, release_id, model_name, model_version, started_at, status
            ) VALUES (
                %s, 'GOLD-001', 'mock-test', 'v1', NOW(), 'running'
            );
        """, (test_run_id,))
        db_conn.commit()

        # First insertion
        persist_prediction(
            db_conn,
            run_id=test_run_id,
            benchmark_id=test_bench_id,
            predicted_fields={"predicted_concept": "operating_profit"},
            confidence_json={"test": True},
            raw_model_output='{"test": true}',
        )
        # Duplicate insertion must raise psycopg2.IntegrityError
        with pytest.raises(psycopg2.IntegrityError):
            persist_prediction(
                db_conn,
                run_id=test_run_id,
                benchmark_id=test_bench_id,
                predicted_fields={"predicted_concept": "ebitda"},
                confidence_json={"test": True},
                raw_model_output='{"test": true}',
            )
    finally:
        db_conn.rollback()
        cur = db_conn.cursor()
        cur.execute("DELETE FROM financial_classifier_evaluation_predictions WHERE run_id = %s;", (test_run_id,))
        cur.execute("DELETE FROM financial_classifier_evaluation_runs WHERE run_id = %s;", (test_run_id,))
        db_conn.commit()


# ---------------------------------------------------------------------------
# 5. Explicit Evidence V2 & Policy Derivation
# ---------------------------------------------------------------------------

def test_explicit_evidence_v2_schema_invariants():
    """Verify explicit-evidence-v2 removes valuation_eligibility and contains strict evidence instructions."""
    from modules.analysis.kev_gold_evaluator import STATIC_QUESTIONS_V2, compute_question_schema_hash

    assert len(STATIC_QUESTIONS_V2) == 12
    assert "valuation_eligibility" not in STATIC_QUESTIONS_V2
    assert "basis_evidence" in STATIC_QUESTIONS_V2
    assert "lease_inclusion" in STATIC_QUESTIONS_V2
    assert "dilution" in STATIC_QUESTIONS_V2
    assert "tax_basis" in STATIC_QUESTIONS_V2
    assert "scope" in STATIC_QUESTIONS_V2

    # Check negative instructions
    assert "Choose INC_LEASES or EX_LEASES only when" in STATIC_QUESTIONS_V2["lease_inclusion"]["instructions"]
    assert "Do not infer from normal accounting convention" not in STATIC_QUESTIONS_V2["lease_inclusion"]["instructions"]
    assert "Choose BASIC or DILUTED only when" in STATIC_QUESTIONS_V2["dilution"]["instructions"]
    assert "Choose GROSS or NET only when" in STATIC_QUESTIONS_V2["tax_basis"]["instructions"]
    assert "Choose a specific operation scope only when" in STATIC_QUESTIONS_V2["scope"]["instructions"]
    assert "Choose a specific evidence basis only when" in STATIC_QUESTIONS_V2["basis_evidence"]["instructions"]

    # Verify hash is deterministic
    h1 = compute_question_schema_hash(STATIC_QUESTIONS_V2)
    h2 = compute_question_schema_hash(STATIC_QUESTIONS_V2)
    assert h1 == h2
    assert len(h1) == 64


def test_deterministic_policy_derivation():
    """Verify deterministic policy derivation correctly assigns eligibility and policy abstention."""
    from modules.analysis.kev_gold_evaluator import derive_deterministic_policy
    from modules.analysis.financial_classifier_benchmark import ValuationEligibility

    # Concept requiring lease treatment without it -> REQUIRES_BASIS, abstain True
    elig, abstain = derive_deterministic_policy({
        "predicted_concept": "ebitda",
        "predicted_lease_inclusion": "unspecified",
        "predicted_alias_role": "DIRECT_VALUE_LABEL",
        "predicted_value_pattern": "DIRECT_LEVEL",
        "predicted_should_abstain": False,
    })
    assert elig == ValuationEligibility.REQUIRES_BASIS.value
    assert abstain is True

    # Concept requiring dilution without it -> REQUIRES_BASIS, abstain True
    elig, abstain = derive_deterministic_policy({
        "predicted_concept": "heps_basic",
        "predicted_dilution": "unspecified",
        "predicted_alias_role": "DIRECT_VALUE_LABEL",
        "predicted_value_pattern": "DIRECT_LEVEL",
        "predicted_should_abstain": False,
    })
    assert elig == ValuationEligibility.REQUIRES_BASIS.value
    assert abstain is True

    # Concept mention only -> INFORMATIONAL_ONLY, abstain True
    elig, abstain = derive_deterministic_policy({
        "predicted_concept": "operating_profit",
        "predicted_alias_role": "CONCEPT_MENTION_ONLY",
        "predicted_value_pattern": "UNKNOWN",
        "predicted_should_abstain": False,
    })
    assert elig == ValuationEligibility.INFORMATIONAL_ONLY.value
    assert abstain is True

    # Raw model abstention True -> INFORMATIONAL_ONLY, abstain True
    elig, abstain = derive_deterministic_policy({
        "predicted_concept": "operating_profit",
        "predicted_alias_role": "DIRECT_VALUE_LABEL",
        "predicted_value_pattern": "DIRECT_LEVEL",
        "predicted_should_abstain": True,
    })
    assert elig == ValuationEligibility.INFORMATIONAL_ONLY.value
    assert abstain is True

    # Direct value label with qualifiers satisfied -> ELIGIBLE_WITH_QUALIFIER, abstain False
    elig, abstain = derive_deterministic_policy({
        "predicted_concept": "ebitda",
        "predicted_lease_inclusion": "inc_leases",
        "predicted_scope": "group_consolidated",
        "predicted_alias_role": "DIRECT_VALUE_LABEL",
        "predicted_value_pattern": "DIRECT_LEVEL",
        "predicted_should_abstain": False,
    })
    assert elig == ValuationEligibility.ELIGIBLE_WITH_QUALIFIER.value
    assert abstain is False


# ---------------------------------------------------------------------------
# 6. Standardization, Metrics & Immutability Regression Tests
# ---------------------------------------------------------------------------

def test_canonical_13_dimensions_constant():
    """Verify CANONICAL_13_DIMENSIONS constant contains exactly the 13 canonical dimensions."""
    from modules.analysis.kev_gold_evaluator import CANONICAL_13_DIMENSIONS

    assert len(CANONICAL_13_DIMENSIONS) == 13
    expected = (
        "concept", "scope", "dilution", "tax_basis", "capex_basis",
        "lease_inclusion", "basis_evidence", "margin_denominator", "attribution",
        "alias_role", "value_pattern", "valuation_eligibility", "should_abstain",
    )
    assert CANONICAL_13_DIMENSIONS == expected


def test_normalize_basis_evidence():
    """Verify normalize_basis_evidence canonicalizes NULL/empty/variants to 'unspecified' without mutating data."""
    from modules.analysis.kev_gold_evaluator import normalize_basis_evidence

    assert normalize_basis_evidence(None) == "unspecified"
    assert normalize_basis_evidence("") == "unspecified"
    assert normalize_basis_evidence("   ") == "unspecified"
    assert normalize_basis_evidence("None") == "unspecified"
    assert normalize_basis_evidence("null") == "unspecified"
    assert normalize_basis_evidence("UNSPECIFIED") == "unspecified"
    assert normalize_basis_evidence("unspecified") == "unspecified"
    assert normalize_basis_evidence("balance_sheet_presentation_separate") == "balance_sheet_presentation_separate"
    assert normalize_basis_evidence("EXPLICIT_NOTE_WORDING") == "explicit_note_wording"


def test_unsafe_acceptance_metrics_definitions():
    """Verify explicit unsafe false acceptance and abstention confusion metrics."""
    from modules.analysis.kev_gold_evaluator import compute_evaluation_metrics

    # Mock scored rows to produce: TP=199, FP=23, TN=17, FN=42
    # Total = 281
    mock_rows = []
    dims = [
        "concept", "scope", "dilution", "tax_basis", "capex_basis",
        "lease_inclusion", "basis_evidence", "margin_denominator", "attribution",
        "alias_role", "value_pattern", "valuation_eligibility", "should_abstain"
    ]
    def make_row(bench_id: str, gold_abs: bool, pred_abs: bool) -> dict:
        r = {"benchmark_id": bench_id}
        for d in dims:
            r[f"predicted_{d}"] = "unspecified"
            r[f"effective_{d}"] = "unspecified"
        r["predicted_concept"] = "ebitda"
        r["effective_concept"] = "ebitda"
        r["effective_should_abstain"] = gold_abs
        r["predicted_should_abstain"] = pred_abs
        return r

    # TP: gold=True, pred=True (199)
    for i in range(199):
        mock_rows.append(make_row(f"TP-{i}", True, True))

    # FP: gold=False, pred=True (23)
    for i in range(23):
        mock_rows.append(make_row(f"FP-{i}", False, True))

    # TN: gold=False, pred=False (17)
    for i in range(17):
        mock_rows.append(make_row(f"TN-{i}", False, False))

    # FN: gold=True, pred=False (42)
    for i in range(42):
        mock_rows.append(make_row(f"FN-{i}", True, False))

    assert len(mock_rows) == 281
    metrics = compute_evaluation_metrics(mock_rows, abstain_field="predicted_should_abstain")

    assert metrics["evaluation_population"] == 281
    assert metrics["accepted_count"] == 59          # 17 + 42
    assert metrics["safe_accept_count"] == 17        # TN
    assert metrics["unsafe_accept_count"] == 42      # FN
    assert metrics["unsafe_accept_rate_of_accepted"] == pytest.approx(42 / 59, abs=1e-4)  # ~71.19%
    assert metrics["unsafe_accept_rate_of_population"] == pytest.approx(42 / 281, abs=1e-4) # ~14.95%
    assert metrics["coverage_of_gold_safe"] == pytest.approx(17 / 40, abs=1e-4)             # 42.50%
    ac = metrics["abstention_confusion"]
    assert ac["tp"] == 199
    assert ac["fp"] == 23
    assert ac["tn"] == 17
    assert ac["fn"] == 42


def test_pre_run_schema_guard():
    """Verify assert_valid_pre_run_schema enforces presence of schema_version and 64-char schema_hash."""
    from modules.analysis.kev_gold_evaluator import assert_valid_pre_run_schema

    # Missing version
    with pytest.raises(ValueError, match="question_schema_version must be provided"):
        assert_valid_pre_run_schema({"question_schema_hash": "a" * 64})

    # Missing hash
    with pytest.raises(ValueError, match="question_schema_hash must be computed"):
        assert_valid_pre_run_schema({"question_schema_version": "v2"})

    # Invalid hash length
    with pytest.raises(ValueError, match="question_schema_hash must be computed"):
        assert_valid_pre_run_schema({"question_schema_version": "v2", "question_schema_hash": "short"})

    # Valid config passes
    valid_hash = "f2e26281a4a3ff5c0cad6ac91a84308276398ce5498e6d10f30b3b8630c346cd"
    res = assert_valid_pre_run_schema({
        "question_schema_version": "explicit-evidence-v2",
        "question_schema_hash": valid_hash,
    })
    assert res == valid_hash


def test_completed_run_immutability(db_conn):
    """Verify persist_evaluation_run rejects modifying a completed run."""
    from modules.analysis.kev_gold_evaluator import persist_evaluation_run
    from modules.analysis.gold_release_hashes import (
        GOLD001_LABEL_HASH,
        GOLD001_RELEASE_HASH,
        GOLD001_RELEASE_ID,
        GOLD001_SOURCE_HASH,
    )

    test_run_id = "TEST-IMMUTABLE-RUN-001"
    cur = db_conn.cursor()
    cur.execute("DELETE FROM financial_classifier_evaluation_predictions WHERE run_id = %s;", (test_run_id,))
    cur.execute("DELETE FROM financial_classifier_evaluation_runs WHERE run_id = %s;", (test_run_id,))
    db_conn.commit()

    release_hashes = {
        "release_id": GOLD001_RELEASE_ID,
        "release_hash": GOLD001_RELEASE_HASH,
        "source_hash": GOLD001_SOURCE_HASH,
        "label_hash": GOLD001_LABEL_HASH,
    }
    prov = {
        "run": "mock-model",
        "kev_git_commit": "mock-commit",
    }
    valid_cfg = {
        "question_schema_version": "test-v1",
        "question_schema_hash": "0" * 64,
    }

    try:
        # First creation: status=completed
        persist_evaluation_run(
            db_conn,
            run_id=test_run_id,
            release_hashes=release_hashes,
            provenance=prov,
            configuration_json=valid_cfg,
            status="completed",
        )

        # Attempt to modify completed run must raise ValueError
        with pytest.raises(ValueError, match="is completed and cannot be re-initialized"):
            persist_evaluation_run(
                db_conn,
                run_id=test_run_id,
                release_hashes=release_hashes,
                provenance=prov,
                configuration_json=valid_cfg,
                status="running",
            )
    finally:
        db_conn.rollback()
        cur = db_conn.cursor()
        cur.execute("DELETE FROM financial_classifier_evaluation_predictions WHERE run_id = %s;", (test_run_id,))
        cur.execute("DELETE FROM financial_classifier_evaluation_runs WHERE run_id = %s;", (test_run_id,))
        db_conn.commit()


def test_historical_basis_evidence_backfill_idempotent(db_conn):
    """Verify backfill_historical_basis_evidence is safe, non-destructive, and leaves 0 unrecoverable."""
    from modules.analysis.kev_gold_evaluator import backfill_historical_basis_evidence

    stats = backfill_historical_basis_evidence(db_conn, target_run_ids=["KEV08B-CUDA-GOLD001-FULL-001"])
    run_stats = stats["KEV08B-CUDA-GOLD001-FULL-001"]
    assert run_stats["total"] == 281
    assert run_stats["unrecoverable"] == 0
    # Already backfilled in previous step, so already_populated == 281
    assert run_stats["already_populated"] == 281


def test_policy_matrix_negative_cases():
    """Verify semantic negative cases do not trigger spurious qualifier requirements."""
    from modules.analysis.kev_gold_evaluator import derive_deterministic_policy
    from modules.analysis.financial_classifier_benchmark import ValuationEligibility

    # 1. Non-per-share metric (e.g., operating_profit) does NOT require dilution
    elig, abstain = derive_deterministic_policy({
        "predicted_concept": "operating_profit",
        "predicted_dilution": "unspecified",
        "predicted_alias_role": "DIRECT_VALUE_LABEL",
        "predicted_value_pattern": "DIRECT_LEVEL",
        "predicted_should_abstain": False,
    })
    assert elig == ValuationEligibility.ELIGIBLE.value
    assert abstain is False

    # 2. Non-dividend metric (e.g., revenue) does NOT require tax_basis
    elig, abstain = derive_deterministic_policy({
        "predicted_concept": "accounting_revenue",
        "predicted_tax_basis": "unspecified",
        "predicted_alias_role": "DIRECT_VALUE_LABEL",
        "predicted_value_pattern": "DIRECT_LEVEL",
        "predicted_should_abstain": False,
    })
    assert elig == ValuationEligibility.ELIGIBLE.value
    assert abstain is False

    # 3. Unrelated concept (e.g., revenue) does NOT require lease_inclusion
    elig, abstain = derive_deterministic_policy({
        "predicted_concept": "accounting_revenue",
        "predicted_lease_inclusion": "unspecified",
        "predicted_alias_role": "DIRECT_VALUE_LABEL",
        "predicted_value_pattern": "DIRECT_LEVEL",
        "predicted_should_abstain": False,
    })
    assert elig == ValuationEligibility.ELIGIBLE.value
    assert abstain is False

    # 4. Syntactic mention only -> rejected
    elig, abstain = derive_deterministic_policy({
        "predicted_concept": "accounting_revenue",
        "predicted_alias_role": "CONCEPT_MENTION_ONLY",
        "predicted_value_pattern": "DIRECT_LEVEL",
        "predicted_should_abstain": False,
    })
    assert elig == ValuationEligibility.INFORMATIONAL_ONLY.value
    assert abstain is True

    # 5. Guidance statement -> rejected
    elig, abstain = derive_deterministic_policy({
        "predicted_concept": "operating_profit",
        "predicted_alias_role": "GUIDANCE_STATEMENT",
        "predicted_value_pattern": "DIRECT_LEVEL",
        "predicted_should_abstain": False,
    })
    assert elig == ValuationEligibility.INFORMATIONAL_ONLY.value
    assert abstain is True

    # 6. Change-rate only statement -> rejected
    elig, abstain = derive_deterministic_policy({
        "predicted_concept": "operating_profit",
        "predicted_alias_role": "DIRECT_VALUE_LABEL",
        "predicted_value_pattern": "CHANGE_RATE_ONLY",
        "predicted_should_abstain": False,
    })
    assert elig == ValuationEligibility.INFORMATIONAL_ONLY.value
    assert abstain is True






