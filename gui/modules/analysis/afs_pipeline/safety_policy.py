"""Stage 6: Deterministic Python Safety Policy.

Applies strict rule-based validation to Kev semantic classifications.
Outputs:
- ACCEPT: Deterministically verified and qualified metric.
- REQUIRES_GEMINI: Recognized candidate needing targeted Gemini context adjudication for qualifiers.
- ABSTAIN: Not admissible as a historical actual level (guidance, mention-only, change-only, unknown).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from modules.analysis.financial_classifier_benchmark import AliasRole, ValuePattern
from modules.analysis.financial_concept_dictionary import (
    CapexBasis,
    DilutionBasis,
    DividendTaxBasis,
    LeaseInclusion,
    MarginDenominator,
    OperationScope,
)
from .evidence_package import ContextEvidencePackage
from .kev_classifier import KevSemanticResult


class PolicyDecision(str, Enum):
    ACCEPT = "ACCEPT"
    REQUIRES_GEMINI = "REQUIRES_GEMINI"
    ABSTAIN = "ABSTAIN"


@dataclass(frozen=True)
class SafetyPolicyEvaluation:
    decision: PolicyDecision
    reason: str
    unresolved_questions: List[str]
    qualifiers: Dict[str, Any]


def evaluate_safety_policy(
    package: ContextEvidencePackage,
    kev: KevSemanticResult,
) -> SafetyPolicyEvaluation:
    """Evaluate candidate evidence package and Kev semantic result against safety policy."""
    # 1. Deterministic value requirement
    if package.deterministic_normalized_value is None:
        return SafetyPolicyEvaluation(
            decision=PolicyDecision.ABSTAIN,
            reason="Missing deterministic normalized numeric value",
            unresolved_questions=[],
            qualifiers={},
        )

    # 2. Kev explicit abstention or unknown concept
    if kev.should_abstain:
        return SafetyPolicyEvaluation(
            decision=PolicyDecision.ABSTAIN,
            reason="Kev indicated should_abstain=True",
            unresolved_questions=[],
            qualifiers={},
        )

    concept = kev.concept
    if not concept or concept == "unknown":
        return SafetyPolicyEvaluation(
            decision=PolicyDecision.ABSTAIN,
            reason="Unknown or unclassified financial concept",
            unresolved_questions=[],
            qualifiers={},
        )

    norm_role = str(kev.alias_role or "").upper()
    norm_pattern = str(kev.value_pattern or "").upper()

    # 3. Discursive mention only
    if norm_role == AliasRole.CONCEPT_MENTION_ONLY.value:
        return SafetyPolicyEvaluation(
            decision=PolicyDecision.ABSTAIN,
            reason="Syntactic function is concept mention only",
            unresolved_questions=[],
            qualifiers={},
        )

    # 4. Forward-looking guidance cannot become historical actual
    if norm_role == AliasRole.GUIDANCE_STATEMENT.value:
        return SafetyPolicyEvaluation(
            decision=PolicyDecision.ABSTAIN,
            reason="Guidance or outlook statement cannot become historical actual",
            unresolved_questions=[],
            qualifiers={},
        )

    # 5. Change-only amount or rate cannot become historical level
    if package.numeric_role in ("CHANGE_AMOUNT", "CHANGE_RATE") or norm_pattern == ValuePattern.CHANGE_RATE_ONLY.value:
        return SafetyPolicyEvaluation(
            decision=PolicyDecision.ABSTAIN,
            reason="Change-only amount or rate is not admissible as a historical actual level",
            unresolved_questions=[],
            qualifiers={},
        )

    # 6. Qualifier-dependent accounting concepts
    norm_concept = concept.lower()
    unresolved: List[str] = []

    # Per-share metrics require dilution basis
    if any(k in norm_concept for k in ["eps", "heps", "per_share"]):
        if not kev.dilution or kev.dilution == DilutionBasis.UNSPECIFIED.value:
            unresolved.append("dilution_basis_required")

    # Debt / borrowings / EBITDA require lease treatment
    if any(k in norm_concept for k in ["debt", "borrowing", "ebitda", "lease"]):
        if not kev.lease_inclusion or kev.lease_inclusion == LeaseInclusion.UNSPECIFIED.value:
            unresolved.append("lease_inclusion_required")

    # Capex requires cash payment vs accounting additions
    if "capex" in norm_concept or "capital_expenditure" in norm_concept:
        if not kev.capex_basis or kev.capex_basis == CapexBasis.UNSPECIFIED.value:
            unresolved.append("capex_basis_required")

    # Margins require explicit denominator
    if "margin" in norm_concept:
        if not kev.margin_denominator or kev.margin_denominator == MarginDenominator.UNSPECIFIED.value:
            unresolved.append("margin_denominator_required")

    # Dividends require tax withholding basis
    if "dividend" in norm_concept and "yield" not in norm_concept:
        if not kev.tax_basis or kev.tax_basis == DividendTaxBasis.UNSPECIFIED.value:
            unresolved.append("dividend_tax_basis_required")

    # Share counts require exact category (issued, treasury, external, weighted average)
    if "shares" in norm_concept or "share_count" in norm_concept:
        if concept not in ("issued_shares", "weighted_average_shares", "treasury_shares", "external_shares"):
            unresolved.append("share_count_basis_required")

    qualifiers = {
        "concept": concept,
        "scope": kev.scope or OperationScope.UNSPECIFIED.value,
        "dilution": kev.dilution or DilutionBasis.UNSPECIFIED.value,
        "tax_basis": kev.tax_basis or DividendTaxBasis.UNSPECIFIED.value,
        "capex_basis": kev.capex_basis or CapexBasis.UNSPECIFIED.value,
        "lease_inclusion": kev.lease_inclusion or LeaseInclusion.UNSPECIFIED.value,
        "basis_evidence": kev.basis_evidence or "unspecified",
        "margin_denominator": kev.margin_denominator or MarginDenominator.UNSPECIFIED.value,
        "attribution": kev.attribution or "unspecified",
    }

    if unresolved:
        return SafetyPolicyEvaluation(
            decision=PolicyDecision.REQUIRES_GEMINI,
            reason=f"Candidate requires targeted context adjudication for: {', '.join(unresolved)}",
            unresolved_questions=unresolved,
            qualifiers=qualifiers,
        )

    return SafetyPolicyEvaluation(
        decision=PolicyDecision.ACCEPT,
        reason="Deterministic safety checks satisfied with explicit semantics",
        unresolved_questions=[],
        qualifiers=qualifiers,
    )
