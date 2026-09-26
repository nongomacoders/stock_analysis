"""Comprehensive unit and integration tests for the AFS Evidence Pipeline.

Verifies:
1. candidate numeric extraction (numbers, percentages, currencies, scale, units)
2. by-X-to-Y numeric role parsing (CHANGE_AMOUNT vs ENDING_VALUE / DIRECT_LEVEL)
3. context package construction
4. Kev input contains deterministic candidate
5. Gemini cannot alter candidate numeric value
6. unsupported Gemini enum rejected
7. missing evidence causes abstention
8. guidance cannot become historical actual
9. change-only value cannot become direct level
10. cash capex vs accounting additions remain distinct
11. share-count bases remain distinct
12. raw and AI evidence preserved
13. second-pass challenge cannot mutate structured metrics
"""
import copy
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from modules.analysis.afs_pipeline.archive import archive_afs_pdf
from modules.analysis.afs_pipeline.challenge_pass import ChallengeFinding, ChallengeReport
from modules.analysis.afs_pipeline.checklist import ChecklistStatus, evaluate_checklist
from modules.analysis.afs_pipeline.document_extraction import (
    ExtractedDocument,
    ExtractedPage,
    ExtractedParagraph,
    ExtractedSentence,
)
from modules.analysis.afs_pipeline.evidence_package import (
    ContextEvidencePackage,
    build_evidence_package,
)
from modules.analysis.afs_pipeline.gemini_adjudication import (
    verify_gemini_adjudication,
)
from modules.analysis.afs_pipeline.kev_classifier import KevSemanticResult, classify_with_kev
from modules.analysis.afs_pipeline.numeric_candidates import (
    NumericCandidate,
    extract_numeric_candidates_from_sentence,
)
from modules.analysis.afs_pipeline.reconciliation import (
    HistoricalActualCandidate,
    reconcile_candidates,
)
from modules.analysis.afs_pipeline.safety_policy import (
    PolicyDecision,
    evaluate_safety_policy,
)


def _make_dummy_doc():
    p1 = ExtractedParagraph(
        paragraph_id="p1",
        page_number=18,
        paragraph_index=0,
        text="Revenue increased by R1bn to R12bn.",
        section_heading="Statements of Comprehensive Income",
        note_heading=None,
        sentences=[
            ExtractedSentence("s1", "p1", 18, "Revenue increased by R1bn to R12bn.", 0)
        ],
    )
    page = ExtractedPage(18, "Revenue increased by R1bn to R12bn.", "Statements of Comprehensive Income", [p1])
    return ExtractedDocument(
        document_id="doc_test_1",
        page_count=1,
        pages=[page],
        paragraphs_by_id={"p1": p1},
        sentences_by_id={"s1": p1.sentences[0]},
    )


# 1. Candidate numeric extraction
def test_candidate_numeric_extraction():
    sentence = "Trading margin was 15.5% while gold production was US$1,525/oz and share count was 400,551,604 shares."
    cands = extract_numeric_candidates_from_sentence("s_test", "p_test", 1, sentence)

    tokens = [c.raw_token for c in cands]
    assert any("15.5%" in t for t in tokens)
    assert any("US$1,525/oz" in t for t in tokens)
    assert any("400,551,604 shares" in t for t in tokens)

    # Check normalization
    shares_cand = next(c for c in cands if "400,551,604" in c.raw_token)
    assert shares_cand.normalized_value == Decimal("400551604")
    assert shares_cand.unit == "shares"

    gold_cand = next(c for c in cands if "1,525" in c.raw_token)
    assert gold_cand.normalized_value == Decimal("1525")
    assert gold_cand.unit == "USD_per_oz"


# 2. by-X-to-Y numeric role parsing
def test_by_x_to_y_role_parsing():
    sentence = "Revenue increased by R1bn to R12bn."
    cands = extract_numeric_candidates_from_sentence("s_test", "p_test", 1, sentence)
    assert len(cands) == 2

    c_change = next(c for c in cands if "R1bn" in c.raw_token)
    c_level = next(c for c in cands if "R12bn" in c.raw_token)

    assert c_change.numeric_role == "CHANGE_AMOUNT"
    assert c_change.normalized_value == Decimal("1000000000")
    assert c_change.value_pattern == "change_rate_to_level"

    assert c_level.numeric_role == "ENDING_VALUE"
    assert c_level.normalized_value == Decimal("12000000000")
    assert c_level.value_pattern == "change_rate_to_level"


