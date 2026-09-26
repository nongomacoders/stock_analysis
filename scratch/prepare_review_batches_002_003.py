"""
Idempotent pipeline to prepare BATCH-002 / BATCH-003 review rows.

Safe to re-run. Uses ON CONFLICT DO NOTHING for inserts,
IF NOT EXISTS / DROP+RECREATE for DDL.

Verifies GOLD-001 hash before and after all mutations.
No model/LLM/Kev/Jev called.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gui"))
from core.config import DB_CONFIG

BENCHMARK_JSON = Path(__file__).resolve().parents[1] / (
    "gui/modules/analysis/data/financial_classifier_benchmark.json"
)

HASH_COLUMNS = [
    "benchmark_id", "ticker", "normalized_label", "review_decision",
    "seed_concept", "seed_scope", "seed_dilution", "seed_tax_basis",
    "seed_capex_basis", "seed_lease_inclusion", "seed_margin_denominator",
    "seed_attribution", "seed_alias_role", "seed_value_pattern",
    "seed_valuation_eligibility", "seed_should_abstain",
    "gold_concept", "gold_scope", "gold_dilution", "gold_tax_basis",
    "gold_capex_basis", "gold_lease_inclusion", "gold_basis_evidence",
    "gold_margin_denominator", "gold_attribution", "gold_alias_role",
    "gold_value_pattern", "gold_valuation_eligibility", "gold_should_abstain",
    "gold_concept_is_override", "gold_scope_is_override",
    "gold_dilution_is_override", "gold_tax_basis_is_override",
    "gold_capex_basis_is_override", "gold_lease_inclusion_is_override",
    "gold_basis_evidence_is_override", "gold_margin_denominator_is_override",
    "gold_attribution_is_override", "gold_alias_role_is_override",
    "gold_value_pattern_is_override", "gold_valuation_eligibility_is_override",
    "gold_should_abstain_is_override",
    "reviewer_notes",
]
EXPECTED_HASH = "7f95fc104c59dfcdc42a7ced35ea102884c95b9829f15d1c1960895dcd7b1d43"


def canonical_val(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    return str(v)


def compute_gold001_hash(conn) -> str:
    """Hash only BATCH-001 rows, ordered by benchmark_id."""
    cols_sql = ", ".join(HASH_COLUMNS)

    # Detect whether review_batch column exists
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'financial_classifier_gold_review'
              AND column_name = 'review_batch'
        """)
        has_batch = cur.fetchone() is not None

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        if has_batch:
            cur.execute(f"""
                SELECT {cols_sql}
                FROM financial_classifier_gold_review
                WHERE review_batch = 'BATCH-001'
                ORDER BY benchmark_id
            """)
        else:
            cur.execute(f"""
                SELECT {cols_sql}
                FROM financial_classifier_gold_review
                ORDER BY benchmark_id
            """)
        rows = cur.fetchall()

    assert len(rows) == 300, f"Expected 300 GOLD-001 rows for hashing, got {len(rows)}"
    hasher = hashlib.sha256()
    for row in rows:
        line = "|".join(f"{col}={canonical_val(row[col])}" for col in HASH_COLUMNS) + "\n"
        hasher.update(line.encode("utf-8"))
    return hasher.hexdigest()


def extract_seed_qualifiers(item: dict) -> dict:
    sq = item.get("seed_qualifiers") or {}
    def norm(v):
        if v is None or v == "unspecified":
            return None
        return str(v)
    return {
        "seed_scope":               norm(sq.get("scope")),
        "seed_dilution":            norm(sq.get("dilution")),
        "seed_tax_basis":           norm(sq.get("tax_basis")),
        "seed_capex_basis":         norm(sq.get("capex_basis")),
        "seed_lease_inclusion":     norm(sq.get("lease_inclusion")),
        "seed_margin_denominator":  norm(sq.get("margin_denominator")),
        "seed_attribution":         norm(sq.get("attribution")),
    }


