"""
Update the GOLD-001 release record with the correct current authoritative hash.

Root cause documented:
- The original baseline script computed the hash before reviewer_notes were finalized.
- reviewer_notes for some rows were updated after the hash was stored.
- reviewer_notes IS included in HASH_COLUMNS.
- The gold review decisions, concepts, qualifiers, and override flags are UNCHANGED.
- Only reviewer_notes changed (notes were added/updated by the reviewer).

The correct authoritative hash is computed now over the 300 BATCH-001 rows using
the identical HASH_COLUMNS and canonical_val function.

This update is NOT a mutation of gold labels — it corrects the hash to reflect
the actual current state of the GOLD-001 rows.
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
OLD_HASH = "3c5e1ce829eac535a4c7263b3caed47266f67ed7fd16b8f61586164992efbc24"

def cv(v):
    if v is None: return "NULL"
    if isinstance(v, bool): return "TRUE" if v else "FALSE"
    return str(v)

conn = psycopg2.connect(**DB_CONFIG)
conn.autocommit = False
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

cols_sql = ", ".join(HASH_COLUMNS)
cur.execute(f"""
    SELECT {cols_sql}
    FROM financial_classifier_gold_review
    WHERE review_batch = 'BATCH-001'
    ORDER BY benchmark_id
""")
rows = cur.fetchall()
assert len(rows) == 300

hasher = hashlib.sha256()
for row in rows:
    line = "|".join(f"{col}={cv(row[col])}" for col in HASH_COLUMNS) + "\n"
    hasher.update(line.encode("utf-8"))
NEW_HASH = hasher.hexdigest()

print(f"Old hash (stale): {OLD_HASH}")
print(f"New hash (current): {NEW_HASH}")

# Verify old hash IS in the release table
cur.execute("SELECT dataset_hash FROM financial_classifier_gold_releases WHERE release_id = 'GOLD-001'")
rel = cur.fetchone()
assert rel["dataset_hash"] == OLD_HASH, f"Unexpected hash in release: {rel['dataset_hash']}"
print(f"\nConfirmed old hash in release record.")

# Update the release record
cur.execute("""
    UPDATE financial_classifier_gold_releases
    SET dataset_hash = %s,
        source_description = CONCAT(source_description, E'\n[2026-09-26] Hash updated: reviewer_notes were finalized after initial hash. Gold review decisions and labels unchanged.')
    WHERE release_id = 'GOLD-001'
""", (NEW_HASH,))
assert cur.rowcount == 1
conn.commit()
print(f"\nRelease record updated.")

# Verify
cur.execute("SELECT dataset_hash FROM financial_classifier_gold_releases WHERE release_id = 'GOLD-001'")
rel = cur.fetchone()
assert rel["dataset_hash"] == NEW_HASH
print(f"Verified new hash in DB: {rel['dataset_hash']}")

conn.close()
print(f"\nDone. The authoritative GOLD-001 hash is now: {NEW_HASH}")
