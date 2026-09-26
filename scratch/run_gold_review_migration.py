"""Apply the financial_classifier_gold_review migration."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gui"))
import psycopg2
from core.config import DB_CONFIG

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "gui/core/db/migrations/add_financial_classifier_gold_review.sql"
)

# Strip BOM if present (PowerShell Set-Content with UTF8 adds a BOM)
sql = MIGRATION.read_text(encoding="utf-8-sig")
conn = psycopg2.connect(**DB_CONFIG)
conn.autocommit = True
with conn.cursor() as cur:
    cur.execute(sql)
conn.close()
print("Migration applied successfully.")