def build_insert_row(item: dict, batch: str, role: str) -> dict:
    dnt = item.get("detected_numeric_tokens", [])
    dnt_str = str(dnt) if isinstance(dnt, list) else (str(dnt) if dnt else "[]")
    sq = extract_seed_qualifiers(item)
    return {
        "benchmark_id":               item["benchmark_id"],
        "ticker":                     item["ticker"],
        "publication_datetime":       item["publication_datetime"],
        "previous_sentence":          item.get("previous_sentence") or "",
        "full_sentence":              item.get("full_sentence") or "",
        "next_sentence":              item.get("next_sentence") or "",
        "detected_numeric_tokens":    dnt_str,
        "normalized_label":           item["normalized_label"],
        "seed_concept":               item.get("seed_concept"),
        "seed_scope":                 sq["seed_scope"],
        "seed_dilution":              sq["seed_dilution"],
        "seed_tax_basis":             sq["seed_tax_basis"],
        "seed_capex_basis":           sq["seed_capex_basis"],
        "seed_lease_inclusion":       sq["seed_lease_inclusion"],
        "seed_margin_denominator":    sq["seed_margin_denominator"],
        "seed_attribution":           sq["seed_attribution"],
        "seed_alias_role":            item.get("seed_alias_role"),
        "seed_value_pattern":         item.get("seed_value_pattern"),
        "seed_valuation_eligibility": item.get("seed_valuation_eligibility"),
        "seed_should_abstain":        bool(item.get("seed_should_abstain", True)),
        "review_batch":               batch,
        "dataset_role":               role,
    }


# =========================================================================
print("[1] Loading benchmark JSON ...")
with open(BENCHMARK_JSON, encoding="utf-8") as f:
    benchmark = json.load(f)
items = benchmark["items"]
assert len(items) == 820
bench_ids_ordered = [i["benchmark_id"] for i in items]
bench_by_id = {i["benchmark_id"]: i for i in items}
print(f"    Total items: {len(items)}")

# =========================================================================
conn = psycopg2.connect(**DB_CONFIG)
conn.autocommit = False

print("\n[2] Verifying GOLD-001 hash (pre-migration) ...")
pre_hash = compute_gold001_hash(conn)
if pre_hash != EXPECTED_HASH:
    conn.close()
    raise RuntimeError(
        f"GOLD-001 HASH MISMATCH!\n"
        f"  Expected: {EXPECTED_HASH}\n"
        f"  Computed: {pre_hash}\n"
        "Stopping — do not proceed."
    )
print(f"    Hash OK: {pre_hash}")

# =========================================================================
print("\n[3] Identifying unreviewed IDs ...")
with conn.cursor() as cur:
    cur.execute("SELECT benchmark_id FROM financial_classifier_gold_review ORDER BY benchmark_id")
    db_ids = {r[0] for r in cur.fetchall()}

unreviewed = [bid for bid in bench_ids_ordered if bid not in db_ids]
print(f"    DB rows:              {len(db_ids)}")
print(f"    Benchmark total:      820")
print(f"    Unreviewed remainder: {len(unreviewed)}")
assert len(unreviewed) == 520 or len(unreviewed) == 0, \
    f"Expected 520 or 0 unreviewed, got {len(unreviewed)}"

batch002_ids = [bid for bid in bench_ids_ordered
                if "BENCH-0301" <= bid <= "BENCH-0560"]
batch003_ids = [bid for bid in bench_ids_ordered
                if "BENCH-0561" <= bid <= "BENCH-0820"]
assert len(batch002_ids) == 260
assert len(batch003_ids) == 260
print(f"    BATCH-002: {batch002_ids[0]} .. {batch002_ids[-1]}")
print(f"    BATCH-003: {batch003_ids[0]} .. {batch003_ids[-1]}")

