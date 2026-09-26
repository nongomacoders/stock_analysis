"""
Inspect the canonical benchmark JSON and current DB state to understand:
1. Total benchmark items and their IDs
2. Which IDs are already in the DB (GOLD-001 = 300 rows)
3. Which IDs are missing (the remaining 520)
4. Any duplicates or gaps
"""
import json
import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gui"))
from core.config import DB_CONFIG
import psycopg2
import psycopg2.extras

BENCHMARK_JSON = Path(__file__).resolve().parents[1] / "gui/modules/analysis/data/financial_classifier_benchmark.json"

# --- Load benchmark JSON ---
print(f"Loading benchmark from: {BENCHMARK_JSON}")
with open(BENCHMARK_JSON, encoding="utf-8") as f:
    benchmark = json.load(f)

print(f"\nBenchmark type: {type(benchmark)}")
if isinstance(benchmark, dict):
    print(f"Benchmark keys: {list(benchmark.keys())[:10]}")
    # Try common structures
    if "items" in benchmark:
        items = benchmark["items"]
    elif "benchmark" in benchmark:
        items = benchmark["benchmark"]
    else:
        # Maybe the dict IS the items keyed by benchmark_id?
        first_key = next(iter(benchmark))
        print(f"First key: {first_key!r}, value type: {type(benchmark[first_key])}")
        items = list(benchmark.values())
elif isinstance(benchmark, list):
    items = benchmark
    print(f"List length: {len(items)}")
    print(f"First item keys: {list(items[0].keys()) if items else 'empty'}")

print(f"\nTotal benchmark items: {len(items)}")

# Extract benchmark_ids
benchmark_ids = []
for item in items:
    bid = item.get("benchmark_id") or item.get("id")
    if bid:
        benchmark_ids.append(bid)

print(f"Items with benchmark_id: {len(benchmark_ids)}")
print(f"First 5 IDs: {benchmark_ids[:5]}")
print(f"Last 5 IDs: {benchmark_ids[-5:]}")

# Check for duplicates
dup_counter = Counter(benchmark_ids)
dups = {k: v for k, v in dup_counter.items() if v > 1}
print(f"\nDuplicate IDs: {len(dups)}")
if dups:
    for k, v in list(dups.items())[:10]:
        print(f"  {k}: {v} times")

# --- Load from DB ---
conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

cur.execute("SELECT benchmark_id, review_decision FROM financial_classifier_gold_review ORDER BY benchmark_id")
db_rows = cur.fetchall()
db_ids = set(r["benchmark_id"] for r in db_rows)
print(f"\nDB rows: {len(db_rows)}")
print(f"DB unique IDs: {len(db_ids)}")

# --- Determine overlap and remainder ---
benchmark_id_set = set(benchmark_ids)
in_db_not_benchmark = db_ids - benchmark_id_set
in_benchmark_not_db = benchmark_id_set - db_ids

print(f"\nIn DB but not in benchmark: {len(in_db_not_benchmark)}")
if in_db_not_benchmark:
    print(f"  Sample: {sorted(in_db_not_benchmark)[:10]}")

print(f"In benchmark but not in DB (unreviewed): {len(in_benchmark_not_db)}")
remaining_ids = sorted(in_benchmark_not_db)
print(f"  First 5: {remaining_ids[:5]}")
print(f"  Last 5: {remaining_ids[-5:]}")

# --- Distribution analysis ---
# For remaining items, show concept / ticker / alias_role / valuation_eligibility distribution
remaining_items = [item for item in items
                   if (item.get("benchmark_id") or item.get("id")) in in_benchmark_not_db]
print(f"\nRemaining items to analyze: {len(remaining_items)}")

# Ticker distribution
ticker_counts = Counter(item.get("ticker", "UNKNOWN") for item in remaining_items)
print(f"\nTicker distribution in remaining ({len(ticker_counts)} tickers):")
for t, c in sorted(ticker_counts.items(), key=lambda x: -x[1])[:20]:
    print(f"  {t}: {c}")

# Concept distribution
concept_counts = Counter(item.get("seed_concept") or item.get("concept") for item in remaining_items)
print(f"\nSeed concept distribution in remaining ({len(concept_counts)} concepts):")
for c, n in sorted(concept_counts.items(), key=lambda x: -x[1])[:20]:
    print(f"  {c!r}: {n}")

# Alias role distribution
alias_counts = Counter(item.get("seed_alias_role") for item in remaining_items)
print(f"\nSeed alias_role distribution ({len(alias_counts)} roles):")
for a, n in sorted(alias_counts.items(), key=lambda x: -x[1])[:20]:
    print(f"  {a!r}: {n}")

# Valuation eligibility distribution
ve_counts = Counter(item.get("seed_valuation_eligibility") for item in remaining_items)
print(f"\nSeed valuation_eligibility distribution:")
for v, n in sorted(ve_counts.items(), key=lambda x: -x[1]):
    print(f"  {v!r}: {n}")

# Should abstain distribution
abstain_counts = Counter(item.get("seed_should_abstain") for item in remaining_items)
print(f"\nSeed should_abstain distribution:")
for v, n in sorted(abstain_counts.items(), key=lambda x: -x[1]):
    print(f"  {v!r}: {n}")

conn.close()
print("\nDone.")
