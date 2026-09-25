import json
import re
from collections import defaultdict, Counter
from pathlib import Path
import sys

# Add gui to sys.path
sys.path.insert(0, str(Path("gui").resolve()))
from modules.analysis.financial_concept_dictionary import (
    AliasStatus,
    BasisEvidence,
    CapexBasis,
    DilutionBasis,
    DividendTaxBasis,
    LeaseInclusion,
    MarginDenominator,
    MetricBasis,
    OperationScope,
    ProfitAttribution,
    SemanticQualifiers,
)

# Load verify_parser_rules
sys.path.insert(0, str(Path("scratch").resolve()))
from verify_parser_rules import (
    parse_detected_numeric_tokens,
    resolve_nested_alias_spans,
    NumericTokenType,
    DetectedNumericToken,
    AliasRole,
    ValuePattern,
    ValuationEligibility,
    ReviewStatus,
    BenchmarkDifficulty,
)

# Load existing benchmark
b_path = Path("gui/modules/analysis/data/financial_classifier_benchmark.json")
with open(b_path, "r", encoding="utf-8") as f:
    raw_data = json.load(f)

items = raw_data["items"]
total_before = len(items)

# 1. Exact duplicates: identical (sens_id, full_sentence.strip(), normalized_label)
seen_exact = {}
duplicates_retired = []
unique_items = []

for it in items:
    key = (it["sens_id"], it["full_sentence"].strip(), it["normalized_label"])
    if key in seen_exact:
        duplicates_retired.append((it["benchmark_id"], seen_exact[key], it["normalized_label"], it["full_sentence"][:50]))
    else:
        seen_exact[key] = it["benchmark_id"]
        unique_items.append(it)

# 2. Nested alias matches within the same (sens_id, full_sentence)
sentence_groups = defaultdict(list)
for it in unique_items:
    sentence_groups[(it["sens_id"], it["full_sentence"].strip())].append(it)

nested_retired = []
surviving_items = []

for (sens_id, sentence), group in sentence_groups.items():
    if len(group) == 1:
        surviving_items.append(group[0])
        continue
    
    # Find offsets
    item_spans = []
    for it in group:
        raw = it["raw_label"]
        start = sentence.lower().find(raw.lower())
        if start == -1:
            start = sentence.lower().find(it["normalized_label"].lower())
        end = start + len(raw) if start != -1 else len(sentence)
        item_spans.append((start, end, it))
    
    item_spans.sort(key=lambda x: (-(x[1] - x[0]), x[0]))
    kept = []
    for start, end, it in item_spans:
        contained = False
        for k_start, k_end, k_it in kept:
            if k_start != -1 and start != -1:
                if k_start <= start and end <= k_end and (k_end - k_start) > (end - start):
                    contained = True
                    nested_retired.append((it["benchmark_id"], k_it["benchmark_id"], it["normalized_label"], k_it["normalized_label"], sentence[:50]))
                    break
        if not contained:
            kept.append((start, end, it))
            surviving_items.append(it)

surviving_items.sort(key=lambda x: int(x["benchmark_id"].split("-")[1]))

print(f"Benchmark size before: {total_before}")
print(f"Duplicates removed: {len(duplicates_retired)}")
print(f"Nested alias matches removed: {len(nested_retired)}")
print(f"Surviving items: {len(surviving_items)}")

# 3. Check changes in surviving items
role_changes = 0
pattern_changes = 0
concept_changes = 0
guidance_corrections = 0
margin_corrections = 0
numeric_corrections = 0

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

CHANGE_KEYWORDS = ["increased by", "decreased by", "grew by", "declined by", "rose by", "improved to", "up by", "down by"]

updated_benchmark_items = []

