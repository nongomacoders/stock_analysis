"""Verify the financial_classifier_gold_review table after import."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gui"))
import psycopg2
import psycopg2.extras
from core.config import DB_CONFIG

conn = psycopg2.connect(**DB_CONFIG)
with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
    cur.execute("SELECT COUNT(*) AS total, COUNT(DISTINCT benchmark_id) AS distinct_ids FROM financial_classifier_gold_review")
    row = cur.fetchone()
    print(f"Total rows          : {row['total']}")
    print(f"Distinct benchmark_ids: {row['distinct_ids']}")

    cur.execute("SELECT MIN(benchmark_id), MAX(benchmark_id) FROM financial_classifier_gold_review")
    row = cur.fetchone()
    print(f"Min benchmark_id    : {row['min']}")
    print(f"Max benchmark_id    : {row['max']}")

    cur.execute("SELECT COUNT(*) AS unreviewed FROM financial_classifier_gold_review WHERE review_decision IS NULL")
    row = cur.fetchone()
    print(f"Unreviewed rows     : {row['unreviewed']}")

    # Next 5 unreviewed
    cur.execute("""
        SELECT benchmark_id, ticker, publication_datetime, normalized_label,
               seed_concept, seed_scope, seed_dilution, seed_tax_basis,
               seed_capex_basis, seed_lease_inclusion, seed_margin_denominator,
               seed_attribution, seed_alias_role, seed_value_pattern,
               seed_valuation_eligibility, seed_should_abstain,
               previous_sentence, full_sentence, next_sentence,
               detected_numeric_tokens
        FROM financial_classifier_gold_review
        WHERE review_decision IS NULL
        ORDER BY benchmark_id
        LIMIT 5
    """)
    rows = cur.fetchall()
    print(f"\nNext 5 unreviewed rows:")
    for r in rows:
        print(f"  {r['benchmark_id']} | {r['ticker']} | {r['normalized_label']} | seed_abstain={r['seed_should_abstain']}")

conn.close()
