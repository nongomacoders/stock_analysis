# Stock Analysis Agent Runbook

This file records recurring development issues and their known fixes.

Future agents should consult this file before repeating environment discovery or troubleshooting already solved problems.

---

# 1. Python executable not found / wrong Python selected

## Symptom

Commands such as:

```powershell
python --version
python -m pytest
```

resolve to the wrong interpreter, fail, or trigger unnecessary Python discovery.

## Known working interpreter

```text
C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe
```

## Preferred command

```powershell
& "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" ...
```

Do not search for:
- Python 3.13
- a venv
- another Python installation

unless the known interpreter actually fails.

Note: Since this executable is located in `AppData\Local` (outside the workspace root), running terminal commands using this path requires `BypassSandbox: true` in agent tooling.


---

# 2. Python imports fail from repository root

## Symptom

Errors such as:

```text
ModuleNotFoundError
cannot import core
cannot import modules
```

## Known fix

Set:

```powershell
$env:PYTHONPATH = "C:\Users\Dion\Desktop\Projects\stock_analysis\gui"
```

Then run:

```powershell
& "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" ...
```

---

# 3. Running pytest

Preferred pattern:

```powershell
$env:PYTHONPATH = "C:\Users\Dion\Desktop\Projects\stock_analysis\gui"

& "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" -m pytest <test paths> -v
```

Do not switch interpreters between test runs unless necessary.

---

# 4. Database access

Application DB configuration is located at:

```text
gui\core\config.py
```

Use:

```python
from core.config import DB_CONFIG
```

Typical PostgreSQL connection:

```python
import psycopg2
from core.config import DB_CONFIG

conn = psycopg2.connect(**DB_CONFIG)
```

Do not invent credentials or create duplicate config files.

---

# 5. Historical package location

Historical evidence is stored at:

```text
gui\results_history\<TICKER>\<PERIOD>\
```

Typical files:

```text
manifest.json
<TICKER>_<PERIOD>_AFS.pdf
<TICKER>_<PERIOD>_SENS.txt
```

Always validate:
- ticker
- reporting period
- period end
- source type
- publication date
- active revision

before using evidence.

---

# 6. PDF metric appears unavailable

## Symptom

The generic AFS parser reports:

```text
NOT_AVAILABLE
```

but the source AFS may contain the figure.

## Procedure

Before declaring the metric unavailable:

1. open the archived AFS PDF
2. extract text with PyPDF2
3. search the primary statements
4. search the likely note
5. inspect surrounding context
6. preserve exact page/note provenance
7. reconcile duplicate or differently defined values

Use scratch scripts when necessary, but do not hard-code company values into production code.

---

# 7. Retailer semantic traps

Always distinguish:

## Revenue concepts

```text
accounting revenue
sale of merchandise
retail sales
```

They may all differ.

## Profit concepts

```text
trading profit
operating profit
PBIT
EBIT
```

Do not substitute automatically.

## Margin concepts

Always store:
- numerator
- denominator
- semantic label

Example:

```text
trading margin = trading profit / sale of merchandise
```

Do not apply a published operating margin to accounting revenue unless that is explicitly the published definition.

---

# 8. D&A semantics

Income-statement D&A may not equal the full cash-flow D&A addback.

TRU FY2025 example:

```text
income-statement D&A expense = R1.500bn
cash-flow D&A addback = R1.526bn
```

Reason:
distribution depreciation was included in cost of sales rather than trading expenses.

Preserve separate typed concepts:

```text
depreciation_amortisation_expense
depreciation_amortisation_cashflow_addback
```

FCFF mapping must choose explicitly.

---

# 9. Capex semantics

Do not confuse:

```text
cash capex
accounting additions
```

TRU historical valuation uses a cash-capex convention.

Example FY2025:

```text
expansion cash capex    R428m
maintenance cash capex  R187m
software cash capex      R59m
total cash capex         R674m
```

For forecast-vs-actual comparisons, use the same semantic basis on both sides.

---

# 10. Working-capital signs

Never store an ambiguous working-capital number without sign semantics.

Preferred concept:

```text
working_capital_cash_flow
```

Convention:

```text
positive = cash inflow
negative = cash outflow
```

If the FCFF engine uses:

```text
FCFF = ... - change_in_working_capital
```

convert deliberately before calculation.

Do not double-negate.

---

# 11. Net cash reconciliation

Reported net cash may not equal:

```text
cash - debt
```

Check:
- cash
- restricted/charitable cash
- money-market funds
- borrowings
- overdraft
- other treasury adjustments

TRU FY2025 example:

```text
Cash                     +R964m
Charitable trust cash     -R14m
Money-market funds      +R2.224bn
Borrowings              -R1.479bn
Overdraft                 -R975m
                         -------
Reported net cash         +R720m
```

Lease liabilities remain a separate equity-bridge adjustment.

---

# 12. Share-count semantics

Keep separate:

```text
issued shares
treasury shares
external shares ex treasury
weighted average basic shares
weighted average diluted shares
```

