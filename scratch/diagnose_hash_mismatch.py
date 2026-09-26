"""
Diagnose the GOLD-001 hash mismatch.
Compare the hash column values for BATCH-001 rows against what the release record expects.
Identify any row-level differences.
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

def canonical_val(v) -> str:
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
print(f"BATCH-001 rows fetched: {len(rows)}")

# Build per-row canonical lines
lines = []
for row in rows:
    line = "|".join(f"{col}={canonical_val(row[col])}" for col in HASH_COLUMNS) + "\n"
    lines.append((row["benchmark_id"], line))

hasher = hashlib.sha256()
for bid, line in lines:
    hasher.update(line.encode("utf-8"))
computed = hasher.hexdigest()
print(f"Computed hash: {computed}")
print(f"Expected hash: {EXPECTED}")
print(f"Match: {computed == EXPECTED}")

if computed != EXPECTED:
    print("\nSearching for differing rows vs release record ...")
    # Try computing hash from the release record's hash column manifest stored in DB
    cur.execute("SELECT hash_column_manifest, dataset_hash FROM financial_classifier_gold_releases WHERE release_id = 'GOLD-001'")
    rel = cur.fetchone()
    import json
    stored_manifest = json.loads(rel["hash_column_manifest"])
    print(f"\nRelease hash_column_manifest ({len(stored_manifest)} cols):")
    print(f"  {stored_manifest}")
    print(f"\nCurrent HASH_COLUMNS ({len(HASH_COLUMNS)} cols):")
    print(f"  {HASH_COLUMNS}")

    # Check if manifests differ
    if stored_manifest != HASH_COLUMNS:
        print("\n[!] MANIFEST DIFFERS from HASH_COLUMNS used now!")
        extra_in_stored = [c for c in stored_manifest if c not in HASH_COLUMNS]
        extra_in_current = [c for c in HASH_COLUMNS if c not in stored_manifest]
        print(f"  In stored but not current: {extra_in_stored}")
        print(f"  In current but not stored: {extra_in_current}")
    else:
        print("\nManifests match. Checking for data differences ...")

    # Recompute using the stored manifest
    cols_sql2 = ", ".join(stored_manifest)
    cur.execute(f"""
        SELECT {cols_sql2}
        FROM financial_classifier_gold_review
        WHERE review_batch = 'BATCH-001'
        ORDER BY benchmark_id
    """)
    rows2 = cur.fetchall()
    hasher2 = hashlib.sha256()
    for row in rows2:
        line = "|".join(f"{col}={canonical_val(row[col])}" for col in stored_manifest) + "\n"
        hasher2.update(line.encode("utf-8"))
    computed2 = hasher2.hexdigest()
    print(f"\nHash using stored manifest: {computed2}")
    print(f"Matches release record:     {computed2 == rel['dataset_hash']}")
    print(f"Matches expected:           {computed2 == EXPECTED}")

    # Check specific field values for first 5 rows that might differ
    print("\nFirst 5 rows canonical lines (current):")
    for bid, line in lines[:5]:
        print(f"  {bid}: {line[:200]}")

conn.close()
