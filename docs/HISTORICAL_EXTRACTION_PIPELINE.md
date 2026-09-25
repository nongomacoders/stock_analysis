# Historical Financial-Data Extraction Pipeline: Technical Architecture & Operational Guide

---

## 1. Executive Overview

The historical financial-data extraction pipeline in this repository is a **100% deterministic, audit-trailed, leakage-controlled extraction and valuation engine**. 

Its core engineering purpose is to ingest physical historical reporting packages (AFS PDF documents, SENS announcements, and metadata manifests) as of an immutable historical cut-off date (`as_of_date`), parse and validate every financial metric without lookahead bias, gate readiness via strict semantic type checks, and feed deterministic DCF valuation models.

### Key Architectural Invariants
1. **Physical Date Separation**: `period_end` (economic reporting period close) and `published_at` (document market availability) are strictly segregated. An unresolved publication date fails closed.
2. **Deterministic Extraction**: Zero LLM or AI generation is permitted in metric extraction, arithmetic, normalizations, or valuation calculations.
3. **Immutable History**: Once a historical valuation executes, its inputs, plans, assumptions, and outputs are permanently frozen with SHA-256 cryptographic hashes.
4. **Append-Only Revisions**: Future actuals (reveal outcomes) never overwrite locked historical results; they append as revision-tracked audit rows (`Revision N+1`).

---

## 2. End-to-End Pipeline

The end-to-end lifecycle proceeds across nine distinct stages:

```
[Historical Source Package on Disk]
       │
       ▼
Stage 1: Package Loading & Manifest Validation (historical_packages.py)
       │
       ▼
Stage 2: Text Extraction & Document Classification (pypdf & results_package.py)
       │
       ▼
Stage 3: Deterministic Parsing & Line Pairing (afs_parser.py & sens_parser.py)
       │
       ▼
Stage 4: Observation Reconciliation & Typed Metric Creation (financial_metrics.py)
       │
       ▼
Stage 5: Leakage Filtering & Historical Snapshot Assembly (historical_backtest.py)
       │
       ▼
Stage 6: Historical Baseline Readiness Gating (historical_readiness.py)
       │
       ▼
Stage 7: Retail Forecast Bridge & Assumption Approval (historical_retail_bridge.py / historical_plan.py)
       │
       ▼
Stage 8: Deterministic DCF Valuation Execution (historical_dcf_execution.py)
       │
       ▼
Stage 9: Hash Freezing, Database Lock & Reveal Outcome (historical_backtests.py)
```

### Stage-by-Stage Trace

| Stage | Input | Module / File | Function / Class | Output | Storage State |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Package Load** | `manifest.json`, file paths | `gui/modules/analysis/historical_packages.py` | `validate_period_folder()` | `HistoricalManifest` object | Transient (in-memory) |
| **2. PDF Extraction** | `*_AFS.pdf`, `*_SENS.txt` | `gui/modules/analysis/historical_packages.py` / `gui/modules/analysis/results_package.py` | `pypdf.PdfReader`, `read_document_text()` | Raw Unicode text strings per page / file | Transient |
| **3. Parsing** | Raw text, page streams | `gui/modules/analysis/afs_parser.py` / `gui/modules/analysis/sens_parser.py` | `parse_afs()`, `parse_sens()` | Raw observation dictionaries (`_obs`) | Transient |
| **4. Normalization** | Raw observations | `gui/modules/analysis/results_package.py` | `reconcile_observations()`, `observations_to_metrics()` | List of `FinancialMetric` Pydantic models | Transient / cacheable |
| **5. Snapshotting** | Metrics + `as_of_date` | `gui/modules/analysis/historical_backtest.py` | `resolve_evidence_as_of()`, `HistoricalBacktest` | `evidence_snapshot` (list of `HistoricalEvidence`) | Persisted in `historical_backtests.evidence_snapshot` (JSONB) |
| **6. Readiness Gate** | `HistoricalBacktest` | `gui/modules/analysis/historical_readiness.py` | `evaluate_historical_baseline()` | `HistoricalReadinessResult` (READY / BLOCKED) | Transient validation report |
| **7. Plan & Bridge** | Baseline + Approved assumptions | `gui/modules/analysis/historical_retail_bridge.py` / `gui/modules/analysis/historical_plan.py` | `derive_historical_retail_forecasts()`, `approve_historical_plan_in_place()` | `HistoricalForecastPlan` with frozen `input_hash` | Persisted in `historical_backtest_plans` |
| **8. Valuation** | Locked plan + snapshot | `gui/modules/analysis/historical_dcf_execution.py` | `execute_historical_dcf()` | `HistoricalValuationResult` (EV, Target Price) | Transient calculation result |
| **9. Lock & Persist** | Valuation result + plan | `gui/modules/data/historical_backtests.py` | `insert_result()`, `lock_backtest_in_db()` | Cryptographic lock, DB rows | Persisted in `historical_backtests` & `historical_backtest_results` |