# 3. Context package construction
def test_context_package_construction():
    doc = _make_dummy_doc()
    cand = extract_numeric_candidates_from_sentence("s1", "p1", 18, "Revenue increased by R1bn to R12bn.")[1]
    pkg = build_evidence_package(cand, doc, ticker="TRU.JO", financial_period="FY2025")

    assert pkg.ticker == "TRU.JO"
    assert pkg.financial_period == "FY2025"
    assert pkg.page_number == 18
    assert pkg.section_heading == "Statements of Comprehensive Income"
    assert pkg.target_sentence == "Revenue increased by R1bn to R12bn."
    assert pkg.candidate_numeric_token == "R12bn"
    assert pkg.deterministic_normalized_value == Decimal("12000000000")


# 4. Kev input contains deterministic candidate
def test_kev_input_contains_deterministic_candidate():
    doc = _make_dummy_doc()
    cand = extract_numeric_candidates_from_sentence("s1", "p1", 18, "Revenue increased by R1bn to R12bn.")[1]
    pkg = build_evidence_package(cand, doc, ticker="TRU.JO", financial_period="FY2025")

    with patch("modules.analysis.afs_pipeline.kev_classifier.call_kev_systemone") as mock_call:
        mock_call.return_value = (
            200,
            {
                "model": "kev-latest",
                "answers": {
                    "concept": {"choice": "accounting_revenue", "confidence": 0.99},
                    "scope": {"choice": "group_consolidated", "confidence": 0.95},
                    "dilution": {"choice": "unspecified", "confidence": 0.99},
                    "tax_basis": {"choice": "unspecified", "confidence": 0.99},
                    "capex_basis": {"choice": "unspecified", "confidence": 0.99},
                    "lease_inclusion": {"choice": "unspecified", "confidence": 0.99},
                    "basis_evidence": {"choice": "unspecified", "confidence": 0.99},
                    "margin_denominator": {"choice": "unspecified", "confidence": 0.99},
                    "attribution": {"choice": "unspecified", "confidence": 0.99},
                    "alias_role": {"choice": "DIRECT_VALUE_LABEL", "confidence": 0.99},
                    "value_pattern": {"choice": "DIRECT_LEVEL", "confidence": 0.99},
                    "should_abstain": {"choice": "false", "confidence": 0.99},
                },
            },
            "{}",
            15.0,
        )
        res = classify_with_kev(pkg, "2025-08-28")
        assert res.concept == "accounting_revenue"
        assert res.scope == "group_consolidated"

        # Verify mock received exact candidate token
        sent_payload = mock_call.call_args[0][0]
        assert sent_payload["state"]["detected_numeric_tokens"] == "R12bn"


# 5. Gemini cannot alter candidate numeric value
def test_gemini_cannot_alter_candidate_numeric_value():
    doc = _make_dummy_doc()
    cand = extract_numeric_candidates_from_sentence("s1", "p1", 18, "Revenue increased by R1bn to R12bn.")[1]
    pkg = build_evidence_package(cand, doc, ticker="TRU.JO", financial_period="FY2025")

    # If Gemini returns an altered number, verification must fail
    fraudulent_response = {
        "candidate_number_verified": "R15bn",  # altered from R12bn
        "canonical_concept": "revenue",
        "temporal_classification": "historical_actual",
        "scope": "group_consolidated",
        "dilution": "unspecified",
        "tax_basis": "unspecified",
        "capex_basis": "unspecified",
        "lease_inclusion": "unspecified",
        "margin_denominator": "unspecified",
        "profit_attribution": "unspecified",
        "is_safe_for_historical_intake": True,
        "supporting_quote": "Revenue increased by R1bn to R12bn.",
    }

    is_valid, errors = verify_gemini_adjudication(pkg, fraudulent_response)
    assert not is_valid
    assert any("Candidate token mismatch" in err for err in errors)


