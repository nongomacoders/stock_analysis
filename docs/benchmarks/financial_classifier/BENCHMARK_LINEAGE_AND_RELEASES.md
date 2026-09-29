# Financial Classifier Benchmark Lineage, Releases, and Evaluation Architecture

This document records the authoritative population lineage, release identity hierarchy, database review infrastructure, freeze protocols, and evaluation standards for the SENS financial phrase classifier benchmark.

Future agents and evaluation pipelines must consult this document before modifying benchmark populations, running evaluations, or generating new releases.

---

## 1. Benchmark Population Lineage (581 → 700 → 820)

The numbers `581`, `700`, and `820` describe three distinct persisted or sampled populations across the benchmark's development. They are **not** steps in an arithmetic duplicate-removal equation:

- **581 - Previous Persisted Benchmark Size:**
  The last committed benchmark artifact before span-based identity. Created when occurrence identity collapsed rows by `(sens_id, full_sentence, normalized_label)`.
- **700 - Intermediate Rebuild Candidate Size:**
  A bounded validation run of the rebuilt sampler with `target_count=700`. Reported during intermediate pipeline validation; was never a final persisted population or a count of rows remaining after deduplication.
- **820 - Final Stratified Benchmark Size:**
  The final deterministic sampler target (`target_count=820`) and the size of the synchronized JSON artifact (`gui/modules/analysis/data/financial_classifier_benchmark_820.json`). BATCH-001 contains the first 300 items.

### Pre-Stratification Corpus Audit vs. Sampler Caps
The corpus audit prior to stratification is distinct from the sampler targets:
- **Span-based identity restored 545 distinct source occurrences** that the previous text-key identity collapsed.
- **Span-based identity removed 570 true duplicate regex emissions** referring to an already-seen `(sens_id, alias_start_offset, alias_end_offset, normalized_label)` span.
- Within the final 820-row sampled artifact, **18 of 820** rows are retained distinct occurrences that share the former text key. Within the 700-item intermediate prefix, the corresponding count is **16 of 700**.

> **Note on Arithmetic:** `581 + 545 - 570` is not expected to equal 700 or 820. The 545/570 figures describe the full candidate scan across all SENS announcements prior to stratification, whereas 700 and 820 are explicit sampler caps after ticker and label balancing.
>
> Lineage reconstruction script: `scratch/audit_span_duplicates.py`
> Artifact regeneration script: `scratch/regenerate_benchmark_artifacts.py`

---

## 2. Review Batches and Dataset Partition Roles

The 820 benchmark rows are partitioned into three contiguous, deterministic slices by `benchmark_id`:

| Batch | Range | Size | Dataset Role | Gold Status | Description |
|---|---|---|---|---|---|
| **BATCH-001** | `BENCH-0001` .. `BENCH-0300` | 300 rows | `DEVELOPMENT` | Frozen (`GOLD-001`) | Used for prompt engineering, threshold tuning, and format refinement. |
| **BATCH-002** | `BENCH-0301` .. `BENCH-0560` | 260 rows | `VALIDATION` | Not yet gold | Sliced validation set. Evaluated after tuning, prior to locking production models. |
| **BATCH-003** | `BENCH-0561` .. `BENCH-0820` | 260 rows | `HOLDOUT` | Not yet gold | Strict holdout set. Never exposed to model or prompt tuning; evaluated only once locked. |

### Database Partitioning Schema
Columns added to `financial_classifier_gold_review`:
```sql
review_batch  text  CHECK IN ('BATCH-001', 'BATCH-002', 'BATCH-003')
dataset_role  text  CHECK IN ('DEVELOPMENT', 'VALIDATION', 'HOLDOUT')
```

### Reviewer Views and Progress Queries
Dedicated database views isolate batches and monitor human review progress:
- `financial_classifier_review_batch_002`: Reviewer interface restricted to `BATCH-002`.
- `financial_classifier_review_batch_003`: Reviewer interface restricted to `BATCH-003`.
- `financial_classifier_batch_progress`: Overall progress counts and completion percentages per batch.
- `financial_classifier_batch_progress_by_ticker`: Review progress broken down by ticker.
- `financial_classifier_batch_progress_by_concept`: Review progress broken down by concept label.
- `financial_classifier_batch_progress_by_alias_role`: Review progress broken down by alias role.
- `financial_classifier_batch_progress_by_valuation_eligibility`: Review progress broken down by valuation eligibility.

