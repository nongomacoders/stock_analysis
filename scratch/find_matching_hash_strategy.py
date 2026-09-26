"""
Try all hash computation strategies to find the one matching 3c5e...
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

def canonical_val_v1(v):
    """Original: NULL for None, TRUE/FALSE for bool, str otherwise"""
    if v is None: return "NULL"
    if isinstance(v, bool): return "TRUE" if v else "FALSE"
    return str(v)

def canonical_val_v2(v):
    """Alternative: NULL for None OR 'unspecified', TRUE/FALSE for bool"""
    if v is None: return "NULL"
    if isinstance(v, bool): return "TRUE" if v else "FALSE"
    if v == "unspecified": return "NULL"
    return str(v)

conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
cols_sql = ", ".join(HASH_COLUMNS)

strategies = []

# Strategy A: all 820 rows (no filter), v1 canonical
cur.execute(f"SELECT {cols_sql} FROM financial_classifier_gold_review ORDER BY benchmark_id")
rows_all = cur.fetchall()
hasher = hashlib.sha256()
for row in rows_all:
    line = "|".join(f"{col}={canonical_val_v1(row[col])}" for col in HASH_COLUMNS) + "\n"
    hasher.update(line.encode("utf-8"))
strategies.append(("All 820 rows, v1 canonical", hasher.hexdigest()))

# Strategy B: BATCH-001 only (300 rows), v1 canonical
cur.execute(f"SELECT {cols_sql} FROM financial_classifier_gold_review WHERE review_batch='BATCH-001' ORDER BY benchmark_id")
rows_b1 = cur.fetchall()
hasher = hashlib.sha256()
for row in rows_b1:
    line = "|".join(f"{col}={canonical_val_v1(row[col])}" for col in HASH_COLUMNS) + "\n"
    hasher.update(line.encode("utf-8"))
strategies.append(("BATCH-001 300 rows, v1 canonical", hasher.hexdigest()))

# Strategy C: BATCH-001 only (300 rows), v2 canonical (unspecified->NULL)
hasher = hashlib.sha256()
for row in rows_b1:
    line = "|".join(f"{col}={canonical_val_v2(row[col])}" for col in HASH_COLUMNS) + "\n"
    hasher.update(line.encode("utf-8"))
strategies.append(("BATCH-001 300 rows, v2 unspecified->NULL", hasher.hexdigest()))

# Strategy D: effective view (all rows, no batch filter — 520 have NULL review so excluded)
cur.execute(f"""
    SELECT {cols_sql}
    FROM financial_classifier_gold_effective
    ORDER BY benchmark_id
""")
rows_eff = cur.fetchall()
hasher = hashlib.sha256()
for row in rows_eff:
    line = "|".join(f"{col}={canonical_val_v1(row[col])}" for col in HASH_COLUMNS) + "\n"
    hasher.update(line.encode("utf-8"))
strategies.append((f"Effective view all rows ({len(rows_eff)}), v1 canonical", hasher.hexdigest()))

# Strategy E: just the first 300 rows by benchmark_id (no batch filter)
cur.execute(f"""
    SELECT {cols_sql}
    FROM financial_classifier_gold_review
    ORDER BY benchmark_id
    LIMIT 300
""")
rows_first300 = cur.fetchall()
hasher = hashlib.sha256()
for row in rows_first300:
    line = "|".join(f"{col}={canonical_val_v1(row[col])}" for col in HASH_COLUMNS) + "\n"
    hasher.update(line.encode("utf-8"))
strategies.append(("First 300 rows by benchmark_id (LIMIT 300), v1", hasher.hexdigest()))

print(f"Expected: {EXPECTED}")
print()
for name, h in strategies:
    match = "MATCH!" if h == EXPECTED else "no match"
    print(f"  [{match}] {name}")
    print(f"           {h}")

conn.close()
