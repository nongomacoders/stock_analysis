import csv
import json
from collections import defaultdict, Counter
from datetime import datetime
from pathlib import Path
import re
import sys

# Ensure gui is in pythonpath
sys.path.insert(0, str(Path("gui").resolve()))

from modules.analysis.financial_concept_dictionary import (
    AliasStatus,
    MarginDenominator,
    OperationScope,
    MetricBasis,
    SemanticQualifiers,
)

from modules.analysis.financial_classifier_benchmark import (
    AliasRole,
    BenchmarkDifficulty,
    BenchmarkItem,
    DetectedNumericToken,
    NumericTokenType,
    ReviewStatus,
    ValuationEligibility,
    ValuePattern,
    REVIEW_WORKSHEET_COLUMNS,
    classify_benchmark_item_heuristics,
    export_review_worksheet_csv,
    generate_gold_review_markdown,
    parse_detected_numeric_tokens,
    resolve_nested_alias_spans,
    save_benchmark_json,
)

# 1. Load current benchmark
b_path = Path("gui/modules/analysis/data/financial_classifier_benchmark.json")
with open(b_path, "r", encoding="utf-8") as f:
    raw_json = json.load(f)

corpus_meta = raw_json.get("metadata", {}).get("corpus_metadata", {})
original_items = raw_json["items"]
total_before = len(original_items)
print(f"Total benchmark candidates before: {total_before}")

# 2. Identify exact duplicates: (sens_id, full_sentence.strip(), normalized_label)
seen_exact = {}
duplicates_retired = []
unique_items = []

for it in original_items:
    key = (it["sens_id"], it["full_sentence"].strip(), it["normalized_label"])
    if key in seen_exact:
        duplicates_retired.append({
            "retired_id": it["benchmark_id"],
            "kept_id": seen_exact[key],
            "ticker": it["ticker"],
            "label": it["normalized_label"],
            "sentence": it["full_sentence"][:80],
            "reason": "EXACT_OCCURRENCE_DUPLICATE"
        })
    else:
        seen_exact[key] = it["benchmark_id"]
        unique_items.append(it)

print(f"Duplicates removed: {len(duplicates_retired)}")

# 3. Identify nested alias matches within the same (sens_id, full_sentence)
sentence_groups = defaultdict(list)
for it in unique_items:
    sentence_groups[(it["sens_id"], it["full_sentence"].strip())].append(it)

nested_retired = []
surviving_candidates = []

for (sens_id, sentence), group in sentence_groups.items():
    if len(group) == 1:
        surviving_candidates.append(group[0])
        continue

    # Find character span offsets for each raw_label / normalized_label
    item_spans = []
    for it in group:
        raw = it["raw_label"]
        start = sentence.lower().find(raw.lower())
        if start == -1:
            start = sentence.lower().find(it["normalized_label"].lower())
        end = start + len(raw) if start != -1 else len(sentence)
        item_spans.append((start, end, it))

    # Sort spans by length descending
    item_spans.sort(key=lambda x: (-(x[1] - x[0]), x[0]))
    kept = []
    for start, end, it in item_spans:
        contained = False
        for k_start, k_end, k_it in kept:
            if k_start != -1 and start != -1:
                if k_start <= start and end <= k_end and (k_end - k_start) > (end - start):
                    contained = True
                    nested_retired.append({
                        "retired_id": it["benchmark_id"],
                        "kept_id": k_it["benchmark_id"],
                        "ticker": it["ticker"],
                        "subsumed_label": it["normalized_label"],
                        "kept_label": k_it["normalized_label"],
                        "sentence": sentence[:80],
                        "reason": "NESTED_ALIAS_OVERLAP"
                    })
                    break
        if not contained:
            kept.append((start, end, it))
            surviving_candidates.append(it)

# Sort surviving candidates by numeric benchmark_id index to maintain stability
surviving_candidates.sort(key=lambda x: int(x["benchmark_id"].split("-")[1]))
total_after = len(surviving_candidates)
print(f"Nested alias matches removed: {len(nested_retired)}")
print(f"Surviving candidates after deduplication & nest suppression: {total_after}")

# 4. Re-evaluate and reclassify all surviving items
role_changes = 0
pattern_changes = 0
concept_changes = 0
guidance_corrections = 0
margin_corrections = 0
numeric_corrections = 0

rebuilt_items: list[BenchmarkItem] = []