Batch preparation runner: `scratch/prepare_review_batches_002_003.py`
Batch unit and DB tests: `gui/modules/analysis/tests/test_gold_review_batches.py`

---

## 3. Database Review Schema & Override Infrastructure

Human reviews are tracked in PostgreSQL table `financial_classifier_gold_review`.

### Table Schema and Migration History
- Initial migration: `gui/core/db/migrations/add_financial_classifier_gold_review.sql`
- Override-presence flags migration (v1.0.0 → v1.1.0): `gui/core/db/migrations/add_gold_override_flags_and_evaluation.sql`
- Migration runner: `scratch/run_gold_override_migration_and_baseline.py`
- Review batch migration: `scratch/run_gold_review_migration.py`

### Review Import Infrastructure
- Import script: `gui/scripts/import_gold_review.py`
  ```powershell
  $env:PYTHONPATH = "C:\Users\Dion\Desktop\Projects\stock_analysis\gui"
  & "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" gui/scripts/import_gold_review.py --csv gui/modules/analysis/data/financial_classifier_gold_review_001.csv
  ```
  Note: Add `--force-overwrite-reviewed` only when explicitly intending to replace existing non-blank DB review fields with blank CSV values.

### Key Database Design Decisions
- `detected_numeric_tokens` is stored as `text` (not JSONB) because CSV values are Python-style list literals.
- `publication_datetime` is stored as `timestamp` (no timezone) to represent the source publication time faithfully.
- `seed_should_abstain` is `boolean NOT NULL`; `gold_should_abstain` is `boolean` (nullable).
- All `gold_*` and `review_decision` fields are nullable.
- `review_decision` is constrained to `CONFIRM_SEED | OVERRIDE | ABSTAIN | SKIP`.
- Upsert guard: a blank CSV value never overwrites a non-blank DB review field unless `--force-overwrite-reviewed` is passed.

### Review Workflow Queries
- **Next Unreviewed Items:**
  ```sql
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
  LIMIT 5;
  ```

### Unit & Integration Tests
```powershell
# Pure-logic tests (no DB):
$env:PYTHONPATH = "C:\Users\Dion\Desktop\Projects\stock_analysis\gui"
& "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" -m pytest gui/modules/analysis/tests/test_gold_review_import.py -v -k "not DbImport"

# All tests including DB integration:
$env:RUN_GOLD_REVIEW_DB_TESTS = "1"
& "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" -m pytest gui/modules/analysis/tests/test_gold_review_import.py -v
```

### Sparse Override-Presence Columns
To cleanly distinguish an intentional override (even to `NULL` or unknown) from a confirmation of the seed label, 13 boolean flags (`NOT NULL DEFAULT FALSE`) track human overrides per dimension:
```text
gold_concept_is_override
gold_scope_is_override
gold_dilution_is_override
gold_tax_basis_is_override
gold_capex_basis_is_override
gold_lease_inclusion_is_override
gold_basis_evidence_is_override
gold_margin_denominator_is_override
gold_attribution_is_override
gold_alias_role_is_override
gold_value_pattern_is_override
gold_valuation_eligibility_is_override
gold_should_abstain_is_override
```

### Effective Label Resolution Rule
**CRITICAL:** Never use `COALESCE(gold_field, seed_field)`. A flag = `TRUE` with `gold_field = NULL` represents an intentional human override to unknown/null.

Always resolve effective labels via:
```sql
CASE WHEN <gold_field>_is_override THEN <gold_field> ELSE <seed_field> END
```

### Table Integrity Constraints
- `chk_confirm_seed_no_overrides`: When `review_decision = 'CONFIRM_SEED'`, all override flags must be `FALSE`.
- `chk_skip_no_overrides`: When `review_decision = 'SKIP'`, all override flags must be `FALSE`.
- `chk_override_has_at_least_one_flag`: When `review_decision = 'OVERRIDE'`, at least one override flag must be `TRUE`.
- `chk_abstain_should_abstain_flag`: When `review_decision = 'ABSTAIN'`, `gold_should_abstain_is_override` must be `TRUE`.
- `chk_gold_null_when_no_flag`: If an override flag is `FALSE`, the corresponding `gold_*` column must be `NULL`.