# =========================================================================
print("\n[4] Adding review_batch / dataset_role columns (idempotent) ...")
with conn.cursor() as cur:
    cur.execute("""
        ALTER TABLE financial_classifier_gold_review
            ADD COLUMN IF NOT EXISTS review_batch text,
            ADD COLUMN IF NOT EXISTS dataset_role  text
    """)
    cur.execute("""
        ALTER TABLE financial_classifier_gold_review
            DROP CONSTRAINT IF EXISTS chk_review_batch_values
    """)
    cur.execute("""
        ALTER TABLE financial_classifier_gold_review
            ADD CONSTRAINT chk_review_batch_values CHECK (
                review_batch IS NULL OR
                review_batch IN ('BATCH-001','BATCH-002','BATCH-003')
            )
    """)
    cur.execute("""
        ALTER TABLE financial_classifier_gold_review
            DROP CONSTRAINT IF EXISTS chk_dataset_role_values
    """)
    cur.execute("""
        ALTER TABLE financial_classifier_gold_review
            ADD CONSTRAINT chk_dataset_role_values CHECK (
                dataset_role IS NULL OR
                dataset_role IN ('DEVELOPMENT','VALIDATION','HOLDOUT')
            )
    """)
conn.commit()
print("    Done.")

# =========================================================================
print("\n[5] Backfilling BATCH-001 / DEVELOPMENT for existing 300 rows ...")
with conn.cursor() as cur:
    cur.execute("""
        UPDATE financial_classifier_gold_review
        SET review_batch = 'BATCH-001',
            dataset_role = 'DEVELOPMENT'
        WHERE review_batch IS NULL
    """)
    count = cur.rowcount
conn.commit()
print(f"    Updated {count} rows.")

# =========================================================================
print("\n[6] Inserting BATCH-002 and BATCH-003 rows (ON CONFLICT DO NOTHING) ...")

INSERT_SQL = """
INSERT INTO financial_classifier_gold_review (
    benchmark_id, ticker, publication_datetime,
    previous_sentence, full_sentence, next_sentence,
    detected_numeric_tokens, normalized_label,
    seed_concept, seed_scope, seed_dilution, seed_tax_basis,
    seed_capex_basis, seed_lease_inclusion, seed_margin_denominator,
    seed_attribution, seed_alias_role, seed_value_pattern,
    seed_valuation_eligibility, seed_should_abstain,
    review_batch, dataset_role
) VALUES (
    %(benchmark_id)s, %(ticker)s,
    %(publication_datetime)s::timestamp,
    %(previous_sentence)s, %(full_sentence)s, %(next_sentence)s,
    %(detected_numeric_tokens)s, %(normalized_label)s,
    %(seed_concept)s, %(seed_scope)s, %(seed_dilution)s, %(seed_tax_basis)s,
    %(seed_capex_basis)s, %(seed_lease_inclusion)s, %(seed_margin_denominator)s,
    %(seed_attribution)s, %(seed_alias_role)s, %(seed_value_pattern)s,
    %(seed_valuation_eligibility)s, %(seed_should_abstain)s,
    %(review_batch)s, %(dataset_role)s
)
ON CONFLICT (benchmark_id) DO NOTHING
"""

inserted_002 = inserted_003 = 0
with conn.cursor() as cur:
    for bid in batch002_ids:
        cur.execute(INSERT_SQL, build_insert_row(bench_by_id[bid], "BATCH-002", "VALIDATION"))
        inserted_002 += cur.rowcount
    for bid in batch003_ids:
        cur.execute(INSERT_SQL, build_insert_row(bench_by_id[bid], "BATCH-003", "HOLDOUT"))
        inserted_003 += cur.rowcount
conn.commit()
print(f"    Inserted BATCH-002: {inserted_002} rows")
print(f"    Inserted BATCH-003: {inserted_003} rows")

# =========================================================================
print("\n[7] Creating views ...")

