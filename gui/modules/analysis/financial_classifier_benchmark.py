"""Model-Agnostic Benchmark and Evaluation Harness for Financial Language Classification.

Provides:
1. Typed BenchmarkItem schema preserving rich linguistic and sentence-level context.
2. Formalized ValuationEligibility, AliasRole, ValuePattern, and ReviewStatus enums.
3. Stratified SENS candidate pool builder with ticker and label caps.
4. Model-agnostic prediction interface and evaluation metrics (accuracy, abstention,
   unsafe false acceptance, confidence threshold curves, and calibration).
5. Ground-truth review state management (AUTO_SEEDED vs REVIEW_REQUIRED vs GOLD_CONFIRMED).
"""
from __future__ import annotations

from collections import Counter
import csv
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json
import math
import os
from pathlib import Path
import re
from typing import Any, Callable, Sequence
from uuid import uuid4

from pydantic import BaseModel, Field

from modules.analysis.financial_concept_dictionary import (
    AliasObservation,
    AliasStatus,
    BasisEvidence,
    CanonicalConcept,
    CapexBasis,
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
    normalize_label,
)


# =============================================================================
# 1. Benchmark Enums
# =============================================================================

class ValuationEligibility(str, Enum):
    """Admissibility for direct or conditional downstream valuation model intake."""
    ELIGIBLE = "ELIGIBLE"
    ELIGIBLE_WITH_QUALIFIER = "ELIGIBLE_WITH_QUALIFIER"
    REQUIRES_SCOPE = "REQUIRES_SCOPE"
    REQUIRES_BASIS = "REQUIRES_BASIS"
    REQUIRES_PERIOD = "REQUIRES_PERIOD"
    REQUIRES_SOURCE_SECTION = "REQUIRES_SOURCE_SECTION"
    INFORMATIONAL_ONLY = "INFORMATIONAL_ONLY"
    PROHIBITED = "PROHIBITED"


class AliasRole(str, Enum):
    """Linguistic and syntactic function of the observed financial wording."""
    DIRECT_VALUE_LABEL = "DIRECT_VALUE_LABEL"      # Adjacent value represents canonical metric level directly
    CHANGE_STATEMENT = "CHANGE_STATEMENT"          # Identifies concept, but adjacent number is rate/delta
    GUIDANCE_STATEMENT = "GUIDANCE_STATEMENT"      # Forecast/range/outlook wording rather than historical actual
    CONCEPT_MENTION_ONLY = "CONCEPT_MENTION_ONLY"  # Discursive/narrative mention unsafe for direct numeric extraction


class ValuePattern(str, Enum):
    """Expected syntactic structure of adjacent numeric values."""
    DIRECT_LEVEL = "DIRECT_LEVEL"                  # "profit for the year: R120m", "loss per share of 28c"
    CHANGE_RATE_ONLY = "CHANGE_RATE_ONLY"          # "revenue grew by 10%"
    CHANGE_RATE_TO_LEVEL = "CHANGE_RATE_TO_LEVEL"  # "increased by 6.2% to R5 382 million"
    FROM_TO_LEVEL = "FROM_TO_LEVEL"                # "from R267 million to R327 million"
    RANGE = "RANGE"                                # "between 150 cents and 160 cents"
    UNKNOWN = "UNKNOWN"                            # Complex narrative or unstructured statement


class ReviewStatus(str, Enum):
    """Editorial and verification status of the benchmark item ground truth."""
    AUTO_SEEDED = "AUTO_SEEDED"        # Deterministically seeded; meets strict unambiguous criteria
    REVIEW_REQUIRED = "REVIEW_REQUIRED"  # Requires manual expert review / contextual determination
    GOLD_CONFIRMED = "GOLD_CONFIRMED"    # Fully confirmed by human financial analyst review


class ReviewDecision(str, Enum):
    """Explicit human review decision for a benchmark item."""
    CONFIRM_SEED = "CONFIRM_SEED"
    OVERRIDE = "OVERRIDE"
    ABSTAIN = "ABSTAIN"
    SKIP = "SKIP"


class BenchmarkDifficulty(str, Enum):
    """Categorical classification for review stratification and difficulty analysis."""
    EASY_DIRECT = "A. Easy/direct"
    CHANGE_STATEMENTS = "B. Change statements"
    SCOPE_AMBIGUITY = "C. Scope ambiguity"
    BASIS_AMBIGUITY = "D. Basis ambiguity"
    DEBT_LEASE_AMBIGUITY = "E. Debt/lease ambiguity"
    SHARES_AMBIGUITY = "F. Shares ambiguity"
    CAPEX_AMBIGUITY = "G. Capex ambiguity"
    PROFIT_EBIT_AMBIGUITY = "H. Profit/EBIT/trading-profit ambiguity"
    UNKNOWN_LONG_TAIL = "I. Unknown/long-tail"


class NumericTokenType(str, Enum):
    """Classification of numeric token semantics in financial text."""
    YEAR_OR_DATE = "YEAR_OR_DATE"
    PERCENTAGE = "PERCENTAGE"
    CURRENCY_LEVEL = "CURRENCY_LEVEL"
    PER_SHARE_LEVEL = "PER_SHARE_LEVEL"
    PLAIN_LEVEL = "PLAIN_LEVEL"
    RANGE_BOUND = "RANGE_BOUND"
    SECTION_NUMBER = "SECTION_NUMBER"
    LIST_MARKER = "LIST_MARKER"
    OTHER = "OTHER"
    AMBIGUOUS_NUMBER_FORMAT = 'AMBIGUOUS_NUMBER_FORMAT'


class DetectedNumericToken(BaseModel):
    """Typed numeric token with normalized value and financial unit metadata."""
    raw_text: str
    normalized_numeric_value: float | None = None
    token_type: NumericTokenType = NumericTokenType.OTHER
    currency: str | None = None
    scale: str | None = None
    is_percentage: bool = False
    is_per_share: bool = False
    char_start: int | None = None
    char_end: int | None = None


# =============================================================================
# 2. Benchmark Item Model
# =============================================================================

from pydantic import BaseModel, Field, model_validator


class BenchmarkItem(BaseModel):
    """A single stratified evaluation candidate with sentence-level context, seed, and gold truth."""
    benchmark_id: str
    sens_id: int
    ticker: str
    publication_datetime: str
    source_document_id: str | None = None

    # Contextual Provenance
    raw_label: str
    normalized_label: str
    full_sentence: str
    previous_sentence: str | None = None
    next_sentence: str | None = None
    nearby_heading: str | None = None
    detected_numeric_tokens: list[str] = Field(default_factory=list)
    detected_typed_numeric_tokens: list[DetectedNumericToken] = Field(default_factory=list)

    # Source Spans and Occurrence Provenance
    source_line_index: int | None = None
    sentence_start_offset: int | None = None
    sentence_end_offset: int | None = None
    alias_start_offset: int | None = None
    alias_end_offset: int | None = None

    # Deterministic Numeric Association
    candidate_metric_token: str | None = None
    candidate_change_token: str | None = None
    association_confidence: float = 1.0
    association_reason: str = ""

    # Current Dictionary State
    current_dictionary_status: AliasStatus
    current_proposed_canonical_concept: str | None = None
    current_qualifiers: SemanticQualifiers = Field(default_factory=SemanticQualifiers)

    # Deterministic Seed Fields (Pre-Review)
    seed_concept: str | None = None
    seed_qualifiers: SemanticQualifiers = Field(default_factory=SemanticQualifiers)
    seed_alias_role: AliasRole
    seed_value_pattern: ValuePattern
    seed_valuation_eligibility: ValuationEligibility
    seed_should_abstain: bool = False

    # Human-Confirmed Gold Targets (Strictly None until review_status == GOLD_CONFIRMED)
    gold_concept: str | None = None
    gold_qualifiers: SemanticQualifiers | None = None
    gold_alias_role: AliasRole | None = None
    gold_value_pattern: ValuePattern | None = None
    gold_valuation_eligibility: ValuationEligibility | None = None
    gold_should_abstain: bool | None = None

    # Review Lifecycle
    review_status: ReviewStatus
    difficulty_category: BenchmarkDifficulty = BenchmarkDifficulty.EASY_DIRECT
    reviewer_notes: str = ""
    reviewed_at: str | None = None
    reviewer_id: str | None = None
    review_decision: ReviewDecision | None = None

    @model_validator(mode="after")
    def validate_item_integrity(self) -> BenchmarkItem:
        # Invariant A, B & E: Candidate metric numbers exclude YEAR_OR_DATE, OTHER, SECTION_NUMBER, LIST_MARKER
        has_metric_numbers = any(
            t.token_type not in (
                NumericTokenType.YEAR_OR_DATE,
                NumericTokenType.OTHER,
                NumericTokenType.SECTION_NUMBER,
                NumericTokenType.LIST_MARKER,
                NumericTokenType.AMBIGUOUS_NUMBER_FORMAT,
            )
            for t in self.detected_typed_numeric_tokens
        ) if self.detected_typed_numeric_tokens else bool(self.detected_numeric_tokens)

        if not has_metric_numbers:
            if self.seed_alias_role in {AliasRole.DIRECT_VALUE_LABEL, AliasRole.CHANGE_STATEMENT}:
                raise ValueError(
                    f"BenchmarkItem {self.benchmark_id} has zero numeric tokens but seed_alias_role={self.seed_alias_role.value}"
                )
            if self.seed_value_pattern == ValuePattern.DIRECT_LEVEL:
                raise ValueError(
                    f"BenchmarkItem {self.benchmark_id} has zero numeric tokens but seed_value_pattern=DIRECT_LEVEL"
                )
            if self.gold_alias_role in {AliasRole.DIRECT_VALUE_LABEL, AliasRole.CHANGE_STATEMENT}:
                raise ValueError(
                    f"BenchmarkItem {self.benchmark_id} has zero numeric tokens but gold_alias_role={self.gold_alias_role.value}"
                )
            if self.gold_value_pattern == ValuePattern.DIRECT_LEVEL:
                raise ValueError(
                    f"BenchmarkItem {self.benchmark_id} has zero numeric tokens but gold_value_pattern=DIRECT_LEVEL"
                )

        # Invariant C: CONCEPT_MENTION_ONLY cannot be DIRECT_LEVEL
        if self.seed_alias_role == AliasRole.CONCEPT_MENTION_ONLY and self.seed_value_pattern == ValuePattern.DIRECT_LEVEL:
            raise ValueError(f"CONCEPT_MENTION_ONLY cannot have ValuePattern.DIRECT_LEVEL in {self.benchmark_id}")
        if self.gold_alias_role == AliasRole.CONCEPT_MENTION_ONLY and self.gold_value_pattern == ValuePattern.DIRECT_LEVEL:
            raise ValueError(f"CONCEPT_MENTION_ONLY cannot have ValuePattern.DIRECT_LEVEL in {self.benchmark_id}")

        if self.review_status != ReviewStatus.GOLD_CONFIRMED:
            # gold_* MUST be None
            if (self.gold_concept is not None or self.gold_qualifiers is not None or
                self.gold_alias_role is not None or self.gold_value_pattern is not None or
                self.gold_valuation_eligibility is not None or self.gold_should_abstain is not None):
                raise ValueError(
                    f"BenchmarkItem {self.benchmark_id} has review_status={self.review_status.value}, "
                    f"so all gold_* fields must remain null until GOLD_CONFIRMED."
                )
        else:
            # GOLD_CONFIRMED requires complete gold fields
            if (self.gold_alias_role is None or self.gold_value_pattern is None or
                self.gold_valuation_eligibility is None or self.gold_should_abstain is None):
                raise ValueError(
                    f"BenchmarkItem {self.benchmark_id} is GOLD_CONFIRMED but missing complete gold fields."
                )

            # Conditional on abstention:
            # If gold_should_abstain == False, gold_concept must be non-null.
            # If gold_should_abstain == True, gold_concept may be null.
            if self.gold_should_abstain is False:
                if not self.gold_concept:
                    raise ValueError(
                        f"GOLD_CONFIRMED item {self.benchmark_id} with gold_should_abstain=False requires gold_concept"
                    )

            # Qualifier validation for confirmed non-abstaining valuation baseline items
            if self.gold_should_abstain is False and self.gold_concept:
                gold_q = self.gold_qualifiers or SemanticQualifiers()
                is_valuation_baseline = self.gold_valuation_eligibility in {
                    ValuationEligibility.ELIGIBLE,
                    ValuationEligibility.ELIGIBLE_WITH_QUALIFIER
                }

                # 1. continuing-operations metric -> scope must be explicit
                if "continuing" in self.normalized_label or "continuing" in self.full_sentence.lower():
                    if gold_q.scope == OperationScope.UNSPECIFIED:
                        raise ValueError(
                            f"GOLD_CONFIRMED item {self.benchmark_id} mentions continuing operations but gold scope is UNSPECIFIED"
                        )

                # 2. gross/net dividend -> tax_basis must be explicit
                if self.gold_concept in {"gross_dividend_per_share", "net_dividend_per_share", "dividend_per_share"}:
                    if is_valuation_baseline and gold_q.dividend_tax_basis == DividendTaxBasis.UNSPECIFIED:
                        raise ValueError(
                            f"GOLD_CONFIRMED item {self.benchmark_id} ({self.gold_concept}) used as valuation baseline requires explicit dividend_tax_basis"
                        )

                # 3. capex used as valuation baseline -> capex_basis must be explicit
                if self.gold_concept in {"total_capex", "expansion_capex", "maintenance_capex"}:
                    if is_valuation_baseline and gold_q.capex_basis == CapexBasis.UNSPECIFIED:
                        raise ValueError(
                            f"GOLD_CONFIRMED item {self.benchmark_id} ({self.gold_concept}) used as valuation baseline requires explicit capex_basis"
                        )

                # 4. debt/net debt used as valuation baseline -> lease_inclusion and basis_evidence must be explicit
                if self.gold_concept in {"reported_net_debt", "gross_debt", "interest_bearing_borrowings", "cash_and_cash_equivalents"}:
                    if is_valuation_baseline:
                        if gold_q.lease_inclusion == LeaseInclusion.UNSPECIFIED:
                            raise ValueError(
                                f"GOLD_CONFIRMED item {self.benchmark_id} ({self.gold_concept}) used as valuation baseline requires explicit lease_inclusion"
                            )
                        if gold_q.basis_evidence == BasisEvidence.UNSPECIFIED:
                            raise ValueError(
                                f"GOLD_CONFIRMED item {self.benchmark_id} ({self.gold_concept}) used as valuation baseline requires explicit basis_evidence"
                            )

                # 5. margin used as valuation baseline -> margin_denominator must be explicit
                if self.gold_concept in {"gross_margin", "trading_margin", "operating_margin", "ebitda_margin"}:
                    if is_valuation_baseline and gold_q.margin_denominator == MarginDenominator.UNSPECIFIED:
                        raise ValueError(
                            f"GOLD_CONFIRMED item {self.benchmark_id} ({self.gold_concept}) used as valuation baseline requires explicit margin_denominator"
                        )

                # 6. per-share metric -> dilution basis must be explicit where material
                if self.gold_concept in {"diluted_eps", "diluted_heps"} or "diluted" in self.normalized_label:
                    if is_valuation_baseline and gold_q.dilution_basis == DilutionBasis.UNSPECIFIED:
                        raise ValueError(
                            f"GOLD_CONFIRMED item {self.benchmark_id} ({self.gold_concept}) requires explicit dilution_basis"
                        )

            # Guidance cannot become historical actual baseline
            if self.gold_alias_role == AliasRole.GUIDANCE_STATEMENT:
                if self.gold_valuation_eligibility != ValuationEligibility.INFORMATIONAL_ONLY or not self.gold_should_abstain:
                    raise ValueError(
                        f"GOLD_CONFIRMED guidance item {self.benchmark_id} cannot become historical actual baseline"
                    )

        return self