### Effective Views
- `financial_classifier_gold_effective`: Excludes rows where `review_decision = 'SKIP'`. Evaluates effective columns across all batches.
- `financial_classifier_gold_001_effective`: Strictly filters `WHERE review_batch = 'BATCH-001' AND review_decision <> 'SKIP'` (exactly 281 rows). Invariant under future BATCH-002/003 changes.

---

## 4. Release Identity Hierarchy & Frozen Hashes

Every gold release maintains deterministic SHA-256 hashes establishing an immutable identity hierarchy:

### 1. `source_hash` (Benchmark Input Corpus)
- Identifies the raw input text and context presented to models.
- Ordered deterministically by `benchmark_id`.
- Columns hashed (8): `benchmark_id`, `ticker`, `publication_datetime`, `previous_sentence`, `full_sentence`, `next_sentence`, `detected_numeric_tokens` (canonicalized JSON), `normalized_label`.
- Excludes timestamps and annotation fields.
- **GOLD-001 Source Hash:**
  `4b8594e5b34d7d05273fecda2dd4b817b9dc2e055d77cf0bc6de31cf79ff7610`

### 2. `label_hash` (Effective Annotations & Inclusion)
- Identifies human gold decisions and inclusion status.
- Ordered deterministically by `benchmark_id`.
- **Included rows** (`review_decision <> 'SKIP'`): hashes `benchmark_id`, `is_included=TRUE`, and all 13 effective dimension values.
- **SKIP rows** (`review_decision = 'SKIP'`): hashes ONLY `benchmark_id` and `is_included=FALSE`. Unused effective fields on SKIP rows do not alter `label_hash`.
- **GOLD-001 Label Hash:**
  `f9139858b89ea102d30c22e1007b1e807c5aecc684048ffb31df1dcb73e9ef75`

### 3. `release_hash` (Authoritative Release Identity)
- Composite identifier binding input text, effective labels, and release metadata into a single authoritative release hash.
- Manifest template:
  `release_id={release_id}|schema_version={schema_version}|source_hash={source_hash}|label_hash={label_hash}\n`
- For GOLD-001:
  - `release_id`: `GOLD-001`
  - `schema_version`: `1.1.0`
  - `source_hash`: `4b8594e5b34d7d05273fecda2dd4b817b9dc2e055d77cf0bc6de31cf79ff7610`
  - `label_hash`: `f9139858b89ea102d30c22e1007b1e807c5aecc684048ffb31df1dcb73e9ef75`
- **GOLD-001 Authoritative Release Hash:**
  `f0b3138d32a033b66cd0823cfd83ae89461433209a0552bece6722d2ca98f179`

### 4. `audit_hash` (Complete Provenance State)
- Hashes the complete database state across all 300 reviewed rows, including reviewer notes.
- Columns hashed (43): `benchmark_id`, `ticker`, `normalized_label`, `review_decision`, 12 `seed_*` fields, 13 `gold_*` fields, 13 `gold_*_is_override` flags, `reviewer_notes`.
- **GOLD-001 Audit Hash:**
  `7f95fc104c59dfcdc42a7ced35ea102884c95b9829f15d1c1960895dcd7b1d43`
- Pre-release candidate audit snapshot: `3c5e1ce829eac535a4c7263b3caed47266f67ed7fd16b8f61586164992efbc24`

### 5. Backward Compatibility Hashes
- `dataset_hash`: `7f95fc104c59dfcdc42a7ced35ea102884c95b9829f15d1c1960895dcd7b1d43` (points to `audit_hash`).
- `semantic_hash`: `d759e827f4c9469db407edfc08d7ab73fd21ff3767bb3e44d8255d896f467976` (legacy evaluation hash prior to SKIP-row dimension exclusion).

---

## 5. GOLD-001 Release Characteristics & Baseline Metrics

### Release Profile
- **Release ID:** `GOLD-001`
- **Schema Version:** `1.1.0`
- **Review Rows (BATCH-001):** 300
- **Evaluated Rows (excl. SKIP):** 281
- **Decisions:**
  - `CONFIRM_SEED`: 102
  - `OVERRIDE`: 106
  - `ABSTAIN`: 73
  - `SKIP`: 19

