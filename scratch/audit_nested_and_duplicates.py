import json
from collections import defaultdict
from pathlib import Path

path = Path("gui/modules/analysis/data/financial_classifier_benchmark.json")
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

items = data["items"]
print(f"Total items: {len(items)}")

# Group by (sens_id, full_sentence)
by_sentence = defaultdict(list)
for it in items:
    key = (it["sens_id"], it["full_sentence"].strip())
    by_sentence[key].append(it)

nested_pairs = []
exact_duplicates = []

for (sens_id, sentence), group in by_sentence.items():
    if len(group) > 1:
        # Check for exact label duplicates
        labels = [it["normalized_label"] for it in group]
        if len(labels) != len(set(labels)):
            exact_duplicates.append((sens_id, group))
            
        # Check for nested spans
        for i in range(len(group)):
            for j in range(len(group)):
                if i != j:
                    l1 = group[i]["normalized_label"]
                    l2 = group[j]["normalized_label"]
                    if l1 != l2 and l1 in l2:
                        nested_pairs.append((group[j]["benchmark_id"], l2, group[i]["benchmark_id"], l1, sentence))

print(f"\nExact duplicate occurrences in dataset: {len(exact_duplicates)}")
for sens_id, grp in exact_duplicates:
    print(f"  sens_id {sens_id}: {[it['benchmark_id'] for it in grp]} labels: {[it['normalized_label'] for it in grp]}")
    print(f"    sentence: {grp[0]['full_sentence'][:80]}")

print(f"\nNested alias pairs in dataset: {len(nested_pairs)}")
seen_nested = set()
for b_longer, l_longer, b_shorter, l_shorter, sent in nested_pairs:
    pair_key = (b_longer, b_shorter)
    if pair_key not in seen_nested:
        seen_nested.add(pair_key)
        print(f"  Longer: {b_longer} ({l_longer}) suppresses Shorter: {b_shorter} ({l_shorter})")
        print(f"    sentence: {sent[:90]}")
