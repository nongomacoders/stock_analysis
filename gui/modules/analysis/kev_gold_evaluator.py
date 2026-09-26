"""Kev-4B Evaluation Adapter for Frozen Financial Classifier Gold Releases (GOLD-001).

Maintains strict architectural separation:
1. Python 3.11 stock_analysis application owns:
   - Database connections (PostgreSQL)
   - GOLD-001 cryptographic release verification
   - Blind prompt/question construction
   - Response parsing and strict benchmark enum validation
   - Evaluation run and prediction persistence
   - Metric scoring against gold labels

2. Local Kev service (running in separate Python 3.13 runtime on localhost:8009) owns:
   - Model execution via POST /v1/systemone
   - Single-forward-pass probability computation

Security / Isolation Constraints:
- Kev retains zero database credentials and zero direct database access.
- Evaluator sends strictly blind context (ticker, publication_datetime, sentences, detected_numeric_tokens, normalized_label).
- Zero seed_* and zero gold_* labels or reviewer notes are ever exposed to the Kev service.
- Evaluation runs and predictions are insert-only (append-only) and never overwrite baseline runs or gold tables.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import psycopg2
import psycopg2.extras

from core.config import DB_CONFIG
from modules.analysis.gold_release_hashes import (
    GOLD001_LABEL_HASH,
    GOLD001_RELEASE_HASH,
    GOLD001_RELEASE_ID,
    GOLD001_SCHEMA_VERSION,
    GOLD001_SOURCE_HASH,
    compute_label_hash,
    compute_release_hash,
    compute_source_hash,
)
from modules.analysis.financial_concept_dictionary import (
    BasisEvidence,
    CapexBasis,
    DilutionBasis,
    DividendTaxBasis,
    LeaseInclusion,
    MarginDenominator,
    OperationScope,
    ProfitAttribution,
    build_default_canonical_concepts,
)
from modules.analysis.financial_classifier_benchmark import (
    AliasRole,
    ValuationEligibility,
    ValuePattern,
)

logger = logging.getLogger(__name__)

KEV_DEFAULT_ENDPOINT = "http://127.0.0.1:8009/v1/systemone"
KEV_MODELS_ENDPOINT = "http://127.0.0.1:8009/v1/models"

# ---------------------------------------------------------------------------
# Canonical Benchmark Dimensions & Normalization
# ---------------------------------------------------------------------------

CANONICAL_13_DIMENSIONS: Tuple[str, ...] = (
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
)


def normalize_basis_evidence(val: Optional[str]) -> str:
    """Canonicalize basis_evidence representation for evaluation semantics.
    
    Treats NULL, None, empty string, or case variants as 'unspecified'.
    Does not mutate underlying database or gold rows.
    """
    if val is None:
        return BasisEvidence.UNSPECIFIED.value
    cleaned = str(val).strip().lower()
    if not cleaned or cleaned in ("none", "null", "unspecified"):
        return BasisEvidence.UNSPECIFIED.value
    return cleaned


def assert_valid_pre_run_schema(configuration_json: Dict[str, Any]) -> str:
    """Validate that question schema version and hash are established before inference."""
    version = configuration_json.get("question_schema_version")
    if not version or not isinstance(version, str):
        raise ValueError("PRE-RUN GUARD VIOLATION: question_schema_version must be provided pre-run.")
    schema_hash = configuration_json.get("question_schema_hash")
    if not schema_hash or not isinstance(schema_hash, str) or len(schema_hash) != 64:
        raise ValueError("PRE-RUN GUARD VIOLATION: valid 64-char question_schema_hash must be computed and stored pre-run.")
    return schema_hash


# ---------------------------------------------------------------------------
# Static Question Definitions (13 Canonical Benchmark Dimensions)
# ---------------------------------------------------------------------------

def build_static_concept_criteria() -> Dict[str, str]:
    """Build complete canonical concept choice universe (65 concepts)."""
    base_concepts = build_default_canonical_concepts()
    criteria: Dict[str, str] = {}
    for cid, c in sorted(base_concepts.items()):
        criteria[cid] = c.name

    # Additional canonical concepts appearing in reviewed gold benchmark
    extra_gold_concepts = {
        "weighted_average_shares": "Weighted average ordinary shares in issue",
        "issued_shares": "Total issued ordinary shares",
        "total_assets": "Total statutory balance sheet assets",
        "unknown": "General commentary or not a canonical financial concept",
    }
    for cid, desc in extra_gold_concepts.items():
        if cid not in criteria:
            criteria[cid] = desc

    return criteria


def build_static_questions() -> Dict[str, Dict[str, Any]]:
    """Return model-agnostic, row-invariant question schema for all 13 dimensions."""
    return {
        "concept": {
            "type": "choice",
            "instructions": "Identify the financial concept referred to in the sentence.",
            "criteria": build_static_concept_criteria(),
        },
        "scope": {
            "type": "choice",
            "instructions": "Operating scope.",
            "criteria": {
                OperationScope.UNSPECIFIED.value: "Unspecified scope",
                OperationScope.GROUP_CONSOLIDATED.value: "Group consolidated operations",
                OperationScope.TOTAL_OPERATIONS.value: "Total operations (continuing and discontinued)",
                OperationScope.CONTINUING_OPERATIONS.value: "Continuing operations only",
                OperationScope.DISCONTINUED_OPERATIONS.value: "Discontinued operations only",
                OperationScope.SEGMENT.value: "Specific operating segment",
            },
        },
        "dilution": {
            "type": "choice",
            "instructions": "Dilution basis.",
            "criteria": {
                DilutionBasis.UNSPECIFIED.value: "Unspecified or not per-share",
                DilutionBasis.BASIC.value: "Basic undiluted metric",
                DilutionBasis.DILUTED.value: "Diluted per-share metric",
            },
        },
        "tax_basis": {
            "type": "choice",
            "instructions": "Dividend tax basis.",
            "criteria": {
                DividendTaxBasis.UNSPECIFIED.value: "Unspecified or not a dividend",
                DividendTaxBasis.GROSS.value: "Gross of dividend withholding tax",
                DividendTaxBasis.NET.value: "Net of dividend withholding tax",
            },
        },
        "capex_basis": {
            "type": "choice",
            "instructions": "Capex measurement basis.",
            "criteria": {
                CapexBasis.UNSPECIFIED.value: "Unspecified or not capex",
                CapexBasis.CASH_PAYMENTS.value: "Cash payments for capex",
                CapexBasis.ACCOUNTING_ADDITIONS.value: "Accounting additions to assets",
            },
        },
        "lease_inclusion": {
            "type": "choice",
            "instructions": "Lease liabilities inclusion.",
            "criteria": {
                LeaseInclusion.UNSPECIFIED.value: "Unspecified or not debt/cash",
                LeaseInclusion.INC_LEASES.value: "Including lease liabilities (IFRS 16)",
                LeaseInclusion.EX_LEASES.value: "Excluding lease liabilities",
            },
        },
        "basis_evidence": {
            "type": "choice",
            "instructions": "Evidentiary presentation basis.",
            "criteria": {
                BasisEvidence.UNSPECIFIED.value: "Unspecified or standard context",
                BasisEvidence.BALANCE_SHEET_PRESENTATION_SEPARATE.value: "Separate balance sheet presentation",
                BasisEvidence.EXPLICIT_NOTE_WORDING.value: "Explicit note disclosure",
                BasisEvidence.RECONCILED_SOURCE_FORMULA.value: "Reconciled source formula",
                BasisEvidence.DETERMINISTIC_PARSER_SECTION.value: "Standardized parser section",
            },
        },
        "margin_denominator": {
            "type": "choice",
            "instructions": "Margin denominator basis.",
            "criteria": {
                MarginDenominator.UNSPECIFIED.value: "Unspecified or not a margin",
                MarginDenominator.ACCOUNTING_REVENUE.value: "Statutory accounting revenue",
                MarginDenominator.MERCHANDISE_SALES.value: "Sale of merchandise",
                MarginDenominator.TURNOVER.value: "Turnover",
            },
        },
        "attribution": {
            "type": "choice",
            "instructions": "Earnings profit attribution.",
            "criteria": {
                ProfitAttribution.UNSPECIFIED.value: "Unspecified or not earnings",
                ProfitAttribution.PARENT_EQUITY_HOLDERS.value: "Attributable to equity holders of parent",
                ProfitAttribution.TOTAL_GROUP.value: "Total group earnings",
                ProfitAttribution.NON_CONTROLLING_INTEREST.value: "Attributable to non-controlling interest",
                ProfitAttribution.HEADLINE_ATTRIBUTABLE.value: "Headline earnings attributable to ordinary shareholders",
            },
        },
        "alias_role": {
            "type": "choice",
            "instructions": "Syntactic function of the wording.",
            "criteria": {
                AliasRole.DIRECT_VALUE_LABEL.value: "Direct value label for canonical metric",
                AliasRole.CHANGE_STATEMENT.value: "Change statement or rate delta",
                AliasRole.GUIDANCE_STATEMENT.value: "Guidance, forecast, or outlook wording",
                AliasRole.CONCEPT_MENTION_ONLY.value: "Discursive mention without extractable number",
            },
        },
        "value_pattern": {
            "type": "choice",
            "instructions": "Structure of adjacent numbers.",
            "criteria": {
                ValuePattern.DIRECT_LEVEL.value: "Direct level figure",
                ValuePattern.CHANGE_RATE_ONLY.value: "Change rate or percentage only",
                ValuePattern.CHANGE_RATE_TO_LEVEL.value: "Change rate and level reached",
                ValuePattern.FROM_TO_LEVEL.value: "From a starting level to an ending level",
                ValuePattern.RANGE.value: "Value range",
                ValuePattern.UNKNOWN.value: "Complex or unstructured syntax",
            },
        },
        "valuation_eligibility": {
            "type": "choice",
            "instructions": "Admissibility for valuation intake.",
            "criteria": {
                ValuationEligibility.ELIGIBLE.value: "Directly eligible for valuation intake",
                ValuationEligibility.ELIGIBLE_WITH_QUALIFIER.value: "Eligible with qualifier confirmation",
                ValuationEligibility.REQUIRES_SCOPE.value: "Requires scope verification",
                ValuationEligibility.REQUIRES_BASIS.value: "Requires basis verification",
                ValuationEligibility.REQUIRES_PERIOD.value: "Requires period verification",
                ValuationEligibility.REQUIRES_SOURCE_SECTION.value: "Requires source section verification",
                ValuationEligibility.INFORMATIONAL_ONLY.value: "Informational mention only",
                ValuationEligibility.PROHIBITED.value: "Prohibited from valuation intake",
            },
        },
        "should_abstain": {
            "type": "choice",
            "instructions": "Whether to abstain from classification.",
            "criteria": {
                "true": "Abstain: mention only, ambiguous, or lacks definitive figures",
                "false": "Classify: concrete extractable financial metric information",
            },
        },
    }


STATIC_QUESTIONS = build_static_questions()


def build_explicit_evidence_v2_questions() -> Dict[str, Dict[str, Any]]:
    """Return explicit-evidence-v2 schema without valuation_eligibility, enforcing strict negative constraints."""
    return {
        "concept": {
            "type": "choice",
            "instructions": "Identify the financial concept referred to in the sentence.",
            "criteria": build_static_concept_criteria(),
        },
        "scope": {
            "type": "choice",
            "instructions": "Choose a specific operation scope only when the supplied text explicitly establishes it. Otherwise choose UNSPECIFIED.",
            "criteria": {
                OperationScope.UNSPECIFIED.value: "Unspecified scope",
                OperationScope.GROUP_CONSOLIDATED.value: "Group consolidated operations",
                OperationScope.TOTAL_OPERATIONS.value: "Total operations (continuing and discontinued)",
                OperationScope.CONTINUING_OPERATIONS.value: "Continuing operations only",
                OperationScope.DISCONTINUED_OPERATIONS.value: "Discontinued operations only",
                OperationScope.SEGMENT.value: "Specific operating segment",
            },
        },
        "dilution": {
            "type": "choice",
            "instructions": "Choose BASIC or DILUTED only when the supplied text explicitly states or unambiguously establishes the dilution basis. The fact that a metric is per-share is not sufficient. Otherwise choose UNSPECIFIED.",
            "criteria": {
                DilutionBasis.UNSPECIFIED.value: "Unspecified or not explicitly stated in text",
                DilutionBasis.BASIC.value: "Basic undiluted metric",
                DilutionBasis.DILUTED.value: "Diluted per-share metric",
            },
        },
        "tax_basis": {
            "type": "choice",
            "instructions": "Choose GROSS or NET only when dividend withholding-tax treatment is explicitly stated. Otherwise choose UNSPECIFIED.",
            "criteria": {
                DividendTaxBasis.UNSPECIFIED.value: "Unspecified or withholding tax not explicitly stated",
                DividendTaxBasis.GROSS.value: "Gross of dividend withholding tax",
                DividendTaxBasis.NET.value: "Net of dividend withholding tax",
            },
        },
        "capex_basis": {
            "type": "choice",
            "instructions": "Choose CASH_PAYMENTS or ACCOUNTING_ADDITIONS only when capex accounting basis is explicitly stated in the text. Otherwise choose UNSPECIFIED.",
            "criteria": {
                CapexBasis.UNSPECIFIED.value: "Unspecified capex basis",
                CapexBasis.CASH_PAYMENTS.value: "Cash payments for capex",
                CapexBasis.ACCOUNTING_ADDITIONS.value: "Accounting additions to assets",
            },
        },
        "lease_inclusion": {
            "type": "choice",
            "instructions": "Choose INC_LEASES or EX_LEASES only when the supplied text explicitly establishes lease treatment. Do not infer from the words debt, EBITDA, borrowings, or cash. Otherwise choose UNSPECIFIED.",
            "criteria": {
                LeaseInclusion.UNSPECIFIED.value: "Unspecified lease treatment",
                LeaseInclusion.INC_LEASES.value: "Including lease liabilities (IFRS 16)",
                LeaseInclusion.EX_LEASES.value: "Excluding lease liabilities",
            },
        },
        "basis_evidence": {
            "type": "choice",
            "instructions": "Choose a specific evidence basis only when that basis is explicitly present in the supplied text. Otherwise choose UNSPECIFIED.",
            "criteria": {
                BasisEvidence.UNSPECIFIED.value: "Unspecified or standard context",
                BasisEvidence.BALANCE_SHEET_PRESENTATION_SEPARATE.value: "Separate balance sheet presentation",
                BasisEvidence.EXPLICIT_NOTE_WORDING.value: "Explicit note disclosure",
                BasisEvidence.RECONCILED_SOURCE_FORMULA.value: "Reconciled source formula",
                BasisEvidence.DETERMINISTIC_PARSER_SECTION.value: "Standardized parser section",
            },
        },
        "margin_denominator": {
            "type": "choice",
            "instructions": "Choose a specific denominator only when explicitly stated in the text. Otherwise choose UNSPECIFIED.",
            "criteria": {
                MarginDenominator.UNSPECIFIED.value: "Unspecified margin denominator",
                MarginDenominator.ACCOUNTING_REVENUE.value: "Statutory accounting revenue",
                MarginDenominator.MERCHANDISE_SALES.value: "Sale of merchandise",
                MarginDenominator.TURNOVER.value: "Turnover",
            },
        },
        "attribution": {
            "type": "choice",
            "instructions": "Choose a specific profit attribution only when explicitly established in text. Otherwise choose UNSPECIFIED.",
            "criteria": {
                ProfitAttribution.UNSPECIFIED.value: "Unspecified profit attribution",
                ProfitAttribution.PARENT_EQUITY_HOLDERS.value: "Attributable to equity holders of parent",
                ProfitAttribution.TOTAL_GROUP.value: "Total group earnings",
                ProfitAttribution.NON_CONTROLLING_INTEREST.value: "Attributable to non-controlling interest",
                ProfitAttribution.HEADLINE_ATTRIBUTABLE.value: "Headline earnings attributable to ordinary shareholders",
            },
        },
        "alias_role": {
            "type": "choice",
            "instructions": "Syntactic function of the wording.",
            "criteria": {
                AliasRole.DIRECT_VALUE_LABEL.value: "Direct value label for canonical metric",
                AliasRole.CHANGE_STATEMENT.value: "Change statement or rate delta",
                AliasRole.GUIDANCE_STATEMENT.value: "Guidance, forecast, or outlook wording",
                AliasRole.CONCEPT_MENTION_ONLY.value: "Discursive mention without extractable number",
            },
        },
        "value_pattern": {
            "type": "choice",
            "instructions": "Structure of adjacent numbers.",
            "criteria": {
                ValuePattern.DIRECT_LEVEL.value: "Direct level figure",
                ValuePattern.CHANGE_RATE_ONLY.value: "Change rate or percentage only",
                ValuePattern.CHANGE_RATE_TO_LEVEL.value: "Change rate and level reached",
                ValuePattern.FROM_TO_LEVEL.value: "From a starting level to an ending level",
                ValuePattern.RANGE.value: "Value range",
                ValuePattern.UNKNOWN.value: "Complex or unstructured syntax",
            },
        },
        "should_abstain": {
            "type": "choice",
            "instructions": "Whether to abstain from classification.",
            "criteria": {
                "true": "Abstain: mention only, ambiguous, or lacks definitive figures",
                "false": "Classify: concrete extractable financial metric information",
            },
        },
    }


STATIC_QUESTIONS_V2 = build_explicit_evidence_v2_questions()


def compute_question_schema_hash(questions: Dict[str, Any]) -> str:
    """Compute deterministic SHA-256 hash of question schema."""
    import hashlib
    canonical_repr = json.dumps(questions, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_repr.encode("utf-8")).hexdigest()


def derive_deterministic_policy(predicted_fields: Dict[str, Any]) -> Tuple[str, bool]:
    """Derive valuation_eligibility and should_abstain_policy deterministically from Kev's semantic predictions."""
    concept = predicted_fields.get("predicted_concept")
    scope = predicted_fields.get("predicted_scope") or "unspecified"
    dilution = predicted_fields.get("predicted_dilution") or "unspecified"
    tax_basis = predicted_fields.get("predicted_tax_basis") or "unspecified"
    capex_basis = predicted_fields.get("predicted_capex_basis") or "unspecified"
    lease_inclusion = predicted_fields.get("predicted_lease_inclusion") or "unspecified"
    margin_denominator = predicted_fields.get("predicted_margin_denominator") or "unspecified"
    alias_role = predicted_fields.get("predicted_alias_role") or "CONCEPT_MENTION_ONLY"
    value_pattern = predicted_fields.get("predicted_value_pattern") or "UNKNOWN"
    raw_should_abstain = predicted_fields.get("predicted_should_abstain")

    # 1. Unrecognized or absent concept -> INFORMATIONAL_ONLY, abstain
    if not concept or concept == "unknown":
        return ValuationEligibility.INFORMATIONAL_ONLY.value, True

    # 2. Syntactic mention only or forward-looking guidance -> INFORMATIONAL_ONLY, abstain
    if alias_role in (AliasRole.CONCEPT_MENTION_ONLY.value, AliasRole.GUIDANCE_STATEMENT.value):
        return ValuationEligibility.INFORMATIONAL_ONLY.value, True

    # 3. Unstructured or rate-only pattern -> INFORMATIONAL_ONLY, abstain
    if value_pattern in (ValuePattern.UNKNOWN.value, ValuePattern.RANGE.value, ValuePattern.CHANGE_RATE_ONLY.value):
        return ValuationEligibility.INFORMATIONAL_ONLY.value, True

    # 4. Qualifier-dependent accounting concepts
    norm_concept = str(concept).lower()

    # Debt / EBITDA requires lease treatment
    if any(k in norm_concept for k in ["debt", "borrowing", "ebitda", "lease"]):
        if lease_inclusion == LeaseInclusion.UNSPECIFIED.value:
            return ValuationEligibility.REQUIRES_BASIS.value, True

    # Capex requires capex accounting basis (cash vs additions)
    if "capex" in norm_concept or "capital_expenditure" in norm_concept:
        if capex_basis == CapexBasis.UNSPECIFIED.value:
            return ValuationEligibility.REQUIRES_BASIS.value, True

    # Margins require explicit denominator
    if "margin" in norm_concept:
        if margin_denominator == MarginDenominator.UNSPECIFIED.value:
            return ValuationEligibility.REQUIRES_BASIS.value, True

    # Dividends require tax withholding basis
    if "dividend" in norm_concept and "yield" not in norm_concept:
        if tax_basis == DividendTaxBasis.UNSPECIFIED.value:
            return ValuationEligibility.REQUIRES_BASIS.value, True

    # Per-share metrics require dilution basis
    if any(k in norm_concept for k in ["eps", "heps", "per_share"]):
        if dilution == DilutionBasis.UNSPECIFIED.value:
            return ValuationEligibility.REQUIRES_BASIS.value, True

    # Share counts require period / timing verification
    if any(k in norm_concept for k in ["shares", "share_count"]):
        return ValuationEligibility.REQUIRES_PERIOD.value, True

    # Respect Kev's raw explicit abstention if model affirmatively said to abstain
    if raw_should_abstain is True:
        return ValuationEligibility.INFORMATIONAL_ONLY.value, True

    # 5. Direct value label with verified qualifiers
    has_explicit_qualifiers = (
        scope != OperationScope.UNSPECIFIED.value
        or dilution != DilutionBasis.UNSPECIFIED.value
        or tax_basis != DividendTaxBasis.UNSPECIFIED.value
        or capex_basis != CapexBasis.UNSPECIFIED.value
        or lease_inclusion != LeaseInclusion.UNSPECIFIED.value
        or margin_denominator != MarginDenominator.UNSPECIFIED.value
    )
    if has_explicit_qualifiers:
        return ValuationEligibility.ELIGIBLE_WITH_QUALIFIER.value, False
    return ValuationEligibility.ELIGIBLE.value, False


