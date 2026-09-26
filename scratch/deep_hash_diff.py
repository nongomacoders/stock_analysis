"""
Deep diff between current BATCH-001 rows and what the baseline script would have computed.
Strategy: the baseline script was run_gold_override_migration_and_baseline.py.
Read the compute_dataset_hash function from that script and run it to get the ORIGINAL hash.
Then compare to our current computation.
"""
import hashlib, sys, importlib.util
from pathlib import Path
import psycopg2, psycopg2.extras

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gui"))
from core.config import DB_CONFIG

# Load the original baseline script and extract its hash logic
baseline_path = Path(__file__).resolve().parents[1] / "scratch/run_gold_override_migration_and_baseline.py"
spec = importlib.util.spec_from_file_location("baseline", baseline_path)
baseline_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline_mod)

HASH_COLUMNS_ORIG = baseline_mod.HASH_COLUMNS
canonical_val_orig = baseline_mod.canonical_val

print(f"Original HASH_COLUMNS: {len(HASH_COLUMNS_ORIG)} cols")
print(f"First: {HASH_COLUMNS_ORIG[0]}, Last: {HASH_COLUMNS_ORIG[-1]}")

conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

cols_sql = ", ".join(HASH_COLUMNS_ORIG)
cur.execute(f"""
    SELECT {cols_sql}
    FROM financial_classifier_gold_review
    WHERE review_batch = 'BATCH-001'
    ORDER BY benchmark_id
""")
rows = cur.fetchall()
print(f"\nRows fetched: {len(rows)}")

# Compute hash using original function
hasher = hashlib.sha256()
for row in rows:
    line = "|".join(f"{col}={canonical_val_orig(row[col])}" for col in HASH_COLUMNS_ORIG) + "\n"
    hasher.update(line.encode("utf-8"))

computed_orig_logic = hasher.hexdigest()
EXPECTED = "3c5e1ce829eac535a4c7263b3caed47266f67ed7fd16b8f61586164992efbc24"
print(f"\nComputed (original logic): {computed_orig_logic}")
print(f"Expected:                  {EXPECTED}")
print(f"Match: {computed_orig_logic == EXPECTED}")

# What does the baseline script's compute_dataset_hash function do?
# Let's call it directly if possible
if hasattr(baseline_mod, 'compute_dataset_hash'):
    conn2 = psycopg2.connect(**DB_CONFIG)
    try:
        h = baseline_mod.compute_dataset_hash(conn2)
        print(f"\nDirect baseline compute_dataset_hash: {h}")
        print(f"Match expected: {h == EXPECTED}")
    finally:
        conn2.close()

# Print first 3 rows canonical lines using original logic
print("\nFirst 3 rows using original canonical_val:")
cur.execute(f"""
    SELECT {cols_sql}
    FROM financial_classifier_gold_review
    WHERE review_batch = 'BATCH-001'
    ORDER BY benchmark_id
    LIMIT 3
""")
for row in cur.fetchall():
    line = "|".join(f"{col}={canonical_val_orig(row[col])}" for col in HASH_COLUMNS_ORIG)
    print(f"  {row['benchmark_id']}: {line[:300]}")

conn.close()
