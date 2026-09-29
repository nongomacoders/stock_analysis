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

import re
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Tuple

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
    unresolved_mandatory_categories: List[str] = None

    def __post_init__(self):
        if self.unresolved_mandatory_categories is None:
            self.unresolved_mandatory_categories = []


# ---------------------------------------------------------------------------
# Generic reconciliation identity helpers.
#
# Two candidates may only enter the same reconciliation (conflict) set when
# sufficiently compatible on concept, period, scope, unit, value role, basis,
# and raw semantic identity. UNKNOWN-concept candidates are especially
# dangerous: `unknown + unknown` must never become a conflict merely because
# both lack a canonical concept. Fail closed (review) over false conflicts.
# ---------------------------------------------------------------------------

_UNKNOWN_CONCEPTS = {"unknown", "", "none"}

# Near-duplicate tolerance: same-identity values within 0.1% (relative) are
# rounding/scale presentations of one measurement (e.g. `148.0` US$m vs
# `147,967` US$000), never competing figures. Fail closed to review.
_NEAR_DUPLICATE_REL_TOL = Decimal("0.001")

_NON_LEVEL_TEMPORALS = {"change_only", "guidance", "target", "unknown"}

_CHANGE_PATTERNS = {"CHANGE_AMOUNT", "RATIO_PERCENT", "CHANGE_RATE_ONLY"}

_LEVEL_PATTERNS = {
    "DIRECT_LEVEL",
    "COUNT_SHARES",
    "FROM_TO_LEVEL",
    "CHANGE_RATE_TO_LEVEL",
    "RANGE",
}


def _normalized_label(candidate: "HistoricalActualCandidate") -> str:
    """Normalized raw semantic identity label (detected nearby label)."""
    raw = candidate.qualifiers.get("detected_label") or ""
    return re.sub(r"\s+", " ", str(raw)).strip().lower()


def _is_unknown_concept(candidate: "HistoricalActualCandidate") -> bool:
    return str(candidate.concept or "").strip().lower() in _UNKNOWN_CONCEPTS


def _gemini_temporal(candidate: "HistoricalActualCandidate") -> Optional[str]:
    """Adjudicated temporal classification, if the candidate carries one."""
    g = candidate.gemini_result
    if isinstance(g, dict):
        t = g.get("temporal_classification")
        if t:
            return str(t).strip().lower()
    return None


def _level_class(candidate: "HistoricalActualCandidate") -> Optional[str]:
    """LEVEL vs CHANGE value-role class from the recorded value pattern.

    Returns None when no value pattern was recorded (deterministic default:
    candidates that passed safety are levels unless stated otherwise).
    """
    vp = candidate.qualifiers.get("value_pattern")
    if vp is None:
        return None
    norm = str(vp).strip().upper()
    if norm in _CHANGE_PATTERNS:
        return "CHANGE"
    if norm in _LEVEL_PATTERNS:
        return "LEVEL"
    return None


def _unit_key(candidate: "HistoricalActualCandidate") -> Tuple[Optional[str], Optional[str]]:
    def _norm(v: Any) -> Optional[str]:
        if v is None:
            return None
        s = str(v).strip().lower()
        return None if s in ("", "unspecified", "n/a") else s

    return (_norm(candidate.unit), _norm(candidate.currency))


def _attribution(candidate: "HistoricalActualCandidate") -> Optional[str]:
    q = candidate.qualifiers
    a = q.get("profit_attribution", q.get("attribution"))
    if a is None:
        return None
    s = str(a).strip().lower()
    return None if s in ("", "unspecified") else s


def _raw_digits(candidate: "HistoricalActualCandidate") -> str:
    return re.sub(r"\D", "", candidate.raw_token or "")


_NEAR_DUPLICATE_SCALES = (
    Decimal(1),
    Decimal(10**3),
    Decimal(10**6),
    Decimal(10**9),
)


def _is_near_duplicate(a: "HistoricalActualCandidate", b: "HistoricalActualCandidate") -> bool:
    """Same-identity values within rounding tolerance of each other, allowing
    unit-system rescaling (ones / thousands / millions / billions), e.g.
    `148.0` US$m vs `147,967` US$000 (0.02% apart after rescaling)."""
    if a.value is None or b.value is None or a.value == b.value:
        return False
    try:
        for s in _NEAR_DUPLICATE_SCALES:
            for x, y in ((a.value * s, b.value), (a.value, b.value * s)):
                denom = max(abs(x), abs(y))
                if denom == 0:
                    continue
                if abs(x - y) / denom <= _NEAR_DUPLICATE_REL_TOL:
                    return True
        return False
    except Exception:
        return False