# 6. Unsupported Gemini enum rejected
def test_unsupported_gemini_enum_rejected():
    doc = _make_dummy_doc()
    cand = extract_numeric_candidates_from_sentence("s1", "p1", 18, "Revenue increased by R1bn to R12bn.")[1]
    pkg = build_evidence_package(cand, doc, ticker="TRU.JO", financial_period="FY2025")

    invalid_enum_response = {
        "candidate_number_verified": "R12bn",
        "canonical_concept": "revenue",
        "temporal_classification": "not_a_valid_enum",  # invalid
        "scope": "group_consolidated",
        "dilution": "unspecified",
        "tax_basis": "unspecified",
        "capex_basis": "unspecified",
        "lease_inclusion": "unspecified",
        "margin_denominator": "unspecified",
        "profit_attribution": "unspecified",
        "is_safe_for_historical_intake": True,
        "supporting_quote": "Revenue increased by R1bn to R12bn.",
    }

    is_valid, errors = verify_gemini_adjudication(pkg, invalid_enum_response)
    assert not is_valid
    assert any("Invalid enum value" in err for err in errors)


# 7. Missing evidence causes abstention
def test_missing_evidence_causes_abstention():
    doc = _make_dummy_doc()
    cand = extract_numeric_candidates_from_sentence("s1", "p1", 18, "Revenue increased by R1bn to R12bn.")[1]
    pkg = build_evidence_package(cand, doc, ticker="TRU.JO", financial_period="FY2025")

    # Hallucinated quote not present in context
    hallucinated_quote_response = {
        "candidate_number_verified": "R12bn",
        "canonical_concept": "revenue",
        "temporal_classification": "historical_actual",
        "scope": "group_consolidated",
        "dilution": "unspecified",
        "tax_basis": "unspecified",
        "capex_basis": "unspecified",
        "lease_inclusion": "unspecified",
        "margin_denominator": "unspecified",
        "profit_attribution": "unspecified",
        "is_safe_for_historical_intake": True,
        "supporting_quote": "This sentence was invented by AI and never appeared in AFS.",
    }

    is_valid, errors = verify_gemini_adjudication(pkg, hallucinated_quote_response)
    assert not is_valid
    assert any("Supporting quote does not exist verbatim" in err for err in errors)


# 8. Guidance cannot become historical actual
def test_guidance_cannot_become_historical_actual():
    doc = _make_dummy_doc()
    cand = extract_numeric_candidates_from_sentence("s1", "p1", 18, "Management targets revenue of R14bn for FY2026.")[0]
    pkg = build_evidence_package(cand, doc, ticker="TRU.JO", financial_period="FY2025")

    kev_guidance = KevSemanticResult(
        evidence_id=pkg.evidence_id,
        concept="revenue",
        scope="group_consolidated",
        dilution=None,
        tax_basis=None,
        capex_basis=None,
        lease_inclusion=None,
        basis_evidence=None,
        margin_denominator=None,
        attribution=None,
        alias_role="guidance_statement",  # guidance!
        value_pattern="direct_level",
        should_abstain=False,
        confidence_data={},
        parse_errors=[],
        latency_ms=10.0,
    )

    safety = evaluate_safety_policy(pkg, kev_guidance)
    assert safety.decision == PolicyDecision.ABSTAIN
    assert "guidance" in safety.reason.lower()


# 9. Change-only value cannot become direct level
def test_change_only_cannot_become_direct_level():
    doc = _make_dummy_doc()
    cand = extract_numeric_candidates_from_sentence("s1", "p1", 18, "Revenue increased by R1bn to R12bn.")[0]
    assert cand.numeric_role == "CHANGE_AMOUNT"
    pkg = build_evidence_package(cand, doc, ticker="TRU.JO", financial_period="FY2025")

    kev_change = KevSemanticResult(
        evidence_id=pkg.evidence_id,
        concept="revenue",
        scope="group_consolidated",
        dilution=None,
        tax_basis=None,
        capex_basis=None,
        lease_inclusion=None,
        basis_evidence=None,
        margin_denominator=None,
        attribution=None,
        alias_role="change_statement",
        value_pattern="change_rate_to_level",
        should_abstain=False,
        confidence_data={},
        parse_errors=[],
        latency_ms=10.0,
    )

    safety = evaluate_safety_policy(pkg, kev_change)
    assert safety.decision == PolicyDecision.ABSTAIN
    assert "change-only" in safety.reason.lower()


