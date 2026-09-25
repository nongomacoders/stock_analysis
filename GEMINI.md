# Stock Analysis Project – Persistent Agent Instructions

## Read this first

Before troubleshooting environment, Python, imports, database access, tests, historical packages, or recurring project issues:

1. Read this file.
2. Read `docs/AGENT_RUNBOOK.md`.
3. Inspect the existing implementation before creating new infrastructure.
4. Prefer the smallest targeted change.
5. Do not repeatedly rediscover known environment facts unless they genuinely fail.

---

## Project root

Repository root:

`C:\Users\Dion\Desktop\Projects\stock_analysis`

GUI / Python package root:

`C:\Users\Dion\Desktop\Projects\stock_analysis\gui`

---

## Python interpreter

Use this interpreter unless there is concrete evidence that it is unavailable:

`C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe`

Do not assume:
- `python`
- `py`
- Python 3.13
- a virtual environment
- another interpreter

Preferred PowerShell pattern:

```powershell
& "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" ...
```

Before searching for another Python installation, try the known interpreter above.

---

## PYTHONPATH

For commands importing from the GUI package, use:

```powershell
$env:PYTHONPATH = "C:\Users\Dion\Desktop\Projects\stock_analysis\gui"
```

Then run Python or pytest through the known Python 3.11 executable.

Example:

```powershell
$env:PYTHONPATH = "C:\Users\Dion\Desktop\Projects\stock_analysis\gui"

& "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" -m pytest ...
```

---

## Database

PostgreSQL configuration is loaded through the existing application configuration.

Known location:

`gui\core\config.py`

Use the existing `DB_CONFIG`.

Do not invent database credentials.

Do not create alternate configuration systems unless explicitly requested.

---

## Historical evidence packages

Historical source packages are stored under:

`gui\results_history\<TICKER>\<PERIOD>\`

Typical package:

```text
manifest.json
<TICKER>_<PERIOD>_AFS.pdf
<TICKER>_<PERIOD>_SENS.txt
```

Always validate the manifest and publication dates before using historical evidence.

Do not mix future-period evidence into a historical as-of-date analysis.

---

## Historical backtests

Historical backtests are pseudo-live.

Rules:

- only use information available by the historical as-of date
- unknown evidence availability fails closed
- approved historical ForecastPlans are separate from live ForecastPlans
- locked historical valuation results are immutable
- frozen input hashes must not change
- reveal outcomes are append-only revisions
- newer outcome revisions may supersede older outcomes
- never overwrite the locked historical valuation

TRU FY2025 -> FY2026 is the canonical reference retailer backtest.

See:

`HISTORICAL_BACKTEST_RUNBOOK.md`

and

`gui\architecture\historical_backtest_runbook.md`

---

## PDF extraction

Use Python PDF extraction first.

`PyPDF2` has successfully extracted Truworths AFS documents.

When a generic parser says a value is unavailable:

1. inspect the archived PDF
2. extract/search the PDF text
3. inspect the primary financial statements
4. inspect the relevant note
5. preserve page/note provenance
6. only then classify the metric as unavailable

Do not conclude that a metric is absent merely because a regex/parser failed.

---

## Financial semantic rules

Do not equate concepts merely because values appear similar.

Important distinctions:

- accounting revenue != sale of merchandise
- retail sales may differ from both
- trading profit != PBIT / operating profit
- trading margin denominator must be explicit
- income-statement D&A may differ from cash-flow D&A addback
- cash capex != accounting additions
- working-capital sign convention must be explicit
- reported net cash may exclude restricted or charitable cash
- lease liabilities remain separate from financial net cash
- weighted-average EPS shares != point-in-time valuation shares
- treasury shares must be explicit
- period-end shares may differ from announcement-date shares
- AFS exact values take precedence over rounded SENS figures when semantics and period match

---

## Valuation philosophy

Gemini may assist with:
- semantic interpretation
- source mapping
- research suggestions
- assumption proposals

Python must perform:
- deterministic calculations
- validation
- preflight checks
- DCF
- SOTP
- residual income
- reconciliations
- sensitivities

Do not accept AI-generated fair values at face value.

Missing or unresolved critical inputs should fail closed rather than be silently substituted.

---

## Before creating new code

Before adding a new module, migration, parser, helper, or workflow:

1. search for an existing implementation
2. inspect current tests
3. reuse existing architecture where possible
4. avoid stock-specific production branches
5. prefer generic semantic adapters over company hard-coding

---

## Troubleshooting rule

Before spending time rediscovering:
- Python path
- project path
- PYTHONPATH
- DB config
- historical package location
- pytest invocation

read `docs/AGENT_RUNBOOK.md`.

---

## Midstream error recording rule (mandatory)

Whenever a command, shell invocation, script, or environment tool fails due to a syntax, quoting, path, variable expansion, or platform quirk:

1. Identify the root cause and the working fix.
2. **Immediately record the error, root cause, failing pattern, and working command in `docs/AGENT_RUNBOOK.md` midstream.**
3. Do not postpone documentation until after completing the task, and do not wait for the user to remind you.
4. Then continue and finish the user's task.
