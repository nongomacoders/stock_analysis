"""
Check seed_scope values in DB for BATCH-001 to understand what was stored.
Also check what the GOLD-001 baseline evaluation script computed originally.
"""
import sys
from pathlib import Path
import psycopg2, psycopg2.extras

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gui"))
from core.config import DB_CONFIG

conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

# Check seed_scope values for first 10 BATCH-001 rows
cur.execute("""
    SELECT benchmark_id, seed_scope, seed_dilution, seed_tax_basis
    FROM financial_classifier_gold_review
    WHERE review_batch = 'BATCH-001'
    ORDER BY benchmark_id
    LIMIT 10
""")
rows = cur.fetchall()
print("First 10 BATCH-001 rows - seed qualifier values:")
for r in rows:
    print(f"  {r['benchmark_id']}: scope={r['seed_scope']!r}, dilution={r['seed_dilution']!r}, tax_basis={r['seed_tax_basis']!r}")

# Count how many distinct seed_scope values exist in BATCH-001
cur.execute("""
    SELECT seed_scope, COUNT(*) AS cnt
    FROM financial_classifier_gold_review
    WHERE review_batch = 'BATCH-001'
    GROUP BY seed_scope ORDER BY cnt DESC
""")
print("\nseed_scope values in BATCH-001:")
for r in cur.fetchall():
    print(f"  {r['seed_scope']!r}: {r['cnt']}")

# The ORIGINAL GOLD-001 baseline evaluation script that produced the hash
# Let me read that script and find what it used
baseline_script = Path(__file__).resolve().parents[1] / "scratch/run_gold_override_migration_and_baseline.py"
if baseline_script.exists():
    text = baseline_script.read_text(encoding="utf-8")
    # Find the hash computation context
    idx = text.find("HASH_COLUMNS")
    print(f"\nHash columns in baseline script starts at char {idx}")
    print(text[idx:idx+2000])

conn.close()
