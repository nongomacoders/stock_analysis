import hashlib, psycopg2, psycopg2.extras
import sys
from pathlib import Path
sys.path.insert(0, str(Path("gui").resolve()))
from core.config import DB_CONFIG

TARGET = "3c5e1ce829eac535a4c7263b3caed47266f67ed7fd16b8f61586164992efbc24"

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

def cv(v):
    if v is None: return "NULL"
    if isinstance(v, bool): return "TRUE" if v else "FALSE"
    return str(v)

conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
cols_sql = ", ".join(HASH_COLUMNS)
cur.execute(f"SELECT {cols_sql} FROM financial_classifier_gold_review WHERE review_batch = 'BATCH-001' ORDER BY benchmark_id")
rows = cur.fetchall()

# Current hash
h_curr = hashlib.sha256()
for r in rows:
    line = "|".join(f"{col}={cv(r[col])}" for col in HASH_COLUMNS) + "\n"
    h_curr.update(line.encode("utf-8"))
print("Current hash:", h_curr.hexdigest())

# Test 1: all reviewer_notes NULL
h1 = hashlib.sha256()
for r in rows:
    line = "|".join(f"{col}={(cv(r[col]) if col != 'reviewer_notes' else 'NULL')}" for col in HASH_COLUMNS) + "\n"
    h1.update(line.encode("utf-8"))
print("Test 1 (all reviewer_notes NULL):", h1.hexdigest(), h1.hexdigest() == TARGET)

# Test 2: CONFIRM_SEED reviewer_notes NULL
h2 = hashlib.sha256()
for r in rows:
    line = "|".join(f"{col}={(cv(r[col]) if not (col == 'reviewer_notes' and r['review_decision'] == 'CONFIRM_SEED') else 'NULL')}" for col in HASH_COLUMNS) + "\n"
    h2.update(line.encode("utf-8"))
print("Test 2 (CONFIRM_SEED reviewer_notes NULL):", h2.hexdigest(), h2.hexdigest() == TARGET)

# Test 3: all override flags FALSE
h3 = hashlib.sha256()
for r in rows:
    line = "|".join(f"{col}={(cv(r[col]) if not col.endswith('_is_override') else 'FALSE')}" for col in HASH_COLUMNS) + "\n"
    h3.update(line.encode("utf-8"))
print("Test 3 (all override flags FALSE):", h3.hexdigest(), h3.hexdigest() == TARGET)

# Test 4: without reviewer_notes col
h4 = hashlib.sha256()
for r in rows:
    line = "|".join(f"{col}={cv(r[col])}" for col in HASH_COLUMNS[:-1]) + "\n"
    h4.update(line.encode("utf-8"))
print("Test 4 (without reviewer_notes col):", h4.hexdigest(), h4.hexdigest() == TARGET)

# Test 5: base 29 cols
h5 = hashlib.sha256()
cols_base = HASH_COLUMNS[:29]
for r in rows:
    line = "|".join(f"{col}={cv(r[col])}" for col in cols_base) + "\n"
    h5.update(line.encode("utf-8"))
print("Test 5 (base 29 cols):", h5.hexdigest(), h5.hexdigest() == TARGET)

# Test 6: CRLF vs LF
h6 = hashlib.sha256()
for r in rows:
    line = "|".join(f"{col}={cv(r[col])}" for col in HASH_COLUMNS) + "\r\n"
    h6.update(line.encode("utf-8"))
print("Test 6 (CRLF):", h6.hexdigest(), h6.hexdigest() == TARGET)

# Test 7: without trailing newline
h7 = hashlib.sha256()
for idx, r in enumerate(rows):
    line = "|".join(f"{col}={cv(r[col])}" for col in HASH_COLUMNS)
    if idx < len(rows) - 1:
        line += "\n"
    h7.update(line.encode("utf-8"))
print("Test 7 (no final newline):", h7.hexdigest(), h7.hexdigest() == TARGET)

conn.close()
