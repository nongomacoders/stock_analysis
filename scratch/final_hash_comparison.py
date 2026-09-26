"""
Root cause confirmed: the GOLD-001 release hash was computed using:
    SELECT ... FROM financial_classifier_gold_review ORDER BY benchmark_id
WITHOUT a review_batch filter, over exactly 300 rows (as they existed at that time).

We now need to establish what the CORRECT authoritative hash is.

Strategy: use the identical query the baseline script used (no WHERE, ORDER BY benchmark_id)
but now applied only to BATCH-001 rows. Since no WHERE clause was used originally,
and the table had exactly 300 rows at that time (= the BATCH-001 rows), we should
compute the hash the same way: no WHERE, ORDER BY benchmark_id.
BUT now the table has 820 rows, so we can't use that approach.

The correct forward-compatible approach is to use WHERE review_batch = 'BATCH-001'.
We need to determine which hash is the "truth":
  a) 3c5e... (baseline script, no WHERE, 300 rows at time of creation)
  b) 7f95... (WHERE review_batch = 'BATCH-001', 300 rows now)

Both represent the same 300 rows. The difference MUST be a data difference.

Let's compare row by row between the baseline script hash context and now.
The baseline script's build_dataset_hash() ran without a WHERE clause.
Let's try to replicate that exact query over the first 300 rows (LIMIT 300, no WHERE).
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

# Fetch BATCH-001 rows and BATCH-002/003 first rows to compare order
cur.execute(f"""
    SELECT {cols_sql}, review_batch
    FROM financial_classifier_gold_review
    ORDER BY benchmark_id
    LIMIT 5
""")
print("First 5 rows by ORDER BY benchmark_id (no WHERE):")
for r in cur.fetchall():
    print(f"  {r['benchmark_id']} batch={r['review_batch']} decision={r['review_decision']}")

# Now: the original baseline computed hash with the Python column list.
# The reviewer_notes for BENCH-0061 has U+2019 (right single quote).
# This was in the DB when the hash was computed, so that's consistent.

# Let's compute the hash using NO WHERE (baseline approach) but only on BATCH-001 IDs
cur.execute(f"""
    SELECT {cols_sql}
    FROM financial_classifier_gold_review
    ORDER BY benchmark_id
""")
all_820 = cur.fetchall()

# The dry-run ran on a fresh DB with ONLY 300 rows at 08:50:23.
# At that time, the table had reviewer_notes for all BATCH-001 rows as they were.
# The BATCH-002/003 rows were inserted at 08:51:05 (after the baseline ran).
# So the baseline hash was computed over 300 rows.
# Now: first 300 by benchmark_id = BENCH-0001..0300 = BATCH-001.
# These should be the same rows.

first_300 = [r for r in all_820 if r["benchmark_id"] <= "BENCH-0300"]
print(f"\nRows with benchmark_id <= BENCH-0300: {len(first_300)}")

hasher = hashlib.sha256()
for row in first_300:
    line = "|".join(f"{col}={cv(row[col])}" for col in HASH_COLUMNS) + "\n"
    hasher.update(line.encode("utf-8"))
h = hasher.hexdigest()
print(f"Hash of BENCH-0001..0300 from full table scan: {h}")
print(f"Matches expected: {h == EXPECTED}")

# Also compute directly row by row and store for comparison
cur.execute(f"""
    SELECT {cols_sql}
    FROM financial_classifier_gold_review
    WHERE review_batch = 'BATCH-001'
    ORDER BY benchmark_id
""")
batch001 = cur.fetchall()

# Compare first_300 vs batch001 row by row
print(f"\nComparing first 300 from full scan vs BATCH-001 filter:")
print(f"  Both have {len(first_300)} == {len(batch001)} rows: {len(first_300) == len(batch001)}")

diffs = 0
for i, (r1, r2) in enumerate(zip(first_300, batch001)):
    for col in HASH_COLUMNS:
        if cv(r1[col]) != cv(r2[col]):
            print(f"  DIFF at row {i} ({r1['benchmark_id']}): {col}: {cv(r1[col])!r} vs {cv(r2[col])!r}")
            diffs += 1

if diffs == 0:
    print("  No differences found between full scan and BATCH-001 filter.")
else:
    print(f"  Total field differences: {diffs}")

conn.close()