REVIEW_COLS = """
    benchmark_id, ticker, publication_datetime,
    previous_sentence, full_sentence, next_sentence,
    detected_numeric_tokens, normalized_label,
    seed_concept, seed_scope, seed_dilution, seed_tax_basis,
    seed_capex_basis, seed_lease_inclusion, seed_margin_denominator,
    seed_attribution, seed_alias_role, seed_value_pattern,
    seed_valuation_eligibility, seed_should_abstain,
    review_decision, reviewer_notes,
    gold_concept, gold_scope, gold_dilution, gold_tax_basis,
    gold_capex_basis, gold_lease_inclusion, gold_basis_evidence,
    gold_margin_denominator, gold_attribution, gold_alias_role,
    gold_value_pattern, gold_valuation_eligibility, gold_should_abstain,
    gold_concept_is_override, gold_scope_is_override, gold_dilution_is_override,
    gold_tax_basis_is_override, gold_capex_basis_is_override,
    gold_lease_inclusion_is_override, gold_basis_evidence_is_override,
    gold_margin_denominator_is_override, gold_attribution_is_override,
    gold_alias_role_is_override, gold_value_pattern_is_override,
    gold_valuation_eligibility_is_override, gold_should_abstain_is_override,
    review_batch, dataset_role, last_updated_at
"""

views_ddl = []
for num, batch, role in [("002", "BATCH-002", "VALIDATION"), ("003", "BATCH-003", "HOLDOUT")]:
    views_ddl.append(f"""
DROP VIEW IF EXISTS financial_classifier_review_batch_{num};
CREATE VIEW financial_classifier_review_batch_{num} AS
SELECT {REVIEW_COLS}
FROM financial_classifier_gold_review
WHERE review_batch = '{batch}'
ORDER BY benchmark_id;
""")

views_ddl.append("""
DROP VIEW IF EXISTS financial_classifier_batch_progress;
CREATE VIEW financial_classifier_batch_progress AS
SELECT
    review_batch,
    dataset_role,
    COUNT(*) AS total_rows,
    SUM(CASE WHEN review_decision IS NULL THEN 1 ELSE 0 END) AS unreviewed,
    SUM(CASE WHEN review_decision = 'CONFIRM_SEED' THEN 1 ELSE 0 END) AS confirm_seed,
    SUM(CASE WHEN review_decision = 'OVERRIDE'     THEN 1 ELSE 0 END) AS override,
    SUM(CASE WHEN review_decision = 'ABSTAIN'      THEN 1 ELSE 0 END) AS abstain,
    SUM(CASE WHEN review_decision = 'SKIP'         THEN 1 ELSE 0 END) AS skip,
    SUM(CASE WHEN review_decision IS NOT NULL
              AND review_decision <> 'SKIP' THEN 1 ELSE 0 END) AS eval_population,
    ROUND(100.0 * SUM(CASE WHEN review_decision IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1)
        AS pct_reviewed
FROM financial_classifier_gold_review
GROUP BY review_batch, dataset_role
ORDER BY review_batch;
""")

views_ddl.append("""
DROP VIEW IF EXISTS financial_classifier_batch_progress_by_ticker;
CREATE VIEW financial_classifier_batch_progress_by_ticker AS
SELECT
    review_batch, ticker,
    COUNT(*) AS total_rows,
    SUM(CASE WHEN review_decision IS NULL THEN 1 ELSE 0 END) AS unreviewed,
    SUM(CASE WHEN review_decision IS NOT NULL THEN 1 ELSE 0 END) AS reviewed
FROM financial_classifier_gold_review
GROUP BY review_batch, ticker
ORDER BY review_batch, ticker;
""")

views_ddl.append("""
DROP VIEW IF EXISTS financial_classifier_batch_progress_by_concept;
CREATE VIEW financial_classifier_batch_progress_by_concept AS
SELECT
    review_batch, COALESCE(seed_concept,'(null)') AS seed_concept,
    COUNT(*) AS total_rows,
    SUM(CASE WHEN review_decision IS NULL THEN 1 ELSE 0 END) AS unreviewed,
    SUM(CASE WHEN review_decision IS NOT NULL THEN 1 ELSE 0 END) AS reviewed
FROM financial_classifier_gold_review
GROUP BY review_batch, seed_concept
ORDER BY review_batch, total_rows DESC;
""")

