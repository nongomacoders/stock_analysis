"""Inspect PAN HY2026 extraction results across verified, review, and conflicting candidates.
"""
import json

with open("gui/results_history/PAN/HY2026/afs_experiments/gemini_38_mode_a_audit.json") as f:
    data = json.load(f)

targets = [
    ("gold_produced", "128,296"),
    ("gold_sold", "127,296"),
    ("realised_price", "3,812"),
    ("aisc", "1,874"),
    ("cash_costs", "1,574"),
    ("aic", "2,300"),
    ("revenue", "487.1"),
    ("adjusted_ebitda", "245.2"),
    ("attributable_earnings", "148.0"),
    ("headline_earnings", "148.8"),
    ("operating_cash_flow", "259.5"),
    ("net_debt", "46.2"),
    ("total_capex", "66.1"),
    ("sustaining_capex", "9.6"),
    ("wans_shares", "2,027.3"),
    ("recovered_grade", "6.90"),
    ("recovery", "97"),
    ("throughput", "13,591,354"),
    ("guidance", "275,000"),
]

print("=== CHECKING GEMINI 3.8 FLASH EXTRACTION ACROSS AUDIT LOGS ===")
for name, val in targets:
    found = []
    for r in data["requests_and_responses"]:
        p = r.get("parsed", {})
        tok = str(p.get("candidate_raw_token", ""))
        concept = p.get("canonical_concept", "")
        quote = p.get("supporting_quote", "")
        if val in tok or (val.replace(",", "") in tok.replace(",", "")):
            found.append((concept, tok, quote[:60], r.get("evidence_id")))
    if found:
        print(f"FOUND {name} ({val}): {len(found)} candidate occurrences")
        for c, t, q, ev in found[:2]:
            print(f"   -> concept={c}, token='{t}', ev={ev}")
            print(f"      quote='{q}'")
    else:
        print(f"NOT FOUND in audit logs: {name} ({val})")

print("\n=== CHALLENGE FINDINGS SUMMARY ===")
print("Total challenge findings:", len(data["challenge_summary"]["findings"]))
for f in data["challenge_summary"]["findings"][:10]:
    print(f"  [{f['finding_type']}] ({f['severity']}) p.{f.get('source_page')}: {f['title']}")
    print(f"    {f['description'][:100]}...")
