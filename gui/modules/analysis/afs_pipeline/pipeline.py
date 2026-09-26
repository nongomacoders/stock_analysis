"""AFS Pipeline Orchestrator.

Coordinates all 11 stages of AFS evidence processing:
1. Source Archive
2. Document Extraction
3. Deterministic Numeric Candidate Extraction
4. Context Evidence Packages
5. Kev Semantic Classification
6. Deterministic Safety Policy
7. Targeted Gemini Adjudication
8. Gemini Evidence Verification
9. Cross-Evidence Reconciliation
10. High-Impact Mandatory Review Checklist
11. Whole-Document Skeptical Challenge Pass

Stops before automatic ForecastPlan publication or valuation execution.
"""
from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .archive import ArchivedDocument, archive_afs_pdf
from .challenge_pass import ChallengeReport, run_whole_document_challenge
from .checklist import ChecklistItem, evaluate_checklist
from .document_extraction import ExtractedDocument, extract_document
from .evidence_package import ContextEvidencePackage, build_evidence_package
from .gemini_adjudication import GeminiAdjudicationResult, adjudicate_with_gemini
from .kev_classifier import KevSemanticResult, classify_with_kev
from .numeric_candidates import NumericCandidate, extract_numeric_candidates_from_sentence
from .reconciliation import (
    HistoricalActualCandidate,
    ReconciliationReport,
    reconcile_candidates,
)
from .safety_policy import PolicyDecision, SafetyPolicyEvaluation, evaluate_safety_policy

logger = logging.getLogger(__name__)


@dataclass
class StageRuntimeMetrics:
    stage_1_archive_ms: float = 0.0
    stage_2_extraction_ms: float = 0.0
    stage_3_numeric_ms: float = 0.0
    stage_4_packages_ms: float = 0.0
    stage_5_kev_ms: float = 0.0
    stage_6_safety_ms: float = 0.0
    stage_7_gemini_adjudication_ms: float = 0.0
    stage_9_reconciliation_ms: float = 0.0
    stage_10_checklist_ms: float = 0.0
    stage_11_challenge_ms: float = 0.0
    total_pipeline_ms: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        return asdict(self)


@dataclass
class AFSPipelineResult:
    ticker: str
    company: str
    financial_period: str
    archived_doc: ArchivedDocument
    extracted_doc: ExtractedDocument
    candidates_count: int
    kev_classified_count: int
    deterministic_accepted_count: int
    gemini_escalated_count: int
    gemini_resolved_count: int
    analyst_review_count: int
    conflicts_count: int
    reconciliation_report: ReconciliationReport
    checklist_items: List[ChecklistItem]
    challenge_report: ChallengeReport
    runtimes: StageRuntimeMetrics

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "company": self.company,
            "financial_period": self.financial_period,
            "archived_doc": self.archived_doc.to_dict(),
            "candidates_count": self.candidates_count,
            "kev_classified_count": self.kev_classified_count,
            "deterministic_accepted_count": self.deterministic_accepted_count,
            "gemini_escalated_count": self.gemini_escalated_count,
            "gemini_resolved_count": self.gemini_resolved_count,
            "analyst_review_count": self.analyst_review_count,
            "conflicts_count": self.conflicts_count,
            "verified_candidates": [c.to_dict() for c in self.reconciliation_report.verified_candidates],
            "review_candidates": [c.to_dict() for c in self.reconciliation_report.review_candidates],
            "conflicting_candidates": [c.to_dict() for c in self.reconciliation_report.conflicting_candidates],
            "rejected_candidates": [c.to_dict() for c in self.reconciliation_report.rejected_candidates],
            "reconciliation_findings": self.reconciliation_report.reconciliation_findings,
            "checklist": [item.to_dict() for item in self.checklist_items],
            "challenge_report": self.challenge_report.to_dict(),
            "runtimes": self.runtimes.to_dict(),
        }