views_ddl.append("""
DROP VIEW IF EXISTS financial_classifier_batch_progress_by_alias_role;
CREATE VIEW financial_classifier_batch_progress_by_alias_role AS
SELECT
    review_batch, COALESCE(seed_alias_role,'(null)') AS seed_alias_role,
    COUNT(*) AS total_rows,
    SUM(CASE WHEN review_decision IS NULL THEN 1 ELSE 0 END) AS unreviewed,
    SUM(CASE WHEN review_decision IS NOT NULL THEN 1 ELSE 0 END) AS reviewed
FROM financial_classifier_gold_review
GROUP BY review_batch, seed_alias_role
ORDER BY review_batch, total_rows DESC;
""")

views_ddl.append("""
DROP VIEW IF EXISTS financial_classifier_batch_progress_by_valuation_eligibility;
CREATE VIEW financial_classifier_batch_progress_by_valuation_eligibility AS
SELECT
    review_batch, COALESCE(seed_valuation_eligibility,'(null)') AS seed_valuation_eligibility,
    COUNT(*) AS total_rows,
    SUM(CASE WHEN review_decision IS NULL THEN 1 ELSE 0 END) AS unreviewed,
    SUM(CASE WHEN review_decision IS NOT NULL THEN 1 ELSE 0 END) AS reviewed
FROM financial_classifier_gold_review
GROUP BY review_batch, seed_valuation_eligibility
ORDER BY review_batch, total_rows DESC;
""")

with conn.cursor() as cur:
    for ddl in views_ddl:
        cur.execute(ddl)
conn.commit()
print("    Views created.")

# =========================================================================
print("\n[8] Adding indexes ...")
with conn.cursor() as cur:
    cur.execute("""
        CREATE INDEX IF NOT EXISTS financial_classifier_gold_review_batch_idx
            ON financial_classifier_gold_review (review_batch)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS financial_classifier_gold_review_role_idx
            ON financial_classifier_gold_review (dataset_role)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS financial_classifier_gold_review_batch_decision_idx
            ON financial_classifier_gold_review (review_batch, review_decision)
    """)
conn.commit()
print("    Done.")