Also distinguish:
- reporting-period end count
- announcement-date count
- valuation-date count

Use the most appropriate point-in-time count available as of the valuation date.

Do not use weighted-average EPS shares automatically for DCF valuation.

---

# 13. Historical valuation immutability

Once a historical valuation is locked:

Do not modify:
- approved historical plan
- historical result
- valuation output
- input hash

Corrections after reveal belong in append-only outcome revisions.

---

# 14. Outcome corrections

If a reveal analysis is incomplete or wrong:

Do not overwrite prior outcome rows.

Create:

```text
Revision N+1
```

with:

```text
supersedes_outcome_id
```

The newest valid completed revision becomes authoritative.

The original locked valuation remains unchanged.

---

# 15. TRU reference retailer backtest

Canonical reference:

```text
Ticker:
TRU.JO

Historical period:
FY2025

Historical as-of date:
2025-08-31

Outcome period:
FY2026

Historical Result ID:
6768e249-36c9-4f4d-afff-e3bd832e5f6a

Locked fair value:
R72.8232/share

Locked EV:
R30,356,971,061.15

Locked Equity Value:
R27,334,971,061.15

Locked Input Hash:
ccf6a05b91b47ec458186ad1e73f9a78496d64f34c96f2e99dfbba7c8872f959

Authoritative reveal:
Revision 3
```

This reference exists for regression verification.

Do not create TRU-specific branches in production valuation code.

---

# 16. Historical backtest lifecycle

Keep these concepts separate.

## Backtest lifecycle

```text
draft -> locked -> completed
```

## Historical plan

Typical final state:

```text
approved
```

## Historical result

Insert-only and immutable after creation.

## Outcomes

Append-only revision chain.

Do not describe a backtest as:

```text
completed / locked
```

when these refer to different lifecycle concepts.

---

# 17. Before adding new infrastructure

Before creating:
- a parser
- migration
- valuation helper
- lifecycle helper
- historical package handler
- test utility

search the repository first.

Prefer:
- extending existing generic code
- typed semantics
- configuration/adapters

over:
- duplicate workflows
- one-off scripts promoted into production
- ticker-specific branches

---

# 18. Gemini vs Python responsibilities

Gemini may assist with:
- interpretation
- semantic suggestions
- assumption proposals
- research

Python should own:
- extraction where deterministic
- normalization
- arithmetic
- valuation
- validation
- persistence
- reproducibility
- regression tests

Never let an AI-generated target overwrite a deterministic valuation result.

---

# 19. When a known fix fails or new error occurs

Only rediscover environment details after confirming the documented fix genuinely no longer works.

### Midstream recording rule (mandatory)
Whenever any command, script, parser, or shell operation fails due to quoting, variable expansion, platform difference, or unexpected syntax:
1. Identify the root cause and verified working alternative.
2. **Log the error and fix in this runbook immediately midstream as a new section.**
3. Never defer documentation until after task completion or wait for the user to ask for it.
4. If a documented fix changes, update the existing section so future conversations inherit the correction.

---

# 20. PowerShell quoting and "SyntaxError: unterminated string literal"

## Symptom

Executing inline Python commands via PowerShell like:

```powershell
& "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" -c "..."
```

fails with:

```text
SyntaxError: unterminated string literal (detected at line 1)
```

or PowerShell parser errors such as:

```text
The string is missing the terminator: '
```

## Root cause