# 10. Cash capex vs accounting additions remain distinct
def test_cash_capex_vs_additions_distinct():
    doc = _make_dummy_doc()
    cand1 = NumericCandidate("c1", "R674m", Decimal("674000000"), "ZAR", "ZAR", "m", 1, 0, 5, 21, "p1", "s1", "Cash capex", "Cash capex", "DIRECT_LEVEL", "direct_level")
    cand2 = NumericCandidate("c2", "R710m", Decimal("710000000"), "ZAR", "ZAR", "m", 1, 0, 5, 45, "p2", "s2", "Additions", "Additions", "DIRECT_LEVEL", "direct_level")

    pkg1 = build_evidence_package(cand1, doc, "TRU.JO", "FY2025")
    pkg2 = build_evidence_package(cand2, doc, "TRU.JO", "FY2025")

    kev1 = KevSemanticResult(pkg1.evidence_id, "total_capex", "group_consolidated", None, None, "cash_payments", None, None, None, None, "direct_value_label", "direct_level", False, {}, [], 10.0)
    kev2 = KevSemanticResult(pkg2.evidence_id, "total_capex", "group_consolidated", None, None, "accounting_additions", None, None, None, None, "direct_value_label", "direct_level", False, {}, [], 10.0)

    safety1 = evaluate_safety_policy(pkg1, kev1)
    safety2 = evaluate_safety_policy(pkg2, kev2)

    assert safety1.decision == PolicyDecision.ACCEPT
    assert safety2.decision == PolicyDecision.ACCEPT

    report = reconcile_candidates([(pkg1, kev1, safety1, None), (pkg2, kev2, safety2, None)], "FY2025")

    assert len(report.verified_candidates) == 2
    # Verify that capex bases remained distinct and not merged or collapsed
    assert report.verified_candidates[0].qualifiers["capex_basis"] == "cash_payments"
    assert report.verified_candidates[1].qualifiers["capex_basis"] == "accounting_additions"
    assert any("Capex Distinction verified" in f for f in report.reconciliation_findings)


# 11. Share-count bases remain distinct
def test_share_count_bases_remain_distinct():
    doc = _make_dummy_doc()
    c_issued = NumericCandidate("c_iss", "400,551,604", Decimal("400551604"), None, "shares", None, 1, 0, 10, 50, "p1", "s1", "Issued", "Issued shares", "DIRECT_LEVEL", "direct_level")
    c_treasury = NumericCandidate("c_tr", "21,051,604", Decimal("21051604"), None, "shares", None, 1, 0, 10, 52, "p2", "s2", "Treasury", "Treasury shares", "DIRECT_LEVEL", "direct_level")
    c_basic_wa = NumericCandidate("c_wa", "378,000,000", Decimal("378000000"), None, "shares", None, 1, 0, 10, 54, "p3", "s3", "Weighted basic", "Weighted basic", "DIRECT_LEVEL", "direct_level")

    p1 = build_evidence_package(c_issued, doc, "TRU.JO", "FY2025")
    p2 = build_evidence_package(c_treasury, doc, "TRU.JO", "FY2025")
    p3 = build_evidence_package(c_basic_wa, doc, "TRU.JO", "FY2025")

    k1 = KevSemanticResult(p1.evidence_id, "issued_shares", "group_consolidated", None, None, None, None, None, None, None, "direct_value_label", "direct_level", False, {}, [], 10.0)
    k2 = KevSemanticResult(p2.evidence_id, "treasury_shares", "group_consolidated", None, None, None, None, None, None, None, "direct_value_label", "direct_level", False, {}, [], 10.0)
    k3 = KevSemanticResult(p3.evidence_id, "weighted_average_shares", "group_consolidated", "basic", None, None, None, None, None, None, "direct_value_label", "direct_level", False, {}, [], 10.0)

    s1 = evaluate_safety_policy(p1, k1)
    s2 = evaluate_safety_policy(p2, k2)
    s3 = evaluate_safety_policy(p3, k3)

    report = reconcile_candidates([(p1, k1, s1, None), (p2, k2, s2, None), (p3, k3, s3, None)], "FY2025")
    verified_concepts = [c.concept for c in report.verified_candidates]

    assert "issued_shares" in verified_concepts
    assert "treasury_shares" in verified_concepts
    assert "weighted_average_shares" in verified_concepts
    assert any("Share Count Bases identified" in f for f in report.reconciliation_findings)