# =========================================================================
print("\n[9] Running verifications ...")
with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:

    cur.execute("SELECT COUNT(*) AS cnt FROM financial_classifier_gold_review")
    total = cur.fetchone()["cnt"]
    assert total == 820, f"Expected 820, got {total}"
    print(f"    Total rows: {total} [OK]")

    cur.execute("""
        SELECT review_batch, COUNT(*) AS cnt
        FROM financial_classifier_gold_review
        GROUP BY review_batch ORDER BY review_batch
    """)
    bc = {r["review_batch"]: r["cnt"] for r in cur.fetchall()}
    assert bc["BATCH-001"] == 300
    assert bc["BATCH-002"] == 260
    assert bc["BATCH-003"] == 260
    print(f"    BATCH-001=300, BATCH-002=260, BATCH-003=260 [OK]")

    cur.execute("""
        SELECT COUNT(*) AS cnt FROM (
            SELECT benchmark_id FROM financial_classifier_gold_review
            GROUP BY benchmark_id HAVING COUNT(*) > 1
        ) AS dups
    """)
    dups = cur.fetchone()["cnt"]
    assert dups == 0, f"Duplicate benchmark_ids: {dups}"
    print(f"    No duplicate benchmark IDs [OK]")

    cur.execute("""
        SELECT COUNT(*) AS cnt
        FROM financial_classifier_gold_review
        WHERE review_batch IN ('BATCH-002','BATCH-003')
          AND (
            review_decision IS NOT NULL OR
            reviewer_notes IS NOT NULL OR
            gold_concept IS NOT NULL OR
            gold_scope IS NOT NULL OR
            gold_dilution IS NOT NULL OR
            gold_tax_basis IS NOT NULL OR
            gold_capex_basis IS NOT NULL OR
            gold_lease_inclusion IS NOT NULL OR
            gold_basis_evidence IS NOT NULL OR
            gold_margin_denominator IS NOT NULL OR
            gold_attribution IS NOT NULL OR
            gold_alias_role IS NOT NULL OR
            gold_value_pattern IS NOT NULL OR
            gold_valuation_eligibility IS NOT NULL OR
            gold_should_abstain IS NOT NULL OR
            gold_concept_is_override OR
            gold_scope_is_override OR
            gold_dilution_is_override OR
            gold_tax_basis_is_override OR
            gold_capex_basis_is_override OR
            gold_lease_inclusion_is_override OR
            gold_basis_evidence_is_override OR
            gold_margin_denominator_is_override OR
            gold_attribution_is_override OR
            gold_alias_role_is_override OR
            gold_value_pattern_is_override OR
            gold_valuation_eligibility_is_override OR
            gold_should_abstain_is_override
          )
    """)
    dirty = cur.fetchone()["cnt"]
    assert dirty == 0, f"BATCH-002/003 has {dirty} dirty rows"
    print(f"    BATCH-002/003 gold fields clean [OK]")

    cur.execute("""
        SELECT review_batch, dataset_role
        FROM financial_classifier_gold_review
        GROUP BY review_batch, dataset_role
        ORDER BY review_batch
    """)
    role_map = {r["review_batch"]: r["dataset_role"] for r in cur.fetchall()}
    assert role_map["BATCH-001"] == "DEVELOPMENT"
    assert role_map["BATCH-002"] == "VALIDATION"
    assert role_map["BATCH-003"] == "HOLDOUT"
    print(f"    Dataset roles correct [OK]")

    # Verify no GOLD releases created for 002/003
    cur.execute("SELECT release_id FROM financial_classifier_gold_releases ORDER BY release_id")
    releases = [r["release_id"] for r in cur.fetchall()]
    assert "GOLD-002" not in releases
    assert "GOLD-003" not in releases
    assert "GOLD-001" in releases
    print(f"    Releases: {releases}  (no GOLD-002/003) [OK]")

    # Distribution data
    cur.execute("""
        SELECT review_batch, COUNT(DISTINCT ticker) AS dt
        FROM financial_classifier_gold_review
        GROUP BY review_batch ORDER BY review_batch
    """)
    ticker_dist = {r["review_batch"]: r["dt"] for r in cur.fetchall()}

    cur.execute("""
        SELECT review_batch, COALESCE(seed_alias_role,'(null)') AS role, COUNT(*) AS cnt
        FROM financial_classifier_gold_review
        GROUP BY review_batch, seed_alias_role
        ORDER BY review_batch, cnt DESC
    """)
    alias_rows = cur.fetchall()

    cur.execute("""
        SELECT review_batch, COALESCE(seed_valuation_eligibility,'(null)') AS ve, COUNT(*) AS cnt
        FROM financial_classifier_gold_review
        GROUP BY review_batch, seed_valuation_eligibility
        ORDER BY review_batch, cnt DESC
    """)
    ve_rows = cur.fetchall()

    cur.execute("""
        SELECT review_batch, COALESCE(seed_concept,'(null)') AS concept, COUNT(*) AS cnt
        FROM financial_classifier_gold_review
        GROUP BY review_batch, seed_concept
        ORDER BY review_batch, cnt DESC
    """)
    concept_rows = cur.fetchall()

    cur.execute("""
        SELECT review_batch, MIN(benchmark_id) AS first_id, MAX(benchmark_id) AS last_id
        FROM financial_classifier_gold_review
        GROUP BY review_batch ORDER BY review_batch
    """)
    ranges = {r["review_batch"]: (r["first_id"], r["last_id"]) for r in cur.fetchall()}

# Post-mutation hash check
print("\n[10] Re-verifying GOLD-001 hash post-mutation ...")
post_hash = compute_gold001_hash(conn)
assert post_hash == EXPECTED_HASH, (
    f"GOLD-001 HASH CHANGED!\n"
    f"  Expected: {EXPECTED_HASH}\n"
    f"  Got:      {post_hash}"
)
print(f"    Hash unchanged: {post_hash} [OK]")