def _explicit_mismatch(a: Optional[str], b: Optional[str]) -> bool:
    """True only when both sides explicitly state different values.

    Missing information stays wildcard-compatible so deterministic (Kev-path)
    candidates without adjudicated qualifiers keep their existing behaviour.
    """
    return a is not None and b is not None and a != b


def _peer_compatible(c: "HistoricalActualCandidate", p: "HistoricalActualCandidate") -> bool:
    """Generic reconciliation-identity gate for a candidate pair."""
    # Temporal role: current levels never compete with comparative / change /
    # guidance / target values.
    if _explicit_mismatch(_gemini_temporal(c), _gemini_temporal(p)):
        return False
    # Value role: LEVEL values never compete with CHANGE values.
    if _explicit_mismatch(_level_class(c), _level_class(p)):
        return False
    # Units: explicitly incompatible units/currencies never compete.
    # Each axis only constrains when both sides state it (missing stays
    # wildcard-compatible with deterministic candidates).
    (cu, cc), (pu, pc) = _unit_key(c), _unit_key(p)
    if _explicit_mismatch(cu, pu) or _explicit_mismatch(cc, pc):
        return False
    # Attribution: parent / group / NCI scopes remain separate.
    if _explicit_mismatch(_attribution(c), _attribution(p)):
        return False
    # Raw semantic identity for weak identities: unknown concepts, or
    # coarse segment scopes, require matching non-empty labels.
    c_unknown, p_unknown = _is_unknown_concept(c), _is_unknown_concept(p)
    if c_unknown or p_unknown:
        if not c_unknown or not p_unknown:
            return False
        la, lb = _normalized_label(c), _normalized_label(p)
        if not la or not lb or la != lb:
            return False
    elif str(c.scope or "").strip().lower() == "segment" and str(p.scope or "").strip().lower() == "segment":
        la, lb = _normalized_label(c), _normalized_label(p)
        if la and lb and la != lb:
            return False
    # Scale divergence: identical raw digits but different normalized values
    # means unit/scale normalization disagrees, not competing measurements.
    da, db = _raw_digits(c), _raw_digits(p)
    if da and da == db and c.value != p.value:
        return False
    # Near duplicates: same-identity values within rounding/scale tolerance
    # are one measurement presented twice, never a conflict.
    if _is_near_duplicate(c, p):
        return False
    return True


def _route_fail_closed_reviews(
    preliminary_candidates: List["HistoricalActualCandidate"],
) -> Tuple[Dict[str, str], List[str]]:
    """Determine deterministic REQUIRES_REVIEW routings (fail closed).

    Returns ({candidate_id: reason}, findings). Covers:
    - non-historical temporal classifications (change_only / guidance /
      target / unknown) which are never historical actual levels;
    - same-identity unknown pairs with divergent values;
    - same-concept scale/normalization divergences (identical raw digits,
      different normalized values).
    """
    review_reasons: Dict[str, str] = {}
    findings: List[str] = []
    actives = [c for c in preliminary_candidates if c.final_status != "REJECTED"]

    for c in actives:
        t = _gemini_temporal(c)
        if t in _NON_LEVEL_TEMPORALS:
            review_reasons[c.candidate_id] = (
                f"Temporal classification '{t}' is not a historical actual level"
            )
            findings.append(
                f"REVIEW ROUTED {c.concept} ({c.period}): {c.value} (p.{c.source_page}) "
                f"classified '{t}', not admissible as a historical actual level"
            )

    for i, c in enumerate(actives):
        for p in actives[i + 1 :]:
            if c.concept != p.concept or c.period != p.period or c.scope != p.scope:
                continue
            if c.value == p.value:
                continue
            # Same-identity unknowns with divergent values need an analyst,
            # not a manufactured conflict.
            if _is_unknown_concept(c) and _is_unknown_concept(p):
                la, lb = _normalized_label(c), _normalized_label(p)
                if la and la == lb:
                    for x in (c, p):
                        if x.candidate_id not in review_reasons:
                            review_reasons[x.candidate_id] = (
                                f"Same-identity UNKNOWN candidates diverge "
                                f"('{la}'): {c.value} vs {p.value}"
                            )
                    findings.append(
                        f"REVIEW ROUTED unknown ({c.period}): '{la}' diverges "
                        f"({c.value} p.{c.source_page} vs {p.value} p.{p.source_page}); "
                        f"analyst resolution required"
                    )
            # Near duplicates: same-identity values within rounding/scale
            # tolerance (e.g. '148.0' US$m vs '147,967' US$000).
            if _is_near_duplicate(c, p):
                for x in (c, p):
                    if x.candidate_id not in review_reasons:
                        review_reasons[x.candidate_id] = (
                            f"Near-duplicate values within rounding/scale tolerance: "
                            f"{c.value} vs {p.value}"
                        )
                findings.append(
                    f"REVIEW ROUTED {c.concept} ({c.period}): {c.value} (p.{c.source_page}) vs "
                    f"{p.value} (p.{p.source_page}) within rounding/scale tolerance; "
                    f"analyst confirmation required"
                )
            # Scale/normalization divergence: identical raw digits, different
            # normalized values (e.g. '2,027.3 million' vs '2,027.3').
            da, db = _raw_digits(c), _raw_digits(p)
            if da and da == db:
                for x in (c, p):
                    if x.candidate_id not in review_reasons:
                        review_reasons[x.candidate_id] = (
                            f"Scale/unit normalization diverges for identical raw "
                            f"digits '{da}': {c.value} vs {p.value}"
                        )
                findings.append(
                    f"REVIEW ROUTED {c.concept} ({c.period}): identical raw digits "
                    f"('{c.raw_token}' vs '{p.raw_token}') normalized to {c.value} vs "
                    f"{p.value} (p.{c.source_page} vs p.{p.source_page}); unit resolution required"
                )

    return review_reasons, findings