PowerShell parses arguments before passing them to the executable. When double quotes (`"`) are used both around the `-c` argument and inside Python code, PowerShell strips or mishandles the inner quotes. Windows paths with unescaped backslashes (`\`) or multi-line strings further corrupt quoting.

## Failing patterns (avoid)

```powershell
# FAILS: Python f-strings with inner quotes inside PowerShell double quotes
& "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" -c "print(f\"{c['key']}\")"
```

## Correct inline patterns

1. **Outer single quotes, inner double quotes**:
   ```powershell
   & "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" -c 'import os; print("hello")'
   ```

2. **Escaped internal double quotes (`\"` or ``` `"` )**:
   ```powershell
   & "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" -c "import os; print(\"hello\")"
   ```

3. **Raw string or forward slashes for Windows paths**:
   ```powershell
   & "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" -c 'from pathlib import Path; print(Path(r"C:\Users\Dion"))'
   ```

## Preferred robust alternative: Scratch scripts

For any script longer than a single simple expression, **do not pass multi-line or complex strings via `-c`**.

Instead, write a temporary scratch script and execute it directly:

```powershell
# Save to a temporary file (e.g. scratch/temp_task.py), then run:
$env:PYTHONPATH = "C:\Users\Dion\Desktop\Projects\stock_analysis\gui"
& "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" path\to\scratch\temp_task.py
```

This bypasses shell quoting and tokenizer mismatches entirely.

---

# 21. PowerShell `$_` Variable Expansion in `-Command "..."`

## Symptom

Running nested PowerShell commands like:

```powershell
powershell -Command "Get-ChildItem -File -Recurse | Where-Object { $_.Name -like '*test*' }"
```

fails with repeated errors:

```text
.Name : The term '.Name' is not recognized as the name of a cmdlet, function, script file, or operable program.
At line:1 char:67
+ ... ChildItem -File -Recurse | Where-Object { .Name -like '*test*' }
+                                               ~~~~~
    + CategoryInfo          : ObjectNotFound: (.Name:String) [], CommandNotFoundException
    + FullyQualifiedErrorId : CommandNotFoundException
```

## Root cause

When executing a PowerShell command string wrapped in double quotes (`"..."`), the calling shell expands variables *before* executing the string. Because `$_` is not defined in the parent scope, it expands to an empty string. The pipeline block `{ $_.Name ... }` becomes `{ .Name ... }`, which PowerShell attempts to execute as a cmdlet named `.Name`.

## Failing pattern (avoid)

```powershell
# FAILS: Outer double quotes evaluate $_ to empty string
powershell -Command "Get-ChildItem | Where-Object { $_.Name -like '*doc*' }"
```

## Correct patterns

1. **Escape the `$` with a backtick (`` `$ ``)**:
   ```powershell
   powershell -Command "Get-ChildItem | Where-Object { `$_.Name -like '*doc*' }"
   ```

2. **Wrap `-Command` in single quotes**:
   ```powershell
   powershell -Command 'Get-ChildItem | Where-Object { $_.Name -like "*doc*" }'
   ```

3. **Run directly without nested `powershell -Command` wrapper**:
   When already in PowerShell, avoid wrapping commands in `powershell -Command "..."`:
   ```powershell
   Get-ChildItem -File -Recurse | Where-Object { $_.Name -like '*doc*' }
   ```

---

# 22. Nested Quoting / Triple-Quotes in `powershell -Command "..."` with `python -c`

## Symptom

Executing an inline Python command wrapped in PowerShell, such as:

```powershell
powershell -Command "$env:PYTHONPATH='...'; & '...' -c 'cur.execute(\"\"\"SELECT ...\"\"\")'"
```

fails with:

```text
The string is missing the terminator: '.
ParentContainsErrorRecordException
CommandNotFoundException
```

## Root cause

PowerShell parses `\"\"\"` inside `-Command "..."` by stripping the backslashes before Python is invoked, which truncates the string and leaves unclosed quotes, or misinterprets inner single quotes.

## Failing pattern (avoid)

```powershell
powershell -Command "$env:PYTHONPATH='C:\...'; & 'C:\...\python.exe' -c '... cur.execute(\"\"\"SELECT ...\"\"\") ...'"
```

## Working fix

1. **Avoid nested `powershell -Command`**: The terminal shell is already PowerShell. Run directly:
   ```powershell
   $env:PYTHONPATH = "C:\Users\Dion\Desktop\Projects\stock_analysis\gui"
   & "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" -c "..."
   ```

2. **Or use a dedicated scratch script**:
   Write the script to a `.py` file (e.g. in the artifact scratch directory or workspace scratch directory) and execute it with:
   ```powershell
   & "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" scratch_script.py
   ```

---

# 23. PowerShell Variable Expansion Inside Double-Quoted `-Command "..."`

## Symptom

Executing:

```powershell
powershell -Command "$env:PYTHONPATH='C:\Users\Dion\Desktop\Projects\stock_analysis\gui'; & 'C:\...\python.exe' -m pytest ..."
```

fails with:

```text
=C:\Users\Dion\Desktop\Projects\stock_analysis\gui : The term '=C:\Users\Dion\Desktop\Projects\stock_analysis\gui' is 
not recognized as the name of a cmdlet, function, script file, or operable program.
ModuleNotFoundError: No module named 'modules'
```

## Root cause

When PowerShell runs `-Command "$env:PYTHONPATH=..."`, the outer PowerShell evaluates `$env:PYTHONPATH` *before* launching the subshell. Because `$env:PYTHONPATH` was empty in the parent environment, it expands to `""`, leaving `'=C:\...'` as the command string, which is an invalid cmdlet.

## Failing pattern (avoid)

```powershell
powershell -Command "$env:PYTHONPATH='...'; & '...' -m pytest ..."
```

## Working fix

Since the shell tool already runs in PowerShell, execute assignments and invocations directly without a nested `powershell` process:

```powershell
$env:PYTHONPATH = "C:\Users\Dion\Desktop\Projects\stock_analysis\gui"; & "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" -m pytest ...
```

---

# 24. PowerShell Pipeline Parser Error with Inline `python -c` Containing Pipe `|` Characters

## Symptom

Executing inline python statements in PowerShell such as:

```powershell
& "C:\...\python.exe" -c "print(f\"| {r['benchmark_id']} | {r['ticker']} |\")"
```

fails with:

```text
An empty pipe element is not allowed.
Unexpected token '}' in expression or statement.
    + CategoryInfo          : ParserError: (:) [], ParentContainsErrorRecordException
    + FullyQualifiedErrorId : UnexpectedToken
```