# =============================================================================
# 3. Model-Agnostic Evaluator Interface
# =============================================================================

class ClassifierPrediction(BaseModel):
    """Uniform prediction output from any evaluated classifier (Kev, Jev, rule-based, etc.)."""
    benchmark_id: str
    predicted_concept: str | None = None
    concept_probabilities: dict[str, float] = Field(default_factory=dict)
    predicted_qualifiers: SemanticQualifiers = Field(default_factory=SemanticQualifiers)
    qualifier_probabilities: dict[str, float] = Field(default_factory=dict)
    predicted_alias_role: AliasRole | None = None
    predicted_value_pattern: ValuePattern | None = None
    predicted_valuation_eligibility: ValuationEligibility | None = None
    confidence: float = 1.0  # Overall confidence score in [0.0, 1.0]
    abstain: bool = False    # True if model abstains or indicates low confidence / requires context


class ThresholdMetrics(BaseModel):
    """Evaluation metrics at a specific confidence threshold."""
    threshold: float
    coverage: float
    accuracy: float
    unsafe_false_acceptance_rate: float
    abstention_rate: float
    attempted_count: int
    abstain_count: int
    correct_count: int
    unsafe_false_acceptance_count: int


class CalibrationBucket(BaseModel):
    """A confidence bin for calibration analysis."""
    bin_lower: float
    bin_upper: float
    sample_count: int
    average_confidence: float
    empirical_accuracy: float


class CalibrationReport(BaseModel):
    """Expected Calibration Error (ECE) and Brier score analysis."""
    brier_score: float
    expected_calibration_error: float
    max_calibration_error: float
    buckets: list[CalibrationBucket] = Field(default_factory=list)


class EvaluationResult(BaseModel):
    """Comprehensive evaluation report for a classifier run on the benchmark."""
    total_items: int
    attempted_items: int
    abstention_count: int
    coverage_rate: float
    abstention_rate: float

    # Core Accuracies (Evaluated on Attempted Items)
    concept_accuracy_on_attempted: float
    overall_concept_accuracy: float
    alias_role_accuracy: float
    value_pattern_accuracy: float
    valuation_eligibility_accuracy: float

    # Qualifier Accuracies (Attempted Items)
    qualifier_accuracies: dict[str, float] = Field(default_factory=dict)
    all_qualifiers_exact_match_accuracy: float

    # Abstention & Safety Metrics
    correct_abstention_count: int
    false_abstention_count: int
    unsafe_answer_on_abstain_count: int

    # Unsafe False Acceptance (Most Critical Metric)
    unsafe_false_acceptance_count: int
    unsafe_false_acceptance_rate: float

    # Threshold Curve Analysis
    threshold_metrics: list[ThresholdMetrics] = Field(default_factory=list)

    # Calibration Analysis
    calibration: CalibrationReport | None = None


# =============================================================================
# 4. Benchmark Evaluator Engine
# =============================================================================

class BenchmarkEvaluator:
    """Evaluates classifier predictions against benchmark truth (seed or gold targets)."""

    DEFAULT_THRESHOLDS: list[float] = [0.50, 0.70, 0.80, 0.90, 0.95, 0.97, 0.99]

    def __init__(self, benchmark_items: Sequence[BenchmarkItem]):
        self.benchmark_items = {item.benchmark_id: item for item in benchmark_items}

    def evaluate(
        self,
        predictions: Sequence[ClassifierPrediction],
        thresholds: Sequence[float] | None = None,
        target_mode: str = "seed"
    ) -> EvaluationResult:
        """Evaluates predictions and computes multi-dimensional semantic metrics."""
        if thresholds is None:
            thresholds = self.DEFAULT_THRESHOLDS

        pred_map = {p.benchmark_id: p for p in predictions}
        total = len(self.benchmark_items)
        if total == 0:
            raise ValueError("Cannot evaluate an empty benchmark.")

        attempted = 0
        abstentions = 0
        concept_correct_attempted = 0
        concept_correct_overall = 0
        role_correct = 0
        pattern_correct = 0
        eligibility_correct = 0

        qual_correct: dict[str, int] = {
            "scope": 0, "dilution": 0, "tax_basis": 0, "capex_basis": 0,
            "lease_inclusion": 0, "margin_denominator": 0, "attribution": 0
        }
        all_qual_correct = 0

        correct_abstentions = 0
        false_abstentions = 0
        unsafe_answers_on_abstain = 0
        unsafe_false_acceptances = 0

        confidences: list[float] = []
        accuracies: list[int] = []

        for b_id, item in self.benchmark_items.items():
            if target_mode == "gold":
                if item.gold_alias_role is None:
                    raise ValueError(f"Item {b_id} is not GOLD_CONFIRMED; cannot evaluate in 'gold' mode.")
                target_concept = item.gold_concept
                target_qualifiers = item.gold_qualifiers or SemanticQualifiers()
                target_role = item.gold_alias_role
                target_pattern = item.gold_value_pattern
                target_eligibility = item.gold_valuation_eligibility
                target_should_abstain = item.gold_should_abstain
            else:
                target_concept = item.seed_concept
                target_qualifiers = item.seed_qualifiers
                target_role = item.seed_alias_role
                target_pattern = item.seed_value_pattern
                target_eligibility = item.seed_valuation_eligibility
                target_should_abstain = item.seed_should_abstain

            pred = pred_map.get(b_id)
            if pred is None:
                # Missing prediction treated as unattempted abstention
                pred = ClassifierPrediction(benchmark_id=b_id, abstain=True, confidence=0.0)

            confidences.append(pred.confidence)

            # Check if model abstains
            if pred.abstain:
                abstentions += 1
                if target_should_abstain:
                    correct_abstentions += 1
                else:
                    false_abstentions += 1
                accuracies.append(1 if target_should_abstain else 0)
                continue

            # Model attempted item
            attempted += 1
            is_concept_match = (pred.predicted_concept == target_concept)
            if is_concept_match:
                concept_correct_attempted += 1
                concept_correct_overall += 1
                accuracies.append(1)
            else:
                accuracies.append(0)

            # Check unsafe answer when target says abstain
            if target_should_abstain:
                unsafe_answers_on_abstain += 1

            # Check role & pattern
            if pred.predicted_alias_role == target_role:
                role_correct += 1
            if pred.predicted_value_pattern == target_pattern:
                pattern_correct += 1
            if pred.predicted_valuation_eligibility == target_eligibility:
                eligibility_correct += 1

            # Check qualifiers
            pq = pred.predicted_qualifiers
            gq = target_qualifiers

            scope_m = (pq.scope == gq.scope)
            dil_m = (pq.dilution == gq.dilution)
            tax_m = (pq.tax_basis == gq.tax_basis)
            capex_m = (pq.capex_basis == gq.capex_basis)
            lease_m = (pq.lease_inclusion == gq.lease_inclusion)
            margin_m = (pq.margin_denominator == gq.margin_denominator)
            attr_m = (pq.attribution == gq.attribution)

            if scope_m: qual_correct["scope"] += 1
            if dil_m: qual_correct["dilution"] += 1
            if tax_m: qual_correct["tax_basis"] += 1
            if capex_m: qual_correct["capex_basis"] += 1
            if lease_m: qual_correct["lease_inclusion"] += 1
            if margin_m: qual_correct["margin_denominator"] += 1
            if attr_m: qual_correct["attribution"] += 1

            if all([scope_m, dil_m, tax_m, capex_m, lease_m, margin_m, attr_m]):
                all_qual_correct += 1

            # Unsafe False Acceptance
            is_admissible_claim = pred.predicted_valuation_eligibility in {
                ValuationEligibility.ELIGIBLE, ValuationEligibility.ELIGIBLE_WITH_QUALIFIER
            }
            gold_is_admissible = target_eligibility in {
                ValuationEligibility.ELIGIBLE, ValuationEligibility.ELIGIBLE_WITH_QUALIFIER
            }

            if target_should_abstain:
                unsafe_false_acceptances += 1
            elif not is_concept_match:
                unsafe_false_acceptances += 1
            elif is_admissible_claim and not gold_is_admissible:
                unsafe_false_acceptances += 1

        # Rate calculations
        cov_rate = round(attempted / total * 100, 2)
        abs_rate = round(abstentions / total * 100, 2)
        conc_acc_att = round(concept_correct_attempted / attempted * 100, 2) if attempted > 0 else 0.0
        conc_acc_all = round(concept_correct_overall / total * 100, 2)
        role_acc = round(role_correct / attempted * 100, 2) if attempted > 0 else 0.0
        pat_acc = round(pattern_correct / attempted * 100, 2) if attempted > 0 else 0.0
        elig_acc = round(eligibility_correct / attempted * 100, 2) if attempted > 0 else 0.0

        qual_accs = {
            k: round(v / attempted * 100, 2) if attempted > 0 else 0.0
            for k, v in qual_correct.items()
        }
        all_qual_acc = round(all_qual_correct / attempted * 100, 2) if attempted > 0 else 0.0
        ufa_rate = round(unsafe_false_acceptances / total * 100, 2)

        # Threshold curves
        threshold_metrics_list = self._compute_threshold_curves(predictions, thresholds, target_mode=target_mode)

        # Calibration analysis
        calibration_report = self._compute_calibration(confidences, accuracies)

        return EvaluationResult(
            total_items=total,
            attempted_items=attempted,
            abstention_count=abstentions,
            coverage_rate=cov_rate,
            abstention_rate=abs_rate,
            concept_accuracy_on_attempted=conc_acc_att,
            overall_concept_accuracy=conc_acc_all,
            alias_role_accuracy=role_acc,
            value_pattern_accuracy=pat_acc,
            valuation_eligibility_accuracy=elig_acc,
            qualifier_accuracies=qual_accs,
            all_qualifiers_exact_match_accuracy=all_qual_acc,
            correct_abstention_count=correct_abstentions,
            false_abstention_count=false_abstentions,
            unsafe_answer_on_abstain_count=unsafe_answers_on_abstain,
            unsafe_false_acceptance_count=unsafe_false_acceptances,
            unsafe_false_acceptance_rate=ufa_rate,
            threshold_metrics=threshold_metrics_list,
            calibration=calibration_report
        )

    def _compute_threshold_curves(
        self,
        predictions: Sequence[ClassifierPrediction],
        thresholds: Sequence[float],
        target_mode: str = "seed"
    ) -> list[ThresholdMetrics]:
        """Calculates accuracy, coverage, and unsafe false acceptance across confidence thresholds."""
        pred_map = {p.benchmark_id: p for p in predictions}
        total = len(self.benchmark_items)
        results: list[ThresholdMetrics] = []

        for thresh in sorted(thresholds):
            attempted = 0
            correct = 0
            abstain = 0
            unsafe = 0

            for b_id, item in self.benchmark_items.items():
                if target_mode == "gold":
                    target_concept = item.gold_concept
                    target_eligibility = item.gold_valuation_eligibility
                    target_should_abstain = item.gold_should_abstain
                else:
                    target_concept = item.seed_concept
                    target_eligibility = item.seed_valuation_eligibility
                    target_should_abstain = item.seed_should_abstain

                pred = pred_map.get(b_id)
                if pred is None or pred.abstain or pred.confidence < thresh:
                    abstain += 1
                else:
                    attempted += 1
                    is_correct = (pred.predicted_concept == target_concept)
                    if is_correct:
                        correct += 1

                    is_admissible_claim = pred.predicted_valuation_eligibility in {
                        ValuationEligibility.ELIGIBLE, ValuationEligibility.ELIGIBLE_WITH_QUALIFIER
                    }
                    gold_is_admissible = target_eligibility in {
                        ValuationEligibility.ELIGIBLE, ValuationEligibility.ELIGIBLE_WITH_QUALIFIER
                    }

                    if target_should_abstain or not is_correct or (is_admissible_claim and not gold_is_admissible):
                        unsafe += 1

            cov = round(attempted / total * 100, 2)
            acc = round(correct / attempted * 100, 2) if attempted > 0 else 0.0
            ufa_r = round(unsafe / total * 100, 2)
            abs_r = round(abstain / total * 100, 2)

            results.append(ThresholdMetrics(
                threshold=thresh,
                coverage=cov,
                accuracy=acc,
                unsafe_false_acceptance_rate=ufa_r,
                abstention_rate=abs_r,
                attempted_count=attempted,
                abstain_count=abstain,
                correct_count=correct,
                unsafe_false_acceptance_count=unsafe
            ))
        return results

    def _compute_calibration(
        self,
        confidences: list[float],
        accuracies: list[int],
        num_bins: int = 10
    ) -> CalibrationReport:
        """Calculates Brier score, ECE, and calibration bins."""
        if not confidences:
            return CalibrationReport(brier_score=0.0, expected_calibration_error=0.0, max_calibration_error=0.0)

        n = len(confidences)
        # Brier score = (1/n) * sum((confidence - accuracy)^2)
        brier = sum((c - a) ** 2 for c, a in zip(confidences, accuracies)) / n

        # Binning for ECE
        buckets: list[CalibrationBucket] = []
        bin_size = 1.0 / num_bins
        total_ece = 0.0
        max_ce = 0.0

        for i in range(num_bins):
            b_lower = i * bin_size
            b_upper = (i + 1) * bin_size
            bin_confs = [c for c, a in zip(confidences, accuracies) if b_lower <= c < b_upper or (i == num_bins - 1 and c == 1.0)]
            bin_accs = [a for c, a in zip(confidences, accuracies) if b_lower <= c < b_upper or (i == num_bins - 1 and c == 1.0)]

            cnt = len(bin_confs)
            if cnt > 0:
                avg_conf = sum(bin_confs) / cnt
                emp_acc = sum(bin_accs) / cnt
                gap = abs(avg_conf - emp_acc)
                total_ece += (cnt / n) * gap
                if gap > max_ce:
                    max_ce = gap
                buckets.append(CalibrationBucket(
                    bin_lower=round(b_lower, 2),
                    bin_upper=round(b_upper, 2),
                    sample_count=cnt,
                    average_confidence=round(avg_conf, 4),
                    empirical_accuracy=round(emp_acc, 4)
                ))
            else:
                buckets.append(CalibrationBucket(
                    bin_lower=round(b_lower, 2),
                    bin_upper=round(b_upper, 2),
                    sample_count=0,
                    average_confidence=0.0,
                    empirical_accuracy=0.0
                ))

        return CalibrationReport(
            brier_score=round(brier, 4),
            expected_calibration_error=round(total_ece, 4),
            max_calibration_error=round(max_ce, 4),
            buckets=buckets
        )


