"""Print the keys of one benchmark item and sample data to understand the full schema."""
import json, sys
from pathlib import Path

BENCHMARK_JSON = Path(__file__).resolve().parents[1] / "gui/modules/analysis/data/financial_classifier_benchmark.json"

with open(BENCHMARK_JSON, encoding="utf-8") as f:
    benchmark = json.load(f)

items = benchmark["items"]

# Print first item structure
print("=== First item keys ===")
item = items[0]
for k, v in item.items():
    print(f"  {k!r}: {type(v).__name__} = {str(v)[:120]!r}")

print("\n=== Item at index 300 (first of remaining) ===")
item = items[300]
for k, v in item.items():
    print(f"  {k!r}: {type(v).__name__} = {str(v)[:120]!r}")

# Check metadata
print("\n=== Metadata ===")
for k, v in benchmark.get("metadata", {}).items():
    print(f"  {k!r}: {str(v)[:200]!r}")