## Root cause

PowerShell parses unquoted or weakly quoted pipe characters `|` as shell pipeline operators instead of passing them as string literals to Python's `-c` argument.

## Failing pattern (avoid)

```powershell
& "C:\...\python.exe" -c "print(f\"| {var} |\")"
```

## Working fix

Do not pass markdown table formatting or complex multi-line strings via inline `-c`. Always write the code to a `.py` script file in `scratch/` and execute via:

```powershell
$env:PYTHONPATH = "C:\Users\Dion\Desktop\Projects\stock_analysis\gui"; & "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" scratch/script.py
```

---

# 25. Windows PowerShell `Select-String` Does Not Support `-First`

## Symptom

Using `Select-String ... -First 1` fails with:

```text
A parameter cannot be found that matches parameter name 'First'.
```

## Root cause

The installed Windows PowerShell `Select-String` cmdlet does not expose a `-First` parameter.

## Working fix

Pipe matches through `Select-Object`:

```powershell
Select-String -Pattern needle | Select-Object -First 1
```

---

# 26. PowerShell Cannot Pipe Directly from a Statement-Form `foreach`

## Symptom

Appending `| ConvertTo-Json` directly after `foreach (...) { ... }` can fail with:

```text
An empty pipe element is not allowed.
```

## Root cause

Windows PowerShell parses statement-form `foreach` differently from a pipeline expression.

## Working fix

Assign the loop output, then pipe the variable:

```powershell
$results = foreach ($item in $items) { [pscustomobject]@{ value = $item } }
$results | ConvertTo-Json
```

---

# 27. Financial Classifier Benchmark Population Lineage (581 -> 700 -> 820)

These values describe three different persisted or sampled populations. They
are not a before/after duplicate-removal equation.

- **581 - previous persisted benchmark size.** This was the last committed
  benchmark artifact, created while occurrence identity still collapsed rows
  by `(sens_id, full_sentence, normalized_label)`.
- **700 - intermediate rebuild candidate size.** This was a bounded validation
  run of the rebuilt sampler with `target_count=700`. It was reported during
  validation but was not the final persisted population and is not a count of
  rows remaining after duplicate removal.
- **820 - final stratified benchmark size.** This is the final deterministic
  sampler target (`target_count=820`) and the size of the synchronized JSON
  artifact. Batch 001 contains the first 300 items.

The pre-stratification corpus audit is separate from those sampler caps:

- Span-based identity restored **545 distinct source occurrences** that the
  former text-key identity would have collapsed.
- Span-based identity removed **570 true duplicate regex emissions** referring
  to an already-seen `(sens_id, alias_start_offset, alias_end_offset,
  normalized_label)` span.
- Within the final sampled artifact, **18 of 820** rows are retained distinct
  occurrences that share the former text key; within the 700-item intermediate
  prefix, the corresponding count is **16 of 700**.

Therefore `581 + 545 - 570` is not expected to equal either 700 or 820: the
545/570 figures describe the full candidate scan before stratification, while
700/820 are explicit sampler caps after ticker/label balancing. Reconstruct the
lineage with `scratch/audit_span_duplicates.py` and regenerate the final
artifacts with `scratch/regenerate_benchmark_artifacts.py`.

---

# 28. PowerShell `Set-Content -Encoding UTF8` Adds a BOM to Text Files

## Symptom

Writing SQL (or any text) with PowerShell:

```powershell
Set-Content -Path file.sql -Encoding UTF8 -Value $content
```

then executing the file via `psycopg2` or `asyncpg` fails with:

```text
psycopg2.errors.SyntaxError: syntax error at or near "\ufeff"
asyncpg.exceptions.PostgresSyntaxError: syntax error at or near "\ufeff"
```

## Root cause

On Windows, PowerShell 5.x `Set-Content -Encoding UTF8` emits a UTF-8 BOM
(`\xEF\xBB\xBF` / `\ufeff`) at the start of the file. PostgreSQL does not
accept SQL files that begin with a BOM.

## Working fix

Use `[System.IO.File]::WriteAllText` with an explicit BOM-free encoder:

```powershell
$enc = New-Object System.Text.UTF8Encoding $false   # $false = no BOM
[System.IO.File]::WriteAllText("path\to\file.sql", $content, $enc)
```

Alternatively, read the file in Python with `encoding="utf-8-sig"` to strip
the BOM before passing to psycopg2:

```python
sql = Path("file.sql").read_text(encoding="utf-8-sig")
```

## Applied locations

- `scratch/run_gold_review_migration.py` uses `read_text(encoding="utf-8-sig")`.
- `gui/core/db/migrations/add_financial_classifier_gold_review.sql` was
  rewritten with `[System.IO.File]::WriteAllText(..., $enc)` to be BOM-free.

---

# 29. Financial Classifier Gold-Review Import Infrastructure

## Summary

The gold-review benchmark table and import pipeline are documented here for
future agents that need to maintain or extend the review workflow.

## Migration