# =============================================================================
# 5. Stratified Sampler & Dataset Builder
# =============================================================================

CHANGE_KEYWORDS = ["increased by", "decreased by", "grew by", "declined by", "rose by", "improved to", "up by", "down by"]
GUIDANCE_KEYWORDS = [
    "anticipates that it will report",
    "anticipates that",
    "anticipates to report",
    "expects to report",
    "expect to report",
    "expected to report",
    "expected to be",
    "is expected to",
    "are expected to",
    "forecast",
    "guidance",
    "trading statement",
    "range of",
    "look forward",
    "projected",
    "outlook",
]

CHANGE_VERBS = [
    "increase", "increased", "increases", "increasing",
    "decrease", "decreased", "decreases", "decreasing",
    "grew", "grow", "growth",
    "declined", "decline", "declining",
    "rose", "rise", "rising",
    "fell", "fall", "falling",
    "improved", "improve", "improving",
    "reduced", "reduce", "reducing",
    "up by", "down by",
]

CRITICAL_FAMILIES = {
    "revenue": ["revenue", "turnover", "sales", "retail sales", "merchandise sales", "sale of merchandise"],
    "profit": ["trading profit", "operating profit", "ebit", "pbit", "ebitda", "adjusted ebitda", "underlying ebitda", "normalised ebitda"],
    "per_share": ["eps", "diluted eps", "heps", "diluted heps"],
    "cash_flow": ["cash generated from operations", "working capital", "capex", "capital expenditure", "depreciation", "amortisation"],
    "debt": ["net debt", "net cash", "borrowings", "interest-bearing debt", "lease liabilities"],
    "shares": ["shares in issue", "treasury shares", "weighted average shares", "diluted weighted average shares"],
    "dividends": ["dividend per share", "gross dividend", "net dividend", "interim dividend", "final dividend", "annual dividend"],
    "margins": ["gross margin", "trading margin", "operating margin", "ebitda margin"]
}

CURRENCY_MAP = {
    "R": "ZAR",
    "ZAR": "ZAR",
    "$": "USD",
    "USD": "USD",
    "US$": "USD",
    "€": "EUR",
    "EUR": "EUR",
    "£": "GBP",
    "GBP": "GBP",
}

SCALE_MAP = {
    "billion": "billion",
    "bn": "billion",
    "million": "million",
    "m": "million",
    "thousand": "thousand",
    "k": "thousand",
    "cents": "cents",
    "cent": "cents",
    "c": "cents",
}

NUMERIC_TOKEN_REGEX = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?P<prefix>(?:\b(?:US\$|USD|EUR|GBP|ZAR)\b|R(?=\s*[+\-\u2013\u2014]?\s*\d)|[\$€£])\s*)?"
    r"(?P<sign>[+\-\u2013\u2014])?\s*"
    r"(?P<num>\d{1,3}(?:[ \u00a0]\d{3}(?!\d))+(?:[.,]\d+)?|\d{1,3}(?:,\d{3}(?!\d))+(?:\.\d+)?|\d+[.,]\d+|\d+)"
    r"(?P<suffix>%(?:\s*points?)?|\s*(?:billion|milli?on|cents?|c\b|bn\b|m\b|thousand|k\b))?",
    re.IGNORECASE
)

DATE_EXPRESSION_REGEX = re.compile(
    r"\b(?P<day>\d{1,2})\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(?P<year>\d{4})\b",
    re.IGNORECASE
)

SECTION_OR_LIST_START_REGEX = re.compile(
    r"^\s*(?:[•\-*–—\s]*)(?:"
    r"(?P<section>\d+(?:\.\d+)+\.?)"
    r"|(?P<sec_dot>\d+\.)(?!\d)"
    r"|(?P<paren_num>\(?\d+\))"
    r"|(?P<paren_alpha>\(?[a-zA-Z]\))"
    r")(?:\s+|$)"
)


def _is_ambiguous_single_comma(num_str: str) -> bool:
    cleaned = num_str.replace(' ', '').replace('\u00a0', '')
    parts = cleaned.split(',')
    return (
        '.' not in cleaned
        and len(parts) == 2
        and all(part.isdigit() for part in parts)
        and len(parts[1]) == 3
    )


def _infer_sentence_comma_convention(matches: Sequence[re.Match]) -> str | None:
    decimal_evidence = False
    thousands_evidence = False
    for match in matches:
        number = (match.group('num') or '').replace(' ', '').replace('\u00a0', '')
        if ',' not in number or '.' in number:
            continue
        parts = number.split(',')
        if len(parts) > 2 and all(len(part) == 3 for part in parts[1:]):
            thousands_evidence = True
        elif len(parts) == 2 and len(parts[1]) != 3:
            decimal_evidence = True
    if decimal_evidence == thousands_evidence:
        return None
    return 'decimal' if decimal_evidence else 'thousands'


def normalize_number_string(
    num_str: str,
    *,
    comma_convention: str | None = None,
    decimal_evidence: bool = False,
    thousands_evidence: bool = False,
) -> float | None:
    """Normalize a number without guessing an ambiguous single-comma format.

    Repeated three-digit comma groups are thousands separators. A single comma
    with a non-three-digit tail is decimal. A single three-digit tail requires
    explicit suffix or surrounding-format evidence; otherwise None keeps the
    raw token available while marking its interpretation as ambiguous.
    """
    cleaned = num_str.replace(" ", "").replace("\u00a0", "")
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(".") > cleaned.rfind(","):
            cleaned = cleaned.replace(",", "")
        else:
            cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        parts = cleaned.split(",")
        if len(parts) > 2 and all(len(p) == 3 for p in parts[1:]):
            cleaned = "".join(parts)
        elif _is_ambiguous_single_comma(cleaned):
            if decimal_evidence or comma_convention == 'decimal':
                cleaned = '.'.join(parts)
            elif thousands_evidence or comma_convention == 'thousands':
                cleaned = ''.join(parts)
            else:
                return None
        elif len(parts) == 2 and len(parts[1]) != 3:
            cleaned = f"{parts[0]}.{parts[1]}"
        else:
            cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_detected_numeric_tokens(sentence: str) -> list[DetectedNumericToken]:
    """Extracts typed numeric tokens from JSE financial sentence context with scale, currency, and unit metadata."""
    tokens: list[DetectedNumericToken] = []
    sent_lower = sentence.lower()

    # Detect document section numbers or list markers at sentence start
    sec_spans: list[tuple[int, int]] = []
    sec_match = SECTION_OR_LIST_START_REGEX.match(sentence)
    if sec_match:
        sec_raw = sec_match.group(0).strip()
        is_sec = bool(sec_match.group("section") or sec_match.group("sec_dot"))
        tok_type = NumericTokenType.SECTION_NUMBER if is_sec else NumericTokenType.LIST_MARKER
        sec_spans.append((sec_match.start(), sec_match.end()))
        tokens.append(DetectedNumericToken(
            raw_text=sec_raw,
            normalized_numeric_value=None,
            token_type=tok_type,
            char_start=sec_match.start(),
            char_end=sec_match.end(),
        ))

    # Find date spans to accurately classify calendar days and years
    date_spans: set[tuple[int, int]] = set()
    for dm in DATE_EXPRESSION_REGEX.finditer(sentence):
        date_spans.add(dm.span("day"))
        date_spans.add(dm.span("year"))

    numeric_matches = list(NUMERIC_TOKEN_REGEX.finditer(sentence))
    comma_convention = _infer_sentence_comma_convention(numeric_matches)

    for match in numeric_matches:
        raw_full = match.group(0).strip()
        if not raw_full:
            continue

        start_idx, end_idx = match.span()
        # Exclude numeric tokens covered by document section numbers / list markers
        if any(s <= start_idx and end_idx <= e for s, e in sec_spans):
            continue

        prefix = (match.group("prefix") or "").strip()
        sign = (match.group("sign") or "").strip()
        num_part = (match.group("num") or "").strip()
        suffix = (match.group("suffix") or "").strip()

        suffix_lower = suffix.lower()
        explicit_decimal_evidence = bool(
            suffix_lower.startswith('%')
            or suffix_lower.strip() in SCALE_MAP
        )
        num_val = normalize_number_string(
            num_part,
            comma_convention=comma_convention,
            decimal_evidence=explicit_decimal_evidence,
        )
        ambiguous_number = num_val is None and _is_ambiguous_single_comma(num_part)
        if num_val is None and not ambiguous_number:
            continue
        if sign in {"-", "–", "—"}:
            if num_val is not None:
                num_val = -abs(num_val)

        # Detect currency
        currency = None
        if prefix:
            clean_pref = prefix.strip()
            currency = CURRENCY_MAP.get(clean_pref.upper(), clean_pref.upper())

        # Detect scale and percentage
        scale = None
        is_percentage = False
        is_per_share = False

        if suffix:
            s_clean = suffix.strip().lower()
            if s_clean.startswith("%"):
                is_percentage = True
            elif s_clean in SCALE_MAP:
                scale = SCALE_MAP[s_clean]
                if scale == "cents":
                    is_per_share = True

        # Lookahead for cents if not in suffix
        lookahead = sentence[end_idx:end_idx + 20].lower()
        if not scale and not is_percentage:
            if re.match(r"^\s*cents?\b", lookahead) or re.match(r"^\s*(?:c\b|cps\b)", lookahead):
                scale = "cents"
                is_per_share = True
                m_cents = re.search(r"^\s*(?:cents?|cps|c\b)", lookahead)
                if m_cents:
                    end_idx += m_cents.end()
                raw_full = f"{raw_full} cents"

        # Check if year or part of date
        is_date_or_year = False
        num_span = match.span("num")
        for ds_s, ds_e in date_spans:
            if ds_s <= num_span[0] and num_span[1] <= ds_e:
                is_date_or_year = True
                break

        if not is_date_or_year and not currency and not is_percentage and not scale:
            if re.fullmatch(r"\d{4}", num_part):
                val_int = int(num_part)
                if 1990 <= val_int <= 2040:
                    is_date_or_year = True
            pre_text = sentence[max(0, start_idx - 6):start_idx].upper()
            if any(pre_text.endswith(p) for p in ["FY", "Q1", "Q2", "Q3", "Q4", "H1", "H2"]):
                is_date_or_year = True

        # Check if in range clause
        lookbehind = sentence[max(0, start_idx - 35):start_idx].lower()
        is_in_range = ("between" in lookbehind or "range of" in lookbehind or "to" in lookbehind) and (
            "between" in sent_lower or "range of" in sent_lower or "range" in sent_lower
        )

        if ambiguous_number:
            token_type = NumericTokenType.AMBIGUOUS_NUMBER_FORMAT
        elif is_date_or_year:
            token_type = NumericTokenType.YEAR_OR_DATE
        elif is_percentage:
            token_type = NumericTokenType.PERCENTAGE
        elif currency:
            token_type = NumericTokenType.CURRENCY_LEVEL
        elif is_per_share or scale == "cents":
            token_type = NumericTokenType.PER_SHARE_LEVEL
        elif is_in_range and not scale and not currency:
            token_type = NumericTokenType.RANGE_BOUND
        elif scale in {"million", "billion", "thousand"}:
            token_type = NumericTokenType.CURRENCY_LEVEL if currency else NumericTokenType.PLAIN_LEVEL
        elif num_val is not None:
            token_type = NumericTokenType.PLAIN_LEVEL
        else:
            token_type = NumericTokenType.OTHER

        tokens.append(DetectedNumericToken(
            raw_text=raw_full,
            normalized_numeric_value=num_val,
            token_type=token_type,
            currency=currency,
            scale=scale,
            is_percentage=is_percentage,
            is_per_share=is_per_share,
            char_start=start_idx,
            char_end=end_idx,
        ))

    return tokens


def resolve_nested_alias_spans(matches: list[tuple[int, int, str, Any]]) -> list[tuple[int, int, str, Any]]:
    """Resolves overlapping matches by preferring the longest semantic span when one match is entirely nested.
    
    Each match is a tuple: (start_offset, end_offset, label, *extra).
    """
    sorted_matches = sorted(matches, key=lambda m: (-(m[1] - m[0]), m[0]))
    kept: list[tuple[int, int, str, Any]] = []

    for cand in sorted_matches:
        cand_start, cand_end = cand[0], cand[1]
        contained = False
        for k in kept:
            k_start, k_end = k[0], k[1]
            if k_start <= cand_start and cand_end <= k_end and (k_end - k_start) > (cand_end - cand_start):
                contained = True
                break
        if not contained:
            kept.append(cand)

    return sorted(kept, key=lambda m: m[0])