---

## 3. Source Loading

### Code Reference
```text
Stage:
Source Loading and Manifest Enforcement

File:
gui/modules/analysis/historical_packages.py

Class / Functions:
HistoricalManifest (Pydantic model)
validate_period_folder(folder: Path, expected_ticker: str, as_of_date: date | None)
suggest_manifest(ticker: str, period_label: str, ...)

Purpose:
Validate historical evidence packages against tampering, ensure file identity matches
manifest declarations, extract SHA-256 digests, and enforce availability cutoff dates.

Input:
Directory path on disk containing manifest.json, AFS PDF, and SENS text file.

Output:
Dictionary containing validation status ('VALID', 'WARNING', 'INVALID'), parsed HistoricalManifest,
and list of validated source payloads with SHA-256 IDs.
```

### Mechanisms of Source Loading
1. **Manifest File Structure**: Every package directory must have a valid `manifest.json`.
   ```json
   {
     "schema_version": 1,
     "ticker": "TRU.JO",
     "symbol": "TRU",
     "period_label": "FY2025",
     "period_type": "fiscal_year",
     "period_start": "2024-07-01",
     "period_end": "2025-06-29",
     "sources": [
       {
         "type": "SENS",
         "file": "TRU_FY2025_SENS.txt",
         "published_at": "2025-08-28",
         "active": true,
         "revision": 1
       },
       {
         "type": "AFS",
         "file": "TRU_FY2025_AFS.pdf",
         "published_at": "2025-08-28",
         "active": true,
         "revision": 1
       }
     ]
   }
   ```
2. **Identity & File Integrity**:
   - `canonical_ticker_folder`: Sanitizes tickers to Windows-safe folder names (e.g. `TRU.JO` $\to$ `TRU`).
   - `expected_filenames`: Strictly enforces standard naming `f"{symbol}_{period}_{type}.{ext}"`.
   - File SHA-256 hash checks prevent duplicate or empty files.
3. **Availability Policy & Lookahead Prevention**:
   - `published_at < period_end` triggers a **blocking validation error** (`BLOCKING_ERROR: published_at precedes period_end`), as a document cannot physically be released before the reporting period closes.
   - If `published_at is None`, the source status is marked `unresolved` and **excluded completely** from the historical evidence snapshot (`resolve_evidence_as_of()`).
   - If `as_of_date` is provided and `published_at > as_of_date`, the source is omitted. The system **never** falls back to `period_end` for availability.

---

## 4. PDF Extraction in Detail

### Code Reference
```text
Stage:
Text Extraction from PDF

Files:
gui/modules/analysis/historical_packages.py (lines 402-411)
gui/modules/analysis/afs_parser.py (lines 106-119)
gui/modules/analysis/results_package.py (lines 44-55)

Function / Library:
pypdf.PdfReader (with fallback to PyPDF2.PdfReader)

Purpose:
Extract text streams page-by-page from annual financial statement PDFs.

Input:
File path to AFS PDF document.

Output:
Unicode string representing text content per page, tracking exact 1-indexed page numbers.
```

### Extraction Mechanics
1. **Library Hierarchy**: The project imports `from pypdf import PdfReader`, falling back to `from PyPDF2 import PdfReader` for backwards compatibility. (The environment is running `pypdf 6.19.0`).
2. **Page-by-Page Extraction**:
   - When building the full document model, `enumerate(reader.pages, 1)` iterates over every page.
   - Page text is extracted with `page.extract_text() or ''`.
   - The 1-indexed page number (`page_no`) is passed into every single observation via `_obs()`.
3. **Absence of OCR and Image Processing**:
   - No OCR engine (e.g., Tesseract) is bundled or invoked. The pipeline requires text-based vector PDFs (standard JSE/AFS published annual reports).
   - Images and graphical elements are completely bypassed.
4. **Table Structure Handling**:
   - Tables are **not** parsed with geometric bounding boxes or structural cell extractors (like `pdfplumber` or `camelot`).
   - Instead, the extracted stream from `pypdf` maintains relative line ordering. The parser uses multiline regexes (`(?im)^\s*...`) operating across line boundaries to match line items against numbers.
5. **Caching & Persistence**:
   - Raw extracted text is **transient**. It is kept in memory during the parsing session.
   - Only the structured output (the typed `FinancialMetric` / `HistoricalEvidence` dictionary containing the value, unit, page number, and evidence quote) is persisted to PostgreSQL JSONB.

---

## 5. Deterministic Parsing

### Code Reference
```text
Stage:
Deterministic Financial Statement Parsing

Files:
gui/modules/analysis/afs_parser.py
gui/modules/analysis/sens_parser.py

Functions:
parse_afs(source: dict) -> tuple[list[dict], list[str]]
parse_sens(source: dict) -> list[dict]
_line_pair(text: str, label: str) -> tuple[str | None, str | None, str | None]
_decimal(raw: str | None) -> Decimal | None

Purpose:
Map financial statement lines, note disclosures, and SENS headlines to canonical financial concepts.
```

