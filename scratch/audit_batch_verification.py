"""
Comprehensive audit of BATCH-001 / BATCH-002 / BATCH-003:

1. GOLD-001 hash verification
2. Batch distribution (row count, tickers, dates, seed dimensions)
3. Top-15 tickers and concepts per batch
4. Temporal/issuer clustering analysis
5. Ticker overlap across batches
6. Holdout isolation check
7. Codebase scan for references to review tables
"""
from __future__ import annotations

import hashlib
import sys
from collections import Counter
from pathlib import Path

import psycopg2
import psycopg2.extras

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gui"))
from core.config import DB_CONFIG

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
EXPECTED_HASH = "3c5e1ce829eac535a4c7263b3caed47266f67ed7fd16b8f61586164992efbc24"

def canonical_val(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    return str(v)

conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

SEP = "=" * 72

# =========================================================================
# A: GOLD-001 hash verification
# =========================================================================
print(SEP)
print("A. GOLD-001 HASH VERIFICATION")
print(SEP)

cols_sql = ", ".join(HASH_COLUMNS)
cur.execute(f"""
    SELECT {cols_sql}
    FROM financial_classifier_gold_review
    WHERE review_batch = 'BATCH-001'
    ORDER BY benchmark_id
""")
gold001_rows = cur.fetchall()
assert len(gold001_rows) == 300, f"Expected 300 GOLD-001 rows, got {len(gold001_rows)}"

hasher = hashlib.sha256()
for row in gold001_rows:
    line = "|".join(f"{col}={canonical_val(row[col])}" for col in HASH_COLUMNS) + "\n"
    hasher.update(line.encode("utf-8"))
computed = hasher.hexdigest()
match = computed == EXPECTED_HASH
print(f"  Expected : {EXPECTED_HASH}")
print(f"  Computed : {computed}")
print(f"  Match    : {'YES [OK]' if match else 'NO [FAIL]'}")
if not match:
    raise RuntimeError("GOLD-001 HASH MISMATCH — stopping.")

# Verify release record
cur.execute("SELECT * FROM financial_classifier_gold_releases WHERE release_id = 'GOLD-001'")
rel = cur.fetchone()
print(f"\n  Release record: GOLD-001")
print(f"    review_row_count      : {rel['review_row_count']}")
print(f"    evaluation_row_count  : {rel['evaluation_row_count']}")
print(f"    confirm_seed_count    : {rel['confirm_seed_count']}")
print(f"    override_count        : {rel['override_count']}")
print(f"    abstain_count         : {rel['abstain_count']}")
print(f"    skip_count            : {rel['skip_count']}")
print(f"    dataset_hash          : {rel['dataset_hash']}")
hash_match = rel['dataset_hash'] == EXPECTED_HASH
print(f"    Hash matches expected : {'YES [OK]' if hash_match else 'NO [FAIL]'}")

# No GOLD-002/003
cur.execute("SELECT release_id FROM financial_classifier_gold_releases ORDER BY release_id")
all_releases = [r["release_id"] for r in cur.fetchall()]
print(f"\n  All releases in DB    : {all_releases}")
assert "GOLD-002" not in all_releases
assert "GOLD-003" not in all_releases
print(f"  No GOLD-002 / GOLD-003 : YES [OK]")

# =========================================================================
# B: Per-batch distribution
# =========================================================================
print(f"\n{SEP}")
print("B. BATCH DISTRIBUTION AUDIT")
print(SEP)

# --- Row counts ---
cur.execute("""
    SELECT review_batch, dataset_role, COUNT(*) AS total,
           COUNT(DISTINCT ticker) AS distinct_tickers,
           MIN(publication_datetime::text) AS pub_min,
           MAX(publication_datetime::text) AS pub_max
    FROM financial_classifier_gold_review
    GROUP BY review_batch, dataset_role
    ORDER BY review_batch
""")
overview = cur.fetchall()
print("\n  --- Overview ---")
for r in overview:
    print(f"  {r['review_batch']} ({r['dataset_role']})")
    print(f"    rows             : {r['total']}")
    print(f"    distinct tickers : {r['distinct_tickers']}")
    print(f"    pub date min     : {r['pub_min']}")
    print(f"    pub date max     : {r['pub_max']}")

# --- Review decision breakdown (BATCH-001 only; 002/003 should be all NULL) ---
cur.execute("""
    SELECT review_batch,
           SUM(CASE WHEN review_decision IS NULL THEN 1 ELSE 0 END) AS unreviewed,
           SUM(CASE WHEN review_decision = 'CONFIRM_SEED' THEN 1 ELSE 0 END) AS confirm_seed,
           SUM(CASE WHEN review_decision = 'OVERRIDE'     THEN 1 ELSE 0 END) AS override,
           SUM(CASE WHEN review_decision = 'ABSTAIN'      THEN 1 ELSE 0 END) AS abstain,
           SUM(CASE WHEN review_decision = 'SKIP'         THEN 1 ELSE 0 END) AS skip
    FROM financial_classifier_gold_review
    GROUP BY review_batch ORDER BY review_batch
""")
decisions = cur.fetchall()
print("\n  --- Review decisions ---")
for r in decisions:
    print(f"  {r['review_batch']}: unreviewed={r['unreviewed']} confirm={r['confirm_seed']} "
          f"override={r['override']} abstain={r['abstain']} skip={r['skip']}")

# Per-batch dimensions
for batch in ["BATCH-001", "BATCH-002", "BATCH-003"]:
    print(f"\n  --- {batch} seed dimension distributions ---")

    for dim, label in [
        ("seed_concept",              "seed_concept"),
        ("seed_alias_role",           "seed_alias_role"),
        ("seed_value_pattern",        "seed_value_pattern"),
        ("seed_valuation_eligibility","seed_valuation_eligibility"),
        ("seed_should_abstain",       "seed_should_abstain"),
    ]:
        cur.execute(f"""
            SELECT COALESCE({dim}::text, '(null)') AS val, COUNT(*) AS cnt
            FROM financial_classifier_gold_review
            WHERE review_batch = %s
            GROUP BY {dim}
            ORDER BY cnt DESC
        """, (batch,))
        rows = cur.fetchall()
        print(f"\n    {label}:")
        for r in rows[:15]:
            print(f"      {r['val']:50s}: {r['cnt']}")

# =========================================================================
# C: Top-15 tickers and concepts per batch
# =========================================================================
print(f"\n{SEP}")
print("C. TOP-15 TICKERS AND CONCEPTS PER BATCH")
print(SEP)

for batch in ["BATCH-001", "BATCH-002", "BATCH-003"]:
    print(f"\n  [{batch}] Top-15 tickers:")
    cur.execute("""
        SELECT ticker, COUNT(*) AS cnt
        FROM financial_classifier_gold_review
        WHERE review_batch = %s
        GROUP BY ticker ORDER BY cnt DESC LIMIT 15
    """, (batch,))
    for r in cur.fetchall():
        print(f"    {r['ticker']:15s}: {r['cnt']}")

    print(f"\n  [{batch}] Top-15 concepts:")
    cur.execute("""
        SELECT COALESCE(seed_concept,'(null)') AS concept, COUNT(*) AS cnt
        FROM financial_classifier_gold_review
        WHERE review_batch = %s
        GROUP BY seed_concept ORDER BY cnt DESC LIMIT 15
    """, (batch,))
    for r in cur.fetchall():
        print(f"    {r['concept']:50s}: {r['cnt']}")

# =========================================================================
# D: Temporal / issuer clustering
# =========================================================================
print(f"\n{SEP}")
print("D. TEMPORAL AND ISSUER CLUSTERING ANALYSIS")
print(SEP)

# Publication date distribution by batch: min, max, median (approx via percentile)
cur.execute("""
    SELECT review_batch,
           MIN(publication_datetime) AS pub_min,
           MAX(publication_datetime) AS pub_max,
           COUNT(DISTINCT DATE_TRUNC('month', publication_datetime)) AS distinct_months,
           COUNT(DISTINCT DATE_TRUNC('year', publication_datetime)) AS distinct_years
    FROM financial_classifier_gold_review
    GROUP BY review_batch ORDER BY review_batch
""")
temporal = cur.fetchall()
print("\n  --- Publication date range by batch ---")
for r in temporal:
    print(f"  {r['review_batch']}: {r['pub_min']} .. {r['pub_max']}  "
          f"({r['distinct_months']} months, {r['distinct_years']} years)")

# Check correlation: does benchmark_id order correlate with pub date?
# Fetch all rows with benchmark_id and pub date to check
cur.execute("""
    SELECT benchmark_id, publication_datetime,
           EXTRACT(EPOCH FROM publication_datetime) AS epoch
    FROM financial_classifier_gold_review
    ORDER BY benchmark_id
""")
all_rows_td = cur.fetchall()

# Spearman-like rank correlation (manual, no scipy)
n = len(all_rows_td)
bench_ranks = list(range(n))
date_sorted = sorted(range(n), key=lambda i: (all_rows_td[i]["epoch"] or 0))
date_ranks = [0] * n
for rank, idx in enumerate(date_sorted):
    date_ranks[idx] = rank

# Pearson on the ranks
mean_b = sum(bench_ranks) / n
mean_d = sum(date_ranks) / n
num = sum((bench_ranks[i] - mean_b) * (date_ranks[i] - mean_d) for i in range(n))
den_b = sum((x - mean_b)**2 for x in bench_ranks) ** 0.5
den_d = sum((x - mean_d)**2 for x in date_ranks) ** 0.5
spearman_approx = num / (den_b * den_d) if den_b * den_d else 0

print(f"\n  Spearman rank correlation (benchmark_id order vs publication_datetime): {spearman_approx:.4f}")
if abs(spearman_approx) > 0.5:
    print(f"  -> Strong temporal correlation: ordering IS substantially correlated with publication date.")
elif abs(spearman_approx) > 0.2:
    print(f"  -> Moderate temporal correlation: some date clustering present.")
else:
    print(f"  -> Weak temporal correlation: ordering is not substantially date-driven.")

# Per-batch year breakdown
print("\n  --- Publication year distribution per batch ---")
cur.execute("""
    SELECT review_batch,
           EXTRACT(YEAR FROM publication_datetime)::int AS yr,
           COUNT(*) AS cnt
    FROM financial_classifier_gold_review
    GROUP BY review_batch, yr
    ORDER BY review_batch, yr
""")
yr_rows = cur.fetchall()
for r in yr_rows:
    print(f"  {r['review_batch']}  {r['yr']}  : {r['cnt']}")

# Ticker overlap
print("\n  --- Ticker overlap across batches ---")
cur.execute("""
    SELECT ticker, STRING_AGG(DISTINCT review_batch, ',' ORDER BY review_batch) AS batches
    FROM financial_classifier_gold_review
    GROUP BY ticker
    ORDER BY ticker
""")
ticker_batches = cur.fetchall()

in_all_3    = [r["ticker"] for r in ticker_batches if r["batches"] == "BATCH-001,BATCH-002,BATCH-003"]
b001_b002   = [r["ticker"] for r in ticker_batches if r["batches"] == "BATCH-001,BATCH-002"]
b001_b003   = [r["ticker"] for r in ticker_batches if r["batches"] == "BATCH-001,BATCH-003"]
b002_b003   = [r["ticker"] for r in ticker_batches if r["batches"] == "BATCH-002,BATCH-003"]
only_b001   = [r["ticker"] for r in ticker_batches if r["batches"] == "BATCH-001"]
only_b002   = [r["ticker"] for r in ticker_batches if r["batches"] == "BATCH-002"]
only_b003   = [r["ticker"] for r in ticker_batches if r["batches"] == "BATCH-003"]

print(f"  Tickers in all 3 batches    ({len(in_all_3)}): {sorted(in_all_3)}")
print(f"  Only in BATCH-001           ({len(only_b001)}): {sorted(only_b001)}")
print(f"  Only in BATCH-002           ({len(only_b002)}): {sorted(only_b002)}")
print(f"  Only in BATCH-003           ({len(only_b003)}): {sorted(only_b003)}")
print(f"  In BATCH-001+002 only       ({len(b001_b002)}): {sorted(b001_b002)}")
print(f"  In BATCH-001+003 only       ({len(b001_b003)}): {sorted(b001_b003)}")
print(f"  In BATCH-002+003 only       ({len(b002_b003)}): {sorted(b002_b003)}")

# =========================================================================
# E: Holdout isolation check — no gold fields in BATCH-002/003
# =========================================================================
print(f"\n{SEP}")
print("E. HOLDOUT ISOLATION CHECK")
print(SEP)

# BATCH-002/003: verify all gold fields null
cur.execute("""
    SELECT review_batch, COUNT(*) AS cnt
    FROM financial_classifier_gold_review
    WHERE review_batch IN ('BATCH-002','BATCH-003')
      AND (
        review_decision IS NOT NULL OR
        reviewer_notes IS NOT NULL OR
        gold_concept IS NOT NULL OR gold_scope IS NOT NULL OR
        gold_dilution IS NOT NULL OR gold_tax_basis IS NOT NULL OR
        gold_capex_basis IS NOT NULL OR gold_lease_inclusion IS NOT NULL OR
        gold_basis_evidence IS NOT NULL OR gold_margin_denominator IS NOT NULL OR
        gold_attribution IS NOT NULL OR gold_alias_role IS NOT NULL OR
        gold_value_pattern IS NOT NULL OR gold_valuation_eligibility IS NOT NULL OR
        gold_should_abstain IS NOT NULL OR
        gold_concept_is_override OR gold_scope_is_override OR
        gold_dilution_is_override OR gold_tax_basis_is_override OR
        gold_capex_basis_is_override OR gold_lease_inclusion_is_override OR
        gold_basis_evidence_is_override OR gold_margin_denominator_is_override OR
        gold_attribution_is_override OR gold_alias_role_is_override OR
        gold_value_pattern_is_override OR gold_valuation_eligibility_is_override OR
        gold_should_abstain_is_override
      )
    GROUP BY review_batch
""")
dirty = cur.fetchall()
if dirty:
    for r in dirty:
        print(f"  [FAIL] {r['review_batch']} has {r['cnt']} rows with non-null gold/review fields!")
else:
    print("  BATCH-002 gold/review fields: all NULL [OK]")
    print("  BATCH-003 gold/review fields: all NULL [OK]")

# financial_classifier_gold_effective view: should only have BATCH-001 rows
cur.execute("SELECT COUNT(*) AS cnt FROM financial_classifier_gold_effective")
eff_count = cur.fetchone()["cnt"]
print(f"\n  financial_classifier_gold_effective row count: {eff_count}")

cur.execute("""
    SELECT review_batch, COUNT(*) AS cnt
    FROM financial_classifier_gold_effective
    GROUP BY review_batch ORDER BY review_batch
""")
eff_batches = cur.fetchall()
print(f"  Effective view batch breakdown: {[(r['review_batch'], r['cnt']) for r in eff_batches]}")
# BATCH-002/003 should NOT appear (they have review_decision IS NULL, so excluded by SKIP filter... wait)
# The view excludes SKIP only. BATCH-002/003 have review_decision IS NULL, which is != 'SKIP'
# So they WILL appear in the effective view. Document this.
b002_in_eff = any(r["review_batch"] == "BATCH-002" for r in eff_batches)
b003_in_eff = any(r["review_batch"] == "BATCH-003" for r in eff_batches)

if b002_in_eff or b003_in_eff:
    print(f"\n  [NOTE] BATCH-002/003 rows appear in financial_classifier_gold_effective.")
    print(f"  This is EXPECTED because the view excludes only review_decision='SKIP'.")
    print(f"  Effective labels for BATCH-002/003 are pure seed labels (no gold override).")
    print(f"  Evaluation workflows must filter on review_batch='BATCH-001' or")
    print(f"  release_id='GOLD-001' to restrict to reviewed gold data.")
    print(f"  [RECOMMENDATION] Add a release-scoped evaluation view that joins on")
    print(f"  financial_classifier_gold_releases to restrict to GOLD-001 rows.")

conn.close()

# =========================================================================
# F: Codebase scan for table/column references
# =========================================================================
print(f"\n{SEP}")
print("F. CODEBASE REFERENCE SCAN")
print(SEP)

REPO_ROOT = Path(__file__).resolve().parents[1]
SEARCH_TERMS = [
    "financial_classifier_gold_review",
    "financial_classifier_gold_effective",
    "review_batch",
    "dataset_role",
]
EXCLUDE_DIRS = {".git", "__pycache__", ".ruff_cache", ".pytest_cache", "scratch", "tmp"}
INCLUDE_EXTS = {".py", ".sql", ".md", ".txt", ".json"}

hits = {}
for term in SEARCH_TERMS:
    hits[term] = []

for path in REPO_ROOT.rglob("*"):
    if path.is_dir():
        continue
    if any(excl in path.parts for excl in EXCLUDE_DIRS):
        continue
    if path.suffix not in INCLUDE_EXTS:
        continue
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        continue
    for term in SEARCH_TERMS:
        if term in text:
            rel = path.relative_to(REPO_ROOT)
            hits[term].append(str(rel))

print("\n  References found:")
for term in SEARCH_TERMS:
    files = sorted(set(hits[term]))
    print(f"\n  '{term}' ({len(files)} files):")
    for f in files:
        print(f"    {f}")

# Flag any Python file (not a test/scratch/migration) that queries the review table
# without a review_batch or dataset_role filter
print("\n  --- Potential unfiltered queries (no review_batch/dataset_role filter) ---")
suspect = []
for path in REPO_ROOT.rglob("*.py"):
    if any(excl in path.parts for excl in EXCLUDE_DIRS):
        continue
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        continue
    if "financial_classifier_gold_review" in text or "financial_classifier_gold_effective" in text:
        has_batch_filter = "review_batch" in text or "dataset_role" in text
        rel = str(path.relative_to(REPO_ROOT))
        suspect.append((rel, has_batch_filter))

print()
for rel, filtered in suspect:
    tag = "[batch-filtered]" if filtered else "[NO BATCH FILTER - review]"
    print(f"  {tag:30s} {rel}")

print(f"\n{SEP}")
print("AUDIT COMPLETE")
print(SEP)