LEXICAL_CONNECTORS_AFTER = re.compile(
    r"^\s*(?:of|at|to|from|between|was|is|were|amounted\s+to|increased\s+to|decreased\s+to|improved\s+to|fell\s+to|rose\s+to|reached|stood\s+at|by|:|=)\s*",
    re.IGNORECASE
)

PER_SHARE_SUFFIX = re.compile(
    r"^\s+per\s+(?:ordinary\s+|weighted\s+average\s+|diluted\s+|ordinary\s+issued\s+)?shares?\b",
    re.IGNORECASE
)

CLAUSE_BOUNDARY_REGEX = re.compile(
    r'[;)]|\b(?:as|while|whereas|but|and)\b',
    re.IGNORECASE,
)


def _numeric_alias_affinity(
    concept_id: str | None,
    normalized_label: str,
    token: DetectedNumericToken,
) -> int:
    label = normalized_label.lower()
    is_percentage = token.is_percentage or token.token_type == NumericTokenType.PERCENTAGE
    is_margin = concept_id in {'gross_margin', 'trading_margin', 'operating_margin', 'ebitda_margin'} or 'margin' in label
    is_per_share = concept_id in {
        'eps', 'heps', 'diluted_eps', 'diluted_heps', 'dividend_per_share',
        'nav_per_share', 'cash_flow_per_share',
    } or 'per share' in label
    is_currency = concept_id in {
        'accounting_revenue', 'trading_profit', 'operating_profit', 'ebit',
        'pbit', 'ebitda', 'reported_net_debt', 'cash_and_cash_equivalents',
        'total_capex',
    } or any(word in label for word in ('revenue', 'profit', 'ebit', 'capex', 'debt', 'cash'))
    is_share_count = concept_id in {
        'issued_shares_current', 'treasury_shares', 'wanos', 'diluted_wanos',
    } or 'shares in issue' in label or 'ordinary shares' in label

    if is_margin:
        return 5 if is_percentage else -5
    if is_per_share:
        if token.token_type == NumericTokenType.PER_SHARE_LEVEL or token.scale == 'cents':
            return 5
        if token.token_type == NumericTokenType.CURRENCY_LEVEL and token.scale in {'million', 'billion'}:
            return -5
        return 2 if not is_percentage else 1
    if is_currency:
        if is_percentage:
            return 2
        if token.token_type == NumericTokenType.CURRENCY_LEVEL or token.scale in {'million', 'billion', 'thousand'}:
            return 5
        return 3
    if is_share_count:
        return -5 if token.currency or is_percentage else 5
    return 2


def _numeric_owner_score(
    sentence: str,
    alias_span: tuple[int, int, str, str | None],
    token: DetectedNumericToken,
) -> tuple[int, int, int]:
    start, end, label, concept_id = alias_span
    token_start = token.char_start if token.char_start is not None else 0
    token_end = token.char_end if token.char_end is not None else token_start + len(token.raw_text)
    if token_start >= end:
        between = sentence[end:token_start]
        distance = token_start - end
        connector = bool(LEXICAL_CONNECTORS_AFTER.search(between))
    elif token_end <= start:
        between = sentence[token_end:start]
        distance = start - token_end
        connector = bool(re.search(r'\b(?:of|was|is|were)\s*$', between, re.IGNORECASE))
    else:
        between = ''
        distance = 0
        connector = True
    boundaries = len(CLAUSE_BOUNDARY_REGEX.findall(between))
    affinity = _numeric_alias_affinity(concept_id, label, token)
    score = affinity * 100 + (40 if connector else 0) - boundaries * 250 - distance
    return score, -boundaries, -distance


def associate_numeric_tokens(
    alias_text: str,
    alias_start_in_sent: int,
    alias_end_in_sent: int,
    sentence: str,
    concept_id: str | None,
    norm_label: str,
    tokens: list[DetectedNumericToken],
    competing_alias_spans: Sequence[tuple[int, int, str, str | None]] | None = None,
) -> tuple[str | None, str | None, float, str]:
    """Deterministically associates detected numeric tokens with matched alias based on distance, connectors, and unit compatibility."""
    current_span = (alias_start_in_sent, alias_end_in_sent, norm_label, concept_id)
    ownership_spans = [current_span]
    for span in competing_alias_spans or ():
        if span[:3] != current_span[:3]:
            ownership_spans.append(span)

    valid_candidates = []
    for tok in tokens:
        if tok.token_type in (
            NumericTokenType.YEAR_OR_DATE,
            NumericTokenType.SECTION_NUMBER,
            NumericTokenType.LIST_MARKER,
            NumericTokenType.OTHER,
            NumericTokenType.AMBIGUOUS_NUMBER_FORMAT,
        ):
            continue
        if len(ownership_spans) > 1:
            owner = max(
                ownership_spans,
                key=lambda span: _numeric_owner_score(sentence, span, tok),
            )
            if owner[:3] != current_span[:3]:
                continue
        valid_candidates.append(tok)

    if not valid_candidates:
        return None, None, 1.0, "No valid numeric metric candidates found in sentence context"

    norm_lower = norm_label.lower()
    is_margin = (concept_id in {"gross_margin", "trading_margin", "operating_margin", "ebitda_margin"}) or ("margin" in norm_lower)
    is_per_share = (concept_id in {"eps", "heps", "diluted_eps", "diluted_heps", "dividend_per_share", "nav_per_share", "cash_flow_per_share"}) or ("per share" in norm_lower)
    is_currency = (concept_id in {"accounting_revenue", "trading_profit", "operating_profit", "ebit", "pbit", "ebitda", "reported_net_debt", "cash_and_cash_equivalents", "total_capex"}) or any(k in norm_lower for k in ["revenue", "profit", "ebit", "capex", "debt", "cash"])
    is_share_count = (concept_id in {"issued_shares_current", "treasury_shares", "wanos", "diluted_wanos"}) or ("shares in issue" in norm_lower or "ordinary shares" in norm_lower)

    scored = []
    for tok in valid_candidates:
        t_start = tok.char_start if tok.char_start is not None else sentence.find(tok.raw_text.replace(" cents", ""))
        t_end = tok.char_end if tok.char_end is not None else (t_start + len(tok.raw_text) if t_start != -1 else 0)
        if t_start == -1:
            t_start = 0
            t_end = len(tok.raw_text)

        is_after = t_start >= alias_end_in_sent
        dist = t_start - alias_end_in_sent if is_after else alias_start_in_sent - t_end

        # Check connector
        between_text = sentence[alias_end_in_sent:t_start] if is_after else sentence[t_end:alias_start_in_sent]
        has_connector = bool(LEXICAL_CONNECTORS_AFTER.search(between_text)) if is_after else bool(re.search(r"\b(?:of|was|is|were)\s*$", between_text, re.I))

        # Check unit compatibility
        compatible = True
        is_change_type = tok.is_percentage or tok.token_type == NumericTokenType.PERCENTAGE

        if is_margin:
            # Margins must be percentage
            if not is_change_type:
                compatible = False
        elif is_per_share:
            # Per-share metrics prefer cents / per-share; millions/billions currency are incompatible
            if tok.token_type == NumericTokenType.CURRENCY_LEVEL and tok.scale in {"million", "billion"}:
                compatible = False
        elif is_currency:
            # Aggregate currency metrics: percentage is rate/change, not metric level
            if is_change_type:
                compatible = False
        elif is_share_count:
            # Share counts: currency and percentages are incompatible
            if tok.currency or is_change_type:
                compatible = False

        scored.append({
            "token": tok,
            "span": (t_start, t_end),
            "is_after": is_after,
            "dist": dist,
            "has_connector": has_connector,
            "compatible": compatible,
            "is_change_type": is_change_type,
        })

    metric_cand = None
    change_cand = None
    reasons = []

    # Find candidate metric token: prefer compatible, has_connector, is_after, lowest dist
    metric_candidates = [c for c in scored if c["compatible"] and (not c["is_change_type"] or is_margin)]
    if metric_candidates:
        metric_candidates.sort(key=lambda c: (-int(c["has_connector"]), -int(c["is_after"]), c["dist"]))
        best_m = metric_candidates[0]
        metric_cand = best_m["token"].raw_text
        reasons.append(f"Associated metric level '{metric_cand}' (dist={best_m['dist']}, connector={best_m['has_connector']}, compatible=True)")

    # Find candidate change token
    change_candidates = [c for c in scored if c["is_change_type"] and not is_margin]
    if change_candidates:
        change_candidates.sort(key=lambda c: (-int(c["has_connector"]), -int(c["is_after"]), c["dist"]))
        best_c = change_candidates[0]
        change_cand = best_c["token"].raw_text
        reasons.append(f"Associated change rate '{change_cand}'")

    conf = 0.95 if (metric_cand or change_cand) else 0.50
    return metric_cand, change_cand, conf, "; ".join(reasons)