### 1. Statement Detection & Section Mapping
`afs_parser.py` maps statements using exact title regexes:
```python
STATEMENT_MAP = {
    r"GROUP STATEMENTS? OF FINANCIAL POSITION": ("balance_sheet", { ... }),
    r"GROUP STATEMENTS? OF COMPREHENSIVE INCOME": ("income_statement", { ... }),
    r"GROUP STATEMENTS? OF CASH FLOWS": ("cash_flow_statement", { ... })
}
```
When a statement title regex matches a page, only that page's text is scanned for the corresponding line items.

### 2. Line Pairing: Current vs Comparative Periods
The function `_line_pair(text, label)` matches a line item followed by two consecutive number columns:
```python
pattern = rf"(?im)^\s*{label}\s+(?:\d+(?:\.\d+)?(?:,\s*\d+)?\s+)?(\(?[\d,]+(?:\.\d+)?\)?)\s+(\(?[\d,]+(?:\.\d+)?\)?)\s*$"
```
- Group 1 represents the **Current Period** value.
- Group 2 represents the **Comparative Prior Period** value.
- The optional middle group `(?:\d+(?:\.\d+)?(?:,\s*\d+)?\s+)?` automatically absorbs note reference numbers (e.g. Note `27.2` or `13, 14`).

### 3. Number Parsing, Negatives, and Scaling
`_decimal(raw)` handles negative numbers in brackets:
```python
negative = raw.startswith("(") and raw.endswith(")")
raw = raw.strip("()").replace(",", "").replace(" ", "")
val = Decimal(raw)
return -val if negative else val
```
Units and scaling:
- Balance sheet, Income statement, and Cash flow statement figures default to `scale="millions"`, multiplying the parsed decimal by $1,000,000$ to obtain the base `ZAR` value.
- Cents per share (`CENTS = {"eps", "diluted_eps", "heps", ...}`) are retained with unit `ZAR_cents` and scale `1`.
- Shares (`SHARES = {"issued_shares_current", "treasury_shares", ...}`) are scaled depending on disclosure: Note 14 Treasury Shares in thousands ($10^3$), Note 13 Share Capital in full shares ($1$), or per-share notes in millions ($10^6$).

---

## 6. Typed Metrics Architecture

The pipeline uses two complementary Pydantic representations: `FinancialMetric` (in `gui/modules/analysis/financial_metrics.py`) and `HistoricalEvidence` (in `gui/modules/analysis/historical_backtest.py`).

### Complete Field Schema
```python
class FinancialMetric(BaseModel):
    metric_id: UUID                       # Unique UUID4
    ticker: str                           # e.g. "TRU.JO"
    report_id: UUID | None                # Associated report UUID
    name: str                             # Canonical semantic concept (e.g. "trading_profit")
    value: Decimal | None                 # Raw/normalized numeric decimal
    raw_value: str | None                 # Literal text from document (e.g. "2 892")
    raw_unit: str | None                  # Literal document unit (e.g. "ZAR_million")
    normalized_value: Decimal | None      # Scaled absolute base value (e.g. Decimal("2892000000"))
    normalized_unit: Unit | None          # Standard Unit enum (e.g. Unit.ZAR, Unit.SHARES)
    currency: str | None                  # "ZAR", "GBP", "USD"
    period_start: date | None             # Economic period start
    period_end: date | None               # Economic period end (2025-06-29)
    effective_date: date | None           # Point-in-time date for balance sheet / share counts
    source_date: date | None              # Publication date (2025-08-28)
    observed_at: datetime | None          # Ingestion timestamp
    source_id: str | None                 # Format: "historical:<sha256>"
    source_type: SourceType               # SourceType.COMPANY_DISCLOSURE
    assumption_type: AssumptionType       # AssumptionType.HISTORICAL_ACTUAL
    document_role: str | None             # "annual_financial_statements" or "results_sens"
    source_page: int | None               # 1-indexed physical PDF page (e.g. 21)
    source_section: str | None            # e.g. "cash_flow_statement", "note_share_capital"
    raw_label: str | None                 # Matched line label (e.g. "Trading profit")
    evidence_quote: str | None            # Full line string extracted from document
    parser_version: str | None            # "results-package-1.0"
```