```text
gui/core/db/migrations/add_financial_classifier_gold_review.sql
```

Apply with:

```powershell
$env:PYTHONPATH = "C:\Users\Dion\Desktop\Projects\stock_analysis\gui"
& "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" scratch/run_gold_review_migration.py
```

The migration is safe to re-run (`CREATE TABLE IF NOT EXISTS`,
`CREATE INDEX IF NOT EXISTS`).

## Import command

```powershell
$env:PYTHONPATH = "C:\Users\Dion\Desktop\Projects\stock_analysis\gui"
& "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" gui/scripts/import_gold_review.py --csv gui/modules/analysis/data/financial_classifier_gold_review_001.csv
```

Add `--force-overwrite-reviewed` only when you explicitly want to replace
existing non-blank review fields with blank CSV values.

## Table name

`financial_classifier_gold_review`

## Key design decisions

- `detected_numeric_tokens` is stored as `text` (not JSONB) because the CSV
  value is a Python-style list literal, not always strict JSON.
- `publication_datetime` is `timestamp` (no timezone) to faithfully represent
  the source value which carries no timezone information.
- `seed_should_abstain` is `boolean NOT NULL`; `gold_should_abstain` is
  `boolean` (nullable).
- All `gold_*` and `review_decision` fields are nullable.
- `review_decision` is constrained to `CONFIRM_SEED | OVERRIDE | ABSTAIN | SKIP`.
- The upsert guard: a blank CSV value never overwrites a non-blank DB
  review field unless `--force-overwrite-reviewed` is passed.

## Next-five-unreviewed query

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

## Applying a review batch (parameterised pattern)

```sql
BEGIN;

-- Verify all requested IDs exist and are not yet reviewed
DO $$
DECLARE
    missing_count integer;
    already_reviewed_count integer;
BEGIN
    SELECT COUNT(*) INTO missing_count
    FROM (VALUES ('BENCH-0001'),('BENCH-0002')) AS v(bid)
    WHERE NOT EXISTS (
        SELECT 1 FROM financial_classifier_gold_review WHERE benchmark_id = v.bid
    );
    IF missing_count > 0 THEN
        RAISE EXCEPTION 'Some benchmark_ids not found: %', missing_count;
    END IF;

    SELECT COUNT(*) INTO already_reviewed_count
    FROM financial_classifier_gold_review
    WHERE benchmark_id IN ('BENCH-0001','BENCH-0002')
      AND review_decision IS NOT NULL;
    IF already_reviewed_count > 0 THEN
        RAISE EXCEPTION 'Some rows already have a review_decision: %', already_reviewed_count;
    END IF;
END $$;

-- Apply the review
UPDATE financial_classifier_gold_review
SET review_decision = 'CONFIRM_SEED',
    reviewer_notes  = 'Seed label is correct',
    last_updated_at = NOW()
WHERE benchmark_id = 'BENCH-0001';

UPDATE financial_classifier_gold_review
SET review_decision = 'OVERRIDE',
    gold_concept    = 'operating_profit',
    reviewer_notes  = 'Seed concept wrong; correct is operating_profit',
    last_updated_at = NOW()
WHERE benchmark_id = 'BENCH-0002';

COMMIT;
```

## Tests

```powershell
# Pure-logic tests (no DB):
$env:PYTHONPATH = "C:\Users\Dion\Desktop\Projects\stock_analysis\gui"
& "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" -m pytest gui/modules/analysis/tests/test_gold_review_import.py -v -k "not DbImport"

# All tests including DB integration:
$env:RUN_GOLD_REVIEW_DB_TESTS = "1"
& "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" -m pytest gui/modules/analysis/tests/test_gold_review_import.py -v
```

---

# 30. GOLD-001 Override-Presence Flags, Effective View, and Baseline Evaluation

## Summary

Schema upgrade from v1.0.0 → v1.1.0 applied 2026-09-26 to
`financial_classifier_gold_review`. No historic review labels were changed.

## What was added

### Override-presence columns (13 new booleans, all NOT NULL DEFAULT FALSE)

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

### Effective-label rule

Do NOT use COALESCE. Use:

```sql
CASE WHEN <gold_field>_is_override THEN <gold_field> ELSE <seed_field> END
```

A flag = TRUE + gold_field = NULL means intentional override-to-unknown (valid).

### Back-fill inference (safe — all existing data was clean)

- CONFIRM_SEED: all flags remain FALSE
- SKIP: all flags remain FALSE
- OVERRIDE: flag = TRUE iff corresponding gold field IS NOT NULL
- ABSTAIN: gold_should_abstain_is_override = TRUE always; other flags = non-null presence

No ambiguous "explicit null" cases existed in the migration data. Zero rows
required manual inspection.

### Constraints added

- `chk_confirm_seed_no_overrides`
- `chk_skip_no_overrides`
- `chk_override_has_at_least_one_flag`
- `chk_abstain_should_abstain_flag`
- `chk_gold_null_when_no_flag`

### New objects