def classify_benchmark_item_heuristics(
    norm: str,
    raw: str,
    sentence: str,
    concept_id: str | None,
    dict_status: AliasStatus,
    qualifiers: SemanticQualifiers,
    nums: list[str] | None = None,
    typed_nums: list[DetectedNumericToken] | None = None,
    previous_sentence: str | None = None,
    next_sentence: str | None = None,
    nearby_heading: str | None = None,
    candidate_metric_token: str | None = None,
    candidate_change_token: str | None = None,
) -> tuple[AliasRole, ValuePattern, ValuationEligibility, bool, ReviewStatus, BenchmarkDifficulty, str]:
    """Applies strict deterministic rules to seed benchmark items, maintaining REVIEW_REQUIRED for ambiguities."""
    sent_lower = sentence.lower()
    norm_lower = norm.lower()
    raw_lower = raw.lower()

    if typed_nums is None:
        typed_nums = parse_detected_numeric_tokens(sentence)
    if nums is None:
        nums = [t.raw_text for t in typed_nums]

    # Auto-associate numeric tokens if not explicitly passed
    if candidate_metric_token is None and typed_nums:
        alias_start_in_sent = sentence.find(raw)
        alias_end_in_sent = alias_start_in_sent + len(raw) if alias_start_in_sent != -1 else len(raw)
        cand_m, cand_c, _, _ = associate_numeric_tokens(
            alias_text=raw,
            alias_start_in_sent=alias_start_in_sent if alias_start_in_sent != -1 else 0,
            alias_end_in_sent=alias_end_in_sent,
            sentence=sentence,
            concept_id=concept_id,
            norm_label=norm,
            tokens=typed_nums,
        )
        candidate_metric_token = cand_m
        if candidate_change_token is None:
            candidate_change_token = cand_c

    # Candidate metric numbers exclude YEAR_OR_DATE, OTHER, SECTION_NUMBER, LIST_MARKER
    metric_tokens = [
        t for t in typed_nums
        if t.token_type not in (
            NumericTokenType.YEAR_OR_DATE,
            NumericTokenType.OTHER,
            NumericTokenType.SECTION_NUMBER,
            NumericTokenType.LIST_MARKER,
            NumericTokenType.AMBIGUOUS_NUMBER_FORMAT,
        )
    ]
    has_metric_numbers = bool(metric_tokens)

    # Concept Specificity (Requirement #4 & #8: separate per-share vs aggregate concepts, extend per-share variants)
    PER_SHARE_PATTERN = r"per\s+(?:ordinary\s+|weighted\s+average\s+|diluted\s+|ordinary\s+issued\s+)?shares?"
    if re.search(rf"\bheadline\s+(?:earnings|loss)\s+{PER_SHARE_PATTERN}\b", norm_lower) or re.search(rf"\bheadline\s+(?:earnings|loss)\s+{PER_SHARE_PATTERN}\b", raw_lower):
        concept_id = "diluted_heps" if ("diluted" in norm_lower or "diluted" in raw_lower) else "heps"
    elif re.search(rf"\b(?:basic\s+)?(?:earnings|loss)\s+{PER_SHARE_PATTERN}\b", norm_lower) or re.search(rf"\b(?:basic\s+)?(?:earnings|loss)\s+{PER_SHARE_PATTERN}\b", raw_lower):
        concept_id = "diluted_eps" if ("diluted" in norm_lower or "diluted" in raw_lower) else "eps"
    elif re.search(rf"\b(?:dividend|dividends)\s+{PER_SHARE_PATTERN}\b", norm_lower) or re.search(rf"\b(?:dividend|dividends)\s+{PER_SHARE_PATTERN}\b", raw_lower):
        concept_id = "dividend_per_share"
    elif re.search(rf"\b(?:nav|net\s+asset\s+value)\s+{PER_SHARE_PATTERN}\b", norm_lower) or re.search(rf"\b(?:nav|net\s+asset\s+value)\s+{PER_SHARE_PATTERN}\b", raw_lower):
        concept_id = "nav_per_share"
    elif re.search(rf"\bcash\s+flow\s+{PER_SHARE_PATTERN}\b", norm_lower) or re.search(rf"\bcash\s+flow\s+{PER_SHARE_PATTERN}\b", raw_lower):
        concept_id = "cash_flow_per_share"
    elif norm_lower in {"headline earnings", "earnings", "profit", "operating profit", "trading profit", "nav", "net asset value", "cash flow", "cash generated from operations"}:
        if concept_id in {"eps", "heps", "diluted_eps", "diluted_heps", "dividend_per_share", "nav_per_share", "cash_flow_per_share"}:
            concept_id = None

    # Guidance Detection using context window (Requirement #1)
    context_to_check = [sentence]
    if previous_sentence:
        context_to_check.append(previous_sentence)
    if next_sentence:
        context_to_check.append(next_sentence)
    if nearby_heading:
        context_to_check.append(nearby_heading)

    is_guidance = (
        any(any(k in s.lower() for k in GUIDANCE_KEYWORDS) for s in context_to_check)
        or any(k in norm_lower for k in ["guidance", "forecast", "expected", "projected", "outlook"])
    )

    # Change Detection (Requirement #6)
    has_change_verb = any(re.search(rf"\b{re.escape(v)}\b", sent_lower) for v in CHANGE_VERBS) or any(k in norm_lower for k in CHANGE_KEYWORDS)
    only_percentages = bool(metric_tokens) and all(t.is_percentage or t.token_type == NumericTokenType.PERCENTAGE for t in metric_tokens)
    has_both_rate_and_level = bool(metric_tokens) and any(t.is_percentage or t.token_type == NumericTokenType.PERCENTAGE for t in metric_tokens) and any(t.token_type in (NumericTokenType.CURRENCY_LEVEL, NumericTokenType.PER_SHARE_LEVEL, NumericTokenType.PLAIN_LEVEL) for t in metric_tokens)

    is_margin = (concept_id in {"gross_margin", "trading_margin", "operating_margin", "ebitda_margin"}) or ("margin" in norm_lower)

    # Determine Difficulty Category
    if "debt" in norm_lower or "borrowing" in norm_lower or "lease" in norm_lower:
        diff = BenchmarkDifficulty.DEBT_LEASE_AMBIGUITY
    elif "capex" in norm_lower or "capital expenditure" in norm_lower:
        diff = BenchmarkDifficulty.CAPEX_AMBIGUITY
    elif "share" in norm_lower or "shares" in norm_lower:
        diff = BenchmarkDifficulty.SHARES_AMBIGUITY
    elif any(k in norm_lower for k in ["trading profit", "operating profit", "ebit", "pbit"]):
        diff = BenchmarkDifficulty.PROFIT_EBIT_AMBIGUITY
    elif "continuing" in norm_lower or "discontinued" in norm_lower or norm_lower in {"sales", "turnover", "sales increased by"}:
        diff = BenchmarkDifficulty.SCOPE_AMBIGUITY
    elif "margin" in norm_lower or "working capital" in norm_lower:
        diff = BenchmarkDifficulty.BASIS_AMBIGUITY
    elif has_change_verb or (only_percentages and not is_margin):
        diff = BenchmarkDifficulty.CHANGE_STATEMENTS
    elif dict_status == AliasStatus.UNKNOWN:
        diff = BenchmarkDifficulty.UNKNOWN_LONG_TAIL
    else:
        diff = BenchmarkDifficulty.EASY_DIRECT

    # Invariants A, B, C, D, E: Sentences with NO usable numeric tokens cannot be direct extractions or change statements
    if not has_metric_numbers:
        role = AliasRole.CONCEPT_MENTION_ONLY
        pat = ValuePattern.UNKNOWN
        elig = ValuationEligibility.INFORMATIONAL_ONLY
        abstain = True
        status = ReviewStatus.REVIEW_REQUIRED
        note = f"Narrative mention of '{norm}' without usable numeric level (only dates/years or non-metric tokens detected)"
        return role, pat, elig, abstain, status, diff, note

    # 1. Guidance Statement (Requirement #1 & #5)
    if is_guidance:
        role = AliasRole.GUIDANCE_STATEMENT
        has_range = (
            "between" in sent_lower
            or "range of" in sent_lower
            or any(t.token_type == NumericTokenType.RANGE_BOUND for t in typed_nums)
            or (len(metric_tokens) >= 2 and any("between" in s.lower() for s in context_to_check))
        )
        pat = ValuePattern.RANGE if has_range else ValuePattern.DIRECT_LEVEL
        elig = ValuationEligibility.INFORMATIONAL_ONLY
        abstain = True
        status = ReviewStatus.AUTO_SEEDED if dict_status == AliasStatus.APPROVED else ReviewStatus.REVIEW_REQUIRED
        note = "Guidance / forward-looking trading statement; ineligible for historical actual baseline"
        return role, pat, elig, abstain, status, diff, note

    # Incompatible numeric association check (Requirement #6):
    # If candidate_metric_token is None and not a change statement, cannot be DIRECT_VALUE_LABEL
    if candidate_metric_token is None and not (has_change_verb or (only_percentages and not is_margin)):
        role = AliasRole.CONCEPT_MENTION_ONLY
        pat = ValuePattern.UNKNOWN
        elig = ValuationEligibility.REQUIRES_BASIS if is_margin else ValuationEligibility.INFORMATIONAL_ONLY
        abstain = True
        status = ReviewStatus.REVIEW_REQUIRED
        note = f"Concept '{norm}' lacks compatible numeric level in sentence context"
        return role, pat, elig, abstain, status, diff, note

    # 2. Change Statement (Requirement #6)
    is_change_statement = has_change_verb or (only_percentages and not is_margin)
    if is_change_statement:
        role = AliasRole.CHANGE_STATEMENT
        if only_percentages:
            pat = ValuePattern.CHANGE_RATE_ONLY
            elig = ValuationEligibility.INFORMATIONAL_ONLY
            abstain = True
            status = ReviewStatus.AUTO_SEEDED if dict_status == AliasStatus.APPROVED else ReviewStatus.REVIEW_REQUIRED
            note = "Change / directional reporting sentence with percentage-only rate; ineligible as absolute historical baseline"
            return role, pat, elig, abstain, status, diff, note
        elif "from" in sent_lower and "to" in sent_lower:
            pat = ValuePattern.FROM_TO_LEVEL
            elig = ValuationEligibility.INFORMATIONAL_ONLY
            abstain = False
            status = ReviewStatus.AUTO_SEEDED if dict_status == AliasStatus.APPROVED else ReviewStatus.REVIEW_REQUIRED
            note = "Change reporting sentence with from-to level compound structure"
            return role, pat, elig, abstain, status, diff, note
        elif has_both_rate_and_level:
            pat = ValuePattern.CHANGE_RATE_TO_LEVEL
            elig = ValuationEligibility.INFORMATIONAL_ONLY
            abstain = False
            status = ReviewStatus.AUTO_SEEDED if dict_status == AliasStatus.APPROVED else ReviewStatus.REVIEW_REQUIRED
            note = "Change reporting sentence with rate-to-level compound structure"
            return role, pat, elig, abstain, status, diff, note

    # 3. Margin Denominator Requirement (Requirement #7: do not infer denominator without explicit text evidence)
    if is_margin:
        explicit_denom = None
        if "merchandise sales" in sent_lower or "sale of merchandise" in sent_lower:
            explicit_denom = MarginDenominator.MERCHANDISE_SALES
        elif "retail sales" in sent_lower:
            explicit_denom = MarginDenominator.RETAIL_SALES
        elif "turnover" in sent_lower:
            explicit_denom = MarginDenominator.TURNOVER
        elif "of revenue" in sent_lower or "to revenue" in sent_lower or "on revenue" in sent_lower:
            explicit_denom = MarginDenominator.ACCOUNTING_REVENUE

        if explicit_denom is None:
            qualifiers.margin_denominator = MarginDenominator.UNSPECIFIED
            role = AliasRole.DIRECT_VALUE_LABEL
            pat = ValuePattern.DIRECT_LEVEL
            elig = ValuationEligibility.REQUIRES_BASIS
            abstain = True
            status = ReviewStatus.REVIEW_REQUIRED
            note = f"Margin concept '{norm}' lacks explicit denominator in source text; requires basis"
            return role, pat, elig, abstain, status, diff, note
        else:
            qualifiers.margin_denominator = explicit_denom

    # 4. Direct Value Label
    role = AliasRole.DIRECT_VALUE_LABEL
    pat = ValuePattern.DIRECT_LEVEL

    # Evaluate Valuation Eligibility and Review Status
    if dict_status == AliasStatus.APPROVED and concept_id:
        has_explicit_qualifiers = (
            qualifiers.scope != OperationScope.UNSPECIFIED
            or qualifiers.metric_basis != MetricBasis.UNSPECIFIED
            or qualifiers.margin_denominator != MarginDenominator.UNSPECIFIED
            or qualifiers.capex_basis != CapexBasis.UNSPECIFIED
            or qualifiers.lease_inclusion != LeaseInclusion.UNSPECIFIED
            or qualifiers.dilution != DilutionBasis.UNSPECIFIED
            or qualifiers.tax_basis != DividendTaxBasis.UNSPECIFIED
        )
        if has_explicit_qualifiers:
            elig = ValuationEligibility.ELIGIBLE_WITH_QUALIFIER
        else:
            elig = ValuationEligibility.ELIGIBLE
        abstain = False
        status = ReviewStatus.AUTO_SEEDED
        note = f"Approved canonical concept '{concept_id}' with verified explicit qualifiers"
    elif dict_status == AliasStatus.REQUIRES_CONTEXT:
        if "debt" in norm_lower or "borrowing" in norm_lower:
            elig = ValuationEligibility.REQUIRES_SOURCE_SECTION
            note = "Debt label lacks explicit IFRS 16 lease liability inclusion evidence; requires context"
        elif "capex" in norm_lower or "capital expenditure" in norm_lower:
            elig = ValuationEligibility.REQUIRES_BASIS
            note = "Capex label lacks cash payments vs additions distinction; requires context"
        elif "margin" in norm_lower:
            elig = ValuationEligibility.REQUIRES_BASIS
            note = "Margin label lacks explicit denominator; requires context"
        elif "operations" in norm_lower or "scope" in sent_lower:
            elig = ValuationEligibility.REQUIRES_SCOPE
            note = "Scope unverified; continuing vs total group operations requires context"
        else:
            elig = ValuationEligibility.REQUIRES_PERIOD
            note = "Context required to verify period type, scope, or accounting attribution"
        abstain = True
        status = ReviewStatus.REVIEW_REQUIRED
    elif dict_status == AliasStatus.AMBIGUOUS:
        abstain = True
        status = ReviewStatus.REVIEW_REQUIRED
        if any(k in norm_lower for k in ["debt", "borrowing", "lease", "taxation", "depreciation", "amortisation", "d&a", "cash and cash equivalents"]):
            elig = ValuationEligibility.REQUIRES_SOURCE_SECTION
            note = f"Ambiguous wording '{norm}' lacks balance sheet vs note presentation; requires source section"
        elif any(k in norm_lower for k in ["capex", "capital expenditure", "working capital", "weighted average", "margin"]):
            elig = ValuationEligibility.REQUIRES_BASIS
            note = f"Ambiguous wording '{norm}' lacks accounting basis (cash vs additions, movement vs balance); requires basis"
        elif any(k in norm_lower for k in ["shares", "share", "shares in issue"]):
            elig = ValuationEligibility.REQUIRES_PERIOD
            note = f"Ambiguous share wording '{norm}' lacks point-in-time vs period-end vs WANOS specification; requires period"
        elif any(k in norm_lower for k in ["sales", "turnover", "operating profit", "profit from operations", "pbt", "pbit", "ebit", "eps", "heps", "profit after tax"]):
            elig = ValuationEligibility.REQUIRES_SCOPE
            note = f"Ambiguous wording '{norm}' conflates operating definitions or segments; requires scope"
        else:
            elig = ValuationEligibility.REQUIRES_SCOPE
            note = f"Ambiguous wording '{norm}'; maps to multiple concepts; requires context"
    else:
        # UNKNOWN
        abstain = True
        status = ReviewStatus.REVIEW_REQUIRED
        elig = ValuationEligibility.REQUIRES_SCOPE
        note = f"Unknown / long-tail phrase '{norm}'; requires expert review"

    return role, pat, elig, abstain, status, diff, note


def extract_sentence_context(
    content: str,
    raw_label: str,
    target_line: str | None = None,
    target_line_idx: int | None = None
) -> tuple[str, str | None, str | None, str | None, list[str], list[DetectedNumericToken]]:
    """Extracts the containing sentence, prior sentence, following sentence, and detected numeric tokens."""
    lines = content.splitlines()

    if target_line_idx is None or target_line_idx < 0 or target_line_idx >= len(lines):
        target_line_idx = -1
        if target_line:
            clean_target = target_line.strip()
            for idx, l in enumerate(lines):
                if clean_target == l.strip():
                    target_line_idx = idx
                    break

        if target_line_idx == -1:
            for idx, l in enumerate(lines):
                if raw_label in l:
                    target_line_idx = idx
                    break

    if target_line_idx == -1:
        clean_content = content.replace("\r\n", "\n")
        sentences = re.split(r"(?<=[.!?])\s+", clean_content)
        for s_idx, s in enumerate(sentences):
            if raw_label.lower() in s.lower():
                full_s = s.strip()
                prev_s = sentences[s_idx - 1].strip() if s_idx > 0 else None
                next_s = sentences[s_idx + 1].strip() if s_idx < len(sentences) - 1 else None
                typed_toks = parse_detected_numeric_tokens(full_s)
                return full_s, prev_s, next_s, None, [t.raw_text for t in typed_toks], typed_toks
        typed_toks = parse_detected_numeric_tokens(raw_label)
        return raw_label, None, None, None, [t.raw_text for t in typed_toks], typed_toks

    full_s = lines[target_line_idx].strip()
    prev_s = lines[target_line_idx - 1].strip() if target_line_idx > 0 and lines[target_line_idx - 1].strip() else None
    next_s = lines[target_line_idx + 1].strip() if target_line_idx < len(lines) - 1 and lines[target_line_idx + 1].strip() else None

    # Detect list grammatical dependency for bullet items / list markers
    if re.match(r"^\s*(?:[•\-*–—]|\d+\.|\(?\d+\)|\(?[a-zA-Z]\))\s+", full_s):
        for back_idx in range(target_line_idx - 1, max(-1, target_line_idx - 10), -1):
            cand_line = lines[back_idx].strip()
            if not cand_line:
                continue
            if cand_line.endswith(":") or any(k in cand_line.lower() for k in GUIDANCE_KEYWORDS):
                prev_s = cand_line
                break

    # Detect heading
    heading = None
    for h_idx in range(target_line_idx - 1, max(-1, target_line_idx - 6), -1):
        cand_h = lines[h_idx].strip()
        if cand_h and (cand_h.isupper() or len(cand_h) < 40 or cand_h.endswith(":") or any(k in cand_h.lower() for k in ["trading statement", "results", "guidance"])):
            heading = cand_h
            break

    typed_toks = parse_detected_numeric_tokens(full_s)
    return full_s, prev_s, next_s, heading, [t.raw_text for t in typed_toks], typed_toks


# =============================================================================
# 6. Stratified Dataset Generation and Serialization
# =============================================================================