# ---------------------------------------------------------------------------
# Release Integrity & Population Verification
# ---------------------------------------------------------------------------

def verify_gold001_release(conn: Any) -> Dict[str, str]:
    """Verify that database GOLD-001 release exactly matches canonical immutable hashes."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT *
        FROM financial_classifier_gold_review
        WHERE review_batch = 'BATCH-001'
        ORDER BY benchmark_id;
    """)
    rows = cur.fetchall()
    if len(rows) != 300:
        raise ValueError(f"GOLD-001 review batch row count mismatch: expected 300, got {len(rows)}")

    calc_source_hash = compute_source_hash(rows)
    calc_label_hash = compute_label_hash(rows)
    calc_release_hash = compute_release_hash(
        GOLD001_RELEASE_ID, GOLD001_SCHEMA_VERSION, calc_source_hash, calc_label_hash
    )

    if calc_source_hash != GOLD001_SOURCE_HASH:
        raise ValueError(
            f"GOLD-001 source_hash mismatch!\nExpected: {GOLD001_SOURCE_HASH}\nComputed: {calc_source_hash}"
        )
    if calc_label_hash != GOLD001_LABEL_HASH:
        raise ValueError(
            f"GOLD-001 label_hash mismatch!\nExpected: {GOLD001_LABEL_HASH}\nComputed: {calc_label_hash}"
        )
    if calc_release_hash != GOLD001_RELEASE_HASH:
        raise ValueError(
            f"GOLD-001 release_hash mismatch!\nExpected: {GOLD001_RELEASE_HASH}\nComputed: {calc_release_hash}"
        )

    return {
        "release_id": GOLD001_RELEASE_ID,
        "release_hash": calc_release_hash,
        "source_hash": calc_source_hash,
        "label_hash": calc_label_hash,
    }


