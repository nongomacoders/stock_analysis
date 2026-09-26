import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gui"))
import psycopg2
from core.config import DB_CONFIG

conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor()

cur.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_name = 'financial_classifier_gold_review'")
row = cur.fetchone()
if row:
    print(f"Table found: schema={row[0]}, name={row[1]}")
else:
    print("Table NOT found in information_schema.tables")

try:
    cur.execute("SELECT COUNT(*) FROM financial_classifier_gold_review")
    count = cur.fetchone()[0]
    print(f"Row count: {count}")
except Exception as e:
    print(f"Query error: {e}")

conn.close()
