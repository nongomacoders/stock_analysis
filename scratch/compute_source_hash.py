import hashlib, json, psycopg2, psycopg2.extras
from pathlib import Path
import sys
sys.path.insert(0, str(Path("gui").resolve()))
from core.config import DB_CONFIG

conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
cur.execute("""
    SELECT benchmark_id, ticker, publication_datetime,
           previous_sentence, full_sentence, next_sentence,
           detected_numeric_tokens, normalized_label
    FROM financial_classifier_gold_review
    WHERE review_batch = 'BATCH-001'
    ORDER BY benchmark_id;
""")
rows = cur.fetchall()

def canon_toks(v):
    if v is None: return "[]"
    if isinstance(v, str):
        v = json.loads(v)
    return json.dumps(v, separators=(",", ":"))

def canon_dt(v):
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)

hasher = hashlib.sha256()
for r in rows:
    parts = [
        f"benchmark_id={r['benchmark_id']}",
        f"ticker={r['ticker']}",
        f"publication_datetime={canon_dt(r['publication_datetime'])}",
        f"previous_sentence={r['previous_sentence'] or ''}",
        f"full_sentence={r['full_sentence'] or ''}",
        f"next_sentence={r['next_sentence'] or ''}",
        f"detected_numeric_tokens={canon_toks(r['detected_numeric_tokens'])}",
        f"normalized_label={r['normalized_label']}",
    ]
    line = "|".join(parts) + "\n"
    hasher.update(line.encode("utf-8"))

source_hash = hasher.hexdigest()
print("Computed source_hash for GOLD-001:", source_hash)
conn.close()