for it in surviving_candidates:
    orig_role = it["seed_alias_role"]
    orig_pat = it["seed_value_pattern"]
    orig_concept = it["seed_concept"]
    orig_denom = it.get("seed_qualifiers", {}).get("margin_denominator")

    sent = it["full_sentence"]
    norm = it["normalized_label"]
    raw = it["raw_label"]

    # Re-parse numeric tokens with JSE logic
    typed_nums = parse_detected_numeric_tokens(sent)
    num_strs = [t.raw_text for t in typed_nums]
    if num_strs != it.get("detected_numeric_tokens", []):
        numeric_corrections += 1

    dict_status = AliasStatus(it["current_dictionary_status"])
    qualifiers = SemanticQualifiers(**it.get("current_qualifiers", {}))

    role, val_pat, elig, abstain, rev_status, diff, note = classify_benchmark_item_heuristics(
        norm=norm,
        raw=raw,
        sentence=sent,
        concept_id=orig_concept,
        dict_status=dict_status,
        qualifiers=qualifiers,
        nums=num_strs,
        typed_nums=typed_nums
    )

    # Re-derive concept_id from specificity rules
    norm_lower = norm.lower()
    raw_lower = raw.lower()
    new_concept = orig_concept
    if "headline earnings per share" in norm_lower or "headline earnings per share" in raw_lower:
        new_concept = "diluted_heps" if ("diluted" in norm_lower or "diluted" in raw_lower) else "heps"
    elif "earnings per share" in norm_lower or "earnings per share" in raw_lower:
        new_concept = "diluted_eps" if ("diluted" in norm_lower or "diluted" in raw_lower) else "eps"
    elif "dividend per share" in norm_lower or "dividend per share" in raw_lower:
        new_concept = "dividend_per_share"
    elif "nav per share" in norm_lower or "net asset value per share" in norm_lower:
        new_concept = "nav_per_share"
    elif "cash flow per share" in norm_lower:
        new_concept = "cash_flow_per_share"
    elif norm_lower in {"headline earnings", "earnings", "profit", "operating profit", "trading profit", "nav", "net asset value", "cash flow", "cash generated from operations"}:
        if new_concept in {"eps", "heps", "diluted_eps", "diluted_heps", "dividend_per_share", "nav_per_share", "cash_flow_per_share"}:
            new_concept = None

    if role.value != orig_role:
        role_changes += 1
    if val_pat.value != orig_pat:
        pattern_changes += 1
    if new_concept != orig_concept:
        concept_changes += 1
    if role == AliasRole.GUIDANCE_STATEMENT and orig_role != AliasRole.GUIDANCE_STATEMENT.value:
        guidance_corrections += 1
    if qualifiers.margin_denominator == MarginDenominator.UNSPECIFIED and orig_denom != MarginDenominator.UNSPECIFIED.value:
        margin_corrections += 1

    item = BenchmarkItem(
        benchmark_id=it["benchmark_id"],
        sens_id=it["sens_id"],
        ticker=it["ticker"],
        publication_datetime=it["publication_datetime"],
        source_document_id=it.get("source_document_id"),
        raw_label=it["raw_label"],
        normalized_label=it["normalized_label"],
        full_sentence=it["full_sentence"],
        previous_sentence=it.get("previous_sentence"),
        next_sentence=it.get("next_sentence"),
        nearby_heading=it.get("nearby_heading"),
        detected_numeric_tokens=num_strs,
        detected_typed_numeric_tokens=typed_nums,
        current_dictionary_status=dict_status,
        current_proposed_canonical_concept=new_concept,
        current_qualifiers=qualifiers,
        seed_concept=new_concept,
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
    rebuilt_items.append(item)

# 5. Validate that all items pass BenchmarkItem invariants
print("Validating all rebuilt items against BenchmarkItem integrity rules...")
for item in rebuilt_items:
    BenchmarkItem.model_validate(item.model_dump())
print("All rebuilt items passed validation!")

# 6. Save rebuilt financial_classifier_benchmark.json
save_benchmark_json(rebuilt_items, b_path, corpus_meta=corpus_meta)
print(f"Successfully saved {len(rebuilt_items)} items to {b_path}")

# 7. Identify surviving Batch 001 items
# The original Batch 001 items were BENCH-0001 through BENCH-0300
batch_001_items = [it for it in rebuilt_items if int(it.benchmark_id.split("-")[1]) <= 300]
print(f"Surviving Batch 001 items: {len(batch_001_items)}")

# 8. Export updated financial_classifier_gold_review_001.csv
csv_path = Path("gui/modules/analysis/data/financial_classifier_gold_review_001.csv")
batch_001_ids = [it.benchmark_id for it in batch_001_items]
export_review_worksheet_csv(batch_001_items, csv_path, batch_ids=batch_001_ids)
print(f"Successfully exported {len(batch_001_items)} rows to {csv_path}")

# 9. Export updated FINANCIAL_CLASSIFIER_GOLD_REVIEW_001.md
md_path = Path("docs/FINANCIAL_CLASSIFIER_GOLD_REVIEW_001.md")
generate_gold_review_markdown(batch_001_items, md_path, batch_title="Review Batch 001 (Deterministic Heuristic Baseline)")
print(f"Successfully exported markdown review artifact to {md_path}")

# 10. Write retired IDs artifact for transparency
retired_artifact_path = Path("docs/FINANCIAL_CLASSIFIER_RETIRED_OCCURRENCES_001.json")
retired_report = {
    "generated_at": datetime.now().isoformat(),
    "summary": {
        "benchmark_size_before": total_before,
        "benchmark_size_after": total_after,
        "duplicates_removed_count": len(duplicates_retired),
        "nested_alias_removed_count": len(nested_retired),
        "batch_001_surviving_count": len(batch_001_items),
        "role_changes": role_changes,
        "pattern_changes": pattern_changes,
        "concept_changes": concept_changes,
        "guidance_corrections": guidance_corrections,
        "margin_corrections": margin_corrections,
        "numeric_corrections": numeric_corrections,
    },
    "duplicates_retired": duplicates_retired,
    "nested_retired": nested_retired
}

with open(retired_artifact_path, "w", encoding="utf-8") as f:
    json.dump(retired_report, f, indent=2)
print(f"Saved retired items audit report to {retired_artifact_path}")