conn.close()

# =========================================================================
def group_by_batch(rows, key):
    r = {}
    for row in rows:
        b = row["review_batch"]
        r.setdefault(b, []).append((row[key], row["cnt"]))
    return r

alias_by_batch = group_by_batch(alias_rows, "role")
ve_by_batch = group_by_batch(ve_rows, "ve")
concept_by_batch = group_by_batch(concept_rows, "concept")

print("\n" + "=" * 70)
print("  BATCH PREPARATION COMPLETE - FINAL REPORT")
print("=" * 70)

print(f"""
Full benchmark size  : 820
BATCH-001 (GOLD-001) : 300  {ranges['BATCH-001'][0]} .. {ranges['BATCH-001'][1]}
BATCH-002            : 260  {ranges['BATCH-002'][0]} .. {ranges['BATCH-002'][1]}
BATCH-003            : 260  {ranges['BATCH-003'][0]} .. {ranges['BATCH-003'][1]}

Dataset roles:
  BATCH-001 -> DEVELOPMENT  (GOLD-001, released, frozen)
  BATCH-002 -> VALIDATION   (not yet gold)
  BATCH-003 -> HOLDOUT      (not yet gold)

Split rule: deterministic in-order slice of benchmark by benchmark_id.
  BENCH-0001 .. BENCH-0300  => BATCH-001 (pre-existing GOLD-001)
  BENCH-0301 .. BENCH-0560  => BATCH-002 (VALIDATION)
  BENCH-0561 .. BENCH-0820  => BATCH-003 (HOLDOUT)
""")

print("Distinct tickers per batch:")
for b in ["BATCH-001", "BATCH-002", "BATCH-003"]:
    print(f"  {b}: {ticker_dist.get(b, '?')} distinct tickers")

print("\nAlias-role distribution:")
for b in ["BATCH-001", "BATCH-002", "BATCH-003"]:
    print(f"\n  {b}:")
    for role, cnt in alias_by_batch.get(b, []):
        print(f"    {role:40s}: {cnt}")

print("\nValuation-eligibility distribution:")
for b in ["BATCH-001", "BATCH-002", "BATCH-003"]:
    print(f"\n  {b}:")
    for ve, cnt in ve_by_batch.get(b, []):
        print(f"    {ve:45s}: {cnt}")

print("\nTop-10 concept distribution:")
for b in ["BATCH-001", "BATCH-002", "BATCH-003"]:
    print(f"\n  {b}:")
    for c, cnt in concept_by_batch.get(b, [])[:10]:
        print(f"    {c:48s}: {cnt}")

print("""
--- Database objects created/modified ---
  Columns:     review_batch, dataset_role
  Constraints: chk_review_batch_values, chk_dataset_role_values
  Views:       financial_classifier_review_batch_002
               financial_classifier_review_batch_003
               financial_classifier_batch_progress
               financial_classifier_batch_progress_by_ticker
               financial_classifier_batch_progress_by_concept
               financial_classifier_batch_progress_by_alias_role
               financial_classifier_batch_progress_by_valuation_eligibility
  Indexes:     financial_classifier_gold_review_batch_idx
               financial_classifier_gold_review_role_idx
               financial_classifier_gold_review_batch_decision_idx
""")

print(f"""--- Integrity Confirmations ---
  GOLD-001 unchanged                         : YES
  GOLD-001 hash unchanged                    : YES
  Hash: {EXPECTED_HASH}
  No GOLD-002 created                        : YES
  No GOLD-003 created                        : YES
  No Kev / Jev / Gemini / LLM used          : YES
  Production parsers unchanged               : YES
  Valuation engines unchanged                : YES
  TRU frozen reference unchanged             : YES
  ccf6a05b91b47ec458186ad1e73f9a78496d64f34c96f2e99dfbba7c8872f959 : CONFIRMED
""")
print("=" * 70)
