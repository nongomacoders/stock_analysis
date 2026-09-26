"""Deterministic hash calculations for Financial Classifier Gold Releases.

Establishes the release identity hierarchy:
1. source_hash: Identifies the exact classifier input text and source context.
   Ordered by benchmark_id. Hashes: benchmark_id, ticker, publication_datetime,
   previous_sentence, full_sentence, next_sentence, detected_numeric_tokens, normalized_label.
   Strictly independent of review labels, notes, or timestamps.

2. label_hash: Identifies the effective human annotations and evaluation inclusion.
   Ordered by benchmark_id.
   - Included rows (review_decision != 'SKIP'): hashes benchmark_id, is_included=TRUE,
     and all 13 effective evaluation dimensions.
   - SKIP rows (review_decision == 'SKIP'): hashes ONLY benchmark_id, is_included=FALSE.
     Unused effective labels on SKIP rows do not affect label_hash.

3. release_hash: Authoritative composite release identity.
   Uniquely identifies the evaluable benchmark release by binding:
   release_id, schema_version, source_hash, and label_hash.
   Future classifier evaluation runs must reference this release_hash.

4. audit_hash: Captures the complete annotation state and provenance trail.
   Hashes seed fields, gold fields, override flags, review decisions, reviewer notes,
   and stable item descriptors. Excludes volatile timestamps.

5. semantic_hash: Retained as the legacy/backward-compatible name and value for the
   initial evaluation dataset hash (d759e827...).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Sequence

# ---------------------------------------------------------------------------
# Canonical constants for GOLD-001
# ---------------------------------------------------------------------------

GOLD001_RELEASE_ID = "GOLD-001"

# Schema versioning distinctions:
# 1. annotation_schema_version: Database schema of human review/override fields (v1.1.0 added sparse override flags).
GOLD001_ANNOTATION_SCHEMA_VERSION = "1.1.0"
# 2. release_schema_version: Authoritative release schema version recorded in financial_classifier_gold_releases.schema_version
#    and bound into the canonical release manifest to compute release_hash.
GOLD001_RELEASE_SCHEMA_VERSION = "1.1.0"
# 3. schema_version: Backward-compatible alias for release_schema_version.
GOLD001_SCHEMA_VERSION = "1.1.0"
# 4. release_identity_schema_version: Structural version of the release manifest template itself (key-value manifest v1.0).
RELEASE_IDENTITY_SCHEMA_VERSION = "1.0"

GOLD001_SOURCE_HASH = "4b8594e5b34d7d05273fecda2dd4b817b9dc2e055d77cf0bc6de31cf79ff7610"
GOLD001_LABEL_HASH = "f9139858b89ea102d30c22e1007b1e807c5aecc684048ffb31df1dcb73e9ef75"
GOLD001_RELEASE_HASH = "f0b3138d32a033b66cd0823cfd83ae89461433209a0552bece6722d2ca98f179"
GOLD001_AUDIT_HASH = "7f95fc104c59dfcdc42a7ced35ea102884c95b9829f15d1c1960895dcd7b1d43"
GOLD001_INITIAL_AUDIT_HASH = "3c5e1ce829eac535a4c7263b3caed47266f67ed7fd16b8f61586164992efbc24"
GOLD001_SEMANTIC_HASH = "d759e827f4c9469db407edfc08d7ab73fd21ff3767bb3e44d8255d896f467976"

# ---------------------------------------------------------------------------
# Column manifests
# ---------------------------------------------------------------------------

SOURCE_COLUMNS: List[str] = [
    "benchmark_id",
    "ticker",
    "publication_datetime",
    "previous_sentence",
    "full_sentence",
    "next_sentence",
    "detected_numeric_tokens",
    "normalized_label",
]

EFFECTIVE_DIMENSION_NAMES: List[str] = [
    "concept",
    "scope",
    "dilution",
    "tax_basis",
    "capex_basis",
    "lease_inclusion",
    "basis_evidence",
    "margin_denominator",
    "attribution",
    "alias_role",
    "value_pattern",
    "valuation_eligibility",
    "should_abstain",
]

AUDIT_COLUMNS: List[str] = [
    "benchmark_id",
    "ticker",
    "normalized_label",
    "review_decision",
    # Seed dimensions
    "seed_concept",
    "seed_scope",
    "seed_dilution",
    "seed_tax_basis",
    "seed_capex_basis",
    "seed_lease_inclusion",
    "seed_margin_denominator",
    "seed_attribution",
    "seed_alias_role",
    "seed_value_pattern",
    "seed_valuation_eligibility",
    "seed_should_abstain",
    # Gold dimensions
    "gold_concept",
    "gold_scope",
    "gold_dilution",
    "gold_tax_basis",
    "gold_capex_basis",
    "gold_lease_inclusion",
    "gold_basis_evidence",
    "gold_margin_denominator",
    "gold_attribution",
    "gold_alias_role",
    "gold_value_pattern",
    "gold_valuation_eligibility",
    "gold_should_abstain",
    # Override presence flags
    "gold_concept_is_override",
    "gold_scope_is_override",
    "gold_dilution_is_override",
    "gold_tax_basis_is_override",
    "gold_capex_basis_is_override",
    "gold_lease_inclusion_is_override",
    "gold_basis_evidence_is_override",
    "gold_margin_denominator_is_override",
    "gold_attribution_is_override",
    "gold_alias_role_is_override",
    "gold_value_pattern_is_override",
    "gold_valuation_eligibility_is_override",
    "gold_should_abstain_is_override",
    # Reviewer notes (annotation content)
    "reviewer_notes",
]

# Legacy 15 columns for semantic_hash
SEMANTIC_COLUMNS: List[str] = [
    "benchmark_id",
    "is_included",
    "effective_concept",
    "effective_scope",
    "effective_dilution",
    "effective_tax_basis",
    "effective_capex_basis",
    "effective_lease_inclusion",
    "effective_basis_evidence",
    "effective_margin_denominator",
    "effective_attribution",
    "effective_alias_role",
    "effective_value_pattern",
    "effective_valuation_eligibility",
    "effective_should_abstain",
]


# ---------------------------------------------------------------------------
# Canonical value formatting helpers
# ---------------------------------------------------------------------------

def canonical_val(v: Any) -> str:
    """Serialize a field value deterministically for hashing."""
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


def canonicalize_detected_numeric_tokens(v: Any) -> str:
    """Canonicalize detected_numeric_tokens deterministically."""
    if v is None:
        return "[]"
    if isinstance(v, str):
        v = v.strip()
        if not v:
            return "[]"
        try:
            parsed = json.loads(v)
        except Exception:
            return v
    else:
        parsed = v

    if isinstance(parsed, list):
        return json.dumps(parsed, separators=(",", ":"))
    return json.dumps(parsed, sort_keys=True, separators=(",", ":"))


def compute_effective_dimension(row: Dict[str, Any], dim: str) -> Any:
    """Compute effective value using CASE WHEN override THEN gold ELSE seed."""
    eff_key = f"effective_{dim}"
    if eff_key in row:
        return row[eff_key]

    flag_key = f"gold_{dim}_is_override"
    gold_key = f"gold_{dim}"
    seed_key = f"seed_{dim}"

    is_override = bool(row.get(flag_key, False))
    if is_override:
        return row.get(gold_key)
    return row.get(seed_key)


def is_row_included(row: Dict[str, Any]) -> bool:
    """Determine whether row is in the evaluation population (non-SKIP)."""
    if "is_included" in row:
        return bool(row["is_included"])
    decision = row.get("review_decision")
    return bool(decision is not None and decision != "SKIP")


# ---------------------------------------------------------------------------
# Hash functions
# ---------------------------------------------------------------------------

def compute_source_hash(rows: Sequence[Dict[str, Any]]) -> str:
    """Compute deterministic SHA-256 source_hash over classifier input text.

    Rows are ordered deterministically by benchmark_id.
    Includes: benchmark_id, ticker, publication_datetime, sentences,
    canonicalized detected_numeric_tokens, and normalized_label.
    """
    sorted_rows = sorted(rows, key=lambda r: str(r["benchmark_id"]))
    hasher = hashlib.sha256()

    for r in sorted_rows:
        bid = r["benchmark_id"]
        ticker = r.get("ticker", "")
        dt_str = canonical_val(r.get("publication_datetime"))
        prev_s = r.get("previous_sentence") or ""
        full_s = r.get("full_sentence") or ""
        next_s = r.get("next_sentence") or ""
        toks_str = canonicalize_detected_numeric_tokens(r.get("detected_numeric_tokens"))
        label = r.get("normalized_label", "")

        line = (
            f"benchmark_id={bid}|ticker={ticker}|publication_datetime={dt_str}|"
            f"previous_sentence={prev_s}|full_sentence={full_s}|next_sentence={next_s}|"
            f"detected_numeric_tokens={toks_str}|normalized_label={label}\n"
        )
        hasher.update(line.encode("utf-8"))

    return hasher.hexdigest()


def compute_label_hash(rows: Sequence[Dict[str, Any]]) -> str:
    """Compute deterministic SHA-256 label_hash over effective annotations.

    Rows are ordered deterministically by benchmark_id.
    - Included rows: hashes benchmark_id, is_included=TRUE, and all 13 effective dimensions.
    - SKIP rows: hashes ONLY benchmark_id and is_included=FALSE.
      Unused effective labels on a SKIP row do not affect label_hash.
    """
    sorted_rows = sorted(rows, key=lambda r: str(r["benchmark_id"]))
    hasher = hashlib.sha256()

    for r in sorted_rows:
        bid = r["benchmark_id"]
        included = is_row_included(r)
        if included:
            parts = [f"benchmark_id={bid}", "is_included=TRUE"]
            for dim in EFFECTIVE_DIMENSION_NAMES:
                val = compute_effective_dimension(r, dim)
                parts.append(f"effective_{dim}={canonical_val(val)}")
            line = "|".join(parts) + "\n"
        else:
            line = f"benchmark_id={bid}|is_included=FALSE\n"
        hasher.update(line.encode("utf-8"))

    return hasher.hexdigest()


def compute_release_hash(
    release_id: str,
    schema_version: str,
    source_hash: str,
    label_hash: str,
) -> str:
    """Compute the authoritative release_hash binding source and label hashes.

    Args:
        release_id: Benchmark release identifier (e.g. 'GOLD-001').
        schema_version: Benchmark release schema version recorded in
            financial_classifier_gold_releases.schema_version (e.g. '1.1.0' for GOLD-001).
        source_hash: Deterministic SHA-256 hash of classifier input corpus.
        label_hash: Deterministic SHA-256 hash of effective annotations & inclusion.

    Returns:
        Hex-encoded SHA-256 release_hash over canonical manifest template (v1.0 format).
    """
    manifest = (
        f"release_id={release_id}|"
        f"schema_version={schema_version}|"
        f"source_hash={source_hash}|"
        f"label_hash={label_hash}\n"
    )
    return hashlib.sha256(manifest.encode("utf-8")).hexdigest()


def compute_audit_hash(rows: Sequence[Dict[str, Any]]) -> str:
    """Compute deterministic SHA-256 audit_hash over the complete annotation state.

    Rows are ordered deterministically by benchmark_id.
    Includes seed, gold, flags, decisions, and reviewer_notes.
    Excludes volatile database timestamps.
    """
    sorted_rows = sorted(rows, key=lambda r: str(r["benchmark_id"]))
    hasher = hashlib.sha256()

    for r in sorted_rows:
        line = "|".join(f"{col}={canonical_val(r.get(col))}" for col in AUDIT_COLUMNS) + "\n"
        hasher.update(line.encode("utf-8"))

    return hasher.hexdigest()


def compute_semantic_hash(rows: Sequence[Dict[str, Any]]) -> str:
    """Legacy/backward-compatible semantic hash evaluator (maps to d759e827...)."""
    sorted_rows = sorted(rows, key=lambda r: str(r["benchmark_id"]))
    hasher = hashlib.sha256()

    for r in sorted_rows:
        bid = r["benchmark_id"]
        included = is_row_included(r)
        parts = [f"benchmark_id={bid}", f"is_included={'TRUE' if included else 'FALSE'}"]
        for dim in EFFECTIVE_DIMENSION_NAMES:
            val = compute_effective_dimension(r, dim)
            parts.append(f"effective_{dim}={canonical_val(val)}")
        line = "|".join(parts) + "\n"
        hasher.update(line.encode("utf-8"))

    return hasher.hexdigest()
