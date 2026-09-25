import csv
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path("gui").resolve()))
from modules.analysis.financial_classifier_benchmark import load_benchmark_json, get_batch_001_ids

b_path = Path("gui/modules/analysis/data/financial_classifier_benchmark.json")
items = load_benchmark_json(b_path)
item_map = {it.benchmark_id: it for it in items}

batch_001_ids = get_batch_001_ids()
first_50_ids = batch_001_ids[:50]

print(f"Total surviving Batch 001: {len(batch_001_ids)}")
print(f"Inspecting first 50 Batch 001 items...")

rows = []
inconsistencies = []

for bid in first_50_ids:
    it = item_map[bid]
    typed_tok_strs = [
        f"{t.raw_text} ({t.token_type.value}, norm={t.normalized_numeric_value})"
        for t in it.detected_typed_numeric_tokens
    ]
    
    # Internal consistency audit checks
    # 1. DIRECT_VALUE_LABEL or DIRECT_LEVEL without metric tokens
    metric_tokens = [t for t in it.detected_typed_numeric_tokens if t.token_type not in ("YEAR_OR_DATE", "OTHER")]
    if not metric_tokens:
        if it.seed_alias_role in ("DIRECT_VALUE_LABEL", "CHANGE_STATEMENT"):
            inconsistencies.append((bid, "Zero metric tokens but role is " + it.seed_alias_role.value))
        if it.seed_value_pattern == "DIRECT_LEVEL":
            inconsistencies.append((bid, "Zero metric tokens but pattern is DIRECT_LEVEL"))
    
    # 2. Percentage only with change verb must be CHANGE_STATEMENT/CHANGE_RATE_ONLY
    if metric_tokens and all(t.is_percentage for t in metric_tokens):
        if it.seed_concept not in ("operating_margin", "gross_margin", "trading_margin", "ebitda_margin"):
            if it.seed_value_pattern == "DIRECT_LEVEL":
                inconsistencies.append((bid, "Percentage-only metric level for non-margin concept seeded DIRECT_LEVEL"))
    
    # 3. Guidance must be INFORMATIONAL_ONLY and abstain
    if it.seed_alias_role == "GUIDANCE_STATEMENT":
        if it.seed_valuation_eligibility != "INFORMATIONAL_ONLY" or not it.seed_should_abstain:
            inconsistencies.append((bid, "Guidance statement is not INFORMATIONAL_ONLY or should_abstain=True"))
            
    # 4. Margin denominator unevidenced must be UNSPECIFIED and abstain
    if it.seed_concept in ("operating_margin", "gross_margin", "trading_margin", "ebitda_margin"):
        if it.seed_qualifiers.margin_denominator.value == "unspecified":
            if not it.seed_should_abstain or it.seed_valuation_eligibility != "REQUIRES_BASIS":
                inconsistencies.append((bid, "Unspecified margin denominator is not REQUIRES_BASIS / should_abstain=True"))

    rows.append({
        "benchmark_id": it.benchmark_id,
        "ticker": it.ticker,
        "normalized_label": it.normalized_label,
        "full_sentence": it.full_sentence.replace("\n", " ").strip(),
        "detected_typed_tokens": "; ".join(typed_tok_strs) if typed_tok_strs else "[]",
        "seed_concept": it.seed_concept or "None",
        "seed_alias_role": it.seed_alias_role.value,
        "seed_value_pattern": it.seed_value_pattern.value,
        "seed_valuation_eligibility": it.seed_valuation_eligibility.value,
        "seed_should_abstain": str(it.seed_should_abstain)
    })

print(f"Total rows inspected: {len(rows)}")
print(f"Internal inconsistencies detected: {len(inconsistencies)}")
if inconsistencies:
    for inc in inconsistencies:
        print("  INCONSISTENCY:", inc)
else:
    print("Zero internal inconsistencies across first 50 review rows!")

# Save rows as JSON for formatting into markdown report
with open("scratch/first_50_audit.json", "w", encoding="utf-8") as f:
    json.dump(rows, f, indent=2)
