"""
Binary search to find which row causes the hash to diverge.
Also: try computing the hash BEFORE the dry-run migration would have touched anything
by checking if the original seed_scope values were NULL before import.

The baseline script's dry-run hash was computed AFTER the migration ran (within a 
committed transaction). The migration included backfilling override flags.
But since flags are boolean NOT NULL DEFAULT FALSE, they'd have been FALSE already 
after the first migration committed the DDL.

Let me check: was the dry-run hash computed with the same data as now?
The migration script adds boolean columns with DEFAULT FALSE, so they're FALSE
whether added in dry-run or live run. But the live run confirmed flags too.

Let me check if reviewer_notes has any whitespace or encoding differences.
And whether the issue is the order (benchmark_id lexicographic vs numeric).
"""
import hashlib, sys
from pathlib import Path
import psycopg2, psycopg2.extras

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gui"))
from core.config import DB_CONFIG

HASH_COLUMNS = [
    "benchmark_id", "ticker", "normalized_label", "review_decision",
    "seed_concept", "seed_scope", "seed_dilution", "seed_tax_basis",
    "seed_capex_basis", "seed_lease_inclusion", "seed_margin_denominator",
    "seed_attribution", "seed_alias_role", "seed_value_pattern",
    "seed_valuation_eligibility", "seed_should_abstain",
    "gold_concept", "gold_scope", "gold_dilution", "gold_tax_basis",
    "gold_capex_basis", "gold_lease_inclusion", "gold_basis_evidence",
    "gold_margin_denominator", "gold_attribution", "gold_alias_role",
    "gold_value_pattern", "gold_valuation_eligibility", "gold_should_abstain",
    "gold_concept_is_override", "gold_scope_is_override",
    "gold_dilution_is_override", "gold_tax_basis_is_override",
    "gold_capex_basis_is_override", "gold_lease_inclusion_is_override",
    "gold_basis_evidence_is_override", "gold_margin_denominator_is_override",
    "gold_attribution_is_override", "gold_alias_role_is_override",
    "gold_value_pattern_is_override", "gold_valuation_eligibility_is_override",
    "gold_should_abstain_is_override",
    "reviewer_notes",
]
EXPECTED = "3c5e1ce829eac535a4c7263b3caed47266f67ed7fd16b8f61586164992efbc24"

def cv(v):
    if v is None: return "NULL"
    if isinstance(v, bool): return "TRUE" if v else "FALSE"
    return str(v)

conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

cols_sql = ", ".join(HASH_COLUMNS)
cur.execute(f"""
    SELECT {cols_sql}
    FROM financial_classifier_gold_review
    WHERE review_batch = 'BATCH-001'
    ORDER BY benchmark_id
""")
rows = cur.fetchall()

# Compute per-row running hashes to binary search for divergence
# Compare with the expected hash

# Try: sort by benchmark_id as NUMBER not string
# BENCH-0001 lexicographic == numeric up to 0820 so no issue there

# Try: the reviewer_notes field for edge cases
print("Checking reviewer_notes for special characters:")
for i, row in enumerate(rows):
    if row["reviewer_notes"]:
        notes = row["reviewer_notes"]
        # Check for non-ASCII
        try:
            notes.encode("ascii")
        except UnicodeEncodeError as e:
            print(f"  {row['benchmark_id']}: non-ASCII in reviewer_notes: {notes[:100]!r}")
            break
else:
    print("  All reviewer_notes are ASCII-clean.")

# Check boolean handling - what type does psycopg2 return for bool columns?
print("\nChecking boolean column types for first row:")
cur.execute("""
    SELECT gold_concept_is_override, gold_should_abstain_is_override,
           seed_should_abstain
    FROM financial_classifier_gold_review
    WHERE review_batch = 'BATCH-001'
    ORDER BY benchmark_id LIMIT 1
""")
r = cur.fetchone()
for k, v in r.items():
    print(f"  {k}: type={type(v).__name__}, value={v!r}, canonical={cv(v)!r}")

# Rebuild the hash using the evaluation run stored in DB
# The baseline evaluation run stored per-row predictions.
# The hash stored in releases was computed at a specific moment.
# Let me check if the hash was computed BEFORE or AFTER the override flags were backfilled.

# Fetch the evaluation run record to see what timestamp it was stored
cur.execute("SELECT * FROM financial_classifier_evaluation_runs WHERE run_id = 'BASELINE-SEED-GOLD-001'")
run = cur.fetchone()
if run:
    print(f"\nEvaluation run created_at: {run['created_at']}")

cur.execute("SELECT * FROM financial_classifier_gold_releases WHERE release_id = 'GOLD-001'")
rel = cur.fetchone()
if rel:
    print(f"Release created_at: {rel['created_at']}")
    print(f"Release dataset_hash: {rel['dataset_hash']}")

# The key insight: was the hash computed BEFORE or AFTER the override flags were set?
# Check if ANY override flag is TRUE in BATCH-001 rows
cur.execute("""
    SELECT COUNT(*) AS cnt FROM financial_classifier_gold_review
    WHERE review_batch = 'BATCH-001'
    AND (gold_concept_is_override OR gold_scope_is_override OR
         gold_dilution_is_override OR gold_should_abstain_is_override)
""")
flag_count = cur.fetchone()["cnt"]
print(f"\nBATCH-001 rows with any override flag TRUE: {flag_count}")

# Quick sanity: what hash do we get for just BENCH-0001?
cur.execute(f"""
    SELECT {cols_sql}
    FROM financial_classifier_gold_review
    WHERE benchmark_id = 'BENCH-0001'
""")
r = cur.fetchone()
line = "|".join(f"{col}={cv(r[col])}" for col in HASH_COLUMNS)
print(f"\nBENCH-0001 canonical line ({len(line)} chars):")
print(f"  {line}")

conn.close()
