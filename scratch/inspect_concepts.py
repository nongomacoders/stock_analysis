import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gui"))
import modules.analysis.financial_concept_dictionary as fcd
import modules.analysis.financial_classifier_benchmark as fcb
import psycopg2
import psycopg2.extras
from core.config import DB_CONFIG

print("Members of fcd:")
for name in dir(fcd):
    if not name.startswith("_"):
        val = getattr(fcd, name)
        if isinstance(val, type):
            print(f"  Class: {name}")

conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

# Check distinct effective_concepts in GOLD-001
cur.execute("""
    SELECT DISTINCT effective_concept 
    FROM financial_classifier_gold_001_effective 
    WHERE effective_concept IS NOT NULL
    ORDER BY effective_concept;
""")
eff_concepts = [r["effective_concept"] for r in cur.fetchall()]
print(f"\nDistinct effective_concept in GOLD-001 ({len(eff_concepts)}):")
print(eff_concepts)

# Check distinct seed_concepts across all gold_review
cur.execute("""
    SELECT DISTINCT seed_concept 
    FROM financial_classifier_gold_review 
    WHERE seed_concept IS NOT NULL
    ORDER BY seed_concept;
""")
seed_concepts = [r["seed_concept"] for r in cur.fetchall()]
print(f"\nDistinct seed_concept in gold_review ({len(seed_concepts)}):")
print(seed_concepts)

# Check canonical concepts in dictionary if any
if hasattr(fcd, "DEFAULT_CONCEPTS"):
    print(f"\nDEFAULT_CONCEPTS: {len(fcd.DEFAULT_CONCEPTS)}")
elif hasattr(fcd, "CANONICAL_CONCEPTS"):
    print(f"\nCANONICAL_CONCEPTS: {len(fcd.CANONICAL_CONCEPTS)}")
