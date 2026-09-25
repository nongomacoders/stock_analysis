import json
import re
from pathlib import Path
from collections import Counter, defaultdict

from modules.analysis.financial_concept_dictionary import (
    AliasStatus,
    BasisEvidence,
    CapexBasis,
    DilutionBasis,
    DividendTaxBasis,
    LeaseInclusion,
    MarginDenominator,
    NumericSign,
    OperationScope,
    ProfitAttribution,
    SemanticQualifiers,
)

# Load existing benchmark items
bench_path = Path("gui/modules/analysis/data/financial_classifier_benchmark.json")
raw_data = json.load(open(bench_path, "r", encoding="utf-8"))
raw_items = raw_data["items"]
print(f"Total existing items: {len(raw_items)}")

# 1. Audit exact duplicates
seen_occurrences = set()
unique_items = []
exact_dup_ids = []

for it in raw_items:
    occ_key = (it["sens_id"], it["full_sentence"].strip(), it["normalized_label"])
    if occ_key in seen_occurrences:
        exact_dup_ids.append(it["benchmark_id"])
    else:
        seen_occurrences.add(occ_key)
        unique_items.append(it)

print(f"Exact duplicates removed: {len(exact_dup_ids)}")
print(f"Unique items remaining: {len(unique_items)}")

# 2. Audit nested matches in same sentence
by_sent = defaultdict(list)
for it in unique_items:
    by_sent[(it["sens_id"], it["full_sentence"].strip())].append(it)

nested_ids = []
non_nested_items = []

for (sens_id, sent), grp in by_sent.items():
    if len(grp) == 1:
        non_nested_items.append(grp[0])
        continue
        
    # Find spans for each label in the sentence
    sent_lower = sent.lower()
    item_spans = []
    for it in grp:
        lbl = it["normalized_label"]
        # Find all occurrences of lbl in sent_lower
        start = 0
        while True:
            idx = sent_lower.find(lbl, start)
            if idx == -1:
                break
            item_spans.append((idx, idx + len(lbl), it))
            start = idx + 1
            
    # Resolve overlapping spans: keep longest
    surviving_items = set()
    suppressed_ids = set()
    
    # Sort by span length descending
    item_spans.sort(key=lambda x: (x[1] - x[0]), reverse=True)
    
    occupied_spans = []
    for start, end, it in item_spans:
        # Check if this span is covered by an already occupied longer span
        is_covered = any(occ[0] <= start and occ[1] >= end for occ in occupied_spans)
        if is_covered:
            suppressed_ids.add(it["benchmark_id"])
        else:
            occupied_spans.append((start, end))
            surviving_items.add(it["benchmark_id"])
            
    for it in grp:
        if it["benchmark_id"] in surviving_items and it["benchmark_id"] not in suppressed_ids:
            non_nested_items.append(it)
        else:
            nested_ids.append(it["benchmark_id"])

print(f"Nested items suppressed: {len(nested_ids)}")
print(f"Surviving items after nesting audit: {len(non_nested_items)}")
