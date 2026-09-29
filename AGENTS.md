# Stock Analysis Project – Agent Instructions

Universal guidelines for AI agents working in this repository across all IDEs and tools.

---

## Read This First

Before troubleshooting the environment, Python, imports, database access, tests, historical packages, or recurring project issues:

1. Read this file.
2. Read `docs/README.md` for the documentation directory map and category structure.
3. Read only the relevant active workstream document under `docs/workstreams/<workstream>.md`.
4. Consult `docs/reference/TERMINAL_ERRORS.md` for terminal, shell, and command issues.
5. Inspect existing implementations before creating new infrastructure.
6. Prefer the smallest targeted change.
7. Do not repeatedly rediscover known environment facts unless they genuinely fail.

---

## Terminal and Command Execution Rule

If a terminal command fails, consult docs/reference/TERMINAL_ERRORS.md before inventing a new workaround. Add a concise entry only when a new reusable terminal issue and confirmed fix are discovered.

---

## Project Roots and Environment

### Repository root
```text
C:\Users\Dion\Desktop\Projects\stock_analysis
```

### Application / GUI root
```text
C:\Users\Dion\Desktop\Projects\stock_analysis\gui
```

### Python interpreter
Use this interpreter unless there is concrete evidence that it is unavailable:
```text
C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe
```

Do not assume `python`, `py`, Python 3.13, or an unverified virtual environment. In agent tooling, accessing paths in `AppData\Local` requires `BypassSandbox: true`.

### PYTHONPATH
For commands importing from the application package, set `PYTHONPATH` to the `gui` root:
```powershell
$env:PYTHONPATH = "C:\Users\Dion\Desktop\Projects\stock_analysis\gui"
& "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" ...
```

---

## Database Access

PostgreSQL configuration is loaded through existing application configuration:

- Configuration module: `gui\core\config.py`
- Usage: `from core.config import DB_CONFIG`

Rules:
- Do not invent database credentials.
- Do not create alternate configuration files or connection systems.

---

## Historical Evidence Packages

Historical source packages are stored under:
```text
gui\results_history\<TICKER>\<PERIOD>\
```

Typical package structure:
```text
manifest.json
<TICKER>_<PERIOD>_AFS.pdf
<TICKER>_<PERIOD>_SENS.txt
```

Rules:
- Always validate the manifest and publication dates before using historical evidence.
- Do not mix future-period evidence into a historical as-of-date analysis.

---

## Historical Backtests

Historical backtests are pseudo-live.

Rules:
- Only use information available by the historical as-of date.
- Unknown evidence availability fails closed.
- Approved historical ForecastPlans are strictly separate from live ForecastPlans.
- Locked historical valuation results are immutable; frozen input hashes must not change.
- Reveal outcomes are append-only revisions; newer outcome revisions may supersede older outcomes, but never overwrite locked valuations.
- TRU FY2025 -> FY2026 is the canonical reference retailer backtest.

Reference documentation:
- `HISTORICAL_BACKTEST_RUNBOOK.md`
- `gui\architecture\historical_backtest_runbook.md`

---

## PDF Extraction

Use Python PDF extraction first (`pypdf` / `PyPDF2`).

When a generic parser reports that a value is unavailable:
1. Inspect the archived PDF directly.
2. Extract/search the PDF text.
3. Inspect the primary financial statements.
4. Inspect the relevant note.
5. Preserve exact page and note provenance.
6. Only then classify the metric as unavailable.

Do not conclude that a metric is absent merely because a regex or generic parser failed.

---

## Financial Semantic Rules

Do not equate financial concepts merely because values appear similar.

Key distinctions:
- **Revenue**: Accounting revenue != sale of merchandise != retail sales.
- **Profit**: Trading profit != operating profit != PBIT / EBIT.
- **Margins**: Denominator of any margin calculation must be explicit.
- **D&A**: Income-statement D&A expense != cash-flow D&A non-cash addback.
- **Capex**: Cash capex payments != accounting additions.
- **Working Capital**: Working-capital cash flow sign conventions must be explicit.
- **Liquidity**: Reported net cash may exclude restricted or charitable cash.
- **Leases**: IFRS 16 lease liabilities remain separate from financial net debt/cash.
- **Shares**: Weighted-average EPS shares != point-in-time valuation shares. Treasury shares must be explicit. Period-end shares may differ from announcement-date shares.
- **Hierarchy**: Exact AFS values take precedence over rounded SENS figures when semantics and reporting periods match.

---

## Valuation Philosophy and Division of Responsibilities

### LLM Responsibilities
- Semantic interpretation of disclosures
- Source mapping and concept classification
- Research suggestions
- Assumption proposals

### Python Responsibilities
- Deterministic calculations
- Arithmetic validation and preflight checks
- DCF, SOTP, and residual income modeling
- Cross-evidence reconciliations and sensitivity matrices

Rules:
- Never accept AI-generated fair values at face value.
- Missing or unresolved critical inputs must fail closed rather than be silently substituted.

---

## Code Evolution and Architecture

Before adding a new module, migration, parser, helper, or workflow:
1. Search for an existing implementation.
2. Inspect current tests.
3. Reuse existing architecture where possible.
4. Avoid stock-specific branches in production code; prefer generic semantic adapters.

---

## Related Documentation

- `docs/README.md`: Central documentation catalog and reading sequence.
- `docs/reference/TERMINAL_ERRORS.md`: Confirmed fixes for PowerShell, quoting, environment, and shell syntax issues.
- `docs/workstreams/`: Living active workstream state documents.
- `docs/benchmarks/financial_classifier/BENCHMARK_LINEAGE_AND_RELEASES.md`: Historical benchmark lineage (BATCH-001/002/003, GOLD-001) and release identities.
- `docs/archive/runbooks/AGENT_RUNBOOK.md`: Historical operational runbook archive.