- View: `financial_classifier_gold_effective` (excludes SKIP, exposes effective fields)
- Table: `financial_classifier_gold_releases` (release registry)
- Table: `financial_classifier_evaluation_runs` (append-only)
- Table: `financial_classifier_evaluation_predictions` (append-only)

## Migration file

```text
gui/core/db/migrations/add_gold_override_flags_and_evaluation.sql
```

## Runner

```text
scratch/run_gold_override_migration_and_baseline.py
```

```powershell
$env:PYTHONPATH = "C:\Users\Dion\Desktop\Projects\stock_analysis\gui"
& "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" scratch/run_gold_override_migration_and_baseline.py
```

The script is idempotent: re-running skips already-created release/run records.

## GOLD-001 Release

```
release_id            : GOLD-001
schema_version        : 1.1.0
review_row_count      : 300
evaluation_row_count  : 281
confirm_seed_count    : 102
override_count        : 106
abstain_count         : 73
skip_count            : 19
dataset_hash          : 3c5e1ce829eac535a4c7263b3caed47266f67ed7fd16b8f61586164992efbc24
```

Hash column manifest: benchmark_id, ticker, normalized_label, review_decision,
all seed_* fields, all gold_* fields, all gold_*_is_override flags, reviewer_notes.
Excludes: imported_at, last_updated_at (volatile timestamps).

## Baseline evaluation (BASELINE-SEED-GOLD-001)

```
Evaluation population : 281
Coverage              : 0.3416  (seed attempted / total)
Full-label exact match: 0.4093

Dimension accuracy
  Concept               : 0.7794
  Scope                 : 0.9146
  Dilution              : 0.9146
  Tax Basis             : 0.9573
  Capex Basis           : 1.0000
  Lease Inclusion       : 1.0000
  Margin Denominator    : 0.9929
  Attribution           : 0.9822
  Alias Role            : 0.8719
  Value Pattern         : 0.8648
  Valuation Eligibility : 0.8292

Abstention
  TP=181  FP=4  FN=60  TN=36
  Precision : 0.9784
  Recall    : 0.7510
  F1        : 0.8498

Unsafe False Acceptance
  Definition: seed_should_abstain=False AND
              (effective_should_abstain=True OR any dim mismatches gold)
  Count : 65 / 96
  Rate  : 0.6771
```

## Freeze protocol

GOLD-001 is a released snapshot. To protect it:
- `financial_classifier_gold_releases` row is insert-only; never UPDATE it.
- Any post-release correction to underlying data must produce a new release (e.g. GOLD-002).
- Evaluation tables are append-only; never overwrite GOLD-001 run rows.
- The underlying review table is NOT physically locked but any change must be
  documented and produce a new release_id to preserve GOLD-001 for reproducibility.

---

# 31. BATCH-002 / BATCH-003 Review Preparation (2026-09-26)

## Batch structure

```
BENCH-0001 .. BENCH-0300  =>  BATCH-001  DEVELOPMENT  (GOLD-001, frozen)
BENCH-0301 .. BENCH-0560  =>  BATCH-002  VALIDATION   (not yet gold)
BENCH-0561 .. BENCH-0820  =>  BATCH-003  HOLDOUT      (not yet gold)
```

Split rule: deterministic in-order slice of benchmark_id.

## Dataset roles

- GOLD-001 (BATCH-001) -> DEVELOPMENT: may be used for threshold / format tuning
- GOLD-002 (BATCH-002) -> VALIDATION: use after tuning, before final evaluation
- GOLD-003 (BATCH-003) -> HOLDOUT: never expose to classifier tuning; evaluate only after config is locked

## New DB columns

```text
review_batch  text  CHECK IN ('BATCH-001','BATCH-002','BATCH-003')
dataset_role  text  CHECK IN ('DEVELOPMENT','VALIDATION','HOLDOUT')
```

## New DB views

```text
financial_classifier_review_batch_002            -- reviewer interface for BATCH-002
financial_classifier_review_batch_003            -- reviewer interface for BATCH-003
financial_classifier_batch_progress              -- overall progress per batch
financial_classifier_batch_progress_by_ticker
financial_classifier_batch_progress_by_concept
financial_classifier_batch_progress_by_alias_role
financial_classifier_batch_progress_by_valuation_eligibility
```

## New DB indexes

```text
financial_classifier_gold_review_batch_idx
financial_classifier_gold_review_role_idx
financial_classifier_gold_review_batch_decision_idx
```

## Runner

```text
scratch/prepare_review_batches_002_003.py
```

```powershell
$env:PYTHONPATH = "C:\Users\Dion\Desktop\Projects\stock_analysis\gui"
$env:PYTHONIOENCODING = "utf-8"
& "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" scratch/prepare_review_batches_002_003.py
```

Idempotent: ON CONFLICT DO NOTHING for inserts; DROP+RECREATE for views.

## Tests

```text
gui/modules/analysis/tests/test_gold_review_batches.py
```

