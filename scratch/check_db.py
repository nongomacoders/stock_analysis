import psycopg2
import json
from pathlib import Path
from core.config import DB_CONFIG

# Connect to database and check SENS rows
conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM sens;")
print("SENS count:", cur.fetchone()[0])
conn.close()
