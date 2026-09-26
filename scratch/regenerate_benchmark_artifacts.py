import json, csv, os
from pathlib import Path
import psycopg2
from core.config import DB_CONFIG
from modules.analysis.financial_classifier_benchmark import (
    build_stratified_benchmark,
    save_benchmark_json,
    generate_gold_review_markdown,
    export_review_worksheet_csv,
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

print(f"Total benchmark items generated: {len(items)}")
gold_confirmed_count = sum(1 for it in items if it.review_status == ReviewStatus.GOLD_CONFIRMED)
print(f"GOLD_CONFIRMED count: {gold_confirmed_count}")
assert gold_confirmed_count == 0, "GOLD_CONFIRMED must be exactly 0!"

# Save benchmark JSON
json_path = Path("gui/modules/analysis/data/financial_classifier_benchmark.json")
save_benchmark_json(items, json_path)
print(f"Saved benchmark JSON to {json_path}")

# Batch 001 is first 300 items
batch_001 = items[:300]
batch_001_ids = [it.benchmark_id for it in batch_001]

# Save gold review markdown
md_path = Path("docs/FINANCIAL_CLASSIFIER_GOLD_REVIEW_001.md")
generate_gold_review_markdown(batch_001, md_path, batch_title="Review Batch 001")
print(f"Saved gold review markdown to {md_path}")

# Save CSV review worksheet
csv_path = Path("gui/modules/analysis/data/financial_classifier_gold_review_001.csv")
export_review_worksheet_csv(items, csv_path, batch_ids=batch_001_ids)
print(f"Saved CSV review worksheet to {csv_path}")
