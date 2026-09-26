"""Stage 5: Kev Semantic Classification Pass.

Invokes the local Kev service on localhost:8009 using explicit-evidence-v2 questions.
Classifies factual accounting semantics only; does not invent numbers or decide valuation admission.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple

from modules.analysis.kev_gold_evaluator import (
    KEV_DEFAULT_ENDPOINT,
    STATIC_QUESTIONS_V2,
    call_kev_systemone,
    validate_and_parse_prediction,
)
from .evidence_package import ContextEvidencePackage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KevSemanticResult:
    evidence_id: str
    concept: Optional[str]
    scope: Optional[str]
    dilution: Optional[str]
    tax_basis: Optional[str]
    capex_basis: Optional[str]
    lease_inclusion: Optional[str]
    basis_evidence: Optional[str]
    margin_denominator: Optional[str]
    attribution: Optional[str]
    alias_role: Optional[str]
    value_pattern: Optional[str]
    should_abstain: bool
    confidence_data: Dict[str, Any]
    parse_errors: List[str]
    latency_ms: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def classify_with_kev(
    package: ContextEvidencePackage,
    publication_datetime: str,
    endpoint: str = KEV_DEFAULT_ENDPOINT,
    model_name: str = "kev-latest",
    timeout_s: float = 30.0,
) -> KevSemanticResult:
    """Send candidate evidence package to local Kev service for semantic classification."""
    state_dict = {
        "benchmark_id": package.evidence_id,
        "ticker": package.ticker,
        "publication_datetime": publication_datetime,
        "normalized_label": package.detected_label or "",
        "detected_numeric_tokens": package.candidate_numeric_token,
        "previous_sentence": package.previous_paragraph[:200] if package.previous_paragraph else "",
        "full_sentence": package.target_sentence,
        "next_sentence": package.next_paragraph[:200] if package.next_paragraph else "",
    }

    payload = {
        "model": model_name,
        "state": state_dict,
        "questions": STATIC_QUESTIONS_V2,
    }

    try:
        status_code, res_json, raw_text, latency_ms = call_kev_systemone(
            payload, endpoint=endpoint, timeout_s=timeout_s
        )
        if status_code != 200:
            return KevSemanticResult(
                evidence_id=package.evidence_id,
                concept=None,
                scope=None,
                dilution=None,
                tax_basis=None,
                capex_basis=None,
                lease_inclusion=None,
                basis_evidence=None,
                margin_denominator=None,
                attribution=None,
                alias_role=None,
                value_pattern=None,
                should_abstain=True,
                confidence_data={"error": f"HTTP {status_code}"},
                parse_errors=[f"HTTP {status_code}: {raw_text}"],
                latency_ms=latency_ms,
            )

        predicted_fields, confidence_data, parse_errors = validate_and_parse_prediction(
            res_json, STATIC_QUESTIONS_V2
        )

        return KevSemanticResult(
            evidence_id=package.evidence_id,
            concept=predicted_fields.get("predicted_concept"),
            scope=predicted_fields.get("predicted_scope"),
            dilution=predicted_fields.get("predicted_dilution"),
            tax_basis=predicted_fields.get("predicted_tax_basis"),
            capex_basis=predicted_fields.get("predicted_capex_basis"),
            lease_inclusion=predicted_fields.get("predicted_lease_inclusion"),
            basis_evidence=predicted_fields.get("predicted_basis_evidence"),
            margin_denominator=predicted_fields.get("predicted_margin_denominator"),
            attribution=predicted_fields.get("predicted_attribution"),
            alias_role=predicted_fields.get("predicted_alias_role"),
            value_pattern=predicted_fields.get("predicted_value_pattern"),
            should_abstain=bool(predicted_fields.get("predicted_should_abstain", False)),
            confidence_data=confidence_data,
            parse_errors=parse_errors,
            latency_ms=latency_ms,
        )

    except Exception as exc:
        logger.warning("Kev classification error for %s: %s", package.evidence_id, exc)
        return KevSemanticResult(
            evidence_id=package.evidence_id,
            concept=None,
            scope=None,
            dilution=None,
            tax_basis=None,
            capex_basis=None,
            lease_inclusion=None,
            basis_evidence=None,
            margin_denominator=None,
            attribution=None,
            alias_role=None,
            value_pattern=None,
            should_abstain=True,
            confidence_data={"exception": str(exc)},
            parse_errors=[str(exc)],
            latency_ms=0.0,
        )
