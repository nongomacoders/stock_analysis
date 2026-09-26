"""Check BENCH-0061 reviewer_notes character encoding."""
import sys
from pathlib import Path
import psycopg2, psycopg2.extras

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gui"))
from core.config import DB_CONFIG

conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

cur.execute("SELECT benchmark_id, reviewer_notes FROM financial_classifier_gold_review WHERE benchmark_id = 'BENCH-0061'")
r = cur.fetchone()
notes = r["reviewer_notes"]
print(f"reviewer_notes: {notes!r}")
print(f"Length: {len(notes)}")
for i, ch in enumerate(notes):
    if ord(ch) > 127:
        print(f"  Non-ASCII at pos {i}: U+{ord(ch):04X} {ch!r}")

# Also check if the hash computed at dry-run time matches if we
# replace the smart quote with a straight apostrophe
import hashlib

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

cols_sql = ", ".join(HASH_COLUMNS)
cur.execute(f"""
    SELECT {cols_sql}
    FROM financial_classifier_gold_review
    WHERE review_batch = 'BATCH-001'
    ORDER BY benchmark_id
""")
rows = cur.fetchall()

# Variant: replace smart quotes with straight apostrophe in reviewer_notes
SMART = "\u2018\u2019\u201c\u201d"
REPLACEMENTS = str.maketrans(SMART, "'''\"")

hasher = hashlib.sha256()
for row in rows:
    line_parts = []
    for col in HASH_COLUMNS:
        val = cv(row[col])
        if col == "reviewer_notes" and row[col]:
            val = cv(row[col].translate(REPLACEMENTS))
        line_parts.append(f"{col}={val}")
    line = "|".join(line_parts) + "\n"
    hasher.update(line.encode("utf-8"))
h = hasher.hexdigest()
print(f"\nHash with smart-quote normalization: {h}")
print(f"Matches expected: {h == EXPECTED}")

# Also try: the original baseline script ran with conn_factory=None (no RealDictCursor)
# but the hash was computed on dictionaries - check for psycopg2 dict ordering issue
# Actually RealDictCursor is used throughout

# Check: at the time of dry-run, was reviewer_notes stored differently?
# Look at what the CSV imported. Read the CSV.
csv_path = Path(__file__).resolve().parents[1] / "gui/scripts/data/financial_classifier_gold_review_001.csv"
if not csv_path.exists():
    csv_path = list(Path(__file__).resolve().parents[1].rglob("financial_classifier_gold_review_001.csv"))
    if csv_path:
        csv_path = csv_path[0]
    else:
        csv_path = None

if csv_path:
    print(f"\nCSV found: {csv_path}")
    with open(csv_path, encoding="utf-8-sig") as f:
        import csv
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("benchmark_id") == "BENCH-0061":
                notes_csv = row.get("reviewer_notes", "")
                print(f"BENCH-0061 reviewer_notes in CSV: {notes_csv!r}")
                for i, ch in enumerate(notes_csv):
                    if ord(ch) > 127:
                        print(f"  Non-ASCII at pos {i}: U+{ord(ch):04X} {ch!r}")
                break
else:
    print("\nCSV not found.")

conn.close()
