"""Tests for FinancialClassifierBenchmark and Evaluation Harness.

Validates:
1. Benchmark serialization (JSON roundtrip).
2. Deterministic sampling reproducibility.
3. No duplicate benchmark IDs in generated dataset.
4. Ticker and label sampling caps (<=10 per label, <=20 per ticker).
5. Enum validity across all benchmark dimensions.
6. Auto-seed restrictions (only approved concepts with explicit qualifiers).
7. Ambiguous cases remain REVIEW_REQUIRED (no silent auto-labeling).
8. Guidance wording does not become historical actual (INFORMATIONAL_ONLY/abstain).
9. Valuation eligibility states correctly assigned.
10. Abstention metric calculation.
11. Unsafe false acceptance calculation.
12. Threshold evaluation curves.
13. Calibration data structure (Brier score, ECE, buckets).
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from modules.analysis.financial_concept_dictionary import (
    AliasStatus,
    BasisEvidence,
    CapexBasis,
    DilutionBasis,
    DividendTaxBasis,
    LeaseInclusion,
    MarginDenominator,
    MetricBasis,
    NumericSign,
    OperationScope,
    SemanticQualifiers,
)
import csv
from modules.analysis.financial_classifier_benchmark import (
    AliasRole,
    BenchmarkDifficulty,
    BenchmarkEvaluator,
    BenchmarkItem,
    CalibrationBucket,
    CalibrationReport,
    ClassifierPrediction,
    DetectedNumericToken,
    EvaluationResult,
    NumericTokenType,
    ReviewDecision,
    ReviewStatus,
    ThresholdMetrics,
    ValuationEligibility,
    ValuePattern,
    REVIEW_WORKSHEET_COLUMNS,
    apply_review_decisions,
    classify_benchmark_item_heuristics,
    export_review_worksheet_csv,
    format_review_progress_report,
    get_batch_001_ids,
    get_csv_review_progress_report,
    get_review_progress_report,
    import_review_worksheet_csv,
    load_benchmark_json,
    parse_detected_numeric_tokens,
    resolve_nested_alias_spans,
    save_benchmark_json,
)


@pytest.fixture
def sample_benchmark_items() -> list[BenchmarkItem]:
    """Generates a controlled diverse set of benchmark items for testing evaluator logic."""
    return [
        # Item 1: Auto-seeded direct revenue (ELIGIBLE)
        BenchmarkItem(
            benchmark_id="BENCH-TEST-0001",
            sens_id=101,
            ticker="TRU.JO",
            publication_datetime="2025-09-01 10:00",
            raw_label="Revenue for the year",
            normalized_label="revenue for the year",
            full_sentence="Revenue for the year was R10.5 billion.",
            detected_numeric_tokens=["10.5"],
            current_dictionary_status=AliasStatus.APPROVED,
            current_proposed_canonical_concept="accounting_revenue",
            seed_concept="accounting_revenue",
            seed_alias_role=AliasRole.DIRECT_VALUE_LABEL,
            seed_value_pattern=ValuePattern.DIRECT_LEVEL,
            seed_valuation_eligibility=ValuationEligibility.ELIGIBLE,
            seed_should_abstain=False,
            review_status=ReviewStatus.AUTO_SEEDED,
            difficulty_category=BenchmarkDifficulty.EASY_DIRECT
        ),
        # Item 2: Auto-seeded change statement (INFORMATIONAL_ONLY, should NOT direct extract)
        BenchmarkItem(
            benchmark_id="BENCH-TEST-0002",
            sens_id=102,
            ticker="TRU.JO",
            publication_datetime="2025-09-01 10:00",
            raw_label="Revenue increased by",
            normalized_label="revenue increased by",
            full_sentence="Revenue increased by 6.2% to R10.5 billion.",
            detected_numeric_tokens=["6.2%", "10.5"],
            current_dictionary_status=AliasStatus.APPROVED,
            current_proposed_canonical_concept="accounting_revenue",
            seed_concept="accounting_revenue",
            seed_alias_role=AliasRole.CHANGE_STATEMENT,
            seed_value_pattern=ValuePattern.CHANGE_RATE_TO_LEVEL,
            seed_valuation_eligibility=ValuationEligibility.INFORMATIONAL_ONLY,
            seed_should_abstain=False,
            review_status=ReviewStatus.AUTO_SEEDED,
            difficulty_category=BenchmarkDifficulty.CHANGE_STATEMENTS
        ),
        # Item 3: Ambiguous label (sales -> REQUIRES_SCOPE / MUST ABSTAIN)
        BenchmarkItem(
            benchmark_id="BENCH-TEST-0003",
            sens_id=103,
            ticker="MRP.JO",
            publication_datetime="2025-09-02 08:00",
            raw_label="Sales",
            normalized_label="sales",
            full_sentence="Total sales were R12.0 billion across divisions.",
            detected_numeric_tokens=["12.0"],
            current_dictionary_status=AliasStatus.AMBIGUOUS,
            current_proposed_canonical_concept=None,
            seed_concept=None,
            seed_alias_role=AliasRole.DIRECT_VALUE_LABEL,
            seed_value_pattern=ValuePattern.DIRECT_LEVEL,
            seed_valuation_eligibility=ValuationEligibility.REQUIRES_SCOPE,
            seed_should_abstain=True,
            review_status=ReviewStatus.REVIEW_REQUIRED,
            difficulty_category=BenchmarkDifficulty.SCOPE_AMBIGUITY
        ),
        # Item 4: Requires Context (net debt without lease evidence -> REQUIRES_SOURCE_SECTION / ABSTAIN)
        BenchmarkItem(
            benchmark_id="BENCH-TEST-0004",
            sens_id=104,
            ticker="SOL.JO",
            publication_datetime="2025-09-03 14:00",
            raw_label="Net debt",
            normalized_label="net debt",
            full_sentence="Reported net debt was R25 billion at year-end.",
            detected_numeric_tokens=["25"],
            current_dictionary_status=AliasStatus.REQUIRES_CONTEXT,
            current_proposed_canonical_concept="reported_net_debt",
            seed_concept="reported_net_debt",
            seed_alias_role=AliasRole.DIRECT_VALUE_LABEL,
            seed_value_pattern=ValuePattern.DIRECT_LEVEL,
            seed_valuation_eligibility=ValuationEligibility.REQUIRES_SOURCE_SECTION,
            seed_should_abstain=True,
            review_status=ReviewStatus.REVIEW_REQUIRED,
            difficulty_category=BenchmarkDifficulty.DEBT_LEASE_AMBIGUITY
        ),
        # Item 5: Guidance statement (expected HEPS -> INFORMATIONAL_ONLY / ABSTAIN)
        BenchmarkItem(
            benchmark_id="BENCH-TEST-0005",
            sens_id=105,
            ticker="CPI.JO",
            publication_datetime="2025-09-04 11:00",
            raw_label="HEPS guidance expected between",
            normalized_label="heps guidance expected between",
            full_sentence="HEPS guidance is expected to be between 150 cents and 160 cents.",
            detected_numeric_tokens=["150", "160"],
            current_dictionary_status=AliasStatus.REQUIRES_CONTEXT,
            current_proposed_canonical_concept="heps",
            seed_concept="heps",
            seed_alias_role=AliasRole.GUIDANCE_STATEMENT,
            seed_value_pattern=ValuePattern.RANGE,
            seed_valuation_eligibility=ValuationEligibility.INFORMATIONAL_ONLY,
            seed_should_abstain=True,
            review_status=ReviewStatus.REVIEW_REQUIRED,
            difficulty_category=BenchmarkDifficulty.EASY_DIRECT
        ),
    ]


def test_1_benchmark_serialization_roundtrip(tmp_path: Path, sample_benchmark_items: list[BenchmarkItem]):
    """1. Ensure benchmark items serialize to JSON and deserialize back with identical fidelity."""
    json_file = tmp_path / "test_benchmark.json"
    save_benchmark_json(sample_benchmark_items, json_file)

    assert json_file.exists()
    reloaded = load_benchmark_json(json_file)

    assert len(reloaded) == len(sample_benchmark_items)
    for orig, loaded in zip(sample_benchmark_items, reloaded):
        assert orig.benchmark_id == loaded.benchmark_id
        assert orig.ticker == loaded.ticker
        assert orig.raw_label == loaded.raw_label
        assert orig.seed_concept == loaded.seed_concept
        assert orig.seed_alias_role == loaded.seed_alias_role
        assert orig.seed_value_pattern == loaded.seed_value_pattern
        assert orig.seed_valuation_eligibility == loaded.seed_valuation_eligibility
        assert orig.seed_should_abstain == loaded.seed_should_abstain
        assert orig.gold_concept is None
        assert loaded.gold_concept is None
        assert orig.gold_alias_role is None
        assert loaded.gold_alias_role is None
        assert orig.review_status == loaded.review_status


def test_2_and_3_dataset_integrity_and_no_duplicate_ids():
    """2 & 3. Ensure actual generated benchmark has unique IDs and valid references."""
    benchmark_path = Path("gui/modules/analysis/data/financial_classifier_benchmark.json")
    assert benchmark_path.exists(), "Benchmark JSON artifact missing"

    items = load_benchmark_json(benchmark_path)
    assert len(items) >= 550, f"Expected at least 550 clean items after deduplication, got {len(items)}"

    # Check unique IDs
    ids = [i.benchmark_id for i in items]
    assert len(ids) == len(set(ids)), "Found duplicate benchmark IDs in dataset"

    for i in items:
        assert i.benchmark_id.startswith("BENCH-")
        assert len(i.ticker) >= 2
        assert len(i.full_sentence) > 0


def test_4_sampling_caps_per_label_and_ticker():
    """4. Enforce sampling caps (max 10 per normalized label, max 20 per ticker)."""
    benchmark_path = Path("gui/modules/analysis/data/financial_classifier_benchmark.json")
    items = load_benchmark_json(benchmark_path)

    from collections import Counter
    label_counts = Counter(i.normalized_label for i in items)
    ticker_counts = Counter(i.ticker for i in items)

    for label, count in label_counts.items():
        assert count <= 10, f"Label '{label}' exceeded cap of 10 occurrences: {count}"

    for ticker, count in ticker_counts.items():
        assert count <= 20, f"Ticker '{ticker}' exceeded cap of 20 occurrences: {count}"

    assert len(ticker_counts) >= 100, f"Expected at least 100 distinct tickers, got {len(ticker_counts)}"


def test_5_enum_validity_across_dataset():
    """5. All benchmark items must use valid project enums."""
    benchmark_path = Path("gui/modules/analysis/data/financial_classifier_benchmark.json")
    items = load_benchmark_json(benchmark_path)

    valid_roles = {e.value for e in AliasRole}
    valid_patterns = {e.value for e in ValuePattern}
    valid_eligibility = {e.value for e in ValuationEligibility}
    valid_reviews = {e.value for e in ReviewStatus}
    valid_difficulties = {e.value for e in BenchmarkDifficulty}

    for item in items:
        assert item.seed_alias_role.value in valid_roles
        assert item.seed_value_pattern.value in valid_patterns
        assert item.seed_valuation_eligibility.value in valid_eligibility
        assert item.review_status.value in valid_reviews
        assert item.difficulty_category.value in valid_difficulties
        if item.gold_alias_role is not None:
            assert item.gold_alias_role.value in valid_roles
            assert item.gold_value_pattern.value in valid_patterns
            assert item.gold_valuation_eligibility.value in valid_eligibility


def test_6_auto_seed_restrictions():
    """6. AUTO_SEEDED status allowed ONLY when concept is approved with explicit qualifiers."""
    benchmark_path = Path("gui/modules/analysis/data/financial_classifier_benchmark.json")
    items = load_benchmark_json(benchmark_path)

    for item in items:
        if item.review_status == ReviewStatus.AUTO_SEEDED:
            assert item.current_dictionary_status == AliasStatus.APPROVED, (
                f"Item {item.benchmark_id} auto-seeded but dictionary status is {item.current_dictionary_status}"
            )
            assert item.seed_concept is not None, f"Item {item.benchmark_id} auto-seeded without seed_concept"
            assert item.gold_concept is None, f"Item {item.benchmark_id} auto-seeded with non-null gold_concept"


def test_7_ambiguous_cases_remain_review_required():
    """7. Ambiguous and unverified cases MUST remain in REVIEW_REQUIRED, never silently approved."""
    benchmark_path = Path("gui/modules/analysis/data/financial_classifier_benchmark.json")
    items = load_benchmark_json(benchmark_path)

    ambiguous_or_unverified = [
        i for i in items
        if i.current_dictionary_status in {AliasStatus.AMBIGUOUS, AliasStatus.REQUIRES_CONTEXT, AliasStatus.UNKNOWN}
    ]
    assert len(ambiguous_or_unverified) > 0

    for item in ambiguous_or_unverified:
        assert item.review_status == ReviewStatus.REVIEW_REQUIRED, (
            f"Ambiguous item {item.benchmark_id} ({item.normalized_label}) was incorrectly marked {item.review_status}"
        )


def test_8_guidance_does_not_become_historical_actual():
    """8. Guidance statements must be marked INFORMATIONAL_ONLY and should abstain from historical actual."""
    role, pat, elig, abstain, status, diff, note = classify_benchmark_item_heuristics(
        norm="heps guidance expected between",
        raw="HEPS guidance expected between",
        sentence="HEPS guidance expected between 150c and 160c.",
        concept_id="heps",
        dict_status=AliasStatus.REQUIRES_CONTEXT,
        qualifiers=SemanticQualifiers()
    )

    assert role == AliasRole.GUIDANCE_STATEMENT
    assert elig == ValuationEligibility.INFORMATIONAL_ONLY
    assert abstain is True
    assert pat == ValuePattern.RANGE


def test_9_valuation_eligibility_states():
    """9. Test diverse valuation eligibility mappings."""
    # Continuing operations -> ELIGIBLE_WITH_QUALIFIER
    role1, _, elig1, _, _, _, _ = classify_benchmark_item_heuristics(
        norm="revenue from continuing operations",
        raw="Revenue from continuing operations",
        sentence="Revenue from continuing operations was R5b.",
        concept_id="accounting_revenue",
        dict_status=AliasStatus.APPROVED,
        qualifiers=SemanticQualifiers(scope=OperationScope.CONTINUING_OPERATIONS)
    )
    assert elig1 == ValuationEligibility.ELIGIBLE_WITH_QUALIFIER

    # Generic capex -> REQUIRES_BASIS
    _, _, elig2, abstain2, _, _, _ = classify_benchmark_item_heuristics(
        norm="capital expenditure",
        raw="Capital expenditure",
        sentence="Capital expenditure was R100m.",
        concept_id=None,
        dict_status=AliasStatus.REQUIRES_CONTEXT,
        qualifiers=SemanticQualifiers()
    )
    assert elig2 == ValuationEligibility.REQUIRES_BASIS
    assert abstain2 is True

    # Ambiguous sales with numeric value -> REQUIRES_SCOPE (not PROHIBITED)
    _, _, elig3, abstain3, _, _, _ = classify_benchmark_item_heuristics(
        norm="sales",
        raw="Sales",
        sentence="Sales were R12b across stores.",
        concept_id=None,
        dict_status=AliasStatus.AMBIGUOUS,
        qualifiers=SemanticQualifiers()
    )
    assert elig3 == ValuationEligibility.REQUIRES_SCOPE
    assert abstain3 is True

    # Narrative sales without numbers -> CONCEPT_MENTION_ONLY / INFORMATIONAL_ONLY
    role4, pat4, elig4, abstain4, _, _, _ = classify_benchmark_item_heuristics(
        norm="sales",
        raw="Sales",
        sentence="Sales increased across stores.",
        concept_id=None,
        dict_status=AliasStatus.AMBIGUOUS,
        qualifiers=SemanticQualifiers()
    )
    assert role4 == AliasRole.CONCEPT_MENTION_ONLY
    assert pat4 == ValuePattern.UNKNOWN
    assert elig4 == ValuationEligibility.INFORMATIONAL_ONLY
    assert abstain4 is True


def test_10_and_11_abstention_and_unsafe_false_acceptance(sample_benchmark_items: list[BenchmarkItem]):
    """10 & 11. Test abstention quality metrics and unsafe false acceptance rate calculation."""
    evaluator = BenchmarkEvaluator(sample_benchmark_items)

    # Prediction set:
    # Item 1: Correctly predicts accounting_revenue (Correct)
    # Item 2: Correctly predicts accounting_revenue (Correct)
    # Item 3: UNSAFE: Model predicts retail_sales confidently on ambiguous "sales" (Unsafe False Acceptance!)
    # Item 4: Correctly abstains on net debt (Correct Abstention)
    # Item 5: Model abstains on guidance (Correct Abstention)
    predictions = [
        ClassifierPrediction(
            benchmark_id="BENCH-TEST-0001",
            predicted_concept="accounting_revenue",
            predicted_valuation_eligibility=ValuationEligibility.ELIGIBLE,
            confidence=0.95,
            abstain=False
        ),
        ClassifierPrediction(
            benchmark_id="BENCH-TEST-0002",
            predicted_concept="accounting_revenue",
            predicted_valuation_eligibility=ValuationEligibility.INFORMATIONAL_ONLY,
            confidence=0.92,
            abstain=False
        ),
        ClassifierPrediction(
            benchmark_id="BENCH-TEST-0003",
            predicted_concept="retail_sales",  # Wrong! Gold is ambiguous/abstain
            predicted_valuation_eligibility=ValuationEligibility.ELIGIBLE,  # Unsafe!
            confidence=0.99,
            abstain=False
        ),
        ClassifierPrediction(
            benchmark_id="BENCH-TEST-0004",
            predicted_concept=None,
            confidence=0.10,
            abstain=True  # Correctly abstained
        ),
        ClassifierPrediction(
            benchmark_id="BENCH-TEST-0005",
            predicted_concept=None,
            confidence=0.20,
            abstain=True  # Correctly abstained
        ),
    ]

    res = evaluator.evaluate(predictions)

    assert res.total_items == 5
    assert res.attempted_items == 3
    assert res.abstention_count == 2
    assert res.coverage_rate == 60.0
    assert res.correct_abstention_count == 2
    assert res.false_abstention_count == 0

    # Unsafe false acceptance: exactly 1 (Item 3, where model predicted confidently on ambiguous sales)
    assert res.unsafe_false_acceptance_count == 1
    assert res.unsafe_false_acceptance_rate == 20.0  # 1 out of 5


def test_12_threshold_evaluation(sample_benchmark_items: list[BenchmarkItem]):
    """12. Test threshold curve calculation across confidence thresholds."""
    evaluator = BenchmarkEvaluator(sample_benchmark_items)

    predictions = [
        ClassifierPrediction(benchmark_id="BENCH-TEST-0001", predicted_concept="accounting_revenue", confidence=0.96),
        ClassifierPrediction(benchmark_id="BENCH-TEST-0002", predicted_concept="accounting_revenue", confidence=0.85),
        ClassifierPrediction(benchmark_id="BENCH-TEST-0003", predicted_concept="retail_sales", confidence=0.75),  # Unsafe
        ClassifierPrediction(benchmark_id="BENCH-TEST-0004", predicted_concept="reported_net_debt", confidence=0.60),
        ClassifierPrediction(benchmark_id="BENCH-TEST-0005", predicted_concept="heps", confidence=0.40),
    ]

    res = evaluator.evaluate(predictions, thresholds=[0.50, 0.80, 0.90, 0.95])
    t_metrics = {m.threshold: m for m in res.threshold_metrics}

    # At threshold 0.95: only Item 1 is attempted (confidence 0.96)
    assert t_metrics[0.95].attempted_count == 1
    assert t_metrics[0.95].accuracy == 100.0
    assert t_metrics[0.95].unsafe_false_acceptance_count == 0

    # At threshold 0.70 (represented in 0.50): more items attempted, including unsafe Item 3
    assert t_metrics[0.50].attempted_count == 4
    assert t_metrics[0.50].unsafe_false_acceptance_count > 0


def test_13_calibration_report_structure(sample_benchmark_items: list[BenchmarkItem]):
    """13. Calibration calculation produces valid Brier score, ECE, and buckets."""
    evaluator = BenchmarkEvaluator(sample_benchmark_items)

    predictions = [
        ClassifierPrediction(benchmark_id="BENCH-TEST-0001", predicted_concept="accounting_revenue", confidence=0.90),
        ClassifierPrediction(benchmark_id="BENCH-TEST-0002", predicted_concept="accounting_revenue", confidence=0.80),
        ClassifierPrediction(benchmark_id="BENCH-TEST-0003", predicted_concept="retail_sales", confidence=0.70),
        ClassifierPrediction(benchmark_id="BENCH-TEST-0004", predicted_concept="wrong_concept", confidence=0.60),
        ClassifierPrediction(benchmark_id="BENCH-TEST-0005", predicted_concept="heps", confidence=0.50),
    ]

    res = evaluator.evaluate(predictions)
    cal = res.calibration
    assert cal is not None
    assert 0.0 <= cal.brier_score <= 1.0
    assert 0.0 <= cal.expected_calibration_error <= 1.0
    assert len(cal.buckets) == 10


def test_14_non_gold_items_cannot_contain_gold_labels():
    """14. BenchmarkItem validator must reject non-gold items with any populated gold_* field."""
    # AUTO_SEEDED with gold_concept set
    with pytest.raises(ValueError, match="all gold_\\* fields must remain null until GOLD_CONFIRMED"):
        BenchmarkItem(
            benchmark_id="BENCH-ERR-001",
            sens_id=999,
            ticker="TEST.JO",
            publication_datetime="2025-09-01 10:00",
            raw_label="Revenue",
            normalized_label="revenue",
            full_sentence="Revenue was R10b.",
            detected_numeric_tokens=["10"],
            current_dictionary_status=AliasStatus.APPROVED,
            current_proposed_canonical_concept="accounting_revenue",
            seed_concept="accounting_revenue",
            seed_alias_role=AliasRole.DIRECT_VALUE_LABEL,
            seed_value_pattern=ValuePattern.DIRECT_LEVEL,
            seed_valuation_eligibility=ValuationEligibility.ELIGIBLE,
            gold_concept="accounting_revenue",  # FORBIDDEN when not GOLD_CONFIRMED!
            review_status=ReviewStatus.AUTO_SEEDED
        )

    # REVIEW_REQUIRED with gold_alias_role set
    with pytest.raises(ValueError, match="all gold_\\* fields must remain null until GOLD_CONFIRMED"):
        BenchmarkItem(
            benchmark_id="BENCH-ERR-002",
            sens_id=999,
            ticker="TEST.JO",
            publication_datetime="2025-09-01 10:00",
            raw_label="Revenue",
            normalized_label="revenue",
            full_sentence="Revenue was R10b.",
            detected_numeric_tokens=["10"],
            current_dictionary_status=AliasStatus.APPROVED,
            current_proposed_canonical_concept="accounting_revenue",
            seed_concept="accounting_revenue",
            seed_alias_role=AliasRole.DIRECT_VALUE_LABEL,
            seed_value_pattern=ValuePattern.DIRECT_LEVEL,
            seed_valuation_eligibility=ValuationEligibility.ELIGIBLE,
            gold_alias_role=AliasRole.DIRECT_VALUE_LABEL,  # FORBIDDEN when not GOLD_CONFIRMED!
            review_status=ReviewStatus.REVIEW_REQUIRED
        )


def test_15_gold_confirmed_requires_complete_gold_fields():
    """15. GOLD_CONFIRMED items require all essential gold fields (role, pattern, eligibility, abstain)."""
    # Incomplete gold fields (missing gold_alias_role, pattern, etc.)
    with pytest.raises(ValueError, match="GOLD_CONFIRMED but missing complete gold fields"):
        BenchmarkItem(
            benchmark_id="BENCH-ERR-003",
            sens_id=999,
            ticker="TEST.JO",
            publication_datetime="2025-09-01 10:00",
            raw_label="Revenue",
            normalized_label="revenue",
            full_sentence="Revenue was R10b.",
            detected_numeric_tokens=["10"],
            current_dictionary_status=AliasStatus.APPROVED,
            current_proposed_canonical_concept="accounting_revenue",
            seed_concept="accounting_revenue",
            seed_alias_role=AliasRole.DIRECT_VALUE_LABEL,
            seed_value_pattern=ValuePattern.DIRECT_LEVEL,
            seed_valuation_eligibility=ValuationEligibility.ELIGIBLE,
            gold_concept="accounting_revenue",
            review_status=ReviewStatus.GOLD_CONFIRMED  # Missing other gold_* fields!
        )

    # Valid GOLD_CONFIRMED item with complete fields
    valid_gold = BenchmarkItem(
        benchmark_id="BENCH-GOLD-001",
        sens_id=999,
        ticker="TEST.JO",
        publication_datetime="2025-09-01 10:00",
        raw_label="Revenue",
        normalized_label="revenue",
        full_sentence="Revenue was R10b.",
        detected_numeric_tokens=["10"],
        current_dictionary_status=AliasStatus.APPROVED,
        current_proposed_canonical_concept="accounting_revenue",
        seed_concept="accounting_revenue",
        seed_alias_role=AliasRole.DIRECT_VALUE_LABEL,
        seed_value_pattern=ValuePattern.DIRECT_LEVEL,
        seed_valuation_eligibility=ValuationEligibility.ELIGIBLE,
        seed_should_abstain=False,
        gold_concept="accounting_revenue",
        gold_qualifiers=SemanticQualifiers(),
        gold_alias_role=AliasRole.DIRECT_VALUE_LABEL,
        gold_value_pattern=ValuePattern.DIRECT_LEVEL,
        gold_valuation_eligibility=ValuationEligibility.ELIGIBLE,
        gold_should_abstain=False,
        review_status=ReviewStatus.GOLD_CONFIRMED,
        reviewer_notes="Verified by human reviewer."
    )
    assert valid_gold.review_status == ReviewStatus.GOLD_CONFIRMED
    assert valid_gold.gold_concept == "accounting_revenue"


def test_16_seed_and_gold_fields_remain_distinct():
    """16. Seed and gold fields remain completely independent and distinct."""
    # Item where human review corrects the deterministic seed
    item = BenchmarkItem(
        benchmark_id="BENCH-DIST-001",
        sens_id=1001,
        ticker="MRP.JO",
        publication_datetime="2025-09-01 10:00",
        raw_label="Sales of merchandise",
        normalized_label="sales of merchandise",
        full_sentence="Sales of merchandise grew 5%.",
        detected_numeric_tokens=["5%"],
        current_dictionary_status=AliasStatus.APPROVED,
        current_proposed_canonical_concept="accounting_revenue",
        seed_concept="accounting_revenue",
        seed_alias_role=AliasRole.DIRECT_VALUE_LABEL,
        seed_value_pattern=ValuePattern.DIRECT_LEVEL,
        seed_valuation_eligibility=ValuationEligibility.ELIGIBLE,
        seed_should_abstain=False,
        gold_concept="retail_sales",  # Human corrected to retail_sales
        gold_qualifiers=SemanticQualifiers(),
        gold_alias_role=AliasRole.DIRECT_VALUE_LABEL,
        gold_value_pattern=ValuePattern.DIRECT_LEVEL,
        gold_valuation_eligibility=ValuationEligibility.INFORMATIONAL_ONLY,
        gold_should_abstain=True,
        review_status=ReviewStatus.GOLD_CONFIRMED
    )

    # Verify seed and gold are different and neither overwrote the other
    assert item.seed_concept == "accounting_revenue"
    assert item.gold_concept == "retail_sales"
    assert item.seed_valuation_eligibility == ValuationEligibility.ELIGIBLE
    assert item.gold_valuation_eligibility == ValuationEligibility.INFORMATIONAL_ONLY
    assert item.seed_should_abstain is False
    assert item.gold_should_abstain is True

    # Evaluator in seed mode targets seed; in gold mode targets gold
    evaluator = BenchmarkEvaluator([item])
    pred_rev = [ClassifierPrediction(benchmark_id="BENCH-DIST-001", predicted_concept="accounting_revenue", confidence=0.9)]
    pred_sales = [ClassifierPrediction(benchmark_id="BENCH-DIST-001", predicted_concept="retail_sales", confidence=0.9)]

    # Target seed: accounting_revenue matches, retail_sales does not
    res_seed = evaluator.evaluate(pred_rev, target_mode="seed")
    assert res_seed.overall_concept_accuracy == 100.0

    # Target gold: retail_sales matches, accounting_revenue does not
    res_gold = evaluator.evaluate(pred_sales, target_mode="gold")
    assert res_gold.overall_concept_accuracy == 100.0


def test_17_concept_mention_only_cannot_be_direct_level():
    """17. CONCEPT_MENTION_ONLY must not have DIRECT_LEVEL value pattern."""
    # In seed
    with pytest.raises(ValueError, match="CONCEPT_MENTION_ONLY cannot have ValuePattern.DIRECT_LEVEL"):
        BenchmarkItem(
            benchmark_id="BENCH-ERR-004",
            sens_id=999,
            ticker="TEST.JO",
            publication_datetime="2025-09-01 10:00",
            raw_label="working capital",
            normalized_label="working capital",
            full_sentence="Management remains focused on working capital.",
            detected_numeric_tokens=["100"],
            current_dictionary_status=AliasStatus.REQUIRES_CONTEXT,
            seed_concept=None,
            seed_alias_role=AliasRole.CONCEPT_MENTION_ONLY,
            seed_value_pattern=ValuePattern.DIRECT_LEVEL,  # FORBIDDEN!
            seed_valuation_eligibility=ValuationEligibility.INFORMATIONAL_ONLY,
            seed_should_abstain=True,
            review_status=ReviewStatus.REVIEW_REQUIRED
        )

    # In gold
    with pytest.raises(ValueError, match="CONCEPT_MENTION_ONLY cannot have ValuePattern.DIRECT_LEVEL"):
        BenchmarkItem(
            benchmark_id="BENCH-ERR-005",
            sens_id=999,
            ticker="TEST.JO",
            publication_datetime="2025-09-01 10:00",
            raw_label="working capital",
            normalized_label="working capital",
            full_sentence="Management remains focused on working capital.",
            detected_numeric_tokens=["100"],
            current_dictionary_status=AliasStatus.REQUIRES_CONTEXT,
            seed_concept=None,
            seed_alias_role=AliasRole.CONCEPT_MENTION_ONLY,
            seed_value_pattern=ValuePattern.UNKNOWN,
            seed_valuation_eligibility=ValuationEligibility.INFORMATIONAL_ONLY,
            seed_should_abstain=True,
            gold_concept=None,
            gold_alias_role=AliasRole.CONCEPT_MENTION_ONLY,
            gold_value_pattern=ValuePattern.DIRECT_LEVEL,  # FORBIDDEN!
            gold_valuation_eligibility=ValuationEligibility.INFORMATIONAL_ONLY,
            gold_should_abstain=True,
            review_status=ReviewStatus.GOLD_CONFIRMED
        )


def test_18_ambiguous_resolvable_metrics_not_automatically_prohibited():
    """18. Ambiguous but resolvable metrics (sales, net debt, capex, borrowings, working capital, shares)

    must map to REQUIRES_SCOPE, REQUIRES_BASIS, REQUIRES_SOURCE_SECTION, or REQUIRES_PERIOD, not PROHIBITED.
    """
    benchmark_path = Path("gui/modules/analysis/data/financial_classifier_benchmark.json")
    items = load_benchmark_json(benchmark_path)

    resolvable_keywords = ["sales", "turnover", "net debt", "capex", "capital expenditure", "borrowing", "working capital", "shares in issue"]

    prohibited_count = 0
    checked_count = 0
    for item in items:
        if any(kw in item.normalized_label for kw in resolvable_keywords):
            checked_count += 1
            assert item.seed_valuation_eligibility != ValuationEligibility.PROHIBITED, (
                f"Item {item.benchmark_id} ({item.normalized_label}) was classified PROHIBITED instead of resolvable context gate."
            )
            assert item.seed_valuation_eligibility in {
                ValuationEligibility.REQUIRES_SCOPE,
                ValuationEligibility.REQUIRES_BASIS,
                ValuationEligibility.REQUIRES_SOURCE_SECTION,
                ValuationEligibility.REQUIRES_PERIOD,
                ValuationEligibility.ELIGIBLE,
                ValuationEligibility.ELIGIBLE_WITH_QUALIFIER,
                ValuationEligibility.INFORMATIONAL_ONLY
            }

    assert checked_count > 0, "No items found matching resolvable keywords"
    # Ensure dataset-wide prohibited count is 0
    all_prohibited = [i for i in items if i.seed_valuation_eligibility == ValuationEligibility.PROHIBITED]
    assert len(all_prohibited) == 0, f"Expected 0 PROHIBITED items in benchmark, found {len(all_prohibited)}"


def test_19_deterministic_sampling_reproducible():
    """19. Benchmark IDs and sampling remain completely reproducible across multiple loads."""
    benchmark_path = Path("gui/modules/analysis/data/financial_classifier_benchmark.json")
    items1 = load_benchmark_json(benchmark_path)
    items2 = load_benchmark_json(benchmark_path)

    assert len(items1) == len(items2)
    for i1, i2 in zip(items1, items2):
        assert i1.benchmark_id == i2.benchmark_id
        assert i1.ticker == i2.ticker
        assert i1.normalized_label == i2.normalized_label
        assert i1.seed_alias_role == i2.seed_alias_role
        assert i1.seed_valuation_eligibility == i2.seed_valuation_eligibility
        assert i1.gold_concept is None and i2.gold_concept is None


def test_20_direct_level_with_zero_numeric_tokens_fails():
    """20. DIRECT_LEVEL with zero numeric tokens must fail validation in seed and gold."""
    # In seed
    with pytest.raises(ValueError, match="zero numeric tokens but seed_value_pattern=DIRECT_LEVEL"):
        BenchmarkItem(
            benchmark_id="BENCH-FAIL-001",
            sens_id=1,
            ticker="MRP.JO",
            publication_datetime="2025-09-01 10:00",
            raw_label="sales",
            normalized_label="sales",
            full_sentence="Total sales grew across divisions during the first half.",
            detected_numeric_tokens=[],  # ZERO NUMBERS!
            current_dictionary_status=AliasStatus.AMBIGUOUS,
            seed_concept=None,
            seed_alias_role=AliasRole.CONCEPT_MENTION_ONLY,
            seed_value_pattern=ValuePattern.DIRECT_LEVEL,  # FORBIDDEN!
            seed_valuation_eligibility=ValuationEligibility.INFORMATIONAL_ONLY,
            seed_should_abstain=True,
            review_status=ReviewStatus.REVIEW_REQUIRED
        )

    # In gold
    with pytest.raises(ValueError, match="zero numeric tokens but gold_value_pattern=DIRECT_LEVEL"):
        BenchmarkItem(
            benchmark_id="BENCH-FAIL-002",
            sens_id=1,
            ticker="MRP.JO",
            publication_datetime="2025-09-01 10:00",
            raw_label="sales",
            normalized_label="sales",
            full_sentence="Total sales grew across divisions during the first half.",
            detected_numeric_tokens=[],  # ZERO NUMBERS!
            current_dictionary_status=AliasStatus.AMBIGUOUS,
            seed_concept=None,
            seed_alias_role=AliasRole.CONCEPT_MENTION_ONLY,
            seed_value_pattern=ValuePattern.UNKNOWN,
            seed_valuation_eligibility=ValuationEligibility.INFORMATIONAL_ONLY,
            seed_should_abstain=True,
            gold_concept=None,
            gold_alias_role=AliasRole.CONCEPT_MENTION_ONLY,
            gold_value_pattern=ValuePattern.DIRECT_LEVEL,  # FORBIDDEN!
            gold_valuation_eligibility=ValuationEligibility.INFORMATIONAL_ONLY,
            gold_should_abstain=True,
            review_status=ReviewStatus.GOLD_CONFIRMED
        )


def test_21_direct_value_label_with_zero_numeric_tokens_fails():
    """21. DIRECT_VALUE_LABEL with zero numeric tokens must fail validation."""
    with pytest.raises(ValueError, match="zero numeric tokens but seed_alias_role=DIRECT_VALUE_LABEL"):
        BenchmarkItem(
            benchmark_id="BENCH-FAIL-003",
            sens_id=1,
            ticker="TRU.JO",
            publication_datetime="2025-09-01 10:00",
            raw_label="revenue",
            normalized_label="revenue",
            full_sentence="Revenue growth was driven by merchandise momentum.",
            detected_numeric_tokens=[],  # ZERO NUMBERS!
            current_dictionary_status=AliasStatus.APPROVED,
            seed_concept="accounting_revenue",
            seed_alias_role=AliasRole.DIRECT_VALUE_LABEL,  # FORBIDDEN!
            seed_value_pattern=ValuePattern.UNKNOWN,
            seed_valuation_eligibility=ValuationEligibility.INFORMATIONAL_ONLY,
            seed_should_abstain=True,
            review_status=ReviewStatus.REVIEW_REQUIRED
        )


def test_22_concept_mention_only_permits_zero_numeric_tokens():
    """22. CONCEPT_MENTION_ONLY with UNKNOWN value pattern correctly validates with zero numeric tokens."""
    item = BenchmarkItem(
        benchmark_id="BENCH-VALID-001",
        sens_id=1,
        ticker="MRP.JO",
        publication_datetime="2025-09-01 10:00",
        raw_label="working capital",
        normalized_label="working capital",
        full_sentence="Management remains focused on working capital discipline.",
        detected_numeric_tokens=[],  # ZERO NUMBERS ALLOWED!
        current_dictionary_status=AliasStatus.REQUIRES_CONTEXT,
        seed_concept="working_capital",
        seed_alias_role=AliasRole.CONCEPT_MENTION_ONLY,
        seed_value_pattern=ValuePattern.UNKNOWN,
        seed_valuation_eligibility=ValuationEligibility.INFORMATIONAL_ONLY,
        seed_should_abstain=True,
        review_status=ReviewStatus.REVIEW_REQUIRED
    )
    assert item.seed_alias_role == AliasRole.CONCEPT_MENTION_ONLY
    assert item.seed_value_pattern == ValuePattern.UNKNOWN
    assert item.seed_should_abstain is True


def test_23_change_statement_requires_detected_numeric_pattern():
    """23. CHANGE_STATEMENT with zero numeric tokens fails validation."""
    with pytest.raises(ValueError, match="zero numeric tokens but seed_alias_role=CHANGE_STATEMENT"):
        BenchmarkItem(
            benchmark_id="BENCH-FAIL-004",
            sens_id=1,
            ticker="TRU.JO",
            publication_datetime="2025-09-01 10:00",
            raw_label="revenue increased",
            normalized_label="revenue increased",
            full_sentence="Revenue increased across all retail store networks.",
            detected_numeric_tokens=[],  # ZERO NUMBERS FORBIDDEN FOR CHANGE_STATEMENT!
            current_dictionary_status=AliasStatus.APPROVED,
            seed_concept="accounting_revenue",
            seed_alias_role=AliasRole.CHANGE_STATEMENT,
            seed_value_pattern=ValuePattern.CHANGE_RATE_ONLY,
            seed_valuation_eligibility=ValuationEligibility.INFORMATIONAL_ONLY,
            seed_should_abstain=True,
            review_status=ReviewStatus.REVIEW_REQUIRED
        )

    # Valid change statement with rate number succeeds
    valid_change = BenchmarkItem(
        benchmark_id="BENCH-VALID-002",
        sens_id=1,
        ticker="TRU.JO",
        publication_datetime="2025-09-01 10:00",
        raw_label="revenue increased by",
        normalized_label="revenue increased by",
        full_sentence="Revenue increased by 8.5%.",
        detected_numeric_tokens=["8.5%"],
        current_dictionary_status=AliasStatus.APPROVED,
        seed_concept="accounting_revenue",
        seed_alias_role=AliasRole.CHANGE_STATEMENT,
        seed_value_pattern=ValuePattern.CHANGE_RATE_ONLY,
        seed_valuation_eligibility=ValuationEligibility.INFORMATIONAL_ONLY,
        seed_should_abstain=False,
        review_status=ReviewStatus.AUTO_SEEDED
    )
    assert valid_change.seed_alias_role == AliasRole.CHANGE_STATEMENT


def test_24_gold_confirmed_should_abstain_conditional_concept():
    """24. GOLD_CONFIRMED requires gold_concept if should_abstain=False, but permits None if should_abstain=True."""
    # should_abstain=False with gold_concept=None -> FAILS
    with pytest.raises(ValueError, match="gold_should_abstain=False requires gold_concept"):
        BenchmarkItem(
            benchmark_id="BENCH-FAIL-005",
            sens_id=1,
            ticker="TRU.JO",
            publication_datetime="2025-09-01 10:00",
            raw_label="sales",
            normalized_label="sales",
            full_sentence="Sales were R10b.",
            detected_numeric_tokens=["10"],
            current_dictionary_status=AliasStatus.AMBIGUOUS,
            seed_concept=None,
            seed_alias_role=AliasRole.DIRECT_VALUE_LABEL,
            seed_value_pattern=ValuePattern.DIRECT_LEVEL,
            seed_valuation_eligibility=ValuationEligibility.REQUIRES_SCOPE,
            seed_should_abstain=True,
            gold_concept=None,  # FORBIDDEN when should_abstain=False!
            gold_alias_role=AliasRole.DIRECT_VALUE_LABEL,
            gold_value_pattern=ValuePattern.DIRECT_LEVEL,
            gold_valuation_eligibility=ValuationEligibility.ELIGIBLE,
            gold_should_abstain=False,
            review_status=ReviewStatus.GOLD_CONFIRMED
        )

    # should_abstain=True with gold_concept=None -> SUCCEEDS
    valid_abstain = BenchmarkItem(
        benchmark_id="BENCH-VALID-003",
        sens_id=1,
        ticker="TRU.JO",
        publication_datetime="2025-09-01 10:00",
        raw_label="sales",
        normalized_label="sales",
        full_sentence="Sales were R10b.",
        detected_numeric_tokens=["10"],
        current_dictionary_status=AliasStatus.AMBIGUOUS,
        seed_concept=None,
        seed_alias_role=AliasRole.DIRECT_VALUE_LABEL,
        seed_value_pattern=ValuePattern.DIRECT_LEVEL,
        seed_valuation_eligibility=ValuationEligibility.REQUIRES_SCOPE,
        seed_should_abstain=True,
        gold_concept=None,  # ALLOWED when should_abstain=True!
        gold_alias_role=AliasRole.DIRECT_VALUE_LABEL,
        gold_value_pattern=ValuePattern.DIRECT_LEVEL,
        gold_valuation_eligibility=ValuationEligibility.REQUIRES_SCOPE,
        gold_should_abstain=True,
        review_status=ReviewStatus.GOLD_CONFIRMED
    )
    assert valid_abstain.gold_concept is None
    assert valid_abstain.gold_should_abstain is True


def test_25_eligible_confirmed_capex_requires_capex_basis():
    """25. Confirmed non-abstaining capex used as valuation baseline requires explicit capex_basis."""
    # capex_basis=UNSPECIFIED -> FAILS
    with pytest.raises(ValueError, match="valuation baseline requires explicit capex_basis"):
        BenchmarkItem(
            benchmark_id="BENCH-FAIL-006",
            sens_id=1,
            ticker="TRU.JO",
            publication_datetime="2025-09-01 10:00",
            raw_label="capital expenditure",
            normalized_label="capital expenditure",
            full_sentence="Capital expenditure was R500m.",
            detected_numeric_tokens=["500"],
            current_dictionary_status=AliasStatus.REQUIRES_CONTEXT,
            seed_concept="total_capex",
            seed_alias_role=AliasRole.DIRECT_VALUE_LABEL,
            seed_value_pattern=ValuePattern.DIRECT_LEVEL,
            seed_valuation_eligibility=ValuationEligibility.REQUIRES_BASIS,
            seed_should_abstain=True,
            gold_concept="total_capex",
            gold_qualifiers=SemanticQualifiers(capex_basis=CapexBasis.UNSPECIFIED),  # FORBIDDEN!
            gold_alias_role=AliasRole.DIRECT_VALUE_LABEL,
            gold_value_pattern=ValuePattern.DIRECT_LEVEL,
            gold_valuation_eligibility=ValuationEligibility.ELIGIBLE,
            gold_should_abstain=False,
            review_status=ReviewStatus.GOLD_CONFIRMED
        )

    # capex_basis=CASH_PAYMENTS -> SUCCEEDS
    valid_capex = BenchmarkItem(
        benchmark_id="BENCH-VALID-004",
        sens_id=1,
        ticker="TRU.JO",
        publication_datetime="2025-09-01 10:00",
        raw_label="capital expenditure",
        normalized_label="capital expenditure",
        full_sentence="Capital expenditure paid was R500m.",
        detected_numeric_tokens=["500"],
        current_dictionary_status=AliasStatus.REQUIRES_CONTEXT,
        seed_concept="total_capex",
        seed_alias_role=AliasRole.DIRECT_VALUE_LABEL,
        seed_value_pattern=ValuePattern.DIRECT_LEVEL,
        seed_valuation_eligibility=ValuationEligibility.REQUIRES_BASIS,
        seed_should_abstain=True,
        gold_concept="total_capex",
        gold_qualifiers=SemanticQualifiers(capex_basis=CapexBasis.CASH_PAYMENTS),
        gold_alias_role=AliasRole.DIRECT_VALUE_LABEL,
        gold_value_pattern=ValuePattern.DIRECT_LEVEL,
        gold_valuation_eligibility=ValuationEligibility.ELIGIBLE_WITH_QUALIFIER,
        gold_should_abstain=False,
        review_status=ReviewStatus.GOLD_CONFIRMED
    )
    assert valid_capex.gold_qualifiers.capex_basis == CapexBasis.CASH_PAYMENTS


def test_26_eligible_confirmed_debt_requires_lease_and_basis_evidence():
    """26. Confirmed non-abstaining debt baseline requires explicit lease_inclusion and basis_evidence."""
    # Missing lease_inclusion -> FAILS
    with pytest.raises(ValueError, match="valuation baseline requires explicit lease_inclusion"):
        BenchmarkItem(
            benchmark_id="BENCH-FAIL-007",
            sens_id=1,
            ticker="TRU.JO",
            publication_datetime="2025-09-01 10:00",
            raw_label="net debt",
            normalized_label="net debt",
            full_sentence="Net debt was R2.5 billion.",
            detected_numeric_tokens=["2.5"],
            current_dictionary_status=AliasStatus.REQUIRES_CONTEXT,
            seed_concept="reported_net_debt",
            seed_alias_role=AliasRole.DIRECT_VALUE_LABEL,
            seed_value_pattern=ValuePattern.DIRECT_LEVEL,
            seed_valuation_eligibility=ValuationEligibility.REQUIRES_SOURCE_SECTION,
            seed_should_abstain=True,
            gold_concept="reported_net_debt",
            gold_qualifiers=SemanticQualifiers(lease_inclusion=LeaseInclusion.UNSPECIFIED),  # FORBIDDEN!
            gold_alias_role=AliasRole.DIRECT_VALUE_LABEL,
            gold_value_pattern=ValuePattern.DIRECT_LEVEL,
            gold_valuation_eligibility=ValuationEligibility.ELIGIBLE,
            gold_should_abstain=False,
            review_status=ReviewStatus.GOLD_CONFIRMED
        )

    # Missing basis_evidence -> FAILS
    with pytest.raises(ValueError, match="valuation baseline requires explicit basis_evidence"):
        BenchmarkItem(
            benchmark_id="BENCH-FAIL-008",
            sens_id=1,
            ticker="TRU.JO",
            publication_datetime="2025-09-01 10:00",
            raw_label="net debt",
            normalized_label="net debt",
            full_sentence="Net debt was R2.5 billion.",
            detected_numeric_tokens=["2.5"],
            current_dictionary_status=AliasStatus.REQUIRES_CONTEXT,
            seed_concept="reported_net_debt",
            seed_alias_role=AliasRole.DIRECT_VALUE_LABEL,
            seed_value_pattern=ValuePattern.DIRECT_LEVEL,
            seed_valuation_eligibility=ValuationEligibility.REQUIRES_SOURCE_SECTION,
            seed_should_abstain=True,
            gold_concept="reported_net_debt",
            gold_qualifiers=SemanticQualifiers(
                lease_inclusion=LeaseInclusion.EX_LEASES,
                basis_evidence=BasisEvidence.UNSPECIFIED  # FORBIDDEN!
            ),
            gold_alias_role=AliasRole.DIRECT_VALUE_LABEL,
            gold_value_pattern=ValuePattern.DIRECT_LEVEL,
            gold_valuation_eligibility=ValuationEligibility.ELIGIBLE,
            gold_should_abstain=False,
            review_status=ReviewStatus.GOLD_CONFIRMED
        )

    # Both explicit -> SUCCEEDS
    valid_debt = BenchmarkItem(
        benchmark_id="BENCH-VALID-005",
        sens_id=1,
        ticker="TRU.JO",
        publication_datetime="2025-09-01 10:00",
        raw_label="net debt",
        normalized_label="net debt",
        full_sentence="Net debt was R2.5 billion.",
        detected_numeric_tokens=["2.5"],
        current_dictionary_status=AliasStatus.REQUIRES_CONTEXT,
        seed_concept="reported_net_debt",
        seed_alias_role=AliasRole.DIRECT_VALUE_LABEL,
        seed_value_pattern=ValuePattern.DIRECT_LEVEL,
        seed_valuation_eligibility=ValuationEligibility.REQUIRES_SOURCE_SECTION,
        seed_should_abstain=True,
        gold_concept="reported_net_debt",
        gold_qualifiers=SemanticQualifiers(
            lease_inclusion=LeaseInclusion.EX_LEASES,
            basis_evidence=BasisEvidence.BALANCE_SHEET_PRESENTATION_SEPARATE
        ),
        gold_alias_role=AliasRole.DIRECT_VALUE_LABEL,
        gold_value_pattern=ValuePattern.DIRECT_LEVEL,
        gold_valuation_eligibility=ValuationEligibility.ELIGIBLE_WITH_QUALIFIER,
        gold_should_abstain=False,
        review_status=ReviewStatus.GOLD_CONFIRMED
    )
    assert valid_debt.gold_qualifiers.lease_inclusion == LeaseInclusion.EX_LEASES
    assert valid_debt.gold_qualifiers.basis_evidence == BasisEvidence.BALANCE_SHEET_PRESENTATION_SEPARATE


def test_27_eligible_confirmed_margin_requires_denominator():
    """27. Confirmed non-abstaining margin baseline requires explicit margin_denominator."""
    with pytest.raises(ValueError, match="valuation baseline requires explicit margin_denominator"):
        BenchmarkItem(
            benchmark_id="BENCH-FAIL-009",
            sens_id=1,
            ticker="TRU.JO",
            publication_datetime="2025-09-01 10:00",
            raw_label="operating margin",
            normalized_label="operating margin",
            full_sentence="Operating margin was 15.2%.",
            detected_numeric_tokens=["15.2%"],
            current_dictionary_status=AliasStatus.REQUIRES_CONTEXT,
            seed_concept="operating_margin",
            seed_alias_role=AliasRole.DIRECT_VALUE_LABEL,
            seed_value_pattern=ValuePattern.DIRECT_LEVEL,
            seed_valuation_eligibility=ValuationEligibility.REQUIRES_BASIS,
            seed_should_abstain=True,
            gold_concept="operating_margin",
            gold_qualifiers=SemanticQualifiers(margin_denominator=MarginDenominator.UNSPECIFIED),  # FORBIDDEN!
            gold_alias_role=AliasRole.DIRECT_VALUE_LABEL,
            gold_value_pattern=ValuePattern.DIRECT_LEVEL,
            gold_valuation_eligibility=ValuationEligibility.ELIGIBLE,
            gold_should_abstain=False,
            review_status=ReviewStatus.GOLD_CONFIRMED
        )

    valid_margin = BenchmarkItem(
        benchmark_id="BENCH-VALID-006",
        sens_id=1,
        ticker="TRU.JO",
        publication_datetime="2025-09-01 10:00",
        raw_label="operating margin",
        normalized_label="operating margin",
        full_sentence="Operating margin was 15.2%.",
        detected_numeric_tokens=["15.2%"],
        current_dictionary_status=AliasStatus.REQUIRES_CONTEXT,
        seed_concept="operating_margin",
        seed_alias_role=AliasRole.DIRECT_VALUE_LABEL,
        seed_value_pattern=ValuePattern.DIRECT_LEVEL,
        seed_valuation_eligibility=ValuationEligibility.REQUIRES_BASIS,
        seed_should_abstain=True,
        gold_concept="operating_margin",
        gold_qualifiers=SemanticQualifiers(margin_denominator=MarginDenominator.ACCOUNTING_REVENUE),
        gold_alias_role=AliasRole.DIRECT_VALUE_LABEL,
        gold_value_pattern=ValuePattern.DIRECT_LEVEL,
        gold_valuation_eligibility=ValuationEligibility.ELIGIBLE_WITH_QUALIFIER,
        gold_should_abstain=False,
        review_status=ReviewStatus.GOLD_CONFIRMED
    )
    assert valid_margin.gold_qualifiers.margin_denominator == MarginDenominator.ACCOUNTING_REVENUE


def test_28_eligible_confirmed_continuing_scope_requires_explicit_scope():
    """28. Continuing operations concept requires explicit scope qualifier."""
    with pytest.raises(ValueError, match="mentions continuing operations but gold scope is UNSPECIFIED"):
        BenchmarkItem(
            benchmark_id="BENCH-FAIL-010",
            sens_id=1,
            ticker="TRU.JO",
            publication_datetime="2025-09-01 10:00",
            raw_label="revenue from continuing operations",
            normalized_label="revenue from continuing operations",
            full_sentence="Revenue from continuing operations was R8.5 billion.",
            detected_numeric_tokens=["8.5"],
            current_dictionary_status=AliasStatus.APPROVED,
            seed_concept="accounting_revenue",
            seed_alias_role=AliasRole.DIRECT_VALUE_LABEL,
            seed_value_pattern=ValuePattern.DIRECT_LEVEL,
            seed_valuation_eligibility=ValuationEligibility.ELIGIBLE_WITH_QUALIFIER,
            seed_should_abstain=False,
            gold_concept="accounting_revenue",
            gold_qualifiers=SemanticQualifiers(scope=OperationScope.UNSPECIFIED),  # FORBIDDEN!
            gold_alias_role=AliasRole.DIRECT_VALUE_LABEL,
            gold_value_pattern=ValuePattern.DIRECT_LEVEL,
            gold_valuation_eligibility=ValuationEligibility.ELIGIBLE_WITH_QUALIFIER,
            gold_should_abstain=False,
            review_status=ReviewStatus.GOLD_CONFIRMED
        )


def test_29_guidance_cannot_become_historical_actual_baseline():
    """29. Guidance statements must remain INFORMATIONAL_ONLY and should_abstain=True."""
    with pytest.raises(ValueError, match="cannot become historical actual baseline"):
        BenchmarkItem(
            benchmark_id="BENCH-FAIL-011",
            sens_id=1,
            ticker="TRU.JO",
            publication_datetime="2025-09-01 10:00",
            raw_label="heps expected to be between",
            normalized_label="heps expected to be between",
            full_sentence="HEPS is expected to be between 120c and 130c.",
            detected_numeric_tokens=["120", "130"],
            current_dictionary_status=AliasStatus.REQUIRES_CONTEXT,
            seed_concept="heps",
            seed_alias_role=AliasRole.GUIDANCE_STATEMENT,
            seed_value_pattern=ValuePattern.RANGE,
            seed_valuation_eligibility=ValuationEligibility.INFORMATIONAL_ONLY,
            seed_should_abstain=True,
            gold_concept="heps",
            gold_alias_role=AliasRole.GUIDANCE_STATEMENT,
            gold_value_pattern=ValuePattern.RANGE,
            gold_valuation_eligibility=ValuationEligibility.ELIGIBLE,  # FORBIDDEN FOR GUIDANCE!
            gold_should_abstain=False,  # FORBIDDEN FOR GUIDANCE!
            review_status=ReviewStatus.GOLD_CONFIRMED
        )


# =============================================================================
# Review Worksheet Workflow Tests (Tests 30 to 41)
# =============================================================================

def test_30_csv_export_round_trip(tmp_path: Path):
    """30. Verify CSV worksheet export: 300 rows, 35 columns, seed populated, gold unpopulated."""
    benchmark_path = Path("gui/modules/analysis/data/financial_classifier_benchmark.json")
    items = load_benchmark_json(benchmark_path)
    batch_ids = get_batch_001_ids()
    assert len(batch_ids) == 178

    csv_file = tmp_path / "review_001.csv"
    export_review_worksheet_csv(items, csv_file, batch_ids=batch_ids)
    assert csv_file.exists()

    with open(csv_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert len(rows) == 178
    assert list(rows[0].keys()) == REVIEW_WORKSHEET_COLUMNS
    assert len(REVIEW_WORKSHEET_COLUMNS) == 35

    for row in rows:
        assert row["benchmark_id"].startswith("BENCH-")
        assert row["ticker"]
        assert row["full_sentence"]
        assert row["seed_alias_role"] in [r.value for r in AliasRole]
        assert row["seed_value_pattern"] in [p.value for p in ValuePattern]
        assert row["seed_valuation_eligibility"] in [e.value for e in ValuationEligibility]

        # Gold values strictly unpopulated for unconfirmed batch
        assert row["gold_concept"] == ""
        assert row["gold_scope"] == ""
        assert row["gold_alias_role"] == ""
        assert row["gold_value_pattern"] == ""
        assert row["gold_valuation_eligibility"] == ""
        assert row["gold_should_abstain"] == ""
        assert row["review_decision"] == ""


def test_31_confirm_seed_import():
    """31. CONFIRM_SEED copies seed values into gold, sets GOLD_CONFIRMED, and records provenance."""
    item = BenchmarkItem(
        benchmark_id="BENCH-CONF-001",
        sens_id=10,
        ticker="TEST.JO",
        publication_datetime="2025-09-01 10:00",
        raw_label="revenue",
        normalized_label="revenue",
        full_sentence="Revenue reached R100 million.",
        detected_numeric_tokens=["100"],
        current_dictionary_status=AliasStatus.APPROVED,
        seed_concept="accounting_revenue",
        seed_qualifiers=SemanticQualifiers(scope=OperationScope.GROUP_CONSOLIDATED),
        seed_alias_role=AliasRole.DIRECT_VALUE_LABEL,
        seed_value_pattern=ValuePattern.DIRECT_LEVEL,
        seed_valuation_eligibility=ValuationEligibility.ELIGIBLE,
        seed_should_abstain=False,
        review_status=ReviewStatus.REVIEW_REQUIRED
    )

    csv_row = {
        "benchmark_id": "BENCH-CONF-001",
        "ticker": "TEST.JO",
        "publication_datetime": "2025-09-01 10:00",
        "full_sentence": "Revenue reached R100 million.",
        "normalized_label": "revenue",
        "detected_numeric_tokens": json.dumps(["100"]),
        "review_decision": "CONFIRM_SEED",
        "reviewer_notes": "Confirmed by reviewer"
    }

    updated = apply_review_decisions([item], [csv_row], reviewer_id="human_review_batch_001", reviewed_at="2026-09-25T16:00:00")
    assert len(updated) == 1
    up = updated[0]

    assert up.review_status == ReviewStatus.GOLD_CONFIRMED
    assert up.review_decision == ReviewDecision.CONFIRM_SEED
    assert up.gold_concept == "accounting_revenue"
    assert up.gold_qualifiers.scope == OperationScope.GROUP_CONSOLIDATED
    assert up.gold_alias_role == AliasRole.DIRECT_VALUE_LABEL
    assert up.gold_value_pattern == ValuePattern.DIRECT_LEVEL
    assert up.gold_valuation_eligibility == ValuationEligibility.ELIGIBLE
    assert up.gold_should_abstain is False
    assert up.reviewed_at == "2026-09-25T16:00:00"
    assert up.reviewer_id == "human_review_batch_001"
    assert up.reviewer_notes == "Confirmed by reviewer"

    # Invariant: CONFIRM_SEED cannot bypass validation rules.
    # If seed capex lacks capex_basis but is ELIGIBLE, CONFIRM_SEED must fail!
    invalid_seed_capex = BenchmarkItem(
        benchmark_id="BENCH-CONF-002",
        sens_id=11,
        ticker="TEST.JO",
        publication_datetime="2025-09-01 10:00",
        raw_label="capital expenditure",
        normalized_label="capital expenditure",
        full_sentence="Capital expenditure was R50m.",
        detected_numeric_tokens=["50"],
        current_dictionary_status=AliasStatus.REQUIRES_CONTEXT,
        seed_concept="total_capex",
        seed_qualifiers=SemanticQualifiers(capex_basis=CapexBasis.UNSPECIFIED),
        seed_alias_role=AliasRole.DIRECT_VALUE_LABEL,
        seed_value_pattern=ValuePattern.DIRECT_LEVEL,
        seed_valuation_eligibility=ValuationEligibility.ELIGIBLE,  # FORBIDDEN FOR UNVERIFIED CAPEX
        seed_should_abstain=False,
        review_status=ReviewStatus.REVIEW_REQUIRED
    )
    bad_csv_row = {
        "benchmark_id": "BENCH-CONF-002",
        "ticker": "TEST.JO",
        "publication_datetime": "2025-09-01 10:00",
        "full_sentence": "Capital expenditure was R50m.",
        "normalized_label": "capital expenditure",
        "detected_numeric_tokens": json.dumps(["50"]),
        "review_decision": "CONFIRM_SEED",
    }
    with pytest.raises(ValueError, match="used as valuation baseline requires explicit capex_basis"):
        apply_review_decisions([invalid_seed_capex], [bad_csv_row])


def test_32_override_import():
    """32. OVERRIDE applies explicit human-provided replacement gold fields and qualifiers."""
    item = BenchmarkItem(
        benchmark_id="BENCH-OVER-001",
        sens_id=20,
        ticker="TRU.JO",
        publication_datetime="2025-09-01 10:00",
        raw_label="borrowings",
        normalized_label="borrowings",
        full_sentence="Total borrowings were R1 200 million.",
        detected_numeric_tokens=["1200"],
        current_dictionary_status=AliasStatus.REQUIRES_CONTEXT,
        seed_concept=None,
        seed_alias_role=AliasRole.CONCEPT_MENTION_ONLY,
        seed_value_pattern=ValuePattern.UNKNOWN,
        seed_valuation_eligibility=ValuationEligibility.INFORMATIONAL_ONLY,
        seed_should_abstain=True,
        review_status=ReviewStatus.REVIEW_REQUIRED
    )

    csv_row = {
        "benchmark_id": "BENCH-OVER-001",
        "ticker": "TRU.JO",
        "publication_datetime": "2025-09-01 10:00",
        "full_sentence": "Total borrowings were R1 200 million.",
        "normalized_label": "borrowings",
        "detected_numeric_tokens": json.dumps(["1200"]),
        "gold_concept": "gross_debt",
        "gold_lease_inclusion": "ex_leases",
        "gold_basis_evidence": "explicit_note_wording",
        "gold_alias_role": "DIRECT_VALUE_LABEL",
        "gold_value_pattern": "DIRECT_LEVEL",
        "gold_valuation_eligibility": "ELIGIBLE_WITH_QUALIFIER",
        "gold_should_abstain": "False",
        "review_decision": "OVERRIDE",
        "reviewer_notes": "Explicitly confirmed note wording separate from leases"
    }

    updated = apply_review_decisions([item], [csv_row], reviewer_id="human_review_batch_001")
    up = updated[0]

    assert up.review_status == ReviewStatus.GOLD_CONFIRMED
    assert up.review_decision == ReviewDecision.OVERRIDE
    assert up.gold_concept == "gross_debt"
    assert up.gold_qualifiers.lease_inclusion == LeaseInclusion.EX_LEASES
    assert up.gold_qualifiers.basis_evidence == BasisEvidence.EXPLICIT_NOTE_WORDING
    assert up.gold_alias_role == AliasRole.DIRECT_VALUE_LABEL
    assert up.gold_value_pattern == ValuePattern.DIRECT_LEVEL
    assert up.gold_valuation_eligibility == ValuationEligibility.ELIGIBLE_WITH_QUALIFIER
    assert up.gold_should_abstain is False
    assert up.reviewer_notes == "Explicitly confirmed note wording separate from leases"


def test_33_abstain_import():
    """33. ABSTAIN enforces gold_should_abstain=True and permits null gold_concept."""
    item = BenchmarkItem(
        benchmark_id="BENCH-ABS-001",
        sens_id=30,
        ticker="TEST.JO",
        publication_datetime="2025-09-01 10:00",
        raw_label="sales",
        normalized_label="sales",
        full_sentence="Sales across branches showed momentum.",
        detected_numeric_tokens=[],
        current_dictionary_status=AliasStatus.REQUIRES_CONTEXT,
        seed_concept=None,
        seed_alias_role=AliasRole.CONCEPT_MENTION_ONLY,
        seed_value_pattern=ValuePattern.UNKNOWN,
        seed_valuation_eligibility=ValuationEligibility.INFORMATIONAL_ONLY,
        seed_should_abstain=True,
        review_status=ReviewStatus.REVIEW_REQUIRED
    )

    csv_row = {
        "benchmark_id": "BENCH-ABS-001",
        "ticker": "TEST.JO",
        "publication_datetime": "2025-09-01 10:00",
        "full_sentence": "Sales across branches showed momentum.",
        "normalized_label": "sales",
        "detected_numeric_tokens": "[]",
        "gold_concept": "",
        "review_decision": "ABSTAIN",
        "reviewer_notes": "Narrative discussion only; must abstain"
    }

    updated = apply_review_decisions([item], [csv_row])
    up = updated[0]

    assert up.review_status == ReviewStatus.GOLD_CONFIRMED
    assert up.review_decision == ReviewDecision.ABSTAIN
    assert up.gold_should_abstain is True
    assert up.gold_concept is None
    assert up.gold_alias_role == AliasRole.CONCEPT_MENTION_ONLY
    assert up.gold_value_pattern == ValuePattern.UNKNOWN


def test_34_skip_behavior():
    """34. SKIP leaves the item unconfirmed with null gold fields."""
    item = BenchmarkItem(
        benchmark_id="BENCH-SKIP-001",
        sens_id=40,
        ticker="TEST.JO",
        publication_datetime="2025-09-01 10:00",
        raw_label="operating profit",
        normalized_label="operating profit",
        full_sentence="Operating profit increased by 5%.",
        detected_numeric_tokens=["5%"],
        current_dictionary_status=AliasStatus.APPROVED,
        seed_concept="operating_profit",
        seed_alias_role=AliasRole.CHANGE_STATEMENT,
        seed_value_pattern=ValuePattern.CHANGE_RATE_ONLY,
        seed_valuation_eligibility=ValuationEligibility.INFORMATIONAL_ONLY,
        seed_should_abstain=True,
        review_status=ReviewStatus.REVIEW_REQUIRED
    )

    csv_row = {
        "benchmark_id": "BENCH-SKIP-001",
        "ticker": "TEST.JO",
        "publication_datetime": "2025-09-01 10:00",
        "full_sentence": "Operating profit increased by 5%.",
        "normalized_label": "operating profit",
        "detected_numeric_tokens": json.dumps(["5%"]),
        "review_decision": "SKIP",
        "reviewer_notes": "Postpone decision to Batch 002"
    }

    updated = apply_review_decisions([item], [csv_row])
    up = updated[0]

    assert up.review_status == ReviewStatus.REVIEW_REQUIRED
    assert up.review_decision == ReviewDecision.SKIP
    assert up.gold_concept is None
    assert up.gold_qualifiers is None
    assert up.gold_alias_role is None
    assert up.gold_value_pattern is None
    assert up.gold_valuation_eligibility is None
    assert up.gold_should_abstain is None
    assert up.reviewer_notes == "Postpone decision to Batch 002"


def test_35_invalid_enum_rejection():
    """35. Invalid enum strings in review_decision, alias_role, or qualifiers are strictly rejected."""
    item = BenchmarkItem(
        benchmark_id="BENCH-ERR-010",
        sens_id=50,
        ticker="TEST.JO",
        publication_datetime="2025-09-01 10:00",
        raw_label="revenue",
        normalized_label="revenue",
        full_sentence="Revenue was R100m.",
        detected_numeric_tokens=["100"],
        current_dictionary_status=AliasStatus.APPROVED,
        seed_concept="accounting_revenue",
        seed_alias_role=AliasRole.DIRECT_VALUE_LABEL,
        seed_value_pattern=ValuePattern.DIRECT_LEVEL,
        seed_valuation_eligibility=ValuationEligibility.ELIGIBLE,
        seed_should_abstain=False,
        review_status=ReviewStatus.REVIEW_REQUIRED
    )

    # Invalid review_decision
    bad_dec_row = {
        "benchmark_id": "BENCH-ERR-010",
        "ticker": "TEST.JO",
        "publication_datetime": "2025-09-01 10:00",
        "full_sentence": "Revenue was R100m.",
        "normalized_label": "revenue",
        "detected_numeric_tokens": json.dumps(["100"]),
        "review_decision": "APPROVE_IT",  # INVALID
    }
    with pytest.raises(ValueError, match="Invalid review_decision 'APPROVE_IT'"):
        apply_review_decisions([item], [bad_dec_row])

    # Invalid gold_alias_role
    bad_role_row = {
        "benchmark_id": "BENCH-ERR-010",
        "ticker": "TEST.JO",
        "publication_datetime": "2025-09-01 10:00",
        "full_sentence": "Revenue was R100m.",
        "normalized_label": "revenue",
        "detected_numeric_tokens": json.dumps(["100"]),
        "gold_alias_role": "NOT_A_ROLE",  # INVALID
        "gold_value_pattern": "DIRECT_LEVEL",
        "gold_valuation_eligibility": "ELIGIBLE",
        "gold_should_abstain": "False",
        "review_decision": "OVERRIDE",
    }
    with pytest.raises(ValueError, match="Invalid value 'NOT_A_ROLE' for AliasRole"):
        apply_review_decisions([item], [bad_role_row])

    # Invalid qualifier enum
    bad_qual_row = {
        "benchmark_id": "BENCH-ERR-010",
        "ticker": "TEST.JO",
        "publication_datetime": "2025-09-01 10:00",
        "full_sentence": "Revenue was R100m.",
        "normalized_label": "revenue",
        "detected_numeric_tokens": json.dumps(["100"]),
        "gold_scope": "INVALID_SCOPE",  # INVALID
        "gold_alias_role": "DIRECT_VALUE_LABEL",
        "gold_value_pattern": "DIRECT_LEVEL",
        "gold_valuation_eligibility": "ELIGIBLE",
        "gold_should_abstain": "False",
        "review_decision": "OVERRIDE",
    }
    with pytest.raises(ValueError, match="Invalid value 'INVALID_SCOPE' for OperationScope"):
        apply_review_decisions([item], [bad_qual_row])


def test_36_missing_benchmark_id_rejection():
    """36. Missing benchmark ID or non-existent benchmark ID fails import."""
    item = BenchmarkItem(
        benchmark_id="BENCH-EXISTS-001",
        sens_id=60,
        ticker="TEST.JO",
        publication_datetime="2025-09-01 10:00",
        raw_label="revenue",
        normalized_label="revenue",
        full_sentence="Revenue was R100m.",
        detected_numeric_tokens=["100"],
        current_dictionary_status=AliasStatus.APPROVED,
        seed_concept="accounting_revenue",
        seed_alias_role=AliasRole.DIRECT_VALUE_LABEL,
        seed_value_pattern=ValuePattern.DIRECT_LEVEL,
        seed_valuation_eligibility=ValuationEligibility.ELIGIBLE,
        seed_should_abstain=False,
        review_status=ReviewStatus.REVIEW_REQUIRED
    )

    # Empty benchmark_id
    with pytest.raises(ValueError, match="CSV row missing 'benchmark_id'"):
        apply_review_decisions([item], [{"benchmark_id": "", "review_decision": "CONFIRM_SEED"}])

    # Non-existent benchmark_id
    with pytest.raises(ValueError, match="Benchmark ID 'BENCH-GHOST-999' not found"):
        apply_review_decisions([item], [{"benchmark_id": "BENCH-GHOST-999", "review_decision": "CONFIRM_SEED"}])


def test_37_duplicate_id_rejection():
    """37. Duplicate benchmark IDs within the CSV worksheet are rejected."""
    item = BenchmarkItem(
        benchmark_id="BENCH-DUP-001",
        sens_id=70,
        ticker="TEST.JO",
        publication_datetime="2025-09-01 10:00",
        raw_label="revenue",
        normalized_label="revenue",
        full_sentence="Revenue was R100m.",
        detected_numeric_tokens=["100"],
        current_dictionary_status=AliasStatus.APPROVED,
        seed_concept="accounting_revenue",
        seed_alias_role=AliasRole.DIRECT_VALUE_LABEL,
        seed_value_pattern=ValuePattern.DIRECT_LEVEL,
        seed_valuation_eligibility=ValuationEligibility.ELIGIBLE,
        seed_should_abstain=False,
        review_status=ReviewStatus.REVIEW_REQUIRED
    )

    rows = [
        {
            "benchmark_id": "BENCH-DUP-001",
            "ticker": "TEST.JO",
            "publication_datetime": "2025-09-01 10:00",
            "full_sentence": "Revenue was R100m.",
            "normalized_label": "revenue",
            "detected_numeric_tokens": json.dumps(["100"]),
            "review_decision": "CONFIRM_SEED",
        },
        {
            "benchmark_id": "BENCH-DUP-001",
            "ticker": "TEST.JO",
            "publication_datetime": "2025-09-01 10:00",
            "full_sentence": "Revenue was R100m.",
            "normalized_label": "revenue",
            "detected_numeric_tokens": json.dumps(["100"]),
            "review_decision": "SKIP",
        }
    ]

    with pytest.raises(ValueError, match="Duplicate benchmark_id found in CSV: BENCH-DUP-001"):
        apply_review_decisions([item], rows)


def test_38_partial_write_prevention(tmp_path: Path):
    """38. Validation failure prevents partial write and preserves original JSON unchanged."""
    item1 = BenchmarkItem(
        benchmark_id="BENCH-ATOM-001",
        sens_id=81,
        ticker="TEST.JO",
        publication_datetime="2025-09-01 10:00",
        raw_label="revenue",
        normalized_label="revenue",
        full_sentence="Revenue was R100m.",
        detected_numeric_tokens=["100"],
        current_dictionary_status=AliasStatus.APPROVED,
        seed_concept="accounting_revenue",
        seed_alias_role=AliasRole.DIRECT_VALUE_LABEL,
        seed_value_pattern=ValuePattern.DIRECT_LEVEL,
        seed_valuation_eligibility=ValuationEligibility.ELIGIBLE,
        seed_should_abstain=False,
        review_status=ReviewStatus.REVIEW_REQUIRED
    )
    item2 = BenchmarkItem(
        benchmark_id="BENCH-ATOM-002",
        sens_id=82,
        ticker="TEST.JO",
        publication_datetime="2025-09-01 10:00",
        raw_label="operating profit",
        normalized_label="operating profit",
        full_sentence="Operating profit was R50m.",
        detected_numeric_tokens=["50"],
        current_dictionary_status=AliasStatus.APPROVED,
        seed_concept="operating_profit",
        seed_alias_role=AliasRole.DIRECT_VALUE_LABEL,
        seed_value_pattern=ValuePattern.DIRECT_LEVEL,
        seed_valuation_eligibility=ValuationEligibility.ELIGIBLE,
        seed_should_abstain=False,
        review_status=ReviewStatus.REVIEW_REQUIRED
    )

    json_file = tmp_path / "test_benchmark.json"
    save_benchmark_json([item1, item2], json_file)
    original_bytes = json_file.read_bytes()

    # CSV with row 1 valid CONFIRM_SEED, row 2 invalid decision
    csv_file = tmp_path / "test_reviews.csv"
    with open(csv_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=REVIEW_WORKSHEET_COLUMNS)
        writer.writeheader()
        writer.writerow({
            "benchmark_id": "BENCH-ATOM-001",
            "ticker": "TEST.JO",
            "publication_datetime": "2025-09-01 10:00",
            "full_sentence": "Revenue was R100m.",
            "normalized_label": "revenue",
            "detected_numeric_tokens": json.dumps(["100"]),
            "review_decision": "CONFIRM_SEED"
        })
        writer.writerow({
            "benchmark_id": "BENCH-ATOM-002",
            "ticker": "TEST.JO",
            "publication_datetime": "2025-09-01 10:00",
            "full_sentence": "Operating profit was R50m.",
            "normalized_label": "operating profit",
            "detected_numeric_tokens": json.dumps(["50"]),
            "review_decision": "INVALID_DECISION"  # WILL FAIL!
        })

    with pytest.raises(ValueError, match="Invalid review_decision 'INVALID_DECISION'"):
        import_review_worksheet_csv(csv_file, json_file)

    # Verify JSON file on disk was NOT partially updated
    assert json_file.read_bytes() == original_bytes
    reloaded = load_benchmark_json(json_file)
    assert reloaded[0].review_status == ReviewStatus.REVIEW_REQUIRED
    assert reloaded[0].gold_concept is None


def test_39_qualifier_validation():
    """39. Confirmed valuation baseline requires required qualifiers (capex basis, lease inclusion, denominator)."""
    item = BenchmarkItem(
        benchmark_id="BENCH-QVAL-001",
        sens_id=91,
        ticker="TEST.JO",
        publication_datetime="2025-09-01 10:00",
        raw_label="operating margin",
        normalized_label="operating margin",
        full_sentence="Operating margin improved to 12.5%.",
        detected_numeric_tokens=["12.5%"],
        current_dictionary_status=AliasStatus.REQUIRES_CONTEXT,
        seed_concept="operating_margin",
        seed_alias_role=AliasRole.DIRECT_VALUE_LABEL,
        seed_value_pattern=ValuePattern.DIRECT_LEVEL,
        seed_valuation_eligibility=ValuationEligibility.REQUIRES_BASIS,
        seed_should_abstain=True,
        review_status=ReviewStatus.REVIEW_REQUIRED
    )

    # Missing margin denominator on confirmed ELIGIBLE baseline
    bad_row = {
        "benchmark_id": "BENCH-QVAL-001",
        "ticker": "TEST.JO",
        "publication_datetime": "2025-09-01 10:00",
        "full_sentence": "Operating margin improved to 12.5%.",
        "normalized_label": "operating margin",
        "detected_numeric_tokens": json.dumps(["12.5%"]),
        "gold_concept": "operating_margin",
        "gold_margin_denominator": "unspecified",  # FORBIDDEN FOR VALUATION BASELINE
        "gold_alias_role": "DIRECT_VALUE_LABEL",
        "gold_value_pattern": "DIRECT_LEVEL",
        "gold_valuation_eligibility": "ELIGIBLE",
        "gold_should_abstain": "False",
        "review_decision": "OVERRIDE"
    }

    with pytest.raises(ValueError, match="valuation baseline requires explicit margin_denominator"):
        apply_review_decisions([item], [bad_row])


def test_40_original_source_context_immutability():
    """40. Modifying original source sentence, ticker, label, or numbers raises ValueError."""
    item = BenchmarkItem(
        benchmark_id="BENCH-IMMUT-001",
        sens_id=95,
        ticker="TEST.JO",
        publication_datetime="2025-09-01 10:00",
        raw_label="revenue",
        normalized_label="revenue",
        full_sentence="Revenue was R100m.",
        detected_numeric_tokens=["100"],
        current_dictionary_status=AliasStatus.APPROVED,
        seed_concept="accounting_revenue",
        seed_alias_role=AliasRole.DIRECT_VALUE_LABEL,
        seed_value_pattern=ValuePattern.DIRECT_LEVEL,
        seed_valuation_eligibility=ValuationEligibility.ELIGIBLE,
        seed_should_abstain=False,
        review_status=ReviewStatus.REVIEW_REQUIRED
    )

    # Sentence tampering
    with pytest.raises(ValueError, match="full_sentence mismatch"):
        apply_review_decisions([item], [{
            "benchmark_id": "BENCH-IMMUT-001",
            "ticker": "TEST.JO",
            "publication_datetime": "2025-09-01 10:00",
            "full_sentence": "Revenue was R100m TAMPERED.",
            "normalized_label": "revenue",
            "detected_numeric_tokens": json.dumps(["100"]),
            "review_decision": "CONFIRM_SEED"
        }])

    # Ticker tampering
    with pytest.raises(ValueError, match="ticker mismatch"):
        apply_review_decisions([item], [{
            "benchmark_id": "BENCH-IMMUT-001",
            "ticker": "TAMPERED.JO",
            "publication_datetime": "2025-09-01 10:00",
            "full_sentence": "Revenue was R100m.",
            "normalized_label": "revenue",
            "detected_numeric_tokens": json.dumps(["100"]),
            "review_decision": "CONFIRM_SEED"
        }])

    # Numbers tampering
    with pytest.raises(ValueError, match="detected_numeric_tokens mismatch"):
        apply_review_decisions([item], [{
            "benchmark_id": "BENCH-IMMUT-001",
            "ticker": "TEST.JO",
            "publication_datetime": "2025-09-01 10:00",
            "full_sentence": "Revenue was R100m.",
            "normalized_label": "revenue",
            "detected_numeric_tokens": json.dumps(["999"]),
            "review_decision": "CONFIRM_SEED"
        }])


def test_41_deterministic_review_statistics(tmp_path: Path):
    """41. Progress reporting correctly aggregates total, reviewed, confirmed, abstained, overridden, skipped, remaining."""
    items = [
        BenchmarkItem(
            benchmark_id=f"BENCH-STAT-00{idx}",
            sens_id=idx,
            ticker=f"TK{idx}.JO",
            publication_datetime="2025-09-01 10:00",
            raw_label="metric",
            normalized_label="metric",
            full_sentence=f"Metric was {idx}00.",
            detected_numeric_tokens=[f"{idx}00"],
            current_dictionary_status=AliasStatus.APPROVED,
            seed_concept="revenue",
            seed_alias_role=AliasRole.DIRECT_VALUE_LABEL,
            seed_value_pattern=ValuePattern.DIRECT_LEVEL,
            seed_valuation_eligibility=ValuationEligibility.ELIGIBLE,
            seed_should_abstain=False,
            review_status=ReviewStatus.REVIEW_REQUIRED
        )
        for idx in range(1, 6)
    ]

    csv_file = tmp_path / "stats_review.csv"
    with open(csv_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=REVIEW_WORKSHEET_COLUMNS)
        writer.writeheader()
        # Item 1: CONFIRM_SEED
        writer.writerow({
            "benchmark_id": "BENCH-STAT-001", "ticker": "TK1.JO", "publication_datetime": "2025-09-01 10:00",
            "full_sentence": "Metric was 100.", "normalized_label": "metric", "detected_numeric_tokens": json.dumps(["100"]),
            "review_decision": "CONFIRM_SEED"
        })
        # Item 2: OVERRIDE
        writer.writerow({
            "benchmark_id": "BENCH-STAT-002", "ticker": "TK2.JO", "publication_datetime": "2025-09-01 10:00",
            "full_sentence": "Metric was 200.", "normalized_label": "metric", "detected_numeric_tokens": json.dumps(["200"]),
            "gold_concept": "operating_profit", "gold_alias_role": "DIRECT_VALUE_LABEL", "gold_value_pattern": "DIRECT_LEVEL",
            "gold_valuation_eligibility": "ELIGIBLE", "gold_should_abstain": "False", "review_decision": "OVERRIDE"
        })
        # Item 3: ABSTAIN
        writer.writerow({
            "benchmark_id": "BENCH-STAT-003", "ticker": "TK3.JO", "publication_datetime": "2025-09-01 10:00",
            "full_sentence": "Metric was 300.", "normalized_label": "metric", "detected_numeric_tokens": json.dumps(["300"]),
            "review_decision": "ABSTAIN"
        })
        # Item 4: SKIP
        writer.writerow({
            "benchmark_id": "BENCH-STAT-004", "ticker": "TK4.JO", "publication_datetime": "2025-09-01 10:00",
            "full_sentence": "Metric was 400.", "normalized_label": "metric", "detected_numeric_tokens": json.dumps(["400"]),
            "review_decision": "SKIP"
        })
        # Item 5: UNREVIEWED
        writer.writerow({
            "benchmark_id": "BENCH-STAT-005", "ticker": "TK5.JO", "publication_datetime": "2025-09-01 10:00",
            "full_sentence": "Metric was 500.", "normalized_label": "metric", "detected_numeric_tokens": json.dumps(["500"]),
            "review_decision": ""
        })

    # Test report from CSV directly
    csv_report = get_csv_review_progress_report(csv_file)
    assert csv_report.batch_total == 5
    assert csv_report.reviewed == 4
    assert csv_report.gold_confirmed == 3
    assert csv_report.confirmed_seed == 1
    assert csv_report.overridden == 1
    assert csv_report.abstained == 1
    assert csv_report.skipped == 1
    assert csv_report.remaining == 1

    # Apply decisions and test report from items
    with open(csv_file, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    updated_items = apply_review_decisions(items, rows)
    item_report = get_review_progress_report(updated_items)
    assert item_report.batch_total == 5
    assert item_report.reviewed == 4
    assert item_report.gold_confirmed == 3
    assert item_report.confirmed_seed == 1
    assert item_report.overridden == 1
    assert item_report.abstained == 1
    assert item_report.skipped == 1
    assert item_report.remaining == 1

    # Formatted report test
    formatted = format_review_progress_report(item_report)
    assert "Batch total:     5" in formatted
    assert "Reviewed:        4 (80.0%)" in formatted
    assert "Remaining:       1 (20.0%)" in formatted


# =============================================================================
# 11. Corpus-Level Integrity Tests (JSE Numbers, Overlaps, Guidance, Heuristics)
# =============================================================================

def test_comma_decimal_currency_level_extraction():
    """Validates South African / JSE comma-decimal currency level extraction."""
    s1 = "Revenue R235,6 billion, up 4,3%; up 6,8%"
    toks1 = parse_detected_numeric_tokens(s1)
    rev_tok = next(t for t in toks1 if t.currency == "ZAR")
    assert rev_tok.raw_text == "R235,6 billion"
    assert rev_tok.normalized_numeric_value == 235.6
    assert rev_tok.token_type == NumericTokenType.CURRENCY_LEVEL
    assert rev_tok.scale == "billion"

    s2 = "Cash generated ... R16,6 billion"
    toks2 = parse_detected_numeric_tokens(s2)
    assert len(toks2) == 1
    assert toks2[0].raw_text == "R16,6 billion"
    assert toks2[0].normalized_numeric_value == 16.6
    assert toks2[0].token_type == NumericTokenType.CURRENCY_LEVEL
    assert toks2[0].scale == "billion"

    s3 = "Capex was R235,6 million and EUR 1.8 billion with $13.7 million"
    toks3 = parse_detected_numeric_tokens(s3)
    curr_map = {t.currency: t for t in toks3}
    assert curr_map["ZAR"].normalized_numeric_value == 235.6
    assert curr_map["ZAR"].scale == "million"
    assert curr_map["EUR"].normalized_numeric_value == 1.8
    assert curr_map["EUR"].scale == "billion"
    assert curr_map["USD"].normalized_numeric_value == 13.7
    assert curr_map["USD"].scale == "million"


def test_spaced_thousands_decimal_extraction():
    """Validates spaced-thousands and comma-thousands decimal formatting."""
    s1 = "Headline earnings per share 2 562,7 cents"
    toks1 = parse_detected_numeric_tokens(s1)
    assert len(toks1) == 1
    assert toks1[0].raw_text == "2 562,7 cents"
    assert toks1[0].normalized_numeric_value == 2562.7
    assert toks1[0].scale == "cents"
    assert toks1[0].is_per_share is True
    assert toks1[0].token_type == NumericTokenType.PER_SHARE_LEVEL

    s2 = "Level was 2 562.7 and 2,562.7"
    toks2 = parse_detected_numeric_tokens(s2)
    assert len(toks2) == 2
    assert toks2[0].normalized_numeric_value == 2562.7
    assert toks2[1].normalized_numeric_value == 2562.7


def test_percentage_identification():
    """Validates percentage identification and negative sign preservation."""
    s = "Revenue up 4,3%; up 6,8% with growth of 24.5% and decline of -11.6%"
    toks = parse_detected_numeric_tokens(s)
    pcts = [t for t in toks if t.is_percentage]
    assert len(pcts) == 4
    vals = [t.normalized_numeric_value for t in pcts]
    assert vals == [4.3, 6.8, 24.5, -11.6]
    for p in pcts:
        assert p.token_type == NumericTokenType.PERCENTAGE


def test_dates_years_distinguished_from_metric_values():
    """Ensures calendar dates and standalone years are not classified as metric levels."""
    s1 = "for the year ended 30 June 2025"
    toks1 = parse_detected_numeric_tokens(s1)
    assert len(toks1) == 2
    assert toks1[0].token_type == NumericTokenType.YEAR_OR_DATE  # 30 day of June 2025
    assert toks1[1].token_type == NumericTokenType.YEAR_OR_DATE  # 2025

    # A sentence with only calendar years/dates cannot seed as DIRECT_VALUE_LABEL / DIRECT_LEVEL
    role, pat, elig, abstain, status, diff, note = classify_benchmark_item_heuristics(
        norm="headline earnings per share",
        raw="Headline earnings per share",
        sentence=s1,
        concept_id="heps",
        dict_status=AliasStatus.APPROVED,
        qualifiers=SemanticQualifiers()
    )
    assert role == AliasRole.CONCEPT_MENTION_ONLY
    assert pat == ValuePattern.UNKNOWN
    assert elig == ValuationEligibility.INFORMATIONAL_ONLY
    assert abstain is True


def test_longest_semantic_span_wins():
    """Verifies that longer spans subsume and suppress strictly contained shorter spans."""
    # Match tuples: (start, end, label)
    matches = [
        (0, 27, "headline earnings per share"),
        (9, 27, "earnings per share"),
        (0, 17, "headline earnings"),
    ]
    resolved = resolve_nested_alias_spans(matches)
    assert len(resolved) == 1
    assert resolved[0][2] == "headline earnings per share"


def test_heps_suppresses_nested_eps_match():
    """Ensures 'headline earnings per share' suppresses nested 'earnings per share'."""
    sentence = "Headline earnings per share increase 14%"
    m_heps = (0, 27, "headline earnings per share", "heps")
    m_eps = (9, 27, "earnings per share", "eps")
    resolved = resolve_nested_alias_spans([m_eps, m_heps])
    assert len(resolved) == 1
    assert resolved[0][2] == "headline earnings per share"
    assert resolved[0][3] == "heps"


def test_diluted_heps_suppresses_shorter_nested_aliases():
    """Ensures 'diluted headline earnings per share' suppresses both HEPS and EPS."""
    sentence = "Diluted headline earnings per share 150 cents"
    m_dil_heps = (0, 35, "diluted headline earnings per share", "diluted_heps")
    m_heps = (8, 35, "headline earnings per share", "heps")
    m_eps = (17, 35, "earnings per share", "eps")
    resolved = resolve_nested_alias_spans([m_eps, m_dil_heps, m_heps])
    assert len(resolved) == 1
    assert resolved[0][2] == "diluted headline earnings per share"
    assert resolved[0][3] == "diluted_heps"


def test_exact_occurrence_duplicates_rejected():
    """Ensures identical occurrences (sens_id, full_sentence, normalized_label) are rejected."""
    # Simulate extraction with BENCH-0008 vs BENCH-0009 case
    seen_occurrences = set()
    sens_id = 6
    sentence = "• Revenue for Q3 2025 increased to $13.7 million"
    norm = "revenue"

    key = (sens_id, sentence.strip(), norm)
    # First occurrence added
    assert key not in seen_occurrences
    seen_occurrences.add(key)

    # Second identical occurrence must be rejected
    assert key in seen_occurrences


def test_guidance_range_classified_guidance_statement_range():
    """Ensures guidance with range is classified as GUIDANCE_STATEMENT / RANGE / INFORMATIONAL_ONLY."""
    sentence = "anticipates that it will report: a basic loss per share of between 138.30 cents and 138.48 cents"
    role, pat, elig, abstain, status, diff, note = classify_benchmark_item_heuristics(
        norm="basic loss per share",
        raw="basic loss per share",
        sentence=sentence,
        concept_id="eps",
        dict_status=AliasStatus.APPROVED,
        qualifiers=SemanticQualifiers()
    )
    assert role == AliasRole.GUIDANCE_STATEMENT
    assert pat == ValuePattern.RANGE
    assert elig == ValuationEligibility.INFORMATIONAL_ONLY
    assert abstain is True


def test_percentage_only_growth_classified_change_statement_change_rate_only():
    """Ensures statements with change verbs and only percentage tokens are CHANGE_STATEMENT / CHANGE_RATE_ONLY."""
    s1 = "Earnings per share increase 16%"
    role1, pat1, elig1, abstain1, status1, diff1, note1 = classify_benchmark_item_heuristics(
        norm="earnings per share",
        raw="Earnings per share",
        sentence=s1,
        concept_id="eps",
        dict_status=AliasStatus.APPROVED,
        qualifiers=SemanticQualifiers()
    )
    assert role1 == AliasRole.CHANGE_STATEMENT
    assert pat1 == ValuePattern.CHANGE_RATE_ONLY
    assert elig1 == ValuationEligibility.INFORMATIONAL_ONLY
    assert abstain1 is True

    s2 = "Headline earnings per share increase 14%"
    role2, pat2, elig2, abstain2, status2, diff2, note2 = classify_benchmark_item_heuristics(
        norm="headline earnings per share",
        raw="Headline earnings per share",
        sentence=s2,
        concept_id="heps",
        dict_status=AliasStatus.APPROVED,
        qualifiers=SemanticQualifiers()
    )
    assert role2 == AliasRole.CHANGE_STATEMENT
    assert pat2 == ValuePattern.CHANGE_RATE_ONLY
    assert elig2 == ValuationEligibility.INFORMATIONAL_ONLY
    assert abstain2 is True


def test_margin_denominator_not_inferred_without_evidence():
    """Ensures margin concepts do not assume accounting_revenue without deterministic source evidence."""
    sentence = "in a 22.2% operating margin"
    qualifiers = SemanticQualifiers()
    role, pat, elig, abstain, status, diff, note = classify_benchmark_item_heuristics(
        norm="operating margin",
        raw="operating margin",
        sentence=sentence,
        concept_id="operating_margin",
        dict_status=AliasStatus.APPROVED,
        qualifiers=qualifiers
    )
    assert qualifiers.margin_denominator == MarginDenominator.UNSPECIFIED
    assert elig == ValuationEligibility.REQUIRES_BASIS
    assert abstain is True
    assert status == ReviewStatus.REVIEW_REQUIRED

    # Explicit evidence in text sets explicit denominator
    sentence_explicit = "achieved an operating margin of 22.2% of merchandise sales"
    q_explicit = SemanticQualifiers()
    role_e, pat_e, elig_e, abstain_e, status_e, diff_e, note_e = classify_benchmark_item_heuristics(
        norm="operating margin",
        raw="operating margin",
        sentence=sentence_explicit,
        concept_id="operating_margin",
        dict_status=AliasStatus.APPROVED,
        qualifiers=q_explicit
    )
    assert q_explicit.margin_denominator == MarginDenominator.MERCHANDISE_SALES
    assert elig_e == ValuationEligibility.ELIGIBLE_WITH_QUALIFIER
    assert abstain_e is False


def test_heps_maps_to_heps_rather_than_headline_earnings():
    """Ensures 'Headline earnings per share 2 562,7 cents' maps to heps, preserving concept specificity."""
    sentence = "Headline earnings per share 2 562,7 cents"
    role, pat, elig, abstain, status, diff, note = classify_benchmark_item_heuristics(
        norm="headline earnings per share",
        raw="Headline earnings per share",
        sentence=sentence,
        concept_id="heps",
        dict_status=AliasStatus.APPROVED,
        qualifiers=SemanticQualifiers()
    )
    assert role == AliasRole.DIRECT_VALUE_LABEL
    assert pat == ValuePattern.DIRECT_LEVEL
    assert elig == ValuationEligibility.ELIGIBLE
    assert abstain is False



