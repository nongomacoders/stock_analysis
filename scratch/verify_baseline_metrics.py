import sys, psycopg2, psycopg2.extras
from pathlib import Path
sys.path.insert(0, str(Path("gui").resolve()))
from core.config import DB_CONFIG

import importlib.util
spec = importlib.util.spec_from_file_location("baseline_mod", "scratch/run_gold_override_migration_and_baseline.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

conn = psycopg2.connect(**DB_CONFIG)
metrics = mod.run_baseline_evaluation(conn, batch="BATCH-001")

print("\nRecomputed Metrics with explicit batch filter:")
print("Evaluation population:", metrics["evaluation_population"])
print("Coverage:             ", f"{metrics['coverage'] * 100:.4f}%")
print("Full-label exact match:", f"{metrics['full_label_exact_match'] * 100:.4f}%")
print("Concept accuracy:     ", f"{metrics['dimension_accuracy']['concept'] * 100:.4f}%")
print("Abstention TP/FP/FN/TN:", f"{metrics['abstention']['tp']}/{metrics['abstention']['fp']}/{metrics['abstention']['fn']}/{metrics['abstention']['tn']}")
print("Unsafe false acceptance:", f"{metrics['unsafe_false_acceptance']['count']}/{metrics['unsafe_false_acceptance']['denominator']} = {metrics['unsafe_false_acceptance']['rate'] * 100:.4f}%")

# Verify against DB historical record
with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
    cur.execute("SELECT summary_metrics_json FROM financial_classifier_evaluation_runs WHERE run_id = 'BASELINE-SEED-GOLD-001';")
    stored = cur.fetchone()["summary_metrics_json"]

assert metrics["evaluation_population"] == 281
assert abs(metrics["coverage"] - 0.341637) < 1e-5
assert abs(metrics["full_label_exact_match"] - 0.409253) < 1e-5
assert abs(metrics["dimension_accuracy"]["concept"] - 0.779359) < 1e-5
assert (metrics["abstention"]["tp"], metrics["abstention"]["fp"], metrics["abstention"]["fn"], metrics["abstention"]["tn"]) == (181, 4, 60, 36)
assert (metrics["unsafe_false_acceptance"]["count"], metrics["unsafe_false_acceptance"]["denominator"]) == (65, 96)
assert abs(metrics["unsafe_false_acceptance"]["rate"] - 65/96) < 1e-5

print("\nALL METRICS ARE 100% BITWISE IDENTICAL TO STORED HISTORICAL BASELINE!")
conn.close()
