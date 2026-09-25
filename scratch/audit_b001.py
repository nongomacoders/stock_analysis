import json
from collections import defaultdict
from pathlib import Path

bench_data = json.load(open('gui/modules/analysis/data/financial_classifier_benchmark.json', encoding='utf-8'))
items = bench_data['items']

# Extract Batch 001 IDs from docs/FINANCIAL_CLASSIFIER_GOLD_REVIEW_001.md
import re
text = open('docs/FINANCIAL_CLASSIFIER_GOLD_REVIEW_001.md', encoding='utf-8').read()
b001_ids = list(dict.fromkeys(re.findall(r'BENCH-\d{4}', text)))
print("Batch 001 total IDs:", len(b001_ids))

b001_items = [it for it in items if it['benchmark_id'] in set(b001_ids)]
# Preserve order
b001_map = {it['benchmark_id']: it for it in b001_items}
ordered_b001 = [b001_map[bid] for bid in b001_ids if bid in b001_map]

# Check duplicates within Batch 001
seen_occurrences = set()
b001_exact_dups = []
b001_nested = []

# Group by (sens_id, full_sentence)
by_sent = defaultdict(list)
for it in ordered_b001:
    by_sent[(it['sens_id'], it['full_sentence'].strip())].append(it)

for (sens_id, sent), grp in by_sent.items():
    # Exact duplicate labels
    seen_labels = set()
    for it in grp:
        lbl = it['normalized_label']
        if lbl in seen_labels:
            b001_exact_dups.append(it['benchmark_id'])
        else:
            seen_labels.add(lbl)
            
    # Nested labels
    for i in range(len(grp)):
        l1 = grp[i]['normalized_label']
        b1 = grp[i]['benchmark_id']
        for j in range(len(grp)):
            if i != j:
                l2 = grp[j]['normalized_label']
                b2 = grp[j]['benchmark_id']
                if l1 != l2 and l1 in l2 and b1 not in b001_exact_dups:
                    b001_nested.append((b2, l2, b1, l1))

print("Batch 001 exact duplicates:", len(b001_exact_dups), b001_exact_dups[:10])
print("Batch 001 nested items to suppress:", len(b001_nested), b001_nested[:5])