### Concept Hierarchy Definitions
- **Raw Value (`raw_value`, `raw_unit`)**: The verbatim textual string from the document (e.g. `"2 892"`, `"R million"`).
- **Normalized Value (`normalized_value`, `normalized_unit`)**: Deterministically scaled base representation (e.g. `Decimal("2892000000")`, `Unit.ZAR`).
- **Observation**: An unvetted fact directly parsed from a single source document.
- **Metric**: A validated, typed `FinancialMetric` carrying explicit date, provenance, and semantic metadata.
- **Semantic Role**: The financial duty the metric performs in the model (e.g., `merchandise_sales_baseline`, `equity_bridge_reported_net_cash`).
- **Document Role**: The origin document classification (`annual_financial_statements` vs `results_sens`).
- **Assumption**: A forward-looking policy parameter (`ForecastAssumption`), requiring reviewer approval.
- **Forecast**: A derived future expectation computed deterministically by applying an approved assumption to a historical baseline metric.

---

## 7. Semantic Conflict Resolution

When similar or competing figures exist across sources, deterministic resolution rules apply.

### 1. Separation of Concepts at Parser Level
The parser never coalesces distinct concepts into a single field:
- `revenue` vs `sale_of_merchandise` vs `retail_sales`: All three are emitted as separate observations.
- `trading_profit` vs `profit_before_finance_costs_and_tax` (Operating Profit / PBIT): Emitted separately.
- `depreciation_amortisation_expense` vs `depreciation_amortisation_cashflow_addback`: Emitted separately.

