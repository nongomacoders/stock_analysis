import json
from pathlib import Path

# Load scratch/verify_parser_rules module
import sys
sys.path.insert(0, str(Path("scratch").resolve()))
from verify_parser_rules import (
    parse_detected_numeric_tokens,
    NumericTokenType,
    resolve_nested_alias_spans
)

# Load existing benchmark items
b_path = Path("gui/modules/analysis/data/financial_classifier_benchmark.json")
with open(b_path, "r", encoding="utf-8") as f:
    items = json.load(f)["items"]

print(f"Total benchmark items: {len(items)}")

# Test cases mentioned by user:
# 1. "Revenue R235,6 billion, up 4,3%; up 6,8%"
# 2. "anticipates that it will report: a basic loss per share of between 138.30 cents and 138.48 cents"
# 3. "Earnings per share increase 16%" / "Headline earnings per share increase 14%"
# 4. "in a 22.2% operating margin"
# 5. "Headline earnings per share 2 562,7 cents"

for it in items:
    s = it["full_sentence"]
    b_id = it["benchmark_id"]
    if "235,6" in s:
        print(f"[{b_id}] JSE format item: {s[:60]}")
        toks = parse_detected_numeric_tokens(s)
        print("  Detected tokens:", [(t.raw_text, t.normalized_numeric_value, t.token_type.value) for t in toks])
    if "138.30" in s:
        print(f"[{b_id}] Guidance item: {s[:60]}")
        toks = parse_detected_numeric_tokens(s)
        print("  Detected tokens:", [(t.raw_text, t.normalized_numeric_value, t.token_type.value) for t in toks])
    if "increase 14%" in s or "increase 16%" in s:
        print(f"[{b_id}] Change-rate item: {s[:60]}")
        toks = parse_detected_numeric_tokens(s)
        print("  Detected tokens:", [(t.raw_text, t.normalized_numeric_value, t.token_type.value) for t in toks])
    if "22.2%" in s or "operating margin" in it["normalized_label"]:
        if "22.2%" in s:
            print(f"[{b_id}] Margin denominator item: {s[:60]}")
            toks = parse_detected_numeric_tokens(s)
            print("  Detected tokens:", [(t.raw_text, t.normalized_numeric_value, t.token_type.value) for t in toks])