TRIGGER_WORDS = [
    "revenue", "sales", "turnover", "profit", "ebit", "ebitda", "heps", "eps", "loss",
    "dividend", "cash", "capex", "expenditure", "debt", "borrowing", "lease", "shares",
    "margin", "tax", "working capital", "depreciation", "amortisation", "nav", "asset",
    "earnings", "merchandise", "pbit", "pbt", "d&a", "inventor"
]


def build_stratified_benchmark(
    conn,
    alias_dict_path: Path | str,
    target_count: int = 820,
    max_per_label: int = 10,
    max_per_ticker: int = 20
) -> list[BenchmarkItem]:
    """Extracts a stratified benchmark candidate pool from PostgreSQL SENS with overlap suppression."""
    with open(alias_dict_path, "r", encoding="utf-8") as f:
        dict_data = json.load(f)

    alias_meta: dict[str, dict] = {}
    for a in dict_data["aliases"]:
        alias_meta[a["normalized_label"]] = a

    sorted_aliases = sorted(alias_meta.keys(), key=len, reverse=True)
    alias_regexes: list[tuple[str, re.Pattern]] = []
    for a in sorted_aliases:
        escaped = re.escape(a).replace(r"\ ", r"\s+")
        pat = re.compile(rf"(?i)\b{escaped}\b")
        alias_regexes.append((a, pat))

    cur = conn.cursor()
    cur.execute("SELECT sens_id, ticker, publication_datetime, source_document_id, content FROM sens ORDER BY sens_id;")
    rows = cur.fetchall()

    label_counts: Counter[str] = Counter()
    ticker_counts: Counter[str] = Counter()
    sampled_items: list[BenchmarkItem] = []
    seen_exact_occurrences: set[tuple[int, int, int, str]] = set()

    bench_idx = 1
    for sens_id, ticker, pub_dt, src_doc_id, content in rows:
        if not content or len(content) < 50:
            continue

        dt_str = pub_dt.strftime("%Y-%m-%d %H:%M") if pub_dt else "2025-01-01 00:00"
        lines = content.splitlines(keepends=True)
        line_offset = 0

        for line_idx, line_raw in enumerate(lines):
            line_len = len(line_raw)
            line_clean = line_raw.strip()
            current_line_start = line_offset
            line_offset += line_len

            if not line_clean or len(line_clean) < 15 or len(line_clean) > 350:
                continue

            line_lower = line_clean.lower()
            if not any(tw in line_lower for tw in TRIGGER_WORDS):
                continue

            # Find all alias matches on this line
            line_matches: list[tuple[int, int, str, str]] = []
            for norm_label, pat in alias_regexes:
                first_word = norm_label.split()[0]
                if first_word not in line_lower:
                    continue
                for m in pat.finditer(line_clean):
                    m_start, m_end = m.start(), m.end()
                    matched_text = m.group(0)

                    # Extended per-share recognition (Requirement #4)
                    post_text = line_clean[m_end:]
                    m_suff = PER_SHARE_SUFFIX.match(post_text)
                    if m_suff and norm_label in {
                        'headline earnings', 'earnings', 'profit', 'dividend', 'dividends',
                        'nav', 'net asset value', 'loss', 'basic loss', 'headline loss'
                    }:
                        m_end = m_end + m_suff.end()
                        matched_text = line_clean[m_start:m_end]
                        norm_label = normalize_label(matched_text)

                    line_matches.append((m_start, m_end, norm_label, matched_text))

            if not line_matches:
                continue

            # Resolve overlapping/nested spans: longest span suppresses strictly contained shorter matches
            resolved_matches = resolve_nested_alias_spans(line_matches)
            competing_alias_spans = [
                (
                    span_start,
                    span_end,
                    span_label,
                    (alias_meta.get(span_label) or {}).get('canonical_concept'),
                )
                for span_start, span_end, span_label, _ in resolved_matches
            ]

            for m_start, m_end, norm_label, raw_found in resolved_matches:
                if label_counts[norm_label] >= max_per_label:
                    continue
                if ticker_counts[ticker] >= max_per_ticker:
                    break

                # Source offset provenance (Requirement #5)
                alias_start_offset = current_line_start + m_start
                alias_end_offset = current_line_start + m_end
                sentence_start_offset = current_line_start
                sentence_end_offset = current_line_start + len(line_clean)
                source_line_index = line_idx

                # Deduplicate exact occurrences by stable span identity (sens_id, alias_start_offset, alias_end_offset, normalized_label)
                occ_key = (sens_id, alias_start_offset, alias_end_offset, norm_label)
                if occ_key in seen_exact_occurrences:
                    continue
                seen_exact_occurrences.add(occ_key)

                full_s, prev_s, next_s, heading, nums, typed_toks = extract_sentence_context(
                    content, raw_found, target_line=line_clean, target_line_idx=line_idx
                )

                # Look up alias in dictionary
                am = alias_meta.get(norm_label)
                if am:
                    dict_status = AliasStatus(am["status"])
                    concept_id = am["canonical_concept"]
                    q_dict = am.get("qualifiers", {})
                    qualifiers = SemanticQualifiers(**q_dict)
                else:
                    # Dynamic per-share alias or extended phrase
                    if "headline" in norm_label and "share" in norm_label:
                        concept_id = "diluted_heps" if "diluted" in norm_label else "heps"
                        dict_status = AliasStatus.APPROVED
                    elif "share" in norm_label and ("eps" in norm_label or "earnings" in norm_label or "loss" in norm_label):
                        concept_id = "diluted_eps" if "diluted" in norm_label else "eps"
                        dict_status = AliasStatus.APPROVED
                    elif "dividend" in norm_label and "share" in norm_label:
                        concept_id = "dividend_per_share"
                        dict_status = AliasStatus.APPROVED
                    elif "nav" in norm_label or ("net asset value" in norm_label and "share" in norm_label):
                        concept_id = "nav_per_share"
                        dict_status = AliasStatus.APPROVED
                    else:
                        dict_status = AliasStatus.UNKNOWN
                        concept_id = None
                    qualifiers = SemanticQualifiers()

                alias_start_in_sent = full_s.find(raw_found)
                alias_end_in_sent = alias_start_in_sent + len(raw_found) if alias_start_in_sent != -1 else m_end

                # Deterministic numeric token association (Requirement #6)
                cand_metric, cand_change, assoc_conf, assoc_reason = associate_numeric_tokens(
                    alias_text=raw_found,
                    alias_start_in_sent=alias_start_in_sent if alias_start_in_sent != -1 else 0,
                    alias_end_in_sent=alias_end_in_sent if alias_start_in_sent != -1 else len(raw_found),
                    sentence=full_s,
                    concept_id=concept_id,
                    norm_label=norm_label,
                    tokens=typed_toks,
                    competing_alias_spans=competing_alias_spans,
                )

                role, val_pat, elig, abstain, rev_status, diff, note = classify_benchmark_item_heuristics(
                    norm=norm_label,
                    raw=raw_found,
                    sentence=full_s,
                    concept_id=concept_id,
                    dict_status=dict_status,
                    qualifiers=qualifiers,
                    nums=nums,
                    typed_nums=typed_toks,
                    previous_sentence=prev_s,
                    next_sentence=next_s,
                    nearby_heading=heading,
                    candidate_metric_token=cand_metric,
                    candidate_change_token=cand_change,
                )

                item = BenchmarkItem(
                    benchmark_id=f"BENCH-{bench_idx:04d}",
                    sens_id=sens_id,
                    ticker=ticker,
                    publication_datetime=dt_str,
                    source_document_id=str(src_doc_id) if src_doc_id else None,
                    raw_label=raw_found,
                    normalized_label=norm_label,
                    full_sentence=full_s,
                    previous_sentence=prev_s,
                    next_sentence=next_s,
                    nearby_heading=heading,
                    detected_numeric_tokens=nums,
                    detected_typed_numeric_tokens=typed_toks,
                    source_line_index=source_line_index,
                    sentence_start_offset=sentence_start_offset,
                    sentence_end_offset=sentence_end_offset,
                    alias_start_offset=alias_start_offset,
                    alias_end_offset=alias_end_offset,
                    candidate_metric_token=cand_metric,
                    candidate_change_token=cand_change,
                    association_confidence=assoc_conf,
                    association_reason=assoc_reason,
                    current_dictionary_status=dict_status,
                    current_proposed_canonical_concept=concept_id,
                    current_qualifiers=qualifiers,
                    seed_concept=concept_id,
                    seed_qualifiers=qualifiers,
                    seed_alias_role=role,
                    seed_value_pattern=val_pat,
                    seed_valuation_eligibility=elig,
                    seed_should_abstain=abstain,
                    gold_concept=None,
                    gold_qualifiers=None,
                    gold_alias_role=None,
                    gold_value_pattern=None,
                    gold_valuation_eligibility=None,
                    gold_should_abstain=None,
                    review_status=rev_status,
                    difficulty_category=diff,
                    reviewer_notes=note
                )
                sampled_items.append(item)
                label_counts[norm_label] += 1
                ticker_counts[ticker] += 1
                bench_idx += 1

                if len(sampled_items) >= target_count:
                    break
            if len(sampled_items) >= target_count:
                break
        if len(sampled_items) >= target_count:
            break

    return sampled_items