### 2. Precedence Hierarchy
In `results_package.py` (`reconcile_observations`) and `historical_readiness.py`:
- **AFS takes precedence over SENS** for accounting statement figures. SENS is rounded (e.g. to R0.1bn), whereas AFS gives exact values (to Rm or R'000).
- **SENS takes precedence over AFS** specifically for corporate actions announced concurrently: `announcement_date_external_shares` and `annual_dividend_per_share`.

### 3. Concrete Example: TRU FY2025 D&A Reconciliation
```
Income Statement (AFS p. 19):
  "Depreciation and amortisation" = R1,500m
  -> Stored as: depreciation_amortisation_expense = Decimal("1500000000")

Cash Flow Note 33.1 (AFS p. 98):
  "Depreciation and amortisation" = R1,526m
  -> Stored as: depreciation_amortisation_cashflow_addback = Decimal("1526000000")

Reconciliation (AFS Note 27.1 p. 82 & Note 27.2 pp. 82–83):
  Trading expenses D&A (Note 27.2) = R1,500m
  Distribution depreciation included in Cost of Sales (Note 27.1) = R26m
  Total cash flow addback = R1,500m + R26m = R1,526m
```
In `historical_readiness.py`, both concepts are evaluated and verified:
- `statuses["depreciation_amortisation_expense"]` confirms R1,500m.
- `statuses["depreciation_amortisation_cashflow_addback"]` confirms R1,526m.
- The readiness report attaches the exact audit note explaining why R1,526m is the complete addback for FCFF calculations.

---

## 8. Working-Capital Sign Handling

Working capital movements are a common source of sign errors in corporate finance pipelines. The project resolves this with explicit typed semantics.

### 1. Extraction
In `afs_parser.py` (lines 120–133):
The cash-flow statement line `"Working capital movements"` is parsed with `_line_pair()`.
For TRU FY2025, the statement line on Page 21 is:
```text
Working capital movements    33.2    166    38
```
- Current period (FY2025): `+166` (`Decimal("166000000")`, +R166m cash inflow)
- Comparative prior period (FY2024): `+38` (`Decimal("38000000")`, +R38m cash inflow)
- Stored as both `working_capital_movement` and `working_capital_cash_flow`.

### 2. Sign Convention
The convention is explicitly defined in `_obs()` and `HistoricalReadinessResult`:
$$\mathbf{positive} = \text{cash inflow (working capital released)}$$
$$\mathbf{negative} = \text{cash outflow (working capital absorbed)}$$

### 3. Valuation Engine Conversion
In `historical_dcf_execution.py` (line 105):
$$\text{FCF} = \text{EBIT} - \text{Tax} + \text{Depreciation} - \text{Capex} - \Delta\text{WC} - \text{Other}$$
Where $\Delta\text{WC}$ is defined as cash outflow (investment in working capital).
In `historical_readiness.py`, `working_capital_sign_convention="positive_cash_inflow"`.
When the analyst accepts an assumption of $\text{R0}$ or converts historical working capital cash flow ($+R166m$), the sign is mapped into the `ForecastYear` object without double-negation.

---

## 9. Capex Handling

### 1. Component Extraction
In `afs_parser.py` (Cash Flow Statement, lines 58–60 & 134–135):
- `capex_expansion`: `"Acquisition of plant and equipment to expand operations"` = `R428m`
- `capex_maintenance`: `"Acquisition of plant and equipment to maintain operations"` = `R187m`
- `intangible_additions`: `"Acquisition of computer software"` = `R59m`

### 2. Total Calculation
In lines 192–196:
```python
tot = sum(total_capex_components.values())  # 428 + 187 + 59 = 674
observations.append(_obs(source, ANNUAL_FINANCIAL_STATEMENTS, "total_capex", tot, "ZAR", ... scale="millions"))
observations.append(_obs(source, ANNUAL_FINANCIAL_STATEMENTS, "cash_capex", tot, "ZAR", ... scale="millions"))
```
The total is computed as the sum of physical cash additions on the cash flow statement.

### 3. Cash Capex vs Accounting Additions
- **Cash capex** (R674m): Cash paid as per Statement of Cash Flows. This is the convention required by the valuation engine for DCF.
- **Accounting additions** (Note 7 PPE additions + Note 8 Intangible additions): Includes unpaid capex and capital accruals. Kept strictly separate.
- The semantic basis is recorded as `capex_basis = "cash_capex"`.

---

## 10. Net Cash Handling

In retail valuations, lease liabilities (IFRS 16) must not be commingled with financial net debt.

### 1. Reported Net Cash Reconstruction
In `historical_readiness.py` (lines 250–278), reported net cash is verified through two independent paths:
1. **SENS Headline Extraction**: Direct parsing from SENS (`Net cash of R720 million`).
2. **AFS Balance Sheet & Notes Reconciliation**:
   ```
   + Cash and cash equivalents (Balance Sheet p. 18):       R964m
   - Charitable trust cash (AFS Note 16, p. 58):            -R14m
   + Current assets held at fair value (Money Market p. 18):+R2,224m
   - Interest-bearing borrowings (Balance Sheet p. 18):    -R1,479m
   - Bank overdraft (Balance Sheet p. 18):                  -R975m
   --------------------------------------------------------
   = Reconciled Reported Net Cash:                          +R720m
   ```
If all AFS balance sheet components are present, `historical_readiness.py` deterministically recalculates this reconciliation and cross-checks it against SENS.

### 2. Debt Concepts Distinction (Net Cash vs WACC)
A critical financial distinction is enforced between balance-sheet carrying debt and contractual debt for WACC:
- **Contractual debt for WACC = R2.443bn**: This is the contractual principal basis used for the debt-to-equity weighting in WACC (`historical_backtest_results.valuation_result -> 'contractual_debt_for_wacc'`).
- **Balance-sheet borrowings + overdraft = R2.454bn**: This is the balance-sheet carrying amount of borrowings ($\text{R1,479m}$) plus overdraft ($\text{R975m}$) used in the net cash reconciliation.
- **These should never be treated as interchangeable.** R2.443bn is the contractual principal basis used for WACC, while R2.454bn is the balance-sheet carrying amount of borrowings plus overdraft.

### 3. Treatment of Leases
- Non-current lease liabilities ($\text{R2,697m}$) and current lease liabilities ($\text{R1,045m}$) total **R3,742m** (AFS Balance Sheet p. 18, Note 20.1 p. 63).
- **Leases are never subtracted inside `reported_net_cash`**. They are stored in `lease_liabilities` as a distinct equity-bridge liability.
- In `historical_dcf_execution.py` (lines 137–143), `reconcile_equity` handles `cash=net_cash` ($+R720m$) and `lease_adjustments=lease_adj` ($-R3,742m$) as two explicit, independent bridge items.

---

## 11. Share-Count Handling

The pipeline extracts and manages five distinct share concepts for TRU FY2025:

| Metric Name | Extracted Value | Source & Provenance | Effective Date |
| :--- | :--- | :--- | :--- |
| `issued_shares_current` | $408,498,899$ | AFS Note 13 (p. 55) & SENS | $2025-06-29$ |
| `treasury_shares` | $33,138,000$ | AFS Note 14 (p. 56) | $2025-06-29$ |
| `period_end_external_shares` | $375,360,899$ | Derived: Note 13 ($408,498,899$) $-$ Note 14 ($33,138,000$) | $2025-06-29$ |
| `announcement_date_external_shares` | $383,367,835$ | SENS Announcement: $408,498,899 - 25,131,064$ | $2025-08-28$ |
| `weighted_average_basic_shares` | $374,400,000$ | AFS Note 31.1 (p. 95) ($374.4\text{m}$) | Full FY2025 |
| `weighted_average_diluted_shares` | $378,800,000$ | AFS Note 31.2 (p. 96) ($378.8\text{m}$) | Full FY2025 |

### Denominator Policy and Warning
- `select_historical_share_count()` in `historical_backtest.py` prioritizes:
  1. `forecast_diluted_shares`
  2. `external_shares_ex_treasury` (period-end external shares)
  3. `weighted_average_diluted_shares`
  4. `issued_shares_current`
  5. `weighted_average_basic_shares`
- In `historical_readiness.py` (lines 450–456), when the valuation date ($2025-08-31$) is after the announcement date ($2025-08-28$), the system issues a **Methodological Warning**: the announcement-date external count ($383.37m$) is more current than the period-end count ($375.36m$). The locked valuation's use of $375.36m$ is flagged for methodological clarity without mutating the locked result.

---

## 12. Readiness Gate

Before any `HistoricalForecastPlan` or DCF execution can proceed, `assert_historical_baseline_ready()` in `historical_readiness.py` must pass.

### Gating Requirements

```
Core Gating Concepts (All MUST be AVAILABLE):
  1.  accounting_revenue
  2.  sale_of_merchandise
  3.  trading_profit
  4.  depreciation_amortisation_expense
  5.  cash_capex
  6.  working_capital_cash_flow
  7.  effective_tax_rate
  8.  reported_net_cash
  9.  lease_liabilities
  10. historical_share_denominator
  11. historical_market_price
```

### Readiness Status Enumeration
- `AVAILABLE`: Validated value present within allowed scale, sign, and unit bounds.
- `MISSING`: Concept absent or null in eligible evidence snapshot. **(Blocks execution)**.
- `INVALID_SCALE`: Magnitude below min or above max (e.g. retail revenue $< 10^9$). **(Blocks execution)**.
- `INVALID_UNIT`: Unit mismatch (e.g. expected `ZAR`, got `percentage`). **(Blocks execution)**.
- `INVALID_SIGN`: Negative value when non-negative required. **(Blocks execution)**.
- `PERIOD_MISMATCH`: Observation period end does not match backtest period. **(Blocks execution)**.
- `DILUTION_UNMODELED`: Triggered if unadjusted `issued_shares_current` is used without modeling treasury shares. *(Allowed with warning)*.

---

## 13. Gemini / LLM Involvement

To preserve scientific reproducibility and regulatory audit standards, LLMs are strictly segregated:

```
+-----------------------------------------------------------------------+
| DETERMINISTIC PYTHON LAYER (No LLM Access)                            |
| - Manifest validation and SHA-256 hashing                             |
| - AFS PDF and SENS text parsing (pypdf, regex)                        |
| - Number scaling, unit conversions, and sign normalizations           |
| - Baseline readiness gating                                           |
| - Retail forecast bridge mathematical derivations                     |
| - DCF valuation and equity bridge calculations                        |
| - Database locks and cryptographic input hashing                      |
+-----------------------------------------------------------------------+
                                  ▲
                                  │ (Only reads structured summaries)
                                  │ (Cannot overwrite deterministic facts)
                                  ▼
+-----------------------------------------------------------------------+
| OPTIONAL GEMINI / LLM ASSISTANT LAYER                                 |
| - Qualitative research summarization (generate_deepresearch_from_...) |
| - High-level price change explanations                                |
| - Interactive chat guidance / code explanation                        |
+-----------------------------------------------------------------------+
```

### Specific Operational Facts
- **Gemini never reads the full AFS PDF directly** during the historical backtest pipeline.
- **Gemini cannot modify or overwrite** extracted source metrics.
- **All valuation assumptions require explicit analyst approval** (`approved_by`, `approved_at`). AI-proposed assumptions remain in `status='proposed'` and will deliberately block plan approval and valuation execution until accepted by a human reviewer.

---

## 14. Database Persistence

All historical backtest operations are persisted across four dedicated PostgreSQL tables in `gui/core/db/migrations/add_historical_backtests.sql` and `gui/core/db/migrations/add_historical_outcome_revisions.sql`:

### 1. `historical_backtests`
- **What is stored**: Container metadata, `as_of_date`, `evidence_snapshot` (complete JSONB dump of all eligible `HistoricalEvidence`), `market_snapshot`, and overall lifecycle status.
- **Lifecycle status**: `'draft' -> 'locked' -> 'completed'` (or `'failed'`).
- **Mutability**: Mutable during draft; permanently frozen upon lock.

### 2. `historical_backtest_plans`
- **What is stored**: The `HistoricalForecastPlan`, version number, assumption snapshot (growth rates, WACC, margin), horizon, and input hash.
- **Lifecycle status**: `'draft' -> 'approved' -> 'superseded'` (or `'locked'`).
- **Versioning**: Compound unique key `(backtest_id, plan_version)`. Edits to draft produce version increments; approved plans are immutable.

### 3. `historical_backtest_results`
- **What is stored**: Deterministic valuation output (Fair Value per share, Enterprise Value, Equity Value, DCF forecast schedule, warnings).
- **Mutability**: **Insert-only and completely immutable**. Unique key `(backtest_id, historical_plan_id, valuation_engine_version, input_hash)`. There is no SQL `UPDATE` path.

### 4. `historical_backtest_outcomes`
- **What is stored**: Perfect foresight / actual outcome comparisons once future actuals are revealed (e.g. FY2026 actuals).
- **Revisions**: Uses an append-only revision pattern:
  - Columns: `revision` (integer), `supersedes_outcome_id` (UUID), `outcome_status` (`'partial'` or `'completed'`), `outcome_hash`.
  - Unique constraint: `UNIQUE (backtest_id, transition_key, revision)`.
  - Corrections append as `Revision N+1` referencing `supersedes_outcome_id`.

---

## 15. Lock and Immutability Controls

### 1. Construction of `input_hash`
In `historical_backtest.py` (lines 125–132):
```python
def backtest_input_hash(backtest, forecast_plan, engine_version, ...):
    return canonical_hash({
        'ticker': backtest.ticker,
        'as_of_date': backtest.as_of_date,
        'evidence_ids': sorted(x.evidence_id for x in backtest.evidence_snapshot if x.availability == Availability.AVAILABLE),
        'market_ids': sorted(x.snapshot_id for x in backtest.market_snapshot),
        'forecast_plan': forecast_plan.model_dump(mode='json'),
        'engine_version': engine_version
    })
```
Every input that contributes to the valuation—source evidence SHA-256 IDs, market price snapshot IDs, approved forecast assumptions, and engine code version—is sorted and serialized via canonical JSON to produce a 64-character SHA-256 digest.

### 2. Enforcement
- Attempting to call `execute_historical_dcf()` on an unlocked backtest raises `ValueError("Backtest must be locked before execution")`.
- Once `locked_at` is set, attempting to modify plan assumptions raises `ValueError("Cannot edit or approve a locked historical plan")`.
- The database schema rejects any duplicate valuation attempt with the same input hash.

---

## 16. Failure Modes & System Behavior

| Failure Mode | Root Cause | System Response | Action Required |
| :--- | :--- | :--- | :--- |
| **Missing manifest.json** | Package created without manifest | **Fails Closed** (`INVALID`) | Analyst must generate starter manifest |
| **published_at < period_end** | Manifest error (document dated before period close) | **Blocking Error** (`BLOCKING_ERROR`) | Correct manifest with true announcement date |
| **published_at is None** | SENS footer date unparseable | **Fails Closed** (Excluded from evidence) | Analyst provides explicit date override |
| **PDF Text Layout Change** | Publisher altered spacing or line order | Metric classified `NOT_AVAILABLE` | Inspect PDF with Python script; adapt regex |
| **Negative Bracket Mismatch** | Unusual bracket formatting or currency symbol | Defaults to positive or fails regex | Verify `_decimal()` handling |
| **Duplicate Source Hashes** | Same PDF copied twice in manifest | **Fails Closed** (`Duplicate file hash`) | Remove redundant file from manifest |
| **Unmodeled Dilution** | Using issued shares while treasury shares exist | **Pass with Warning** (`DILUTION_UNMODELED`) | Configure external share count |
| **Unapproved Assumption** | Plan submitted while assumption in `PROPOSED` | **Blocking Error** | Human reviewer must approve assumption |

---

## 17. Behavior with a New Retail Company

If a new company package (e.g. `gui/results_history/XYZ/FY2024/`) is added:

### Generic Features
- Manifest parsing, SHA-256 file hashing, publication date enforcement, and leakage exclusion are **100% generic** and will work for any stock.
- The standard statement mappings for Balance Sheet (`Total assets`, `Inventories`, `Cash and cash equivalents`), Income Statement (`Revenue`, `Gross profit`, `Finance costs`), and Cash Flows (`Cash generated from operations`, `Tax paid`) are standard IFRS lines and will parse automatically if the company uses standard titles.

### Company-Specific & Retailer Patterns Currently in Code
The parser currently contains several patterns tailored to Truworths terminology:
1. **Merchandise Sales vs Revenue**: `Sale of merchandise` is specifically searched in `STATEMENT_MAP`. Other retailers might call this `"Sale of goods"` or `"Merchandise sales"`.
2. **Trading Profit vs Operating Profit**: Note 27 segment lines and `Trading profit` are matched. Retailers reporting solely `"Operating profit"` or `"PBIT"` will require an adapter mapping.
3. **Capex Line Labels**: Lines 58–60 in `afs_parser.py` look for:
   - `"Acquisition of plant and equipment to expand operations"`
   - `"Acquisition of plant and equipment to maintain operations"`
   - `"Acquisition of computer software"`
   Retailers reporting a single `"Purchase of property, plant and equipment"` line will not populate `total_capex_components` unless adapted.
4. **Segment Note Numbers**: Lines 147, 151, 155, 171, 174 search specific note titles (`Note 13 Share Capital`, `Note 14 Treasury Shares`, `Note 33 Cash Flow`). Companies numbering these notes differently will not parse these specific note items automatically.
5. **Fallbacks in `historical_readiness.py`**: Lines 122–124 and 331 default fallback filename strings to `"TRU_FY2025_AFS.pdf"` if raw file metadata is unpopulated.

---

## 18. Current Limitations & Technical Debt

1. **Parser Regex Hard-Coding**:
   - The regex line matchers in `afs_parser.py` expect South African English terminology. Multi-jurisdictional reporting (US GAAP / UK Companies Act) using different wording will require regex extensions.
2. **Text-Stream Dependency**:
   - Complex multi-column notes (such as detailed segment breakdowns where numbers wrap across line boundaries) can occasionally fail regex line pairing.
3. **Hard-coded Fallback Strings**:
   - In `historical_readiness.py`, certain diagnostic notes contain hard-coded references to Note 27.1 / Note 33.1 and TRU file names if metadata is sparse. These should be generalized into company-agnostic metadata attributes.
4. **Single Explicit Forecast Year**:
   - The current historical retail bridge defaults to a 1-year explicit forecast (`FY2026`) followed by perpetuity terminal value. While methodologically sound, multi-year forecast horizons (3–5 years) require extending the horizon generator.

---

## 19. Visual Pipeline Flowchart

```text
┌────────────────────────────────────────────────────────────────────────┐
│                   HISTORICAL SOURCE PACKAGE (ON DISK)                  │
│   manifest.json  +  <TICKER>_<PERIOD>_AFS.pdf  +  <TICKER>_SENS.txt    │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│             STAGE 1: SOURCE LOADING & MANIFEST VALIDATION              │
│       gui/modules/analysis/historical_packages.py                      │
│   • validate_period_folder()                                           │
│   • Enforce published_at >= period_end (Anti-lookahead gate)           │
│   • SHA-256 digest computation per document                            │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                 STAGE 2: PDF & SENS TEXT EXTRACTION                    │
│       pypdf.PdfReader  /  read_document_text()                         │
│   • Page-by-page text stream extraction with 1-indexed page tagging   │
│   • Transient text memory buffers (Zero OCR / No geometric tables)     │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│               STAGE 3: DETERMINISTIC FINANCIAL PARSING                 │
│       gui/modules/analysis/afs_parser.py  &  sens_parser.py            │
│   • Regex statement detection (Balance Sheet, Income, Cash Flow)       │
│   • _line_pair(): Current period vs comparative prior period           │
│   • _decimal(): Negatives in brackets, unit scaling (Rm, cents, shares)│
└────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│             STAGE 4: RECONCILIATION & TYPED METRIC EMISSION            │
│       gui/modules/analysis/results_package.py                          │
│   • reconcile_observations(): AFS exact values override SENS rounded   │
│   • SENS corporate action shares preferred for announcement date       │
│   • Emission of typed FinancialMetric models                           │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│           STAGE 5: HISTORICAL BACKTEST EVIDENCE SNAPSHOTTING           │
│       gui/modules/analysis/historical_backtest.py                      │
│   • resolve_evidence_as_of(): Exclusion of sources where pub > cutoff  │
│   • Assembling immutable evidence_snapshot in HistoricalBacktest       │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│               STAGE 6: HISTORICAL BASELINE READINESS GATE              │
│       gui/modules/analysis/historical_readiness.py                     │
│   • evaluate_historical_baseline(): 11 Core Gating Concepts            │
│   • Scale, sign, and unit assertions                                   │
│   • Segregation of Cash Capex vs Additions & Leases vs Net Cash        │
│   • Status: READY or BLOCKED                                           │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│            STAGE 7: RETAIL FORECAST BRIDGE & ASSUMPTION APPROVAL       │
│       gui/modules/analysis/historical_retail_bridge.py                 │
│       gui/modules/analysis/historical_plan.py                          │
│   • derive_historical_retail_forecasts(): Baseline x Approved Growth   │
│   • Human Analyst Review: approve_historical_plan_in_place()           │
│   • All assumptions moved from PROPOSED to ACCEPTED                    │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│               STAGE 8: DETERMINISTIC DCF ENGINE EXECUTION              │
│       gui/modules/analysis/historical_dcf_execution.py                 │
│   • validate_historical_execution_prerequisites()                      │
│   • calculate_dcf(): FCFF, WACC, TV, PV explicit                       │
│   • reconcile_equity(): Operating Value + Net Cash - Leases = Equity   │
│   • Historical Fair Value / Target Share Price                         │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│          STAGE 9: CRYPTOGRAPHIC LOCK & DATABASE PERSISTENCE            │
│       gui/core/db/migrations/add_historical_backtests.sql              │
│   • canonical_hash(): Frozen input_hash computed                       │
│   • INSERT INTO historical_backtests (status='locked')                 │
│   • INSERT INTO historical_backtest_plans (immutable snapshot)         │
│   • INSERT INTO historical_backtest_results (immutable valuation)      │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│            STAGE 10: FUTURE ACTUALS REVEAL (APPEND-ONLY)               │
│       gui/core/db/migrations/add_historical_outcome_revisions.sql     │
│   • compare_forecast_actuals(): Realized vs Forecast variance          │
│   • INSERT INTO historical_backtest_outcomes (Revision N+1)            │
│   • locked historical valuation result remains permanently unchanged   │
└────────────────────────────────────────────────────────────────────────┘
```