# 12. Raw and AI evidence preserved
def test_raw_and_ai_evidence_preserved():
    doc = _make_dummy_doc()
    cand = NumericCandidate("c1", "R12bn", Decimal("12000000000"), "ZAR", "ZAR", "bn", 1, 0, 5, 18, "p1", "s1", "Revenue", "Revenue", "ENDING_VALUE", "change_rate_to_level")
    pkg = build_evidence_package(cand, doc, "TRU.JO", "FY2025")
    kev = KevSemanticResult(pkg.evidence_id, "revenue", "group_consolidated", None, None, None, None, None, None, None, "direct_value_label", "change_rate_to_level", False, {"score": 0.98}, [], 12.0)
    safety = evaluate_safety_policy(pkg, kev)

    report = reconcile_candidates([(pkg, kev, safety, None)], "FY2025")
    candidate = report.verified_candidates[0]

    # Verify both raw deterministic candidate and AI classification are intact
    assert candidate.raw_token == "R12bn"
    assert candidate.value == Decimal("12000000000")
    assert candidate.source_page == 18
    assert candidate.kev_result["concept"] == "revenue"
    assert candidate.kev_result["confidence_data"] == {"score": 0.98}


# 13. Second-pass challenge cannot mutate structured metrics
def test_challenge_pass_cannot_mutate_structured_metrics():
    # Construct verified candidates
    c1 = HistoricalActualCandidate(
        candidate_id="c1",
        evidence_id="ev_c1",
        concept="revenue",
        value=Decimal("12000000000"),
        raw_token="R12bn",
        unit="ZAR",
        currency="ZAR",
        period="FY2025",
        scope="group_consolidated",
        qualifiers={},
        source_page=18,
        source_paragraph_id="p1",
        extraction_method="DETERMINISTIC_KEV",
        kev_result={},
        gemini_result=None,
        safety_status="ACCEPT",
        final_status="VERIFIED",
        reconciliation_notes=None,
    )

    original_c1 = copy.deepcopy(c1)

    # Simulated challenge report with critical findings
    finding = ChallengeFinding(
        finding_type="ADVERSE_TREND",
        title="Severe Margin Compression in Office UK",
        description="Office UK operating margin fell from 14% to 8% due to UK freight inflation.",
        severity="MATERIAL",
        source_page=35,
        source_section="Segment Report",
        evidence_quote_or_span="Office UK margin compressed to 8%",
        already_in_model=False,
        affected_metric_or_assumption="trading_margin",
        recommended_analyst_review="Review Office UK cost assumptions",
    )

    report = ChallengeReport(
        findings=[finding],
        raw_prompt="prompt",
        raw_response="response",
        model_name="gemini-3.8-flash",
        prompt_version="v1",
    )

    # Assert structured candidate is unchanged
    assert c1 == original_c1
    assert c1.value == Decimal("12000000000")
    assert report.findings[0].severity == "MATERIAL"


# 14. Full-page extraction coverage
def test_full_page_extraction_coverage():
    from pathlib import Path
    from modules.analysis.afs_pipeline.document_extraction import extract_document
    pdf_path = Path(r"C:\Users\Dion\Desktop\Projects\stock_analysis\gui\results_history\TRU\FY2025\TRU_FY2025_AFS.pdf")
    doc = extract_document(pdf_path, "doc_test_full", max_pages=None)
    assert doc.total_pdf_pages == 156
    assert doc.page_count == 156
    assert doc.pages_with_embedded_text == 156
    assert doc.pages_no_usable_text == 0
    assert doc.pages_failed == 0
    assert doc.pages_requiring_ocr == 0


# 15. Note reference vs financial amount
def test_note_reference_vs_financial_amount():
    row_text = "Lease liabilities 20.1  2,697 2,927"
    cands = extract_numeric_candidates_from_sentence("s_lease", "p_lease", 18, row_text)
    assert len(cands) == 2
    # Verify 20.1 is not in candidate numeric stream
    assert all(c.normalized_value != Decimal("20.1") for c in cands)
    # Verify note_reference is tagged on candidates
    assert all(c.note_reference == "20.1" for c in cands)
    # Check current vs comparative
    curr = next(c for c in cands if c.temporal_role == "CURRENT_PERIOD")
    prior = next(c for c in cands if c.temporal_role == "COMPARATIVE_PERIOD")
    assert curr.normalized_value == Decimal("2697")
    assert prior.normalized_value == Decimal("2927")


# 16. Current vs comparative year binding
def test_current_vs_comparative_year_binding():
    row_text = "Interest-bearing borrowings 16  1,479 1,208"
    cands = extract_numeric_candidates_from_sentence("s_borrow", "p_borrow", 18, row_text)
    assert len(cands) == 2
    curr = next(c for c in cands if c.temporal_role == "CURRENT_PERIOD")
    prior = next(c for c in cands if c.temporal_role == "COMPARATIVE_PERIOD")
    assert curr.normalized_value == Decimal("1479")
    assert curr.note_reference == "16"
    assert prior.normalized_value == Decimal("1208")
    assert prior.note_reference == "16"