def save_benchmark_json(items: Sequence[BenchmarkItem], path: Path | str, corpus_meta: dict | None = None) -> None:
    """Serializes benchmark items and metadata into formatted JSON atomically via temporary file replacement."""
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = out_path.with_name(f"{out_path.name}.tmp.{uuid4().hex}")

    meta = {
        "version": "1.0",
        "created_at": datetime.now().isoformat(),
        "total_items": len(items),
        "corpus_metadata": corpus_meta or {},
        "stratification_summary": {
            "distinct_tickers": len(set(i.ticker for i in items)),
            "distinct_labels": len(set(i.normalized_label for i in items)),
            "roles": Counter(i.seed_alias_role.value for i in items),
            "patterns": Counter(i.seed_value_pattern.value for i in items),
            "eligibility": Counter(i.seed_valuation_eligibility.value for i in items),
            "review_status": Counter(i.review_status.value for i in items),
            "difficulties": Counter(i.difficulty_category.value for i in items)
        }
    }

    data = {
        "metadata": meta,
        "items": [item.model_dump() for item in items]
    }

    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        temp_path.replace(out_path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise


save_benchmark_json_atomic = save_benchmark_json


def load_benchmark_json(path: Path | str) -> list[BenchmarkItem]:
    """Loads benchmark items from JSON artifact."""
    in_path = Path(path)
    with open(in_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [BenchmarkItem(**item) for item in data["items"]]


def generate_benchmark_review_markdown(items: Sequence[BenchmarkItem], path: Path | str) -> None:
    """Generates human-review artifact grouped by difficulty category."""
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    grouped: dict[BenchmarkDifficulty, list[BenchmarkItem]] = {d: [] for d in BenchmarkDifficulty}
    for item in items:
        grouped[item.difficulty_category].append(item)

    lines: list[str] = [
        "# Financial Classifier Benchmark Review (Phase 1)",
        "",
        "This artifact organizes the stratified SENS candidate pool for expert review before running",
        "Kev-4B or other semantic classifiers.",
        "",
        "## Summary Statistics",
        f"- **Total Candidates**: {len(items)}",
        f"- **Distinct Tickers**: {len(set(i.ticker for i in items))}",
        f"- **Distinct Normalized Labels**: {len(set(i.normalized_label for i in items))}",
        f"- **Auto-Seeded**: {sum(1 for i in items if i.review_status == ReviewStatus.AUTO_SEEDED)}",
        f"- **Review Required**: {sum(1 for i in items if i.review_status == ReviewStatus.REVIEW_REQUIRED)}",
        "",
        "---",
        ""
    ]

    for diff_cat, cat_items in grouped.items():
        lines.append(f"## {diff_cat.value} (Count: {len(cat_items)})")
        lines.append("")
        if not cat_items:
            lines.append("*(No items in this category)*\n")
            continue

        lines.append("| ID | Ticker | Detected Label | Seed Concept | Seed Role | Seed Pattern | Seed Eligibility | Review Action Needed |")
        lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
        for it in cat_items:
            act = "Verify explicit scope / presentation" if it.review_status == ReviewStatus.REVIEW_REQUIRED else "Confirm auto-seed"
            lines.append(
                f"| `{it.benchmark_id}` | **{it.ticker}** | `{it.normalized_label}` | `{it.seed_concept or 'UNKNOWN'}` | "
                f"`{it.seed_alias_role.value}` | `{it.seed_value_pattern.value}` | `{it.seed_valuation_eligibility.value}` | {act} |"
            )
        lines.append("")

        lines.append("### Representative Context Samples")
        for it in cat_items[:5]:
            lines.append(f"#### [{it.benchmark_id}] {it.ticker} — `{it.normalized_label}`")
            lines.append(f"- **Sentence**: *\"{it.full_sentence}\"*")
            if it.previous_sentence:
                lines.append(f"- **Prior Context**: *\"{it.previous_sentence}\"*")
            if it.next_sentence:
                lines.append(f"- **Following Context**: *\"{it.next_sentence}\"*")
            lines.append(f"- **Reviewer Notes**: {it.reviewer_notes}")
            lines.append("")
        lines.append("---")
        lines.append("")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def generate_gold_review_markdown(items: Sequence[BenchmarkItem], path: Path | str, batch_title: str = "Review Batch 001") -> None:
    """Generates detailed manual-review artifact with blank gold-confirmation fields."""
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = [
        f"# Financial Classifier Gold Benchmark — {batch_title}",
        "",
        "This artifact presents stratified SENS items for manual expert review.",
        "Deterministic heuristic values are preserved as `seed_*` for reference.",
        "The reviewer must confirm or correct the `gold_*` fields. Items remain in `REVIEW_REQUIRED` until confirmed.",
        "",
        "## Review Instructions",
        "1. **Gold Concept**: Canonical concept ID (e.g. `accounting_revenue`, `trading_profit`, `eps`) or `None` if invalid/discursive.",
        "2. **Gold Qualifiers**: Explicit qualifiers (e.g. `scope=continuing_operations`, `tax_basis=gross`).",
        "3. **Gold Alias Role**: `DIRECT_VALUE_LABEL`, `CHANGE_STATEMENT`, `GUIDANCE_STATEMENT`, or `CONCEPT_MENTION_ONLY`.",
        "4. **Gold Value Pattern**: `DIRECT_LEVEL`, `CHANGE_RATE_ONLY`, `CHANGE_RATE_TO_LEVEL`, `FROM_TO_LEVEL`, `RANGE`, or `UNKNOWN`.",
        "5. **Gold Valuation Eligibility**: `ELIGIBLE`, `ELIGIBLE_WITH_QUALIFIER`, `REQUIRES_SCOPE`, `REQUIRES_BASIS`, `REQUIRES_PERIOD`, `REQUIRES_SOURCE_SECTION`, `INFORMATIONAL_ONLY`, or `PROHIBITED`.",
        "6. **Should Abstain**: `True` if metric cannot safely be extracted without additional external context.",
        "",
        f"## Batch Summary (Total: {len(items)} items)",
        f"- **Distinct Tickers**: {len(set(i.ticker for i in items))}",
        f"- **Distinct Labels**: {len(set(i.normalized_label for i in items))}",
        "",
        "---",
        ""
    ]

    for idx, it in enumerate(items, 1):
        lines.append(f"### Item {idx:03d} — [`{it.benchmark_id}`] **{it.ticker}** ({it.publication_datetime})")
        lines.append(f"- **Detected Label**: `{it.raw_label}` (normalized: `{it.normalized_label}`)")
        if it.nearby_heading:
            lines.append(f"- **Section Heading**: *{it.nearby_heading}*")
        if it.previous_sentence:
            lines.append(f"- **Prior Sentence**: *\"{it.previous_sentence}\"*")
        lines.append(f"- **Target Sentence**: **\"{it.full_sentence}\"**")
        if it.next_sentence:
            lines.append(f"- **Next Sentence**: *\"{it.next_sentence}\"*")
        if it.detected_numeric_tokens:
            lines.append(f"- **Detected Numbers**: `[{', '.join(repr(t) for t in it.detected_numeric_tokens)}]`")
        else:
            lines.append("- **Detected Numbers**: `[]`")
        lines.append(f"- **Difficulty Category**: `{it.difficulty_category.value}`")
        lines.append("")
        lines.append("**Deterministic Seed Baseline:**")
        lines.append(f"- Seed Concept: `{it.seed_concept or 'None'}`")
        lines.append(f"- Seed Qualifiers: `{it.seed_qualifiers.model_dump(exclude_defaults=True)}`")
        lines.append(f"- Seed Alias Role: `{it.seed_alias_role.value}`")
        lines.append(f"- Seed Value Pattern: `{it.seed_value_pattern.value}`")
        lines.append(f"- Seed Valuation Eligibility: `{it.seed_valuation_eligibility.value}`")
        lines.append(f"- Seed Should Abstain: `{it.seed_should_abstain}`")
        lines.append(f"- Seed Heuristic Note: *{it.reviewer_notes}*")
        lines.append("")
        lines.append("**Human Reviewer Confirmation:**")
        lines.append("- [ ] Gold Concept: `[                                        ]`")
        lines.append("- [ ] Gold Qualifiers: `[                                     ]`")
        lines.append("- [ ] Gold Alias Role: `[                                     ]`")
        lines.append("- [ ] Gold Value Pattern: `[                                  ]`")
        lines.append("- [ ] Gold Valuation Eligibility: `[                          ]`")
        lines.append("- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`")
        lines.append("- [ ] Reviewer Notes: `[                                      ]`")
        lines.append("")
        lines.append("---")
        lines.append("")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# =============================================================================
# 9. Review Worksheet Workflow (CSV Export, Import, and Progress Reporting)
# =============================================================================

REVIEW_WORKSHEET_COLUMNS: list[str] = [
    "benchmark_id",
    "ticker",
    "publication_datetime",
    "previous_sentence",
    "full_sentence",
    "next_sentence",
    "detected_numeric_tokens",
    "normalized_label",
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
    "reviewer_notes",
    "review_decision",
]


def parse_bool(val: Any) -> bool:
    """Parses boolean representation from string or bool."""
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    if s in {"true", "1", "yes"}:
        return True
    if s in {"false", "0", "no"}:
        return False
    raise ValueError(f"Cannot parse '{val}' as boolean (expected True/False)")


def parse_enum_val(enum_cls: type[Enum], val: Any, default: Any = None) -> Any:
    """Parses enum value safely, supporting enum instance, member value, or case-insensitive name."""
    if val is None or (isinstance(val, str) and not val.strip()):
        return default
    if isinstance(val, enum_cls):
        return val
    s = str(val).strip()
    for member in enum_cls:
        if member.value == s or member.name == s or member.value.lower() == s.lower():
            return member
    raise ValueError(f"Invalid value '{val}' for {enum_cls.__name__}. Allowed: {[m.value for m in enum_cls]}")


def verify_source_context_unmodified(existing: BenchmarkItem, row: dict[str, str]) -> None:
    """Deterministic validation ensuring human review did not modify immutable source context."""
    b_id = existing.benchmark_id
    if row.get("ticker", "").strip() != existing.ticker:
        raise ValueError(
            f"Source context modified for {b_id}: ticker mismatch ('{row.get('ticker')}' != '{existing.ticker}')"
        )
    if row.get("publication_datetime", "").strip() != existing.publication_datetime:
        raise ValueError(
            f"Source context modified for {b_id}: publication_datetime mismatch ('{row.get('publication_datetime')}' != '{existing.publication_datetime}')"
        )
    if row.get("full_sentence", "").strip() != existing.full_sentence.strip():
        raise ValueError(
            f"Source context modified for {b_id}: full_sentence mismatch"
        )
    if row.get("normalized_label", "").strip() != existing.normalized_label:
        raise ValueError(
            f"Source context modified for {b_id}: normalized_label mismatch ('{row.get('normalized_label')}' != '{existing.normalized_label}')"
        )
    if "previous_sentence" in row and (row.get("previous_sentence", "").strip() != (existing.previous_sentence or "").strip()):
        raise ValueError(
            f"Source context modified for {b_id}: previous_sentence mismatch"
        )
    if "next_sentence" in row and (row.get("next_sentence", "").strip() != (existing.next_sentence or "").strip()):
        raise ValueError(
            f"Source context modified for {b_id}: next_sentence mismatch"
        )
    if "detected_numeric_tokens" in row:
        raw_nums = row.get("detected_numeric_tokens", "").strip()
        if raw_nums:
            try:
                parsed_nums = json.loads(raw_nums)
            except Exception:
                raise ValueError(f"Malformed detected_numeric_tokens in CSV for {b_id}: {raw_nums}")
            if parsed_nums != existing.detected_numeric_tokens:
                raise ValueError(
                    f"Source context modified for {b_id}: detected_numeric_tokens mismatch ({parsed_nums} != {existing.detected_numeric_tokens})"
                )


def get_batch_001_ids(gold_md_path: Path | str | None = None) -> list[str]:
    """Retrieves the exact 300 benchmark IDs in Gold Review Batch 001."""
    p = Path(gold_md_path) if gold_md_path else Path("docs/FINANCIAL_CLASSIFIER_GOLD_REVIEW_001.md")
    if not p.exists():
        p = Path("C:/Users/Dion/Desktop/Projects/stock_analysis/docs/FINANCIAL_CLASSIFIER_GOLD_REVIEW_001.md")
    with open(p, "r", encoding="utf-8") as f:
        text = f.read()
    raw_ids = re.findall(r"BENCH-\d{4}", text)
    seen: set[str] = set()
    ordered_ids: list[str] = []
    for bid in raw_ids:
        if bid not in seen:
            seen.add(bid)
            ordered_ids.append(bid)
    return ordered_ids


def export_review_worksheet_csv(
    items: Sequence[BenchmarkItem],
    out_csv_path: Path | str,
    batch_ids: Sequence[str] | None = None
) -> Path:
    """Exports items to the standardized human review worksheet CSV.
    
    Seed values are populated as review suggestions.
    Gold fields remain strictly unpopulated for unconfirmed items.
    """
    out_path = Path(out_csv_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if batch_ids is not None:
        item_map = {it.benchmark_id: it for it in items}
        target_items = [item_map[bid] for bid in batch_ids if bid in item_map]
    else:
        target_items = list(items)

    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=REVIEW_WORKSHEET_COLUMNS)
        writer.writeheader()
        for it in target_items:
            sq = it.seed_qualifiers
            is_gold = it.review_status == ReviewStatus.GOLD_CONFIRMED
            gq = it.gold_qualifiers if is_gold else None

            row = {
                "benchmark_id": it.benchmark_id,
                "ticker": it.ticker,
                "publication_datetime": it.publication_datetime,
                "previous_sentence": it.previous_sentence or "",
                "full_sentence": it.full_sentence,
                "next_sentence": it.next_sentence or "",
                "detected_numeric_tokens": json.dumps(it.detected_numeric_tokens),
                "normalized_label": it.normalized_label,
                "seed_concept": it.seed_concept or "",
                "seed_scope": sq.scope.value if sq else OperationScope.UNSPECIFIED.value,
                "seed_dilution": sq.dilution.value if sq else DilutionBasis.UNSPECIFIED.value,
                "seed_tax_basis": sq.tax_basis.value if sq else DividendTaxBasis.UNSPECIFIED.value,
                "seed_capex_basis": sq.capex_basis.value if sq else CapexBasis.UNSPECIFIED.value,
                "seed_lease_inclusion": sq.lease_inclusion.value if sq else LeaseInclusion.UNSPECIFIED.value,
                "seed_margin_denominator": sq.margin_denominator.value if sq else MarginDenominator.UNSPECIFIED.value,
                "seed_attribution": sq.attribution.value if sq else ProfitAttribution.UNSPECIFIED.value,
                "seed_alias_role": it.seed_alias_role.value,
                "seed_value_pattern": it.seed_value_pattern.value,
                "seed_valuation_eligibility": it.seed_valuation_eligibility.value,
                "seed_should_abstain": str(it.seed_should_abstain),
                "gold_concept": (it.gold_concept or "") if is_gold else "",
                "gold_scope": (gq.scope.value if gq else "") if is_gold else "",
                "gold_dilution": (gq.dilution.value if gq else "") if is_gold else "",
                "gold_tax_basis": (gq.tax_basis.value if gq else "") if is_gold else "",
                "gold_capex_basis": (gq.capex_basis.value if gq else "") if is_gold else "",
                "gold_lease_inclusion": (gq.lease_inclusion.value if gq else "") if is_gold else "",
                "gold_basis_evidence": (gq.basis_evidence.value if gq else "") if is_gold else "",
                "gold_margin_denominator": (gq.margin_denominator.value if gq else "") if is_gold else "",
                "gold_attribution": (gq.attribution.value if gq else "") if is_gold else "",
                "gold_alias_role": (it.gold_alias_role.value if it.gold_alias_role else "") if is_gold else "",
                "gold_value_pattern": (it.gold_value_pattern.value if it.gold_value_pattern else "") if is_gold else "",
                "gold_valuation_eligibility": (it.gold_valuation_eligibility.value if it.gold_valuation_eligibility else "") if is_gold else "",
                "gold_should_abstain": (str(it.gold_should_abstain) if it.gold_should_abstain is not None else "") if is_gold else "",
                "reviewer_notes": it.reviewer_notes if is_gold else "",
                "review_decision": it.review_decision.value if it.review_decision else "",
            }
            writer.writerow(row)

    return out_path


def apply_review_decisions(
    items: Sequence[BenchmarkItem],
    csv_rows: Sequence[dict[str, str]],
    reviewer_id: str = "human_review_batch_001",
    reviewed_at: str | None = None
) -> list[BenchmarkItem]:
    """Validates and applies human review decisions from CSV rows to benchmark items.
    
    Rules:
    - benchmark_id must already exist
    - source context must not be changed
    - duplicate benchmark IDs fail
    - invalid enum values fail
    - malformed qualifiers fail
    - CONFIRM_SEED cannot bypass current BenchmarkItem validation
    - OVERRIDE must pass all GOLD_CONFIRMED validation
    - ABSTAIN must pass abstention rules
    - SKIP must leave gold fields null
    - no partial write on validation failure
    """
    item_map = {it.benchmark_id: it.model_copy(deep=True) for it in items}
    seen_ids: set[str] = set()

    for row in csv_rows:
        bid = row.get("benchmark_id", "").strip()
        if not bid:
            raise ValueError("CSV row missing 'benchmark_id'")
        if bid in seen_ids:
            raise ValueError(f"Duplicate benchmark_id found in CSV: {bid}")
        seen_ids.add(bid)

        if bid not in item_map:
            raise ValueError(f"Benchmark ID '{bid}' not found in benchmark items")

        existing = item_map[bid]

        # Verify source context immutability
        verify_source_context_unmodified(existing, row)

        decision_str = row.get("review_decision", "").strip()
        if not decision_str:
            # Unreviewed item, leave untouched
            continue

        try:
            decision = ReviewDecision(decision_str)
        except ValueError:
            raise ValueError(
                f"Invalid review_decision '{decision_str}' for item {bid}. "
                f"Allowed values: {[d.value for d in ReviewDecision]}"
            )

        now_ts = reviewed_at or datetime.now().isoformat()
        notes = row.get("reviewer_notes", "").strip()

        if decision == ReviewDecision.SKIP:
            existing.review_status = ReviewStatus.REVIEW_REQUIRED
            existing.review_decision = ReviewDecision.SKIP
            existing.reviewed_at = now_ts
            existing.reviewer_id = reviewer_id
            if notes:
                existing.reviewer_notes = notes
            existing.gold_concept = None
            existing.gold_qualifiers = None
            existing.gold_alias_role = None
            existing.gold_value_pattern = None
            existing.gold_valuation_eligibility = None
            existing.gold_should_abstain = None
            item_map[bid] = BenchmarkItem.model_validate(existing.model_dump())

        elif decision == ReviewDecision.CONFIRM_SEED:
            existing.gold_concept = existing.seed_concept
            existing.gold_qualifiers = existing.seed_qualifiers.model_copy()
            existing.gold_alias_role = existing.seed_alias_role
            existing.gold_value_pattern = existing.seed_value_pattern
            existing.gold_valuation_eligibility = existing.seed_valuation_eligibility
            existing.gold_should_abstain = existing.seed_should_abstain
            existing.review_status = ReviewStatus.GOLD_CONFIRMED
            existing.review_decision = ReviewDecision.CONFIRM_SEED
            existing.reviewed_at = now_ts
            existing.reviewer_id = reviewer_id
            if notes:
                existing.reviewer_notes = notes
            # Model validation strictly catches any seed that cannot be gold confirmed
            item_map[bid] = BenchmarkItem.model_validate(existing.model_dump())

        elif decision == ReviewDecision.OVERRIDE:
            raw_role = row.get("gold_alias_role", "").strip()
            raw_pat = row.get("gold_value_pattern", "").strip()
            raw_elig = row.get("gold_valuation_eligibility", "").strip()
            raw_abs = row.get("gold_should_abstain", "").strip()

            if not raw_role:
                raise ValueError(f"OVERRIDE for {bid} requires explicit gold_alias_role")
            if not raw_pat:
                raise ValueError(f"OVERRIDE for {bid} requires explicit gold_value_pattern")
            if not raw_elig:
                raise ValueError(f"OVERRIDE for {bid} requires explicit gold_valuation_eligibility")
            if not raw_abs:
                raise ValueError(f"OVERRIDE for {bid} requires explicit gold_should_abstain")

            gold_role = parse_enum_val(AliasRole, raw_role)
            gold_pat = parse_enum_val(ValuePattern, raw_pat)
            gold_elig = parse_enum_val(ValuationEligibility, raw_elig)
            gold_abstain = parse_bool(raw_abs)

            raw_concept = row.get("gold_concept", "").strip()
            gold_concept = raw_concept if raw_concept else None

            gold_qualifiers = SemanticQualifiers(
                scope=parse_enum_val(OperationScope, row.get("gold_scope"), default=OperationScope.UNSPECIFIED),
                dilution=parse_enum_val(DilutionBasis, row.get("gold_dilution"), default=DilutionBasis.UNSPECIFIED),
                tax_basis=parse_enum_val(DividendTaxBasis, row.get("gold_tax_basis"), default=DividendTaxBasis.UNSPECIFIED),
                capex_basis=parse_enum_val(CapexBasis, row.get("gold_capex_basis"), default=CapexBasis.UNSPECIFIED),
                lease_inclusion=parse_enum_val(LeaseInclusion, row.get("gold_lease_inclusion"), default=LeaseInclusion.UNSPECIFIED),
                basis_evidence=parse_enum_val(BasisEvidence, row.get("gold_basis_evidence"), default=BasisEvidence.UNSPECIFIED),
                margin_denominator=parse_enum_val(MarginDenominator, row.get("gold_margin_denominator"), default=MarginDenominator.UNSPECIFIED),
                attribution=parse_enum_val(ProfitAttribution, row.get("gold_attribution"), default=ProfitAttribution.UNSPECIFIED),
            )

            existing.gold_concept = gold_concept
            existing.gold_qualifiers = gold_qualifiers
            existing.gold_alias_role = gold_role
            existing.gold_value_pattern = gold_pat
            existing.gold_valuation_eligibility = gold_elig
            existing.gold_should_abstain = gold_abstain
            existing.review_status = ReviewStatus.GOLD_CONFIRMED
            existing.review_decision = ReviewDecision.OVERRIDE
            existing.reviewed_at = now_ts
            existing.reviewer_id = reviewer_id
            if notes:
                existing.reviewer_notes = notes

            item_map[bid] = BenchmarkItem.model_validate(existing.model_dump())

        elif decision == ReviewDecision.ABSTAIN:
            raw_concept = row.get("gold_concept", "").strip()
            gold_concept = raw_concept if raw_concept else None
            gold_abstain = True

            gold_role = parse_enum_val(AliasRole, row.get("gold_alias_role"), default=existing.seed_alias_role)
            gold_pat = parse_enum_val(ValuePattern, row.get("gold_value_pattern"), default=existing.seed_value_pattern)
            gold_elig = parse_enum_val(ValuationEligibility, row.get("gold_valuation_eligibility"), default=ValuationEligibility.INFORMATIONAL_ONLY)

            if not existing.detected_numeric_tokens:
                gold_role = AliasRole.CONCEPT_MENTION_ONLY
                gold_pat = ValuePattern.UNKNOWN

            gold_qualifiers = SemanticQualifiers(
                scope=parse_enum_val(OperationScope, row.get("gold_scope"), default=OperationScope.UNSPECIFIED),
                dilution=parse_enum_val(DilutionBasis, row.get("gold_dilution"), default=DilutionBasis.UNSPECIFIED),
                tax_basis=parse_enum_val(DividendTaxBasis, row.get("gold_tax_basis"), default=DividendTaxBasis.UNSPECIFIED),
                capex_basis=parse_enum_val(CapexBasis, row.get("gold_capex_basis"), default=CapexBasis.UNSPECIFIED),
                lease_inclusion=parse_enum_val(LeaseInclusion, row.get("gold_lease_inclusion"), default=LeaseInclusion.UNSPECIFIED),
                basis_evidence=parse_enum_val(BasisEvidence, row.get("gold_basis_evidence"), default=BasisEvidence.UNSPECIFIED),
                margin_denominator=parse_enum_val(MarginDenominator, row.get("gold_margin_denominator"), default=MarginDenominator.UNSPECIFIED),
                attribution=parse_enum_val(ProfitAttribution, row.get("gold_attribution"), default=ProfitAttribution.UNSPECIFIED),
            )

            existing.gold_concept = gold_concept
            existing.gold_qualifiers = gold_qualifiers
            existing.gold_alias_role = gold_role
            existing.gold_value_pattern = gold_pat
            existing.gold_valuation_eligibility = gold_elig
            existing.gold_should_abstain = gold_abstain
            existing.review_status = ReviewStatus.GOLD_CONFIRMED
            existing.review_decision = ReviewDecision.ABSTAIN
            existing.reviewed_at = now_ts
            existing.reviewer_id = reviewer_id
            if notes:
                existing.reviewer_notes = notes

            item_map[bid] = BenchmarkItem.model_validate(existing.model_dump())

    return list(item_map.values())


@dataclass
class ReviewProgressReport:
    """Progress statistics across human benchmark review."""
    batch_total: int
    reviewed: int
    gold_confirmed: int
    abstained: int
    overridden: int
    confirmed_seed: int
    skipped: int
    remaining: int
    by_alias_role: dict[str, int]
    by_valuation_eligibility: dict[str, int]
    by_canonical_concept: dict[str, int]
    by_ticker: dict[str, int]


def get_review_progress_report(
    items: Sequence[BenchmarkItem],
    batch_ids: Sequence[str] | None = None
) -> ReviewProgressReport:
    """Generates deterministic review progress statistics for items or a specific batch subset."""
    if batch_ids is not None:
        target_set = set(batch_ids)
        target_items = [it for it in items if it.benchmark_id in target_set]
    else:
        target_items = list(items)

    batch_total = len(target_items)
    reviewed_items = [it for it in target_items if it.review_decision is not None]
    reviewed = len(reviewed_items)

    gold_confirmed = sum(1 for it in target_items if it.review_status == ReviewStatus.GOLD_CONFIRMED)
    abstained = sum(1 for it in target_items if it.review_decision == ReviewDecision.ABSTAIN)
    overridden = sum(1 for it in target_items if it.review_decision == ReviewDecision.OVERRIDE)
    confirmed_seed = sum(1 for it in target_items if it.review_decision == ReviewDecision.CONFIRM_SEED)
    skipped = sum(1 for it in target_items if it.review_decision == ReviewDecision.SKIP)
    remaining = batch_total - reviewed

    role_counter = Counter(
        (it.gold_alias_role.value if (it.review_status == ReviewStatus.GOLD_CONFIRMED and it.gold_alias_role) else it.seed_alias_role.value)
        for it in target_items
    )
    elig_counter = Counter(
        (it.gold_valuation_eligibility.value if (it.review_status == ReviewStatus.GOLD_CONFIRMED and it.gold_valuation_eligibility) else it.seed_valuation_eligibility.value)
        for it in target_items
    )
    concept_counter = Counter(
        (it.gold_concept if (it.review_status == ReviewStatus.GOLD_CONFIRMED and it.gold_concept) else (it.seed_concept or "UNRESOLVED"))
        for it in target_items
    )
    ticker_counter = Counter(it.ticker for it in target_items)

    return ReviewProgressReport(
        batch_total=batch_total,
        reviewed=reviewed,
        gold_confirmed=gold_confirmed,
        abstained=abstained,
        overridden=overridden,
        confirmed_seed=confirmed_seed,
        skipped=skipped,
        remaining=remaining,
        by_alias_role=dict(role_counter),
        by_valuation_eligibility=dict(elig_counter),
        by_canonical_concept=dict(concept_counter),
        by_ticker=dict(ticker_counter),
    )


def get_csv_review_progress_report(csv_path: Path | str) -> ReviewProgressReport:
    """Reads review decisions directly from CSV and computes progress statistics."""
    c_path = Path(csv_path)
    with open(c_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    batch_total = len(rows)
    reviewed = 0
    gold_confirmed = 0
    abstained = 0
    overridden = 0
    confirmed_seed = 0
    skipped = 0

    role_counts: Counter[str] = Counter()
    elig_counts: Counter[str] = Counter()
    concept_counts: Counter[str] = Counter()
    ticker_counts: Counter[str] = Counter()

    for r in rows:
        ticker_counts[r.get("ticker", "UNKNOWN")] += 1
        dec = r.get("review_decision", "").strip()

        if dec:
            reviewed += 1
            if dec == ReviewDecision.SKIP.value:
                skipped += 1
            elif dec == ReviewDecision.CONFIRM_SEED.value:
                confirmed_seed += 1
                gold_confirmed += 1
            elif dec == ReviewDecision.OVERRIDE.value:
                overridden += 1
                gold_confirmed += 1
            elif dec == ReviewDecision.ABSTAIN.value:
                abstained += 1
                gold_confirmed += 1

        # Role, eligibility, concept: use gold if confirmed else seed
        if dec in {ReviewDecision.CONFIRM_SEED.value, ReviewDecision.OVERRIDE.value, ReviewDecision.ABSTAIN.value}:
            role = r.get("gold_alias_role", "").strip() or r.get("seed_alias_role", "")
            elig = r.get("gold_valuation_eligibility", "").strip() or r.get("seed_valuation_eligibility", "")
            c = r.get("gold_concept", "").strip() or r.get("seed_concept", "") or "UNRESOLVED"
        else:
            role = r.get("seed_alias_role", "")
            elig = r.get("seed_valuation_eligibility", "")
            c = r.get("seed_concept", "") or "UNRESOLVED"

        role_counts[role] += 1
        elig_counts[elig] += 1
        concept_counts[c] += 1

    remaining = batch_total - reviewed
    return ReviewProgressReport(
        batch_total=batch_total,
        reviewed=reviewed,
        gold_confirmed=gold_confirmed,
        abstained=abstained,
        overridden=overridden,
        confirmed_seed=confirmed_seed,
        skipped=skipped,
        remaining=remaining,
        by_alias_role=dict(role_counts),
        by_valuation_eligibility=dict(elig_counts),
        by_canonical_concept=dict(concept_counts),
        by_ticker=dict(ticker_counts),
    )


def format_review_progress_report(report: ReviewProgressReport) -> str:
    """Formats ReviewProgressReport into human-readable summary text."""
    pct_reviewed = (report.reviewed / report.batch_total * 100.0) if report.batch_total else 0.0
    pct_rem = (report.remaining / report.batch_total * 100.0) if report.batch_total else 0.0
    lines = [
        f"Review Progress Report (Batch Total: {report.batch_total})",
        "=" * 40,
        f"Batch total:     {report.batch_total}",
        f"Reviewed:        {report.reviewed} ({pct_reviewed:.1f}%)",
        f"  - Gold confirmed:  {report.gold_confirmed}",
        f"  - Confirmed seed:  {report.confirmed_seed}",
        f"  - Overridden:      {report.overridden}",
        f"  - Abstained:       {report.abstained}",
        f"  - Skipped:         {report.skipped}",
        f"Remaining:       {report.remaining} ({pct_rem:.1f}%)",
        "",
        "Breakdown by Alias Role:",
    ]
    for k, v in sorted(report.by_alias_role.items()):
        lines.append(f"  {k}: {v}")
    lines.append("\nBreakdown by Valuation Eligibility:")
    for k, v in sorted(report.by_valuation_eligibility.items()):
        lines.append(f"  {k}: {v}")
    lines.append("\nBreakdown by Canonical Concept (Top 10):")
    for k, v in sorted(report.by_canonical_concept.items(), key=lambda x: -x[1])[:10]:
        lines.append(f"  {k}: {v}")
    lines.append(f"\nDistinct Tickers: {len(report.by_ticker)}")
    return "\n".join(lines)


def import_review_worksheet_csv(
    csv_path: Path | str,
    benchmark_json_path: Path | str,
    reviewer_id: str = "human_review_batch_001",
    reviewed_at: str | None = None
) -> tuple[list[BenchmarkItem], ReviewProgressReport]:
    """Reads a review worksheet CSV and atomically updates financial_classifier_benchmark.json."""
    c_path = Path(csv_path)
    if not c_path.exists():
        raise FileNotFoundError(f"Review worksheet CSV not found: {c_path}")

    with open(c_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    b_path = Path(benchmark_json_path)
    existing_items = load_benchmark_json(b_path)

    corpus_meta = None
    with open(b_path, "r", encoding="utf-8") as f:
        raw_json = json.load(f)
        corpus_meta = raw_json.get("metadata", {}).get("corpus_metadata")

    # Apply decisions (pure in-memory validation; fails closed with zero write on error)
    updated_items = apply_review_decisions(
        existing_items,
        rows,
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at
    )

    # Atomic write to disk
    save_benchmark_json(updated_items, b_path, corpus_meta=corpus_meta)

    # Generate progress report
    batch_ids = [r["benchmark_id"] for r in rows if r.get("benchmark_id")]
    progress_report = get_review_progress_report(updated_items, batch_ids=batch_ids)

    return updated_items, progress_report