for it in surviving_items:
    orig_role = it["seed_alias_role"]
    orig_pat = it["seed_value_pattern"]
    orig_concept = it["seed_concept"]
    orig_denom = it.get("seed_qualifiers", {}).get("margin_denominator")

    sent = it["full_sentence"]
    sent_lower = sent.lower()
    norm = it["normalized_label"]
    norm_lower = norm.lower()
    raw = it["raw_label"]
    raw_lower = raw.lower()

    # Re-parse numeric tokens
    typed_nums = parse_detected_numeric_tokens(sent)
    num_strs = [t.raw_text for t in typed_nums]
    if num_strs != it.get("detected_numeric_tokens", []):
        numeric_corrections += 1

    # Candidate metric numbers exclude YEAR_OR_DATE and OTHER
    metric_tokens = [t for t in typed_nums if t.token_type not in (NumericTokenType.YEAR_OR_DATE, NumericTokenType.OTHER)]
    has_metric_numbers = bool(metric_tokens)

    # Concept specificity
    concept_id = orig_concept
    if "headline earnings per share" in norm_lower or "headline earnings per share" in raw_lower:
        concept_id = "diluted_heps" if ("diluted" in norm_lower or "diluted" in raw_lower) else "heps"
    elif "earnings per share" in norm_lower or "earnings per share" in raw_lower:
        concept_id = "diluted_eps" if ("diluted" in norm_lower or "diluted" in raw_lower) else "eps"
    elif "dividend per share" in norm_lower or "dividend per share" in raw_lower:
        concept_id = "dividend_per_share"
    elif "nav per share" in norm_lower or "net asset value per share" in norm_lower:
        concept_id = "nav_per_share"
    elif "cash flow per share" in norm_lower:
        concept_id = "cash_flow_per_share"
    elif norm_lower in {"headline earnings", "earnings", "profit", "operating profit", "trading profit", "nav", "net asset value", "cash flow", "cash generated from operations"}:
        if concept_id in {"eps", "heps", "diluted_eps", "diluted_heps", "dividend_per_share", "nav_per_share", "cash_flow_per_share"}:
            concept_id = None

    if concept_id != orig_concept:
        concept_changes += 1

    # Heuristics
    is_guidance = any(k in sent_lower for k in GUIDANCE_KEYWORDS) or any(k in norm_lower for k in ["guidance", "forecast", "expected", "projected", "outlook"])
    has_change_verb = any(re.search(rf"\b{re.escape(v)}\b", sent_lower) for v in CHANGE_VERBS) or any(k in norm_lower for k in CHANGE_KEYWORDS)
    only_percentages = bool(metric_tokens) and all(t.is_percentage or t.token_type == NumericTokenType.PERCENTAGE for t in metric_tokens)
    has_both_rate_and_level = bool(metric_tokens) and any(t.is_percentage or t.token_type == NumericTokenType.PERCENTAGE for t in metric_tokens) and any(t.token_type in (NumericTokenType.CURRENCY_LEVEL, NumericTokenType.PER_SHARE_LEVEL, NumericTokenType.PLAIN_LEVEL) for t in metric_tokens)

    # Difficulty
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
    elif has_change_verb or only_percentages:
        diff = BenchmarkDifficulty.CHANGE_STATEMENTS
    elif it["current_dictionary_status"] == AliasStatus.UNKNOWN.value:
        diff = BenchmarkDifficulty.UNKNOWN_LONG_TAIL
    else:
        diff = BenchmarkDifficulty.EASY_DIRECT

    dict_status = AliasStatus(it["current_dictionary_status"])
    qualifiers = SemanticQualifiers(**it.get("current_qualifiers", {}))

    if not has_metric_numbers:
        role = AliasRole.CONCEPT_MENTION_ONLY
        pat = ValuePattern.UNKNOWN
        elig = ValuationEligibility.INFORMATIONAL_ONLY
        abstain = True
        status = ReviewStatus.REVIEW_REQUIRED
        note = f"Narrative mention of '{norm}' without reported numeric level (only dates/years or non-metric tokens detected)"
    elif is_guidance:
        role = AliasRole.GUIDANCE_STATEMENT
        has_range = ("between" in sent_lower or "range of" in sent_lower or any(t.token_type == NumericTokenType.RANGE_BOUND for t in typed_nums))
        pat = ValuePattern.RANGE if has_range else ValuePattern.DIRECT_LEVEL
        elig = ValuationEligibility.INFORMATIONAL_ONLY
        abstain = True
        status = ReviewStatus.AUTO_SEEDED if dict_status == AliasStatus.APPROVED else ReviewStatus.REVIEW_REQUIRED
        note = "Guidance / forward-looking trading statement; ineligible for historical actual baseline"
        if orig_role != AliasRole.GUIDANCE_STATEMENT.value:
            guidance_corrections += 1
    elif only_percentages or has_change_verb:
        role = AliasRole.CHANGE_STATEMENT
        if only_percentages:
            pat = ValuePattern.CHANGE_RATE_ONLY
            elig = ValuationEligibility.INFORMATIONAL_ONLY
            abstain = True
            status = ReviewStatus.AUTO_SEEDED if dict_status == AliasStatus.APPROVED else ReviewStatus.REVIEW_REQUIRED
            note = "Change / directional reporting sentence with percentage-only rate; ineligible as absolute historical baseline"
        elif "from" in sent_lower and "to" in sent_lower:
            pat = ValuePattern.FROM_TO_LEVEL
            elig = ValuationEligibility.INFORMATIONAL_ONLY
            abstain = False
            status = ReviewStatus.AUTO_SEEDED if dict_status == AliasStatus.APPROVED else ReviewStatus.REVIEW_REQUIRED
            note = "Change reporting sentence with from-to level compound structure"
        elif has_both_rate_and_level:
            pat = ValuePattern.CHANGE_RATE_TO_LEVEL
            elig = ValuationEligibility.INFORMATIONAL_ONLY
            abstain = False
            status = ReviewStatus.AUTO_SEEDED if dict_status == AliasStatus.APPROVED else ReviewStatus.REVIEW_REQUIRED
            note = "Change reporting sentence with rate-to-level compound structure"
        else:
            pat = ValuePattern.CHANGE_RATE_ONLY
            elig = ValuationEligibility.INFORMATIONAL_ONLY
            abstain = True
            status = ReviewStatus.REVIEW_REQUIRED
            note = "Change reporting sentence without compound level"
    else:
        # Check margin denominator
        is_margin = (concept_id in {"gross_margin", "trading_margin", "operating_margin", "ebitda_margin"}) or ("margin" in norm_lower)
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
                if orig_denom != MarginDenominator.UNSPECIFIED.value:
                    margin_corrections += 1
            else:
                qualifiers.margin_denominator = explicit_denom
                role = AliasRole.DIRECT_VALUE_LABEL
                pat = ValuePattern.DIRECT_LEVEL
                elig = ValuationEligibility.ELIGIBLE_WITH_QUALIFIER
                abstain = False
                status = ReviewStatus.AUTO_SEEDED
                note = f"Margin concept '{norm}' with explicit denominator '{explicit_denom.value}'"
        else:
            role = AliasRole.DIRECT_VALUE_LABEL
            pat = ValuePattern.DIRECT_LEVEL
            if dict_status == AliasStatus.APPROVED and concept_id:
                if qualifiers.scope != OperationScope.UNSPECIFIED or qualifiers.metric_basis != MetricBasis.UNSPECIFIED:
                    elig = ValuationEligibility.ELIGIBLE_WITH_QUALIFIER
                else:
                    elig = ValuationEligibility.ELIGIBLE
                abstain = False
                status = ReviewStatus.AUTO_SEEDED
                note = f"Approved canonical concept '{concept_id}' with verified explicit qualifiers"
            elif dict_status == AliasStatus.REQUIRES_CONTEXT:
                elig = ValuationEligibility.REQUIRES_SOURCE_SECTION if ("debt" in norm_lower or "borrowing" in norm_lower) else ValuationEligibility.REQUIRES_PERIOD
                abstain = True
                status = ReviewStatus.REVIEW_REQUIRED
                note = "Context required to verify period type, scope, or accounting attribution"
            else:
                elig = ValuationEligibility.REQUIRES_SCOPE
                abstain = True
                status = ReviewStatus.REVIEW_REQUIRED
                note = f"Ambiguous/unknown wording '{norm}'; requires context"

    if role.value != orig_role:
        role_changes += 1
    if pat.value != orig_pat:
        pattern_changes += 1

    it_updated = dict(it)
    it_updated["detected_numeric_tokens"] = num_strs
    it_updated["detected_typed_numeric_tokens"] = [t.model_dump() for t in typed_nums]
    it_updated["seed_concept"] = concept_id
    it_updated["seed_qualifiers"] = qualifiers.model_dump()
    it_updated["seed_alias_role"] = role.value
    it_updated["seed_value_pattern"] = pat.value
    it_updated["seed_valuation_eligibility"] = elig.value
    it_updated["seed_should_abstain"] = abstain
    it_updated["review_status"] = status.value
    it_updated["difficulty_category"] = diff.value
    it_updated["reviewer_notes"] = note
    it_updated["gold_concept"] = None
    it_updated["gold_qualifiers"] = None
    it_updated["gold_alias_role"] = None
    it_updated["gold_value_pattern"] = None
    it_updated["gold_valuation_eligibility"] = None
    it_updated["gold_should_abstain"] = None
    it_updated["review_decision"] = None
    it_updated["reviewed_at"] = None
    it_updated["reviewer_id"] = None
    updated_benchmark_items.append(it_updated)

print(f"Role changes: {role_changes}")
print(f"Pattern changes: {pattern_changes}")
print(f"Concept changes: {concept_changes}")
print(f"Guidance corrections: {guidance_corrections}")
print(f"Margin qualifier corrections: {margin_corrections}")
print(f"Numeric parsing corrections: {numeric_corrections}")