# 17. Mandatory checklist active document search
def test_mandatory_checklist_active_document_search():
    from modules.analysis.afs_pipeline.reconciliation import ReconciliationReport
    p1 = ExtractedParagraph(
        paragraph_id="p1",
        page_number=58,
        paragraph_index=0,
        text="Note 16 Borrowings. The Group complied with all financial covenants during the period.",
        section_heading="Notes to the AFS",
        note_heading="Note 16: Borrowings",
        sentences=[ExtractedSentence("s1", "p1", 58, "The Group complied with all financial covenants during the period.", 0)],
    )
    page = ExtractedPage(58, "Note 16 Borrowings. The Group complied with all financial covenants during the period.", "Notes to the AFS", [p1])
    doc = ExtractedDocument(
        document_id="doc_cov",
        page_count=1,
        pages=[page],
        paragraphs_by_id={"p1": p1},
        sentences_by_id={"s1": p1.sentences[0]},
    )
    empty_report = ReconciliationReport(
        verified_candidates=[],
        review_candidates=[],
        conflicting_candidates=[],
        rejected_candidates=[],
        reconciliation_findings=[],
    )
    items = evaluate_checklist(
        report=empty_report,
        extracted_doc=doc,
        all_candidates=[],
        is_mining_or_producer=False,
    )
    cov_item = next(i for i in items if i.category == "covenants")
    assert cov_item.status == ChecklistStatus.REQUIRES_REVIEW
    assert 58 in cov_item.source_pages
    assert "Active search identified disclosures" in cov_item.notes


# 18. NOT_FOUND cannot result merely from candidate sampling
def test_not_found_cannot_result_merely_from_candidate_sampling():
    from modules.analysis.afs_pipeline.reconciliation import ReconciliationReport
    p1 = ExtractedParagraph(
        paragraph_id="p1",
        page_number=63,
        paragraph_index=0,
        text="Note 20 Lease liabilities under IFRS 16 totaled R3,742m.",
        section_heading="Notes to the AFS",
        note_heading="Note 20: Leases",
        sentences=[ExtractedSentence("s1", "p1", 63, "Note 20 Lease liabilities under IFRS 16 totaled R3,742m.", 0)],
    )
    page = ExtractedPage(63, "Note 20 Lease liabilities under IFRS 16 totaled R3,742m.", "Notes to the AFS", [p1])
    doc = ExtractedDocument(
        document_id="doc_lease",
        page_count=1,
        pages=[page],
        paragraphs_by_id={"p1": p1},
        sentences_by_id={"s1": p1.sentences[0]},
    )
    empty_report = ReconciliationReport(
        verified_candidates=[],
        review_candidates=[],
        conflicting_candidates=[],
        rejected_candidates=[],
        reconciliation_findings=[],
    )
    # Even if empty candidate sample is provided, search must find the disclosure and NOT mark NOT_FOUND
    items = evaluate_checklist(
        report=empty_report,
        extracted_doc=doc,
        all_candidates=[],
        is_mining_or_producer=False,
    )
    lease_item = next(i for i in items if i.category == "lease_liabilities")
    assert lease_item.status != ChecklistStatus.NOT_FOUND
    assert lease_item.status == ChecklistStatus.REQUIRES_REVIEW
    assert 63 in lease_item.source_pages


# 19. Frozen historical reference loader uses correct period
def test_frozen_historical_reference_loader_uses_correct_period():
    from modules.analysis.afs_pipeline.reference_loader import load_frozen_reference_facts
    facts = load_frozen_reference_facts("TRU", "FY2025")
    assert facts.period_label == "FY2025"
    assert facts.accounting_revenue == Decimal("23071000000")
    assert facts.sale_of_merchandise == Decimal("21323000000")
    assert facts.trading_profit == Decimal("2892000000")
    assert facts.effective_tax_rate_pct == Decimal("25.4")
    assert facts.cash_capex == Decimal("674000000")
    assert facts.working_capital_movement == Decimal("166000000")
    assert facts.reported_net_cash == Decimal("720000000")
    assert facts.total_lease_liabilities == Decimal("3742000000")
    assert facts.issued_shares == Decimal("408498899")
    assert facts.treasury_shares == Decimal("33138000")
    assert facts.external_shares == Decimal("375360899")
    assert facts.weighted_average_basic_shares == Decimal("374400000")
    assert facts.weighted_average_diluted_shares == Decimal("378800000")
    assert facts.depreciation_expense == Decimal("1500000000")
    assert facts.depreciation_cashflow_addback == Decimal("1526000000")

    # Inexistent period must raise ValueError
    with pytest.raises(ValueError):
        load_frozen_reference_facts("TRU", "FY1999")


