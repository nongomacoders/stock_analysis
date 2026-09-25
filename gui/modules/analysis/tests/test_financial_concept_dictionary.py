"""Tests for FinancialConceptDictionary (Phase 1).

Validates:
1. Normalization stability and semantic preservation.
2. Approved aliases mapping to exactly one canonical concept.
3. Ambiguous aliases NOT being auto-resolved.
4. Prohibited financial equivalences strictly enforced.
5. Serialization and deserialization roundtrip.
6. Duplicate alias detection.
7. Provenance preservation in AliasObservation.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest
from pydantic import ValidationError

from modules.analysis.financial_concept_dictionary import (
    AliasObservation,
    AliasStatus,
    CanonicalConcept,
    CapexBasis,
    ConceptCategory,
    DilutionBasis,
    DividendTaxBasis,
    FinancialConceptDictionary,
    LeaseInclusion,
    MarginDenominator,
    MatchClassification,
    MetricBasis,
    NumericSign,
    OperationScope,
    PeriodType,
    ProfitAttribution,
    SemanticQualifiers,
    BasisEvidence,
    build_default_canonical_concepts,
    is_prohibited_equivalence,
    normalize_label,
)


def test_normalization_stability():
    """Test idempotency and semantic preservation in label normalization."""
    test_cases = [
        ("  • Revenue & Other Income: ", "revenue and other income"),
        ("Trading profit – continuing operations", "trading profit - continuing operations"),
        ("Operating profit before finance costs & tax:", "operating profit before finance costs and tax"),
        ("1.2 Headline earnings per share (cents)...", "headline earnings per share (cents)"),
        ("Normalised EBITDA (R'm):", "normalised ebitda (r'm)"),
        ("Adjusted operating profit", "adjusted operating profit"),
        ("Cash capex (payments basis)", "cash capex (payments basis)"),
    ]

    for raw, expected in test_cases:
        norm = normalize_label(raw)
        assert norm == expected, f"Failed for {raw}: got {norm}, expected {expected}"
        # Idempotency check: normalize(normalize(x)) == normalize(x)
        assert normalize_label(norm) == norm, f"Normalization not idempotent for {raw}"

    # Verify meaningful words are NOT stripped
    critical_words = [
        "adjusted", "normalised", "underlying", "continuing",
        "before", "after", "cash", "reported", "trading", "operating"
    ]
    for w in critical_words:
        phrase = f"group {w} result"
        assert w in normalize_label(phrase)


def test_approved_aliases_map_to_exactly_one_concept():
    """Every approved alias must map to exactly one canonical concept."""
    concepts = build_default_canonical_concepts()
    dictionary = FinancialConceptDictionary(concepts=concepts)
    errors = dictionary.validate_integrity()
    assert not errors, f"Integrity errors found: {errors}"

    # Verify lookup of approved aliases
    for c_id, concept in concepts.items():
        for alias in concept.approved_aliases:
            found_concept, classification, _ = dictionary.lookup_label(alias)
            assert found_concept is not None, f"Alias '{alias}' not found in concept '{c_id}'"
            assert found_concept.concept_id == c_id
            assert classification in {
                MatchClassification.EXACT_EXISTING_ALIAS,
                MatchClassification.NORMALIZED_EXISTING_ALIAS
            }


def test_ambiguous_aliases_not_auto_resolved():
    """Ambiguous aliases must return AMBIGUOUS classification and NO resolved canonical concept."""
    concepts = build_default_canonical_concepts()
    dictionary = FinancialConceptDictionary(concepts=concepts)

    ambiguous_labels = [
        "sales",
        "operating profit",
        "capital expenditure",
        "turnover",
        "working capital",
        "debt",
        "cash flow",
        "borrowings",
    ]

    for label in ambiguous_labels:
        concept, classification, note = dictionary.lookup_label(label)
        assert concept is None, f"Ambiguous label '{label}' was incorrectly auto-resolved to '{concept.concept_id if concept else None}'"
        assert classification == MatchClassification.AMBIGUOUS
        assert note is not None


def test_prohibited_equivalences():
    """Ensure financial distinctions are strictly guarded by prohibited equivalences."""
    # Critical required examples from specification:
    # 1. Trading profit != Operating profit
    assert is_prohibited_equivalence("trading_profit", "operating_profit")
    assert is_prohibited_equivalence("operating_profit", "trading_profit")

    # 2. Revenue != Retail sales
    assert is_prohibited_equivalence("revenue", "retail_sales")
    assert is_prohibited_equivalence("retail_sales", "revenue")

    # 3. Sale of merchandise != Revenue
    assert is_prohibited_equivalence("sale_of_merchandise", "revenue")
    assert is_prohibited_equivalence("revenue", "sale_of_merchandise")

    # 4. Cash capex != Accounting additions (total_capex)
    assert is_prohibited_equivalence("cash_capex", "total_capex")
    assert is_prohibited_equivalence("total_capex", "cash_capex")

    # 5. Weighted average shares != Point-in-time shares
    assert is_prohibited_equivalence("weighted_average_basic_shares", "issued_shares_current")
    assert is_prohibited_equivalence("weighted_average_basic_shares", "period_end_external_shares")
    assert is_prohibited_equivalence("weighted_average_diluted_shares", "period_end_external_shares")

    # 6. Net cash != Cash and cash equivalents
    assert is_prohibited_equivalence("reported_net_cash", "cash_and_cash_equivalents")
    assert is_prohibited_equivalence("cash_and_cash_equivalents", "reported_net_cash")

    # 7. Additional critical distinctions
    assert is_prohibited_equivalence("operating_profit", "ebit")
    assert is_prohibited_equivalence("trading_profit", "ebit")
    assert is_prohibited_equivalence("ebitda", "adjusted_ebitda")
    assert is_prohibited_equivalence("ebitda", "normalised_ebitda")
    assert is_prohibited_equivalence("retail_sales", "sale_of_merchandise")
    assert is_prohibited_equivalence("depreciation_amortisation_expense", "depreciation_amortisation_cashflow_addback")

    # Verify that a concept definition violating prohibited equivalence raises an error
    with pytest.raises(ValueError, match="cannot have prohibited concept"):
        CanonicalConcept(
            concept_id="invalid_trading_profit",
            name="Invalid Trading Profit",
            description="Testing prohibited validation",
            category=ConceptCategory.INCOME_STATEMENT,
            expected_units=["ZAR"],
            allowed_sections=["income_statement"],
            approved_aliases=["Operating profit"],
            prohibited_equivalences=["Operating profit"]
        )


def test_duplicate_alias_detection():
    """Detect when an approved alias is assigned to two different canonical concepts."""
    c1 = CanonicalConcept(
        concept_id="concept_one",
        name="Concept One",
        description="First concept",
        category=ConceptCategory.INCOME_STATEMENT,
        expected_units=["ZAR"],
        allowed_sections=["income_statement"],
        approved_aliases=["Shared Alias Wording"]
    )
    c2 = CanonicalConcept(
        concept_id="concept_two",
        name="Concept Two",
        description="Second concept",
        category=ConceptCategory.INCOME_STATEMENT,
        expected_units=["ZAR"],
        allowed_sections=["income_statement"],
        approved_aliases=["Shared Alias Wording"]
    )

    d = FinancialConceptDictionary(concepts={"concept_one": c1, "concept_two": c2})
    errors = d.validate_integrity()
    assert len(errors) == 1
    assert "Duplicate approved alias 'Shared Alias Wording'" in errors[0]


def test_source_provenance_preservation():
    """Ensure AliasObservation retains all required provenance fields."""
    obs = AliasObservation(
        raw_label="• Revenue increased by 10% to R10.5 billion",
        normalized_label="revenue increased by 10% to r10.5 billion",
        canonical_concept="accounting_revenue",
        status=AliasStatus.CANDIDATE,
        classification=MatchClassification.POTENTIAL_ALIAS,
        occurrence_count=142,
        ticker_count=47,
        first_seen="2025-08-01 10:00",
        last_seen="2026-09-20 14:00",
        sample_tickers=["TRU.JO", "BID.JO", "MRP.JO"],
        sample_sources=["sens_101", "sens_205"],
        sample_contexts=["Revenue increased by 10% to R10.5 billion driven by retail expansion"],
        disambiguation_note="Candidate phrase with syntax tail"
    )

    assert obs.raw_label.startswith("• Revenue")
    assert obs.occurrence_count == 142
    assert obs.ticker_count == 47
    assert len(obs.sample_tickers) == 3
    assert len(obs.sample_sources) == 2
    assert len(obs.sample_contexts) == 1
    assert obs.status == AliasStatus.CANDIDATE


def test_serialization_deserialization():
    """Ensure dictionary serializes to and deserializes from JSON without loss."""
    concepts = build_default_canonical_concepts()
    dictionary = FinancialConceptDictionary(concepts=concepts)

    obs = AliasObservation(
        raw_label="Headline earnings per share",
        normalized_label="headline earnings per share",
        canonical_concept="heps",
        status=AliasStatus.APPROVED,
        classification=MatchClassification.EXACT_EXISTING_ALIAS,
        occurrence_count=629,
        ticker_count=180,
        sample_tickers=["TRU.JO", "BID.JO"],
        sample_sources=["sens_1", "sens_2"]
    )
    dictionary.register_observation(obs)

    json_str = dictionary.to_json()
    reloaded = FinancialConceptDictionary.from_json(json_str)

    assert len(reloaded.concepts) == len(dictionary.concepts)
    assert len(reloaded.alias_registry) == 1
    assert reloaded.alias_registry["headline earnings per share"].occurrence_count == 629
    assert reloaded.alias_registry["headline earnings per share"].canonical_concept == "heps"


def test_exported_json_artifact_validity():
    """Verify that the generated JSON artifact exists and is structurally sound."""
    json_path = Path("C:/Users/Dion/Desktop/Projects/stock_analysis/gui/modules/analysis/data/financial_concept_aliases.json")
    assert json_path.exists(), "Exported artifact financial_concept_aliases.json does not exist"

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "metadata" in data
    assert "canonical_concepts" in data
    assert "aliases" in data
    assert data["metadata"]["corpus_stats"]["sens_rows"] >= 5281
    assert len(data["canonical_concepts"]) >= 35
    assert len(data["aliases"]) >= 800

    # Ensure every alias has qualifiers populated
    for alias in data["aliases"][:50]:
        assert "qualifiers" in alias, f"Alias {alias['normalized_label']} missing qualifiers"


def test_qualifier_validation_rules():
    """Verify strict semantic validation rules on AliasObservation qualifiers."""
    # 1. Rule 1: Gross/net dividend basis must be explicit
    with pytest.raises(ValueError, match="indicates gross dividend; tax_basis must be GROSS"):
        AliasObservation(
            raw_label="gross dividend per share",
            normalized_label="gross dividend per share",
            canonical_concept="dividend_per_share",
            status=AliasStatus.CANDIDATE,
            qualifiers=SemanticQualifiers(tax_basis=DividendTaxBasis.UNSPECIFIED)
        )

    with pytest.raises(ValueError, match="indicates net dividend; tax_basis must be NET"):
        AliasObservation(
            raw_label="net dividend amount per share",
            normalized_label="net dividend amount per share",
            canonical_concept="dividend_per_share",
            status=AliasStatus.CANDIDATE,
            qualifiers=SemanticQualifiers(tax_basis=DividendTaxBasis.GROSS)
        )

    with pytest.raises(ValueError, match="cannot be APPROVED with unspecified tax_basis"):
        AliasObservation(
            raw_label="dividend per share",
            normalized_label="dividend per share",
            canonical_concept="dividend_per_share",
            status=AliasStatus.APPROVED,
            qualifiers=SemanticQualifiers(tax_basis=DividendTaxBasis.UNSPECIFIED)
        )

    # Valid candidate dividend with unspecified tax basis remaining in REQUIRES_CONTEXT
    valid_req_div = AliasObservation(
        raw_label="dividend per share",
        normalized_label="dividend per share",
        canonical_concept="dividend_per_share",
        status=AliasStatus.REQUIRES_CONTEXT,
        qualifiers=SemanticQualifiers(tax_basis=DividendTaxBasis.UNSPECIFIED)
    )
    assert valid_req_div.status == AliasStatus.REQUIRES_CONTEXT

    # 2. Rule 2: Continuing-operations scope must be preserved
    with pytest.raises(ValueError, match="contains continuing-operations indicator; qualifiers.scope must be CONTINUING_OPERATIONS"):
        AliasObservation(
            raw_label="revenue from continuing operations",
            normalized_label="revenue from continuing operations",
            canonical_concept="accounting_revenue",
            status=AliasStatus.CANDIDATE,
            qualifiers=SemanticQualifiers(scope=OperationScope.TOTAL_OPERATIONS)
        )

    # Valid continuing operations observation
    valid_cont = AliasObservation(
        raw_label="revenue from continuing operations",
        normalized_label="revenue from continuing operations",
        canonical_concept="accounting_revenue",
        status=AliasStatus.CANDIDATE,
        qualifiers=SemanticQualifiers(scope=OperationScope.CONTINUING_OPERATIONS)
    )
    assert valid_cont.qualifiers.scope == OperationScope.CONTINUING_OPERATIONS

    # 3. Rule 3: Capex basis cannot default to cash_capex
    with pytest.raises(ValueError, match="Generic capex label .* cannot map directly to cash_capex"):
        AliasObservation(
            raw_label="Total capital expenditure",
            normalized_label="total capital expenditure",
            canonical_concept="cash_capex",
            status=AliasStatus.CANDIDATE,
            qualifiers=SemanticQualifiers(capex_basis=CapexBasis.CASH_PAYMENTS)
        )

    with pytest.raises(ValueError, match="Capex basis cannot default to CASH_PAYMENTS"):
        AliasObservation(
            raw_label="Total capital expenditure",
            normalized_label="total capital expenditure",
            canonical_concept="total_capex",
            status=AliasStatus.CANDIDATE,
            qualifiers=SemanticQualifiers(capex_basis=CapexBasis.CASH_PAYMENTS)
        )

    # 4. Rule 4: Debt lease inclusion cannot default without evidence
    with pytest.raises(ValueError, match="cannot be APPROVED .* with unspecified lease_inclusion"):
        AliasObservation(
            raw_label="total borrowings",
            normalized_label="total borrowings",
            canonical_concept="interest_bearing_borrowings",
            status=AliasStatus.APPROVED,
            qualifiers=SemanticQualifiers(lease_inclusion=LeaseInclusion.UNSPECIFIED)
        )

    # Debt without explicit lease evidence is valid as REQUIRES_CONTEXT with lease_inclusion=UNSPECIFIED
    valid_req_debt = AliasObservation(
        raw_label="total borrowings",
        normalized_label="total borrowings",
        canonical_concept="interest_bearing_borrowings",
        status=AliasStatus.REQUIRES_CONTEXT,
        qualifiers=SemanticQualifiers(
            lease_inclusion=LeaseInclusion.UNSPECIFIED,
            basis_evidence=BasisEvidence.UNSPECIFIED
        ),
        disambiguation_note="Debt lease treatment unspecified; requires context to determine IFRS 16 lease inclusion"
    )
    assert valid_req_debt.status == AliasStatus.REQUIRES_CONTEXT
    assert valid_req_debt.qualifiers.lease_inclusion == LeaseInclusion.UNSPECIFIED

    # Attempting to approve debt with lease_inclusion but without basis_evidence raises ValueError
    with pytest.raises(ValueError, match="without explicit basis_evidence"):
        AliasObservation(
            raw_label="interest-bearing borrowings",
            normalized_label="interest-bearing borrowings",
            canonical_concept="interest_bearing_borrowings",
            status=AliasStatus.APPROVED,
            qualifiers=SemanticQualifiers(
                lease_inclusion=LeaseInclusion.EX_LEASES,
                basis_evidence=BasisEvidence.UNSPECIFIED
            )
        )

    # Debt with explicit evidence can be APPROVED with EX_LEASES via EXPLICIT_NOTE_WORDING
    valid_app_debt = AliasObservation(
        raw_label="interest-bearing borrowings excluding lease liabilities",
        normalized_label="interest-bearing borrowings excluding lease liabilities",
        canonical_concept="interest_bearing_borrowings",
        status=AliasStatus.APPROVED,
        qualifiers=SemanticQualifiers(
            lease_inclusion=LeaseInclusion.EX_LEASES,
            basis_evidence=BasisEvidence.EXPLICIT_NOTE_WORDING,
            custom_notes="Explicitly stated in label/note text"
        )
    )
    assert valid_app_debt.status == AliasStatus.APPROVED
    assert valid_app_debt.qualifiers.lease_inclusion == LeaseInclusion.EX_LEASES
    assert valid_app_debt.qualifiers.basis_evidence == BasisEvidence.EXPLICIT_NOTE_WORDING

    # Balance sheet face borrowings can be APPROVED with EX_LEASES via BALANCE_SHEET_PRESENTATION_SEPARATE
    # ONLY when the same source document explicitly presents lease liabilities separately
    valid_bs_debt = AliasObservation(
        raw_label="Interest-bearing borrowings",
        normalized_label="interest-bearing borrowings",
        canonical_concept="interest_bearing_borrowings",
        status=AliasStatus.APPROVED,
        qualifiers=SemanticQualifiers(
            lease_inclusion=LeaseInclusion.EX_LEASES,
            basis_evidence=BasisEvidence.BALANCE_SHEET_PRESENTATION_SEPARATE,
            custom_notes="Statement of financial position explicitly presents lease liabilities on a separate line item"
        ),
        disambiguation_note="Source document explicitly presents lease liabilities separately from interest-bearing borrowings"
    )
    assert valid_bs_debt.status == AliasStatus.APPROVED
    assert valid_bs_debt.qualifiers.basis_evidence == BasisEvidence.BALANCE_SHEET_PRESENTATION_SEPARATE

    # Rejects BALANCE_SHEET_PRESENTATION_SEPARATE if same document does not prove separate lease liabilities
    with pytest.raises(ValueError, match="without evidence that the same source document explicitly presents lease liabilities separately"):
        AliasObservation(
            raw_label="Interest-bearing borrowings",
            normalized_label="interest-bearing borrowings",
            canonical_concept="interest_bearing_borrowings",
            status=AliasStatus.APPROVED,
            qualifiers=SemanticQualifiers(
                lease_inclusion=LeaseInclusion.EX_LEASES,
                basis_evidence=BasisEvidence.BALANCE_SHEET_PRESENTATION_SEPARATE,
                custom_notes="Extracted from balance sheet table"  # Does not prove separate lease liabilities
            )
        )

    # When separate lease presentation is not proven in the document, it must remain REQUIRES_CONTEXT
    unverified_bs_debt = AliasObservation(
        raw_label="Interest-bearing borrowings",
        normalized_label="interest-bearing borrowings",
        canonical_concept="interest_bearing_borrowings",
        status=AliasStatus.REQUIRES_CONTEXT,
        qualifiers=SemanticQualifiers(
            lease_inclusion=LeaseInclusion.UNSPECIFIED,
            basis_evidence=BasisEvidence.UNSPECIFIED
        ),
        disambiguation_note="Same source document does not explicitly evidence separate lease liabilities; requires context"
    )
    assert unverified_bs_debt.status == AliasStatus.REQUIRES_CONTEXT
    assert unverified_bs_debt.qualifiers.lease_inclusion == LeaseInclusion.UNSPECIFIED
    assert unverified_bs_debt.qualifiers.basis_evidence == BasisEvidence.UNSPECIFIED

    # 5. Rule 5: Margin denominator cannot be inferred
    with pytest.raises(ValueError, match="cannot have unspecified margin_denominator"):
        AliasObservation(
            raw_label="Trading profit margin",
            normalized_label="trading profit margin",
            canonical_concept="trading_margin",
            status=AliasStatus.APPROVED,
            qualifiers=SemanticQualifiers(margin_denominator=MarginDenominator.UNSPECIFIED)
        )