def get_gold001_evaluation_population(conn: Any) -> List[Dict[str, Any]]:
    """Select the exact 281 evaluation rows for GOLD-001 excluding SKIP rows."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT *
        FROM financial_classifier_gold_001_effective
        ORDER BY benchmark_id;
    """)
    rows = cur.fetchall()
    if len(rows) != 281:
        raise ValueError(f"GOLD-001 evaluation population mismatch: expected 281, got {len(rows)}")
    return rows


# ---------------------------------------------------------------------------
# Blind Payload Construction
# ---------------------------------------------------------------------------

def build_blind_request(
    row: Dict[str, Any],
    model_name: str = "kev-latest",
    questions: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Construct blind TypeSafe SystemOne request payload containing NO seed or gold answers."""
    # Strict assertion against leakage
    forbidden_keys = [
        "seed_concept", "seed_scope", "seed_dilution", "seed_tax_basis", "seed_capex_basis",
        "seed_lease_inclusion", "seed_margin_denominator", "seed_attribution", "seed_alias_role",
        "seed_value_pattern", "seed_valuation_eligibility", "seed_should_abstain",
        "gold_concept", "gold_scope", "gold_dilution", "gold_tax_basis", "gold_capex_basis",
        "gold_lease_inclusion", "gold_basis_evidence", "gold_margin_denominator", "gold_attribution",
        "gold_alias_role", "gold_value_pattern", "gold_valuation_eligibility", "gold_should_abstain",
        "effective_concept", "effective_scope", "effective_dilution", "effective_tax_basis",
        "effective_capex_basis", "effective_lease_inclusion", "effective_basis_evidence",
        "effective_margin_denominator", "effective_attribution", "effective_alias_role",
        "effective_value_pattern", "effective_valuation_eligibility", "effective_should_abstain",
        "review_decision", "reviewer_notes", "was_overridden",
    ]

    state_dict = {
        "benchmark_id": row["benchmark_id"],
        "ticker": row["ticker"],
        "publication_datetime": str(row["publication_datetime"]),
        "normalized_label": row["normalized_label"],
        "detected_numeric_tokens": str(row["detected_numeric_tokens"]),
        "previous_sentence": row.get("previous_sentence") or "",
        "full_sentence": row.get("full_sentence") or "",
        "next_sentence": row.get("next_sentence") or "",
    }

    for k in state_dict:
        if k in forbidden_keys or k.startswith("seed_") or k.startswith("gold_"):
            raise ValueError(f"BLINDNESS VIOLATION: forbidden key '{k}' in request state!")

    active_questions = questions if questions is not None else STATIC_QUESTIONS

    return {
        "model": model_name,
        "state": state_dict,
        "questions": active_questions,
    }



# ---------------------------------------------------------------------------
# Kev Service Interaction & Validation
# ---------------------------------------------------------------------------

def _find_hf_snapshot(repo_id: str) -> Optional[str]:
    """Find local snapshot revision hash in Hugging Face hub cache if present."""
    import os
    from pathlib import Path

    cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
    repo_folder_name = "models--" + repo_id.replace("/", "--")
    snapshots_dir = cache_dir / repo_folder_name / "snapshots"
    if snapshots_dir.exists():
        for child in snapshots_dir.iterdir():
            if child.is_dir():
                return child.name
    return None


def fetch_kev_model_provenance(models_endpoint: str = KEV_MODELS_ENDPOINT) -> Dict[str, Any]:
    """Fetch model provenance metadata from Kev server."""
    req = urllib.request.Request(models_endpoint, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    
    models = data.get("models", [])
    primary = models[0] if models else {}
    run_id = primary.get("run", "jaredpalmer/kev-4b")
    base_id = primary.get("base", "Qwen/Qwen3.5-4B-Base")

    run_hf_rev = _find_hf_snapshot(run_id)
    base_hf_rev = _find_hf_snapshot(base_id)

    return {
        "kev_git_commit": "f1535963cea021439370c23127bc970b6788e730",
        "kev_package_version": "0.1.0",
        "model_run": run_id,
        "model_base": base_id,
        "hf_revision": run_hf_rev,
        "base_hf_revision": base_hf_rev,
        # Backward-compatible keys for 4b if running 4b
        "kev_4b_hf_revision": run_hf_rev if "4b" in run_id else "139fdd94f1b6a6ad80cc15e08fcb99cac885a101",
        "qwen35_4b_hf_revision": base_hf_rev if "4b" in base_id else "1001bb4d826a52d1f399e183466143f4da7b741b",
        "python_runtime": "3.13.7",
        "torch_version": "2.8.0+cpu",
        "device": primary.get("device", "cpu"),
        "backend": primary.get("backend", "torch"),
        "dtype": primary.get("dtype", "float32"),
        "temperature": primary.get("temperature", 2.35),
        "model_name": primary.get("name", "kev-latest"),
        "run": run_id,
        "base": base_id,
        "lora_rank": primary.get("lora", 16),
        "release_date": primary.get("release_date", "2026-09-24"),
    }



def call_kev_systemone(
    payload: Dict[str, Any],
    endpoint: str = KEV_DEFAULT_ENDPOINT,
    timeout_s: float = 600.0,
) -> Tuple[int, Dict[str, Any], str, float]:
    """Execute HTTP POST call to Kev /v1/systemone endpoint.
    
    Returns:
        (status_code, response_json, raw_text, client_latency_ms)
    """
    req_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=req_bytes,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )

    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        raw_text = resp.read().decode("utf-8")
        status_code = resp.status
    t1 = time.perf_counter()

    client_latency_ms = (t1 - t0) * 1000.0
    res_json = json.loads(raw_text)
    return status_code, res_json, raw_text, client_latency_ms


def validate_and_parse_prediction(
    res_json: Dict[str, Any],
    static_questions: Dict[str, Dict[str, Any]],
) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
    """Validate Kev answers against allowed enum universes without silent coercion.
    
    Returns:
        (predicted_fields, confidence_json, parse_errors)
    """
    answers = res_json.get("answers", {})
    predicted: Dict[str, Any] = {}
    confidence_data: Dict[str, Any] = {
        "model": res_json.get("model"),
        "usage": res_json.get("usage"),
        "server_latency_ms": res_json.get("latency_ms"),
        "questions": {},
    }
    parse_errors: List[str] = []

    dimension_keys = list(static_questions.keys())

    for dim in dimension_keys:
        ans = answers.get(dim)
        if not ans:
            parse_errors.append(f"Missing question answer: '{dim}'")
            predicted[f"predicted_{dim}"] = None
            continue

        choice = ans.get("choice")
        allowed = set(static_questions[dim]["criteria"].keys())

        if choice not in allowed:
            parse_errors.append(f"Invalid enum choice for '{dim}': '{choice}' not in allowed criteria")
            predicted[f"predicted_{dim}"] = None
        else:
            if dim == "should_abstain":
                predicted[f"predicted_{dim}"] = (choice == "true")
            elif dim == "concept" and choice == "unknown":
                predicted[f"predicted_{dim}"] = None
            else:
                predicted[f"predicted_{dim}"] = choice

        confidence_data["questions"][dim] = {
            "choice": choice,
            "confidence": ans.get("confidence"),
            "probabilities": ans.get("probabilities"),
        }

    return predicted, confidence_data, parse_errors


# ---------------------------------------------------------------------------
# Database Persistence
# ---------------------------------------------------------------------------

def persist_evaluation_run(
    conn: Any,
    run_id: str,
    release_hashes: Dict[str, str],
    provenance: Dict[str, Any],
    configuration_json: Dict[str, Any],
    status: str = "running",
) -> None:
    """Insert or initialize evaluation run record with immutability guarantees."""
    cur = conn.cursor()

    # Pre-run schema guard: reject unhashed or unversioned schemas
    assert_valid_pre_run_schema(configuration_json)

    # Immutability guard: do not overwrite completed runs or runs with predictions
    cur.execute("""
        SELECT status, configuration_json, release_hash, source_hash, label_hash
        FROM financial_classifier_evaluation_runs
        WHERE run_id = %s;
    """, (run_id,))
    existing = cur.fetchone()
    if existing:
        ex_status = existing[0]
        if ex_status == "completed":
            raise ValueError(f"IMMUTABILITY VIOLATION: Evaluation run '{run_id}' is completed and cannot be re-initialized.")
        cur.execute("SELECT 1 FROM financial_classifier_evaluation_predictions WHERE run_id = %s LIMIT 1;", (run_id,))
        if cur.fetchone():
            raise ValueError(f"IMMUTABILITY VIOLATION: Evaluation run '{run_id}' already has recorded predictions. Configuration cannot be mutated.")

    cur.execute("""
        INSERT INTO financial_classifier_evaluation_runs (
            run_id, release_id, model_name, model_version, configuration_json,
            started_at, status, release_hash, source_hash, label_hash
        ) VALUES (
            %(run_id)s, %(release_id)s, %(model_name)s, %(model_version)s, %(config)s,
            NOW(), %(status)s, %(release_hash)s, %(source_hash)s, %(label_hash)s
        )
        ON CONFLICT (run_id) DO UPDATE SET
            status = EXCLUDED.status,
            configuration_json = EXCLUDED.configuration_json;
    """, {
        "run_id": run_id,
        "release_id": release_hashes["release_id"],
        "model_name": provenance["run"],
        "model_version": provenance["kev_git_commit"],
        "config": json.dumps(configuration_json),
        "status": status,
        "release_hash": release_hashes["release_hash"],
        "source_hash": release_hashes["source_hash"],
        "label_hash": release_hashes["label_hash"],
    })
    conn.commit()


def persist_prediction(
    conn: Any,
    run_id: str,
    benchmark_id: str,
    predicted_fields: Dict[str, Any],
    confidence_json: Dict[str, Any],
    raw_model_output: str,
) -> None:
    """Insert prediction record into financial_classifier_evaluation_predictions."""
    cur = conn.cursor()
    data = {
        "run_id": run_id,
        "benchmark_id": benchmark_id,
        "predicted_concept": predicted_fields.get("predicted_concept"),
        "predicted_scope": predicted_fields.get("predicted_scope"),
        "predicted_dilution": predicted_fields.get("predicted_dilution"),
        "predicted_tax_basis": predicted_fields.get("predicted_tax_basis"),
        "predicted_capex_basis": predicted_fields.get("predicted_capex_basis"),
        "predicted_lease_inclusion": predicted_fields.get("predicted_lease_inclusion"),
        "predicted_basis_evidence": predicted_fields.get("predicted_basis_evidence"),
        "predicted_margin_denominator": predicted_fields.get("predicted_margin_denominator"),
        "predicted_attribution": predicted_fields.get("predicted_attribution"),
        "predicted_alias_role": predicted_fields.get("predicted_alias_role"),
        "predicted_value_pattern": predicted_fields.get("predicted_value_pattern"),
        "predicted_valuation_eligibility": predicted_fields.get("predicted_valuation_eligibility"),
        "derived_valuation_eligibility": predicted_fields.get("derived_valuation_eligibility"),
        "predicted_should_abstain": predicted_fields.get("predicted_should_abstain"),
        "predicted_should_abstain_policy": predicted_fields.get("predicted_should_abstain_policy"),
        "confidence_json": json.dumps(confidence_json),
        "raw_model_output": raw_model_output,
    }

    cur.execute("""
        INSERT INTO financial_classifier_evaluation_predictions (
            run_id, benchmark_id,
            predicted_concept, predicted_scope, predicted_dilution, predicted_tax_basis,
            predicted_capex_basis, predicted_lease_inclusion, predicted_basis_evidence,
            predicted_margin_denominator, predicted_attribution, predicted_alias_role,
            predicted_value_pattern, predicted_valuation_eligibility, derived_valuation_eligibility,
            predicted_should_abstain, predicted_should_abstain_policy,
            confidence_json, raw_model_output
        ) VALUES (
            %(run_id)s, %(benchmark_id)s,
            %(predicted_concept)s, %(predicted_scope)s, %(predicted_dilution)s, %(predicted_tax_basis)s,
            %(predicted_capex_basis)s, %(predicted_lease_inclusion)s, %(predicted_basis_evidence)s,
            %(predicted_margin_denominator)s, %(predicted_attribution)s, %(predicted_alias_role)s,
            %(predicted_value_pattern)s, %(predicted_valuation_eligibility)s, %(derived_valuation_eligibility)s,
            %(predicted_should_abstain)s, %(predicted_should_abstain_policy)s,
            %(confidence_json)s, %(raw_model_output)s
        );
    """, data)
    conn.commit()


def update_run_completed(
    conn: Any,
    run_id: str,
    summary_metrics: Dict[str, Any],
) -> None:
    """Mark evaluation run completed with summary metrics."""
    cur = conn.cursor()
    cur.execute("""
        UPDATE financial_classifier_evaluation_runs
        SET status = 'completed',
            completed_at = NOW(),
            summary_metrics_json = %(metrics)s
        WHERE run_id = %(run_id)s;
    """, {
        "run_id": run_id,
        "metrics": json.dumps(summary_metrics),
    })
    conn.commit()


# ---------------------------------------------------------------------------
# Scoring against GOLD-001 (Post-Persistence Only)
# ---------------------------------------------------------------------------

def score_predictions_against_gold(
    conn: Any,
    run_id: str,
    benchmark_ids: Sequence[str],
) -> List[Dict[str, Any]]:
    """Compare recorded predictions against effective gold labels across all 13 canonical dimensions."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT
            p.benchmark_id,
            p.predicted_concept,
            g.effective_concept,
            p.predicted_should_abstain,
            g.effective_should_abstain,
            p.predicted_scope,
            g.effective_scope,
            p.predicted_dilution,
            g.effective_dilution,
            p.predicted_tax_basis,
            g.effective_tax_basis,
            p.predicted_capex_basis,
            g.effective_capex_basis,
            p.predicted_lease_inclusion,
            g.effective_lease_inclusion,
            p.predicted_basis_evidence,
            g.effective_basis_evidence,
            p.predicted_margin_denominator,
            g.effective_margin_denominator,
            p.predicted_attribution,
            g.effective_attribution,
            p.predicted_alias_role,
            g.effective_alias_role,
            p.predicted_value_pattern,
            g.effective_value_pattern,
            p.predicted_valuation_eligibility,
            p.derived_valuation_eligibility,
            g.effective_valuation_eligibility,
            p.predicted_should_abstain_policy,
            p.confidence_json
        FROM financial_classifier_evaluation_predictions p
        JOIN financial_classifier_gold_001_effective g
          ON p.benchmark_id = g.benchmark_id
        WHERE p.run_id = %s
          AND p.benchmark_id = ANY(%s)
        ORDER BY p.benchmark_id;
    """, (run_id, list(benchmark_ids)))
    
    rows = cur.fetchall()
    scored: List[Dict[str, Any]] = []

    for r in rows:
        conf_dict = r["confidence_json"] or {}
        q_conf = conf_dict.get("questions", {})

        dim_matches: Dict[str, bool] = {}
        for d in CANONICAL_13_DIMENSIONS:
            pred_val = r[f"predicted_{d}"]
            gold_val = r[f"effective_{d}"]
            if d == "basis_evidence":
                dim_matches[d] = (normalize_basis_evidence(pred_val) == normalize_basis_evidence(gold_val))
            elif d == "valuation_eligibility" and pred_val is None and r.get("derived_valuation_eligibility"):
                dim_matches[d] = (r["derived_valuation_eligibility"] == gold_val)
            else:
                dim_matches[d] = (pred_val == gold_val)

        full_label_match = all(dim_matches.values())

        scored.append({
            "benchmark_id": r["benchmark_id"],
            "predicted_concept": r["predicted_concept"],
            "gold_concept": r["effective_concept"],
            "concept_match": dim_matches["concept"],
            "concept_confidence": q_conf.get("concept", {}).get("confidence"),
            "predicted_should_abstain": r["predicted_should_abstain"],
            "gold_should_abstain": r["effective_should_abstain"],
            "abstain_match": dim_matches["should_abstain"],
            "abstain_confidence": q_conf.get("should_abstain", {}).get("confidence"),
            "predicted_should_abstain_policy": r.get("predicted_should_abstain_policy"),
            "derived_valuation_eligibility": r.get("derived_valuation_eligibility"),
            "full_label_match": full_label_match,
            "dimension_matches": dim_matches,
            "server_latency_ms": conf_dict.get("server_latency_ms"),
            "client_latency_ms": conf_dict.get("client_latency_ms"),
        })

    return scored


def compute_evaluation_metrics(
    scored_rows: List[Dict[str, Any]],
    abstain_field: str = "predicted_should_abstain",
) -> Dict[str, Any]:
    """Compute explicit, unambiguous evaluation metrics across all 13 canonical dimensions."""
    total = len(scored_rows)
    if total == 0:
        return {}

    concept_correct = 0
    full_match_count = 0
    dim_correct = {d: 0 for d in CANONICAL_13_DIMENSIONS}

    # Abstention confusion matrix:
    # Gold should_abstain = True: unsafe for valuation intake
    # Predicted should_abstain = True: system rejects/abstains
    # TP: correctly abstained unsafe row (gold=True, pred=True)
    # FP: incorrectly abstained safe row (gold=False, pred=True)
    # TN: correctly accepted safe row (gold=False, pred=False)
    # FN: incorrectly accepted unsafe row (gold=True, pred=False)
    tp = fp = tn = fn = 0

    for r in scored_rows:
        gold_abstain = bool(r["effective_should_abstain"])
        pred_abstain = bool(r[abstain_field])

        if gold_abstain and pred_abstain:
            tp += 1
        elif (not gold_abstain) and pred_abstain:
            fp += 1
        elif (not gold_abstain) and (not pred_abstain):
            tn += 1
        elif gold_abstain and (not pred_abstain):
            fn += 1

        row_matches = {}
        for d in CANONICAL_13_DIMENSIONS:
            p_val = r[f"predicted_{d}"]
            g_val = r[f"effective_{d}"]
            if d == "basis_evidence":
                match = (normalize_basis_evidence(p_val) == normalize_basis_evidence(g_val))
            elif d == "valuation_eligibility" and p_val is None and r.get("derived_valuation_eligibility"):
                match = (r["derived_valuation_eligibility"] == g_val)
            else:
                match = (p_val == g_val)
            if match:
                dim_correct[d] += 1
            row_matches[d] = match

        if r["predicted_concept"] == r["effective_concept"]:
            concept_correct += 1

        if all(row_matches.values()):
            full_match_count += 1

    accepted_count = tn + fn
    safe_accept_count = tn
    unsafe_accept_count = fn
    unsafe_accept_rate_of_accepted = (unsafe_accept_count / accepted_count) if accepted_count > 0 else 0.0
    unsafe_accept_rate_of_population = unsafe_accept_count / total
    coverage_of_gold_safe = (tn / (tn + fp)) if (tn + fp) > 0 else 0.0
    precision = (tp / (tp + fp)) if (tp + fp) > 0 else 0.0
    recall = (tp / (tp + fn)) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    return {
        "evaluation_population": total,
        "concept_accuracy": round(concept_correct / total, 4),
        "concept_correct_count": concept_correct,
        "full_13_dimension_exact_match": round(full_match_count / total, 4),
        "full_13_dimension_exact_match_count": full_match_count,
        "dimension_accuracies": {d: round(dim_correct[d] / total, 4) for d in CANONICAL_13_DIMENSIONS},
        "dimension_correct_counts": dim_correct,
        "abstention_confusion": {
            "tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        },
        "accepted_count": accepted_count,
        "safe_accept_count": safe_accept_count,
        "unsafe_accept_count": unsafe_accept_count,
        "unsafe_accept_rate_of_accepted": round(unsafe_accept_rate_of_accepted, 4),
        "unsafe_accept_rate_of_population": round(unsafe_accept_rate_of_population, 4),
        "coverage_of_gold_safe": round(coverage_of_gold_safe, 4),
    }


def backfill_historical_basis_evidence(
    conn: Any,
    target_run_ids: Optional[Sequence[str]] = None,
) -> Dict[str, Dict[str, int]]:
    """Backfill predicted_basis_evidence column for historical runs from confidence_json or raw_model_output."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if target_run_ids is None:
        cur.execute("SELECT DISTINCT run_id FROM financial_classifier_evaluation_predictions ORDER BY run_id;")
        target_run_ids = [r["run_id"] for r in cur.fetchall()]

    stats: Dict[str, Dict[str, int]] = {}
    for run_id in target_run_ids:
        cur.execute("""
            SELECT benchmark_id, predicted_basis_evidence, confidence_json, raw_model_output
            FROM financial_classifier_evaluation_predictions
            WHERE run_id = %s
            ORDER BY benchmark_id;
        """, (run_id,))
        rows = cur.fetchall()

        already_pop = 0
        recovered = 0
        unrecov = 0

        for r in rows:
            if r["predicted_basis_evidence"] is not None:
                already_pop += 1
                continue

            choice = None
            conf_json = r["confidence_json"]
            if conf_json and isinstance(conf_json, dict):
                choice = conf_json.get("questions", {}).get("basis_evidence", {}).get("choice")
            if not choice and r["raw_model_output"]:
                try:
                    parsed = json.loads(r["raw_model_output"])
                    choice = parsed.get("answers", {}).get("basis_evidence", {}).get("choice")
                except Exception:
                    pass

            if choice is not None:
                cur.execute("""
                    UPDATE financial_classifier_evaluation_predictions
                    SET predicted_basis_evidence = %s
                    WHERE run_id = %s AND benchmark_id = %s AND predicted_basis_evidence IS NULL;
                """, (choice, run_id, r["benchmark_id"]))
                recovered += 1
            else:
                unrecov += 1

        stats[run_id] = {
            "total": len(rows),
            "already_populated": already_pop,
            "recovered": recovered,
            "unrecoverable": unrecov,
        }

    conn.commit()
    return stats