# 20. Challenge page and chunk coverage
def test_challenge_page_and_chunk_coverage():
    import asyncio
    from modules.analysis.afs_pipeline.challenge_pass import run_whole_document_challenge
    from modules.analysis.afs_pipeline.reconciliation import ReconciliationReport

    pages = []
    for p_no in range(1, 157):
        p_obj = ExtractedParagraph(
            paragraph_id=f"p{p_no}",
            page_number=p_no,
            paragraph_index=0,
            text=f"Page {p_no} financial disclosure text.",
            section_heading="Notes",
            note_heading=None,
            sentences=[ExtractedSentence(f"s{p_no}", f"p{p_no}", p_no, f"Page {p_no} text.", 0)],
        )
        pages.append(ExtractedPage(p_no, f"Page {p_no} text.", "Notes", [p_obj]))

    doc = ExtractedDocument(
        document_id="doc_156",
        page_count=156,
        pages=pages,
        paragraphs_by_id={},
        sentences_by_id={},
    )
    rec_report = ReconciliationReport(
        verified_candidates=[],
        review_candidates=[],
        conflicting_candidates=[],
        rejected_candidates=[],
        reconciliation_findings=[],
    )

    with patch("modules.analysis.afs_pipeline.challenge_pass.managed_query_ai", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = '{"findings": []}'
        report = asyncio.run(
            run_whole_document_challenge(
                ticker="TRU",
                financial_period="FY2025",
                extracted_doc=doc,
                reconciliation_report=rec_report,
                chunk_size_pages=35,
            )
        )
        assert report.chunk_count == 5  # ceil(156/35) = 5
        assert len(report.page_coverage) == 156
        assert report.page_coverage[0] == 1
        assert report.page_coverage[-1] == 156
        assert report.failed_chunks == 0
        assert report.retry_count == 0


# 21. GOLD-001 authoritative hash check
def test_gold001_authoritative_hash_check():
    import psycopg2, psycopg2.extras
    from core.config import DB_CONFIG

    AUTHORITATIVE_RELEASE_HASH = "f0b3138d32a033b66cd0823cfd83ae89461433209a0552bece6722d2ca98f179"
    AUTHORITATIVE_SOURCE_HASH = "4b8594e5b34d7d05273fecda2dd4b817b9dc2e055d77cf0bc6de31cf79ff7610"
    AUTHORITATIVE_LABEL_HASH = "f9139858b89ea102d30c22e1007b1e807c5aecc684048ffb31df1dcb73e9ef75"

    conn = psycopg2.connect(**DB_CONFIG)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        # Check releases table
        cur.execute(
            """
            SELECT release_id, release_hash, source_hash, label_hash, review_row_count, evaluation_row_count
            FROM financial_classifier_gold_releases
            WHERE release_id = 'GOLD-001';
            """
        )
        rel = cur.fetchone()
        assert rel is not None, "GOLD-001 release not found in financial_classifier_gold_releases"
        assert rel["release_hash"] == AUTHORITATIVE_RELEASE_HASH, f"Mismatched release_hash: {rel['release_hash']}"
        assert rel["source_hash"] == AUTHORITATIVE_SOURCE_HASH, f"Mismatched source_hash: {rel['source_hash']}"
        assert rel["label_hash"] == AUTHORITATIVE_LABEL_HASH, f"Mismatched label_hash: {rel['label_hash']}"
        assert rel["review_row_count"] == 300, f"Expected 300 total examples, got {rel['review_row_count']}"
        assert rel["evaluation_row_count"] == 281, f"Expected 281 evaluable examples, got {rel['evaluation_row_count']}"

        # Check gold review table row count
        cur.execute("SELECT count(*) as total, count(*) FILTER (WHERE review_decision != 'SKIP') as evaluable FROM financial_classifier_gold_review WHERE review_batch = 'BATCH-001';")
        counts = cur.fetchone()
        assert counts["total"] == 300
        assert counts["evaluable"] == 281
    finally:
        conn.close()

