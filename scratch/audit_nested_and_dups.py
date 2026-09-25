import json
from collections import defaultdict
from pathlib import Path

b_path = Path("gui/modules/analysis/data/financial_classifier_benchmark.json")
with open(b_path, "r", encoding="utf-8") as f:
    data = json.load(f)

items = data["items"]
print(f"Total items in benchmark: {len(items)}")

# 1. Exact duplicates: identical (sens_id, full_sentence.strip(), normalized_label)
seen_exact = {}
duplicates = []
unique_items = []

for it in items:
    key = (it["sens_id"], it["full_sentence"].strip(), it["normalized_label"])
    if key in seen_exact:
        duplicates.append((it["benchmark_id"], seen_exact[key], key))
    else:
        seen_exact[key] = it["benchmark_id"]
        unique_items.append(it)

print(f"Exact duplicates found: {len(duplicates)}")
print(f"Unique items after exact deduplication: {len(unique_items)}")

# 2. Nested alias matches within the same (sens_id, full_sentence)
# Group unique items by (sens_id, full_sentence.strip())
sentence_groups = defaultdict(list)
for it in unique_items:
    sentence_groups[(it["sens_id"], it["full_sentence"].strip())].append(it)

nested_removed = []
surviving_items = []

for key, group in sentence_groups.items():
    if len(group) == 1:
        surviving_items.append(group[0])
        continue
    
    # We have multiple items in the same sentence. Find their character spans in full_sentence.
    sentence = key[1]
    # For each item, find all occurrences of raw_label or normalized_label in sentence
    # We can match raw_label
    item_spans = []
    for it in group:
        raw = it["raw_label"]
        start = sentence.lower().find(raw.lower())
        if start == -1:
            start = sentence.lower().find(it["normalized_label"].lower())
        end = start + len(raw) if start != -1 else len(sentence)
        item_spans.append((start, end, it))
    
    # Sort by span length descending
    item_spans.sort(key=lambda x: (-(x[1] - x[0]), x[0]))
    kept = []
    for start, end, it in item_spans:
        contained = False
        for k_start, k_end, k_it in kept:
            if k_start != -1 and start != -1:
                if k_start <= start and end <= k_end and (k_end - k_start) > (end - start):
                    contained = True
                    nested_removed.append((it["benchmark_id"], k_it["benchmark_id"], it["normalized_label"], k_it["normalized_label"], sentence[:60]))
                    break
        if not contained:
            kept.append((start, end, it))
            surviving_items.append(it)

print(f"Nested alias items removed: {len(nested_removed)}")
print(f"Surviving clean items: {len(surviving_items)}")

# Sort surviving items by original benchmark_id
surviving_items.sort(key=lambda x: int(x["benchmark_id"].split("-")[1]))
print(f"Final surviving items: {len(surviving_items)}")

# Inspect first few nested removals
for n in nested_removed[:10]:
    print(f"Removed nested {n[0]} ('{n[2]}') subsumed by {n[1]} ('{n[3]}') in: \"{n[4]}\"")
