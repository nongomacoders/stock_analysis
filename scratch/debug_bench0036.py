import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gui"))
import psycopg2
import psycopg2.extras
from core.config import DB_CONFIG

conn = psycopg2.connect(**DB_CONFIG)
with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
    cur.execute("SELECT * FROM financial_classifier_gold_review WHERE benchmark_id = 'BENCH-0036'")
    row = cur.fetchone()
    for k, v in row.items():
        print(f"  {k}: {repr(v)} ({type(v).__name__})")
conn.close()