async def run_afs_evidence_pipeline(
    pdf_path: Path | str,
    ticker: str,
    company: str,
    financial_period: str,
    publication_datetime: datetime | str,
    source_url: Optional[str] = None,
    max_pages: Optional[int] = None,
    max_candidates_for_kev: Optional[int] = 100,
    db_conn: Optional[Any] = None,
    run_gemini_passes: bool = True,
) -> AFSPipelineResult:
    """Run full auditable AFS evidence pipeline for a single AFS PDF."""
    t_start = time.perf_counter()
    runtimes = StageRuntimeMetrics()

    # Stage 1: PDF Source Archive
    t0 = time.perf_counter()
    archived_doc = archive_afs_pdf(
        pdf_path=pdf_path,
        ticker=ticker,
        company=company,
        financial_period=financial_period,
        publication_datetime=publication_datetime,
        source_url=source_url,
        db_conn=db_conn,
    )
    runtimes.stage_1_archive_ms = (time.perf_counter() - t0) * 1000.0

    # Stage 2: Document Extraction
    t0 = time.perf_counter()
    extracted_doc = extract_document(
        pdf_path=pdf_path,
        document_id=archived_doc.document_id,
        max_pages=max_pages,
    )
    runtimes.stage_2_extraction_ms = (time.perf_counter() - t0) * 1000.0

    # Stage 3: Candidate Numeric Extraction
    t0 = time.perf_counter()
    all_candidates: List[NumericCandidate] = []
    for sentence in extracted_doc.sentences_by_id.values():
        cands = extract_numeric_candidates_from_sentence(
            sentence_id=sentence.sentence_id,
            paragraph_id=sentence.paragraph_id,
            page_number=sentence.page_number,
            sentence_text=sentence.text,
        )
        all_candidates.extend(cands)
    runtimes.stage_3_numeric_ms = (time.perf_counter() - t0) * 1000.0

    # Stage 4: Context Evidence Packages
    t0 = time.perf_counter()
    evidence_packages: List[ContextEvidencePackage] = []
    for cand in all_candidates:
        pkg = build_evidence_package(
            candidate=cand,
            doc=extracted_doc,
            ticker=ticker,
            financial_period=financial_period,
        )
        evidence_packages.append(pkg)
    runtimes.stage_4_packages_ms = (time.perf_counter() - t0) * 1000.0

    # Limit population for Kev inference if specified (prioritizing primary statements and high-signal notes)
    # Select high-priority packages first (e.g. from statements or with direct levels)
    if max_candidates_for_kev and len(evidence_packages) > max_candidates_for_kev:
        def priority_score(pkg: ContextEvidencePackage) -> int:
            score = 0
            # 1. Primary statement pages get top tier priority
            if pkg.page_number in (18, 19, 20, 21):
                score += 25
            elif pkg.section_heading and "statement" in pkg.section_heading.lower():
                score += 10

            # 2. Key high-impact note headings
            if pkg.note_heading:
                nh_lower = pkg.note_heading.lower()
                if any(k in nh_lower for k in ["note 13", "note 14", "note 16", "note 20", "note 26", "note 27", "note 29", "note 30", "note 31", "note 33", "note 35", "note 12", "note 8"]):
                    score += 15
                else:
                    score += 5

            # 3. Table row with note reference
            if pkg.note_reference:
                score += 8

            # 4. Bound CURRENT_PERIOD or ENDING_VALUE
            if pkg.temporal_role == "CURRENT_PERIOD":
                score += 8
            elif pkg.numeric_role in ("ENDING_VALUE", "DIRECT_LEVEL"):
                score += 4

            # 5. Detected financial label
            if pkg.detected_label:
                score += 5
                dl_lower = pkg.detected_label.lower()
                if any(k in dl_lower for k in ["revenue", "sale", "merchandise", "profit", "margin", "tax", "capex", "capital", "shares", "borrowings", "debt", "cash", "leases", "working capital", "acquisition"]):
                    score += 10

            # 6. Currency / unit presence
            if pkg.currency or pkg.unit:
                score += 3

            return score

        sorted_pkgs = sorted(evidence_packages, key=priority_score, reverse=True)
        active_packages = sorted_pkgs[:max_candidates_for_kev]
    else:
        active_packages = evidence_packages

    # Stage 5: Kev Semantic Classification Pass
    t0 = time.perf_counter()
    pub_dt_str = (
        publication_datetime
        if isinstance(publication_datetime, str)
        else publication_datetime.isoformat()
    )
    kev_results: List[Tuple[ContextEvidencePackage, KevSemanticResult]] = []
    for pkg in active_packages:
        k_res = classify_with_kev(pkg, publication_datetime=pub_dt_str)
        kev_results.append((pkg, k_res))
    runtimes.stage_5_kev_ms = (time.perf_counter() - t0) * 1000.0

    # Stage 6: Deterministic Python Safety Policy
    t0 = time.perf_counter()
    evaluated_policy_items: List[
        Tuple[ContextEvidencePackage, KevSemanticResult, SafetyPolicyEvaluation]
    ] = []
    for pkg, k_res in kev_results:
        safety_eval = evaluate_safety_policy(pkg, k_res)
        evaluated_policy_items.append((pkg, k_res, safety_eval))
    runtimes.stage_6_safety_ms = (time.perf_counter() - t0) * 1000.0

    # Stage 7 & 8: Targeted Gemini Adjudication & Evidence Verification
    t0 = time.perf_counter()
    adjudicated_items: List[
        Tuple[
            ContextEvidencePackage,
            KevSemanticResult,
            SafetyPolicyEvaluation,
            Optional[GeminiAdjudicationResult],
        ]
    ] = []

    gemini_escalated_count = 0
    gemini_resolved_count = 0

    for pkg, k_res, safety_eval in evaluated_policy_items:
        gemini_res = None
        if safety_eval.decision == PolicyDecision.REQUIRES_GEMINI:
            gemini_escalated_count += 1
            if run_gemini_passes:
                gemini_res = await adjudicate_with_gemini(pkg, k_res, safety_eval)
                if gemini_res.is_valid and gemini_res.is_safe_for_historical_intake:
                    gemini_resolved_count += 1
        adjudicated_items.append((pkg, k_res, safety_eval, gemini_res))
    runtimes.stage_7_gemini_adjudication_ms = (time.perf_counter() - t0) * 1000.0

    # Stage 9: Cross-Evidence Reconciliation
    t0 = time.perf_counter()
    reconciliation_report = reconcile_candidates(adjudicated_items, period=financial_period)
    runtimes.stage_9_reconciliation_ms = (time.perf_counter() - t0) * 1000.0

    # Stage 10: High-Impact Mandatory Review Checklist
    t0 = time.perf_counter()
    checklist_items = evaluate_checklist(
        report=reconciliation_report,
        extracted_doc=extracted_doc,
        all_candidates=all_candidates,
        is_mining_or_producer=False,
    )
    runtimes.stage_10_checklist_ms = (time.perf_counter() - t0) * 1000.0

    # Stage 11: Whole-Document Skeptical Challenge Pass
    t0 = time.perf_counter()
    if run_gemini_passes:
        challenge_report = await run_whole_document_challenge(
            ticker=ticker,
            financial_period=financial_period,
            extracted_doc=extracted_doc,
            reconciliation_report=reconciliation_report,
        )
    else:
        challenge_report = ChallengeReport(
            findings=[],
            raw_prompt="Skipped (run_gemini_passes=False)",
            raw_response="Skipped",
            model_name="gemini-3.8-flash",
            prompt_version="skipped",
        )
    runtimes.stage_11_challenge_ms = (time.perf_counter() - t0) * 1000.0

    runtimes.total_pipeline_ms = (time.perf_counter() - t_start) * 1000.0

    # Summary counts
    deterministic_accepted = sum(
        1 for _, _, s in evaluated_policy_items if s.decision == PolicyDecision.ACCEPT
    )

    return AFSPipelineResult(
        ticker=ticker,
        company=company,
        financial_period=financial_period,
        archived_doc=archived_doc,
        extracted_doc=extracted_doc,
        candidates_count=len(all_candidates),
        kev_classified_count=len(kev_results),
        deterministic_accepted_count=deterministic_accepted,
        gemini_escalated_count=gemini_escalated_count,
        gemini_resolved_count=gemini_resolved_count,
        analyst_review_count=len(reconciliation_report.review_candidates),
        conflicts_count=len(reconciliation_report.conflicting_candidates),
        reconciliation_report=reconciliation_report,
        checklist_items=checklist_items,
        challenge_report=challenge_report,
        runtimes=runtimes,
    )