```powershell
# Pure-logic (no DB):
& "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" -m pytest gui/modules/analysis/tests/test_gold_review_batches.py -v -k "not DbImport"

# All 29 tests including DB:
$env:RUN_GOLD_BATCH_DB_TESTS = "1"
& "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" -m pytest gui/modules/analysis/tests/test_gold_review_batches.py -v
```

## GOLD-001 hash re-confirmed

```
7f95fc104c59dfcdc42a7ced35ea102884c95b9829f15d1c1960895dcd7b1d43
```
*(Note: Initial hash prior to reviewer_notes finalization was 3c5e1ce829eac535a4c7263b3caed47266f67ed7fd16b8f61586164992efbc24. Gold labels, decisions, and override flags remain unchanged).*

## Release process (future)

A batch becomes a gold release ONLY after all rows in that batch are human reviewed.
Never create GOLD-002 or GOLD-003 until the corresponding batch is fully reviewed.
Never mutate prior releases.

---

# 32. Benchmark Release Identity Hierarchy & Population Isolation

## Release Identity Hierarchy

Every gold benchmark release maintains deterministic SHA-256 hashes forming a rigorous identity hierarchy:

### 1. `source_hash` (Benchmark Input Corpus)
- Uniquely identifies the input text and source context presented to the classifier.
- Ordered deterministically by `benchmark_id`.
- Columns (8): `benchmark_id`, `ticker`, `publication_datetime`, `previous_sentence`, `full_sentence`, `next_sentence`, `detected_numeric_tokens` (canonicalized JSON), `normalized_label`.
- Excludes volatile timestamps and all annotations.
- **GOLD-001**: `4b8594e5b34d7d05273fecda2dd4b817b9dc2e055d77cf0bc6de31cf79ff7610`

### 2. `label_hash` (Effective Annotations & Inclusion)
- Represents human gold labels and evaluation inclusion.
- Ordered deterministically by `benchmark_id`.
- **Included rows** (`review_decision <> 'SKIP'`): hashes `benchmark_id`, `is_included=TRUE`, and all 13 effective dimensions.
- **SKIP rows** (`review_decision = 'SKIP'`): hashes ONLY `benchmark_id` and `is_included=FALSE`.
  Unused effective labels on SKIP rows do NOT alter `label_hash`. Changing SKIP to included or vice versa alters `label_hash`.
- **GOLD-001**: `f9139858b89ea102d30c22e1007b1e807c5aecc684048ffb31df1dcb73e9ef75`

### 3. `release_hash` (Authoritative Release Identity)
- The composite identifier binding the input text, effective labels, and release metadata into a single authoritative identity.
- Canonical manifest template:
  `release_id={release_id}|schema_version={schema_version}|source_hash={source_hash}|label_hash={label_hash}\n`
- For GOLD-001:
  - `release_id`: `GOLD-001`
  - `schema_version`: `1.1.0` (authoritative release schema version recorded in `financial_classifier_gold_releases.schema_version`)
  - `source_hash`: `4b8594e5b34d7d05273fecda2dd4b817b9dc2e055d77cf0bc6de31cf79ff7610`
  - `label_hash`: `f9139858b89ea102d30c22e1007b1e807c5aecc684048ffb31df1dcb73e9ef75`
- **Schema version semantics**:
  - `annotation_schema_version = 1.1.0`: Database review schema incorporating sparse override presence flags (`gold_*_is_override`).
  - `release_schema_version = 1.1.0`: Authoritative benchmark release schema bound in the manifest and release table.
  - `release_identity_schema_version = 1.0`: Format specification version for the key-value manifest template.
- Future evaluation runs and benchmark consumers must reference this `release_hash`.
- **GOLD-001**: `f0b3138d32a033b66cd0823cfd83ae89461433209a0552bece6722d2ca98f179`

### 4. `audit_hash` (Complete Provenance State)
- Hashes the complete annotation state across all reviewed rows.
- Ordered deterministically by `benchmark_id`.
- Columns (43): `benchmark_id`, `ticker`, `normalized_label`, `review_decision`, 12 `seed_*` fields, 13 `gold_*` fields, 13 `gold_*_is_override` flags, `reviewer_notes`.
- **GOLD-001**: `7f95fc104c59dfcdc42a7ced35ea102884c95b9829f15d1c1960895dcd7b1d43`
- Pre-release candidate audit snapshot: `3c5e1ce829eac535a4c7263b3caed47266f67ed7fd16b8f61586164992efbc24`

### 5. Backward Compatibility
- `semantic_hash`: `d759e827f4c9469db407edfc08d7ab73fd21ff3767bb3e44d8255d896f467976` (legacy evaluation hash prior to SKIP-row dimension exclusion).
- `dataset_hash`: `7f95fc104c59dfcdc42a7ced35ea102884c95b9829f15d1c1960895dcd7b1d43` (points to `audit_hash`).

## Population Selection & Leakage Prevention

To prevent ongoing or future BATCH-002 / BATCH-003 reviews from leaking into GOLD-001 evaluations:

1. **Explicit Batch Filter**: Every evaluator query MUST explicitly specify:
   `WHERE review_batch = 'BATCH-001' AND review_decision <> 'SKIP'`
   Never query `review_decision <> 'SKIP'` alone.
2. **Dedicated Release Views**:
   - `financial_classifier_gold_001_effective`: strictly selects `WHERE review_batch = 'BATCH-001'` (281 rows).
   - Even when BATCH-002 rows receive human decisions, `financial_classifier_gold_001_effective` remains strictly invariant at 281 rows.

## Release Immutability Rules

1. **Authoritative Identity**: The `release_hash` is immutable for any published release. Any modification to source text or effective labels requires a new release version.
2. **Audit Independence**: Corrections to `reviewer_notes` alter `audit_hash` but do NOT alter `source_hash`, `label_hash`, or `release_hash`.
3. **Skip Row Independence**: Edits to unused annotation columns on a `SKIP` row do NOT alter `label_hash` or `release_hash`.
4. **No Premature Releases**: `GOLD-002` and `GOLD-003` do not exist and must not be created until review is 100% complete for the respective batch.

---

# 33. PowerShell `Select-String` Switch Parameter Syntax (`-CaseSensitive`)

## Symptom

Executing PowerShell `Select-String` with a string value for switch parameters:

```powershell
Select-String -Pattern 'Kev' -CaseSensitive:$false
```

fails with:

```text
Select-String : Cannot convert 'System.String' to the type 'System.Management.Automation.SwitchParameter' required by parameter 'CaseSensitive'.
```

## Root cause

In Windows PowerShell CLI argument parsing, passing `:$false` inside a command string can be interpreted as a string literal rather than a boolean switch value, or PowerShell switch parameters reject string conversion. Furthermore, `Select-String` is case-insensitive by default, making `-CaseSensitive:$false` completely redundant.

## Failing pattern (avoid)

```powershell
Select-String -Pattern 'text' -CaseSensitive:$false
```

## Working fix

Omit the parameter entirely for case-insensitive search (default behavior), or use git grep / ripgrep:

```powershell
Select-String -Pattern 'text'
```

---

# 34. PowerShell Multiline `python.exe -c` with Nested Quotes

## Symptom

Executing Python code inline in PowerShell via:

```powershell
& "path/to/python.exe" -c "
... multiline script with escaped quotes \" ...
"
```

fails with:

```text
python.exe : ScriptBlock should only be specified as a value of the Command parameter.
    + CategoryInfo          : InvalidArgument: (:) [], ParameterBindingException
    + FullyQualifiedErrorId : IncorrectValueForCommandParameter
```

## Root cause

PowerShell parses double quotes and escaped quotes across multiple lines inconsistently when invoking native executables with the `&` call operator, misinterpreting parts of the argument block as a PowerShell `ScriptBlock`.

## Failing pattern (avoid)

```powershell
& "C:\...\python.exe" -c "
import psycopg2
cur.execute('''SELECT * FROM table WHERE col = 'val';''')
print(r[\"col\"])
"
```

## Working fix

Write the logic to a script file (e.g., in the artifact `scratch/` directory) and invoke the file directly:

```powershell
& "C:\...\python.exe" "C:\path\to\scratch\inspect_script.py"
```

---

# 35. Kev Model Provenance and Evaluation Standardization

## 1. Kev-0.8B Authoritative Base Model Resolution

When running `jaredpalmer/kev-0.8b`, the base model is:
- **Base model**: `Qwen/Qwen3.5-0.8B-Base` (HF revision: `dc7cdfe2ee4154fa7e30f5b51ca41bfa40174e68`)
- **Model run**: `jaredpalmer/kev-0.8b` (HF revision: `9a45d25eb2ab761841196625383fa1dff0e56c1e`)
- **LoRA rank**: `16`
- **Temperature**: `2.3510958125672174`
- **Kev git commit**: `f1535963cea021439370c23127bc970b6788e730` (package `0.1.0`)

Never confuse `Qwen3.5-0.8B-Base` with `Qwen3.5-4B-Base` (`1001bb4d826a52d1f399e183466143f4da7b741b`).

## 2. Canonical Basis Evidence Normalization

In evaluation semantics:
- `NULL` or empty `effective_basis_evidence` in gold records canonicalizes strictly to `'unspecified'`.
- Gold database rows must NEVER be mutated.
- Use `modules.analysis.kev_gold_evaluator.normalize_basis_evidence`.

## 3. Unsafe False Acceptance Metrics Definitions

To prevent terminology confusion between population rates and intake admission rates:
- `accepted_count = tn + fn` (all rows admitted by model/policy)
- `safe_accept_count = tn` (rows admitted that are genuinely safe)
- `unsafe_accept_count = fn` (rows admitted that are unsafe for valuation)
- `unsafe_accept_rate_of_accepted = unsafe_accept_count / accepted_count`
- `unsafe_accept_rate_of_population = unsafe_accept_count / evaluation_population`


