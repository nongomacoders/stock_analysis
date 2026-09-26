import psycopg2
from core.config import DB_CONFIG
from modules.analysis.financial_classifier_benchmark import (
    build_stratified_benchmark,
    ReviewStatus
)

conn = psycopg2.connect(**DB_CONFIG)
items = build_stratified_benchmark(
    conn=conn,
    alias_dict_path="gui/modules/analysis/data/financial_concept_aliases.json",
    target_count=820,
    max_per_label=10,
    max_per_ticker=20
)
print("Total items built:", len(items))
print("Auto-seeded:", sum(1 for i in items if i.review_status == ReviewStatus.AUTO_SEEDED))
print("Review-required:", sum(1 for i in items if i.review_status == ReviewStatus.REVIEW_REQUIRED))
print("Gold-confirmed (must be 0):", sum(1 for i in items if i.review_status == ReviewStatus.GOLD_CONFIRMED))

# Check items mentioned in user prompt
for i in items:
    if i.benchmark_id in ("BENCH-0012", "BENCH-0026", "BENCH-0028", "BENCH-0036", "BENCH-0037", "BENCH-0041", "BENCH-0095"):
        print("---")
        print(i.benchmark_id, "NORM:", i.normalized_label)
        print("FULL:", i.full_sentence[:70])
        print("PREV:", i.previous_sentence[:70] if i.previous_sentence else None)
        print("NUMS:", i.detected_numeric_tokens)
        print("TYPED:", [(t.raw_text, t.token_type.value) for t in i.detected_typed_numeric_tokens])
        print("METRIC_TOKEN:", i.candidate_metric_token, "CHANGE_TOKEN:", i.candidate_change_token)
        print("ROLE:", i.seed_alias_role.value, "PATTERN:", i.seed_value_pattern.value)
        print("ELIG:", i.seed_valuation_eligibility.value, "ABSTAIN:", i.seed_should_abstain)
        print("OFFSETS: line=", i.source_line_index, "alias_span=", (i.alias_start_offset, i.alias_end_offset))