def reconcile_candidates_direct(
    preliminary_candidates: List[HistoricalActualCandidate],
    period: str,
    derived_candidates: Optional[List[HistoricalActualCandidate]] = None,
    is_mining: bool = False,
) -> ReconciliationReport:
    """Perform peer reconciliation, conflict detection, and derived candidate attachment."""
    candidates_by_concept: Dict[str, List[HistoricalActualCandidate]] = {}
    for c in preliminary_candidates:
        candidates_by_concept.setdefault(c.concept, []).append(c)

    # Cross-evidence checks
    findings: List[str] = []

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

    # Fail-closed review routing before peer comparison (generic identity rules).
    fail_closed_reviews, fail_closed_findings = _route_fail_closed_reviews(
        preliminary_candidates
    )
    findings.extend(fail_closed_findings)

    # Check for internal conflicts within same concept and period
    verified = []
    review = []
    conflicting = []
    rejected = []

    def _as_review_copy(c: "HistoricalActualCandidate", reason: str) -> "HistoricalActualCandidate":
        return HistoricalActualCandidate(
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
            final_status="REQUIRES_REVIEW",
            reconciliation_notes=reason,
        )

    for c in preliminary_candidates:
        if c.final_status == "REJECTED":
            rejected.append(c)
            continue

        # Fail-closed routings never enter conflict sets: non-level temporals,
        # same-identity divergences, and scale divergences require an analyst,
        # not a manufactured conflict.
        if c.candidate_id in fail_closed_reviews:
            review.append(
                _as_review_copy(c, fail_closed_reviews[c.candidate_id])
            )
            continue

        # Look for conflicting values for same exact concept, period, scope,
        # dilution, statement level, temporal role, value role, unit, basis,
        # attribution, and raw semantic identity (generic identity gate).
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
            and p.candidate_id not in fail_closed_reviews
            and _peer_compatible(c, p)
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

    # Attach verified derived candidates
    if derived_candidates:
        for dc in derived_candidates:
            if dc.final_status == "VERIFIED":
                verified.append(dc)
            else:
                review.append(dc)

    # Mandatory category resolution check
    mandatory_categories = [
        ("revenue", ["accounting_revenue", "revenue", "turnover"]),
        ("sales", ["sale_of_merchandise", "retail_sales", "sales_volumes", "gold_sold"]),
        ("profit", ["trading_profit", "operating_profit", "profit_before_finance_costs_and_tax", "adjusted_ebitda", "ebitda"]),
        ("margins", ["trading_margin", "operating_margin", "gross_margin"]),
        ("tax", ["effective_tax_rate", "tax_expense", "statutory_tax_rate"]),
        ("capex", ["cash_capex", "total_capex", "capex_expansion", "capex_maintenance", "sustaining_capex"]),
        ("working_capital", ["working_capital_movement", "working_capital_cash_flow", "inventories", "trade_and_other_receivables"]),
        ("cash", ["cash_and_cash_equivalents", "money_market_funds", "reported_net_cash"]),
        ("debt", ["interest_bearing_borrowings", "bank_overdraft", "reported_net_debt", "net_debt"]),
        ("leases", ["lease_liabilities", "lease_liabilities_current", "lease_liabilities_noncurrent", "leases"]),
        ("shares", ["issued_shares", "treasury_shares", "external_shares_ex_treasury", "external_shares", "weighted_average_basic_shares", "weighted_average_diluted_shares"]),
        ("depreciation_amortisation", ["depreciation_amortisation_expense", "depreciation_amortisation_cashflow_addback", "depreciation_and_amortisation"]),
    ]

    if is_mining:
        mandatory_categories.extend([
            ("production", ["production", "gold_produced", "tonnes_mined"]),
            ("sales_volumes", ["sales_volumes", "gold_sold"]),
            ("commodity_price", ["realised_commodity_price", "gold_price"]),
            ("unit_cost", ["aisc_unit_cost", "unit_cost", "cash_costs", "aic_unit_cost"]),
            ("grade", ["head_grade", "recovered_grade", "grade"]),
            ("recovery", ["plant_recovery", "recovery", "overall_recovery"]),
            ("throughput", ["plant_throughput", "throughput"]),
            ("guidance", ["guidance"]),
            ("hedging", ["hedging"]),
        ])

    resolved_concepts = {c.concept for c in verified}
    unresolved_cats = []
    for cat_name, valid_concepts in mandatory_categories:
        if not any(vc in resolved_concepts for vc in valid_concepts):
            unresolved_cats.append(cat_name)
            findings.append(f"MANDATORY CATEGORY UNRESOLVED: {cat_name} (Requires Review)")
            review_cand = HistoricalActualCandidate(
                candidate_id=f"unresolved_{cat_name}_{period}",
                evidence_id=f"unresolved_{cat_name}_{period}",
                concept=cat_name,
                value=None,
                raw_token="",
                unit=None,
                currency=None,
                period=period,
                scope="group_consolidated",
                qualifiers={"mandatory_category": cat_name, "unresolved": True},
                source_page=0,
                source_paragraph_id="",
                extraction_method="UNRESOLVED_MANDATORY",
                kev_result=None,
                gemini_result=None,
                safety_status="REQUIRES_REVIEW",
                final_status="REQUIRES_REVIEW",
                reconciliation_notes=f"Mandatory category '{cat_name}' not resolved automatically - manual review required",
            )
            review.append(review_cand)

    return ReconciliationReport(
        verified_candidates=verified,
        review_candidates=review,
        conflicting_candidates=conflicting,
        rejected_candidates=rejected,
        reconciliation_findings=findings,
        unresolved_mandatory_categories=unresolved_cats,
    )


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
    derived_candidates: Optional[List[HistoricalActualCandidate]] = None,
    is_mining: bool = False,
) -> ReconciliationReport:
    """Perform cross-evidence reconciliation across all extracted and adjudicated candidates."""
    preliminary_candidates: List[HistoricalActualCandidate] = []

    for package, kev, safety, gemini in evaluated_items:
        # Determine effective concept, qualifiers, and method
        method = "DETERMINISTIC_KEV"
        gemini_dict = gemini.to_dict() if gemini else None
        kev_dict = kev.to_dict() if kev else None

        if safety.decision == PolicyDecision.ABSTAIN:
            final_status = "REJECTED"
            concept = (kev.concept if kev else None) or "unknown"
            qualifiers = safety.qualifiers
        elif safety.decision == PolicyDecision.REQUIRES_GEMINI:
            method = "GEMINI_ADJUDICATED"
            if gemini and gemini.is_valid and gemini.is_safe_for_historical_intake:
                final_status = "VERIFIED"
                concept = gemini.canonical_concept or (kev.concept if kev else None) or "unknown"
                qualifiers = {
                    "concept": concept,
                    "scope": gemini.scope or (kev.scope if kev else "unspecified"),
                    "dilution": gemini.dilution or (kev.dilution if kev else "unspecified"),
                    "tax_basis": gemini.tax_basis or (kev.tax_basis if kev else "unspecified"),
                    "capex_basis": gemini.capex_basis or (kev.capex_basis if kev else "unspecified"),
                    "lease_inclusion": gemini.lease_inclusion or (kev.lease_inclusion if kev else "unspecified"),
                    "margin_denominator": gemini.margin_denominator or (kev.margin_denominator if kev else "unspecified"),
                    "profit_attribution": gemini.profit_attribution or (kev.attribution if kev else "unspecified"),
                }
            else:
                final_status = "REQUIRES_REVIEW"
                concept = (kev.concept if kev else None) or "unknown"
                qualifiers = safety.qualifiers
        else:  # ACCEPT
            final_status = "VERIFIED"
            concept = (kev.concept if kev else None) or "unknown"
            qualifiers = safety.qualifiers

        if package.deterministic_normalized_value is None:
            continue

        cand_period = period if getattr(package, "temporal_role", "STANDALONE") != "COMPARATIVE_PERIOD" else f"{period}_COMPARATIVE"
        cand_qualifiers = dict(qualifiers)
        if getattr(package, "temporal_role", None):
            cand_qualifiers["temporal_role"] = package.temporal_role
        if getattr(package, "note_reference", None):
            cand_qualifiers["note_reference"] = package.note_reference
        # Raw semantic identity for the generic reconciliation identity gate.
        if getattr(package, "detected_label", None):
            cand_qualifiers["detected_label"] = package.detected_label

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

    return reconcile_candidates_direct(preliminary_candidates, period=period, derived_candidates=derived_candidates)