### Baseline Seed Evaluation (`BASELINE-SEED-GOLD-001`)
Evaluated across the 281 non-skipped rows:
- **Coverage:** 34.16% (96 seed attempts / 281 total)
- **Full-Label Exact Match:** 40.93%
- **Dimension Accuracies:**
  - Concept: 77.94%
  - Scope: 91.46%
  - Dilution: 91.46%
  - Tax Basis: 95.73%
  - Capex Basis: 100.00%
  - Lease Inclusion: 100.00%
  - Margin Denominator: 99.29%
  - Attribution: 98.22%
  - Alias Role: 87.19%
  - Value Pattern: 86.48%
  - Valuation Eligibility: 82.92%
- **Abstention Metrics:**
  - TP: 181, FP: 4, FN: 60, TN: 36
  - Precision: 97.84%, Recall: 75.10%, F1: 84.98%
- **Unsafe False Acceptance Rate:**
  - Definition: `seed_should_abstain = FALSE` AND (`effective_should_abstain = TRUE` OR any dimension mismatches gold).
  - Count: 65 / 96
  - Rate: 67.71%

---

## 6. Freeze Rules and Append-Only Evaluation Semantics

To ensure rigorous auditability and prevent benchmark contamination:

1. **Release Records are Insert-Only:**
   Rows in `financial_classifier_gold_releases` are immutable. Never execute an `UPDATE` on existing releases.
2. **Evaluation Runs are Append-Only:**
   Evaluation results in `financial_classifier_evaluation_runs` and `financial_classifier_evaluation_predictions` must never be overwritten. Every new evaluation generates an append-only run record.
3. **No Retroactive Mutation of Gold Data:**
   Corrections to underlying annotations require a new release version (e.g., `GOLD-002`). The `GOLD-001` release row and hashes must remain reproducible indefinitely.
4. **Independent Skip Rows and Reviewer Notes:**
   - Edits to `reviewer_notes` alter `audit_hash` but do not affect `source_hash`, `label_hash`, or `release_hash`.
   - Edits to unused annotation fields on a `SKIP` row do not alter `label_hash` or `release_hash`.
5. **Population Isolation:**
   Evaluator queries must always enforce:
   ```sql
   WHERE review_batch = 'BATCH-001' AND review_decision <> 'SKIP'
   ```
   Never query `review_decision <> 'SKIP'` alone, as ongoing reviews in `BATCH-002` or `BATCH-003` will alter the row count.

---

## 7. Model Provenance & Evaluation Standardization

### 1. Kev-0.8B Provenance
When benchmarking or running `jaredpalmer/kev-0.8b`, the verified model artifacts are:
- **Base Model:** `Qwen/Qwen3.5-0.8B-Base` (HuggingFace revision: `dc7cdfe2ee4154fa7e30f5b51ca41bfa40174e68`)
- **LoRA Model Run:** `jaredpalmer/kev-0.8b` (HuggingFace revision: `9a45d25eb2ab761841196625383fa1dff0e56c1e`)
- **LoRA Rank:** `16`
- **Sampling Temperature:** `2.3510958125672174`
- **Kev Git Commit:** `f1535963cea021439370c23127bc970b6788e730` (package `0.1.0`)

> **Warning:** Never confuse `Qwen3.5-0.8B-Base` with `Qwen3.5-4B-Base` (`1001bb4d826a52d1f399e183466143f4da7b741b`). Kev-0.8B is an 800M parameter model.

### 2. Canonical Basis Evidence Normalization
In evaluation pipelines:
- `NULL` or empty string in `effective_basis_evidence` must strictly canonicalize to `'unspecified'`.
- Gold database rows are never mutated to add this value; the normalization is performed in Python via `modules.analysis.kev_gold_evaluator.normalize_basis_evidence`.

### 3. Metric Standardization: Unsafe False Acceptance
To avoid ambiguity between admission rates and overall population rates:
- `accepted_count = tn + fn` (all candidate rows admitted by the classifier policy)
- `safe_accept_count = tn` (rows admitted that match gold on all dimensions)
- `unsafe_accept_count = fn` (rows admitted that mismatch gold or should have been abstained)
- `unsafe_accept_rate_of_accepted = unsafe_accept_count / accepted_count` (intake danger)
- `unsafe_accept_rate_of_population = unsafe_accept_count / evaluation_population` (corpus danger)
