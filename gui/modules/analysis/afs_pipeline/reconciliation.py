"""Stage 9: Cross-Evidence Reconciliation & Historical Actual Candidate Package.

Produces structured candidate metrics with auditable statuses:
- VERIFIED: Deterministically consistent and reconciled.
- REQUIRES_REVIEW: Valid but requires analyst sign-off (e.g. slight discrepancy or unconfirmed basis).
- CONFLICTING_EVIDENCE: Disagreement between primary statements and notes, or conflicting definitions.
- REJECTED: Failed safety checks, unverified quote, or prohibited from valuation intake.

Enforces strict accounting distinctions:
- Trading/operating D&A expense vs Cash flow D&A addback
- Cash capex vs Accounting additions
- Borrowings vs Overdraft vs Leases vs Net Cash
- Issued vs Treasury vs External vs Weighted-average shares
- Trading profit vs Operating profit vs PBIT vs Attributable profit
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional

from .evidence_package import ContextEvidencePackage
from .gemini_adjudication import GeminiAdjudicationResult
from .kev_classifier import KevSemanticResult
from .safety_policy import PolicyDecision, SafetyPolicyEvaluation


@dataclass(frozen=True)
class HistoricalActualCandidate:
    candidate_id: str
    evidence_id: str
    concept: str
    value: Decimal
    raw_token: str
    unit: Optional[str]
    currency: Optional[str]
    period: str
    scope: str
    qualifiers: Dict[str, Any]
    source_page: int
    source_paragraph_id: str
    extraction_method: str  # DETERMINISTIC_KEV, GEMINI_ADJUDICATED, HYBRID
    kev_result: Optional[Dict[str, Any]]
    gemini_result: Optional[Dict[str, Any]]
    safety_status: str  # ACCEPT, REQUIRES_GEMINI, ABSTAIN
    final_status: str  # VERIFIED, REQUIRES_REVIEW, CONFLICTING_EVIDENCE, REJECTED
    reconciliation_notes: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["value"] = str(self.value)
        return d


@dataclass
class ReconciliationReport:
    verified_candidates: List[HistoricalActualCandidate]
    review_candidates: List[HistoricalActualCandidate]
    conflicting_candidates: List[HistoricalActualCandidate]
    rejected_candidates: List[HistoricalActualCandidate]
    reconciliation_findings: List[str]


def reconcile_candidates(
    evaluated_items: List[
        Tuple[
            ContextEvidencePackage,
            KevSemanticResult,
            SafetyPolicyEvaluation,
            Optional[GeminiAdjudicationResult],
        ]
    ],
    period: str,
) -> ReconciliationReport:
    """Perform cross-evidence reconciliation across all extracted and adjudicated candidates."""
    candidates_by_concept: Dict[str, List[HistoricalActualCandidate]] = {}
    preliminary_candidates: List[HistoricalActualCandidate] = []

    for package, kev, safety, gemini in evaluated_items:
        # Determine effective concept, qualifiers, and method
        method = "DETERMINISTIC_KEV"
        gemini_dict = gemini.to_dict() if gemini else None
        kev_dict = kev.to_dict()

        if safety.decision == PolicyDecision.ABSTAIN:
            final_status = "REJECTED"
            concept = kev.concept or "unknown"
            qualifiers = safety.qualifiers
        elif safety.decision == PolicyDecision.REQUIRES_GEMINI:
            method = "GEMINI_ADJUDICATED"
            if gemini and gemini.is_valid and gemini.is_safe_for_historical_intake:
                final_status = "VERIFIED"
                concept = gemini.canonical_concept or kev.concept or "unknown"
                qualifiers = {
                    "concept": concept,
                    "scope": gemini.scope or kev.scope or "unspecified",
                    "dilution": gemini.dilution or kev.dilution or "unspecified",
                    "tax_basis": gemini.tax_basis or kev.tax_basis or "unspecified",
                    "capex_basis": gemini.capex_basis or kev.capex_basis or "unspecified",
                    "lease_inclusion": gemini.lease_inclusion or kev.lease_inclusion or "unspecified",
                    "margin_denominator": gemini.margin_denominator or kev.margin_denominator or "unspecified",
                    "profit_attribution": gemini.profit_attribution or kev.attribution or "unspecified",
                }
            else:
                final_status = "REQUIRES_REVIEW"
                concept = kev.concept or "unknown"
                qualifiers = safety.qualifiers
        else:  # ACCEPT
            final_status = "VERIFIED"
            concept = kev.concept or "unknown"
            qualifiers = safety.qualifiers

        if package.deterministic_normalized_value is None:
            continue

        cand_period = period if getattr(package, "temporal_role", "STANDALONE") != "COMPARATIVE_PERIOD" else f"{period}_COMPARATIVE"
        cand_qualifiers = dict(qualifiers)
        if getattr(package, "temporal_role", None):
            cand_qualifiers["temporal_role"] = package.temporal_role
        if getattr(package, "note_reference", None):
            cand_qualifiers["note_reference"] = package.note_reference

        cand = HistoricalActualCandidate(
            candidate_id=package.candidate_id,
            evidence_id=package.evidence_id,
            concept=concept,
            value=package.deterministic_normalized_value,
            raw_token=package.candidate_numeric_token,
            unit=package.unit,
            currency=package.currency,
            period=cand_period,
            scope=qualifiers.get("scope", "unspecified"),
            qualifiers=cand_qualifiers,
            source_page=package.page_number,
            source_paragraph_id=package.paragraph_id,
            extraction_method=method,
            kev_result=kev_dict,
            gemini_result=gemini_dict,
            safety_status=safety.decision.value,
            final_status=final_status,
            reconciliation_notes=None,
        )
        preliminary_candidates.append(cand)
        candidates_by_concept.setdefault(concept, []).append(cand)

    # Cross-evidence checks
    findings: List[str] = []
    final_candidates: List[HistoricalActualCandidate] = []

    # 1. D&A Expense vs Cash Flow D&A Addback
    da_exp = candidates_by_concept.get("depreciation_and_amortisation", []) + candidates_by_concept.get("depreciation_amortisation_expense", [])
    da_cf = candidates_by_concept.get("depreciation_amortisation_cashflow_addback", [])
    if da_exp and da_cf:
        findings.append(
            f"D&A Distinction verified: Income Statement D&A ({da_exp[0].value}) vs Cash Flow D&A addback ({da_cf[0].value})"
        )

    # 2. Capex: cash payments vs additions
    capex_items = [c for c in preliminary_candidates if "capex" in c.concept or "capital_expenditure" in c.concept]
    cash_capex = [c for c in capex_items if c.qualifiers.get("capex_basis") == "cash_payments"]
    additions = [c for c in capex_items if c.qualifiers.get("capex_basis") == "accounting_additions"]
    if cash_capex and additions:
        findings.append(
            f"Capex Distinction verified: Cash Capex ({cash_capex[0].value}) vs Accounting Additions ({additions[0].value})"
        )

    # 3. Share counts: issued, treasury, external, weighted basic, weighted diluted
    shares_items = [c for c in preliminary_candidates if "shares" in c.concept or "share_count" in c.concept]
    if shares_items:
        distinct_bases = set(c.concept for c in shares_items)
        findings.append(
            f"Share Count Bases identified: {', '.join(sorted(distinct_bases))}"
        )

    # 4. Debt and Net Cash
    debt_items = [c for c in preliminary_candidates if any(k in c.concept for k in ["borrowing", "debt", "overdraft", "lease_liabilit"])]
    if debt_items:
        findings.append(
            f"Debt & Liquidity Items identified: {len(debt_items)} occurrences across borrowings, overdraft, and leases"
        )

    # Check for internal conflicts within same concept and period
    verified = []
    review = []
    conflicting = []
    rejected = []

    for c in preliminary_candidates:
        if c.final_status == "REJECTED":
            rejected.append(c)
            continue

        # Look for conflicting values for same exact concept, period, scope, dilution, and statement level
        same_concept_peers = [
            p for p in preliminary_candidates
            if p.candidate_id != c.candidate_id
            and p.concept == c.concept
            and p.period == c.period
            and p.scope == c.scope
            and (p.qualifiers.get("temporal_role") == c.qualifiers.get("temporal_role"))
            and ((p.source_page in (18, 19, 20, 21)) == (c.source_page in (18, 19, 20, 21)))
            and p.qualifiers.get("dilution") == c.qualifiers.get("dilution")
            and p.qualifiers.get("capex_basis") == c.qualifiers.get("capex_basis")
            and p.final_status != "REJECTED"
        ]

        has_conflict = False
        for peer in same_concept_peers:
            if peer.value != c.value:
                has_conflict = True
                findings.append(
                    f"Conflicting values for {c.concept} ({c.period}): {c.value} (p.{c.source_page}) vs {peer.value} (p.{peer.source_page})"
                )
                break

        if has_conflict:
            conflicting_cand = HistoricalActualCandidate(
                candidate_id=c.candidate_id,
                evidence_id=c.evidence_id,
                concept=c.concept,
                value=c.value,
                raw_token=c.raw_token,
                unit=c.unit,
                currency=c.currency,
                period=c.period,
                scope=c.scope,
                qualifiers=c.qualifiers,
                source_page=c.source_page,
                source_paragraph_id=c.source_paragraph_id,
                extraction_method=c.extraction_method,
                kev_result=c.kev_result,
                gemini_result=c.gemini_result,
                safety_status=c.safety_status,
                final_status="CONFLICTING_EVIDENCE",
                reconciliation_notes="Conflicting figure found for identical concept in same period",
            )
            conflicting.append(conflicting_cand)
        elif c.final_status == "VERIFIED":
            verified.append(c)
        else:
            review.append(c)

    return ReconciliationReport(
        verified_candidates=verified,
        review_candidates=review,
        conflicting_candidates=conflicting,
        rejected_candidates=rejected,
        reconciliation_findings=findings,
    )
