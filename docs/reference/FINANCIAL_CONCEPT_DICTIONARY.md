# JSE Financial Concept Dictionary & Alias Inventory (Phase 1)

---

## 1. Executive Summary

This document establishes the **Canonical Financial-Concept Dictionary** for the stock-analysis platform, grounded in empirical evidence mined from the historical JSE SENS corpus in PostgreSQL.

Phase 1 provides a 100% deterministic, audit-trailed, typed financial vocabulary baseline. It formalizes:
1. **Canonical Concept Inventory**: 61 standardized financial metrics across statement roles, valuation models, and per-share definitions.
2. **Real JSE SENS Vocabulary**: 847 distinct normalized candidate line-item labels observed across 16,253 textual occurrences in 5,281 SENS announcements spanning 229 distinct listed issuers.
3. **Strict Semantic Boundary Enforcement**: Absolute separation of non-equivalent financial concepts (e.g. trading profit $\neq$ operating profit, revenue $\neq$ retail sales, cash capex $\neq$ accounting additions, weighted-average shares $\neq$ point-in-time shares).
4. **Audit Provenance**: Full retention of raw label, normalized label, occurrence frequencies, distinct ticker counts, earliest/latest timestamps, sample tickers, and representative context snippets.
5. **Zero LLM / Zero Jev**: Built entirely using deterministic string normalization, typed Pydantic models, and empirical SQL extraction against PostgreSQL. Production parser logic and historical valuation records remain 100% untouched.

---

## 2. Empirical SENS Corpus Specification

The empirical corpus was inspected and mined directly from the PostgreSQL `sens` table:

| Dimension | Corpus Metric | Notes |
| :--- | :--- | :--- |
| **Table Name** | `sens` | Primary historical announcements repository |
| **Relevant Columns** | `sens_id`, `ticker`, `publication_datetime`, `content`, `source_document_id` | Read-only access |
| **Ticker Column** | `ticker` (`character varying`) | JSE share code (e.g. `TRU.JO`, `BID.JO`, `FSR.JO`) |
| **Publication Timestamp** | `publication_datetime` (`timestamptz`) | Physical release timestamp on JSE SENS |
| **Raw Content** | `content` (`text`) | Full unstructured/semi-structured announcement body |
| **Source Document ID** | `source_document_id` (`uuid`, nullable) | Foreign key to `source_documents.id` (81 linked) |
| **Total SENS Rows** | **5,281** | Complete database population analyzed |
| **Distinct Listed Tickers** | **229** | Broad coverage of JSE Main Board and AltX |
| **Earliest Announcement** | `2025-07-27 10:00:00+02:00` | 14-month continuous window |
| **Latest Announcement** | `2026-09-25 12:01:00+02:00` | Latest ingested feed |

---

## 3. Inventory of Existing Canonical Concepts & Aliases

The platform currently defines and recognizes financial concepts across `gui/modules/analysis/afs_parser.py`, `gui/modules/analysis/sens_parser.py`, `gui/modules/analysis/financial_metrics.py`, and `gui/modules/analysis/historical_readiness.py`.

### 3.1 Concept Categories & Inventory Breakdown

| Category | Canonical Concepts | Core Concepts Included |
| :--- | :---: | :--- |
| **Income Statement** | 18 | `accounting_revenue`, `sale_of_merchandise`, `turnover`, `gross_profit`, `cost_of_sales`, `trading_profit`, `operating_profit`, `ebit`, `ebitda`, `adjusted_ebitda`, `normalised_ebitda`, `profit_before_finance_costs_and_tax`, `profit_before_tax`, `profit_for_period`, `attributable_earnings`, `headline_earnings`, `operating_expenses` |
| **Margins** | 4 | `gross_margin`, `trading_margin`, `operating_margin`, `ebitda_margin` |
| **Depreciation & Amortisation** | 3 | `depreciation_and_amortisation`, `depreciation_amortisation_expense`, `depreciation_amortisation_cashflow_addback` |
| **Cash Flow & Working Capital** | 7 | `cash_generated_from_operations`, `operating_cash_flow`, `working_capital_movement`, `working_capital_cash_flow`, `investing_cash_flow`, `financing_cash_flow`, `free_cash_flow` |
| **Capex & Additions** | 5 | `cash_capex`, `total_capex`, `capex_expansion`, `capex_maintenance`, `intangible_additions` |
| **Balance Sheet & Net Debt** | 10 | `cash_and_cash_equivalents`, `money_market_funds`, `interest_bearing_borrowings`, `bank_overdraft`, `reported_net_cash`, `reported_net_debt`, `lease_liabilities`, `lease_liabilities_current`, `lease_liabilities_noncurrent`, `total_assets`, `total_liabilities`, `total_equity`, `inventory` |
| **Share Capital & Denominators** | 7 | `issued_shares_current`, `treasury_shares`, `external_shares_ex_treasury`, `period_end_external_shares`, `announcement_date_external_shares`, `weighted_average_basic_shares`, `weighted_average_diluted_shares` |
| **Per-Share Metrics** | 7 | `eps`, `diluted_eps`, `heps`, `diluted_heps`, `dividend_per_share`, `annual_dividend_per_share`, `final_dividend_per_share`, `interim_dividend_per_share`, `nav_per_share`, `tangible_nav_per_share` |
| **Taxation** | 3 | `tax_expense`, `effective_tax_rate`, `statutory_tax_rate` |
| **Total Canonical Concepts** | **61** | Standardized across the financial model |

---

## 4. Normalization Rules & Integrity Constraints

Normalization standardizes noisy formatting without stripping financially critical qualifiers:

```python
def normalize_label(text: str) -> str:
    # 1. Unicode NFKD decomposition
    # 2. Normalize non-breaking spaces, curly quotes, dashes to '-'
    # 3. Normalize '&' to 'and'
    # 4. Strip leading bullets, numbered lists ('1.1', '(a)', '•', '-')
    # 5. Strip trailing colons, semicolons, dashes, dots
    # 6. Lowercase and collapse repeated whitespace
```

### Critical Qualitative Modifiers Preserved
The normalizer explicitly **retains** all qualifiers that modify economic meaning:
`adjusted`, `normalised`, `underlying`, `continuing`, `before`, `after`, `cash`, `reported`, `trading`, `operating`, `basic`, `diluted`, `headline`, `annual`, `interim`, `final`, `gross`, `net`.

### Prohibited Equivalences Table
The dictionary enforces zero tolerance for conflating financially distinct concepts:

| Concept A | Concept B | Semantic Rationale for Strict Separation |
| :--- | :--- | :--- |
| `trading_profit` | `operating_profit` | Trading profit excludes corporate/non-trading overheads; operating profit includes them. |
| `revenue` | `retail_sales` | Retail sales includes concessions/VAT differences and excludes wholesale/finance revenue. |
| `sale_of_merchandise` | `revenue` | Revenue includes finance charges and fees; merchandise sales reflects goods sold only. |
| `cash_capex` | `total_capex` (additions) | Cash capex reflects cash outflows on cash flow statement; additions include unpaid capex/leases. |
| `weighted_average_basic_shares` | `issued_shares_current` | Point-in-time shares differ from time-weighted shares; conflating them invalidates DCF per-share values. |
| `reported_net_cash` | `cash_and_cash_equivalents` | Net cash is cash minus debt; cash and equivalents is gross balance-sheet liquidity. |
| `operating_profit` | `ebit` | Operating profit includes/excludes associate earnings or fair value items depending on IFRS policy. |
| `ebitda` | `adjusted_ebitda` | Adjusted EBITDA strips one-off restructuring and share-based payments. |
| `reported_net_debt` | `interest_bearing_borrowings` | Borrowings is gross financial debt; net debt subtracts cash balances. |
| `turnover` | `accounting_revenue` | Turnover may include excise duties or concession turnover not recognised as revenue. |
| `depreciation_amortisation_expense` | `depreciation_amortisation_cashflow_addback` | Income statement D&A reflects continuing ops expense; cash flow addback includes discontinued or leases. |

---

### 4.1 Semantic Qualifiers Schema & Enforced Validation Rules

To prevent loss of critical financial information during alias matching, `AliasObservation` and `CanonicalConcept` support typed `SemanticQualifiers`:

```python
class SemanticQualifiers(BaseModel):
    scope: OperationScope = OperationScope.UNSPECIFIED              # continuing_operations | total_operations | segment
    dilution: DilutionBasis = DilutionBasis.UNSPECIFIED            # basic | diluted
    tax_basis: DividendTaxBasis = DividendTaxBasis.UNSPECIFIED      # gross | net
    capex_basis: CapexBasis = CapexBasis.UNSPECIFIED                # cash_payments | accounting_additions
    lease_inclusion: LeaseInclusion = LeaseInclusion.UNSPECIFIED    # ex_leases | inc_leases
    attribution: ProfitAttribution = ProfitAttribution.UNSPECIFIED  # parent_equity_holders | total_group
    sign: NumericSign = NumericSign.UNSPECIFIED                    # positive | negative
    metric_basis: MetricBasis = MetricBasis.UNSPECIFIED            # reported_statutory | underlying_adjusted | normalised
    period_type: PeriodType = PeriodType.UNSPECIFIED                # full_year | interim | quarterly
    margin_denominator: MarginDenominator = MarginDenominator.UNSPECIFIED # merchandise_sales | accounting_revenue
    basis_evidence: BasisEvidence = BasisEvidence.UNSPECIFIED             # balance_sheet_presentation_separate | explicit_note_wording | reconciled_source_formula
    custom_notes: str | None = None
```

#### Enforced Validation Rules (Zero Silent Defaults)
1. **Gross/Net Dividend Basis Must Be Explicit**:
   If an alias maps to a dividend concept, its `tax_basis` must be explicitly declared as `gross` or `net`. Unspecified tax basis is rejected on approval/promotion.
2. **Continuing-Operations Scope Must Be Preserved**:
   Any label indicating "continuing operations" or "from continuing" must have `scope=OperationScope.CONTINUING_OPERATIONS`. It can never be silently merged into total operations.
3. **Capex Basis Cannot Default to Cash Capex**:
   Generic labels like "capital expenditure" or "total capex" are prohibited from defaulting to `cash_capex` or `capex_basis=CASH_PAYMENTS` without explicit cash statement evidence.
4. **Debt Lease Inclusion & Basis Provenance Promotion Rule**:
   - **`interest_bearing_borrowings`**: `BALANCE_SHEET_PRESENTATION_SEPARATE` must represent empirical evidence from the actual issuer document, **not** a theoretical assumption from general IFRS presentation requirements.
     - **Do NOT** automatically classify interest-bearing borrowings as `EX_LEASES` merely because it appears on the balance sheet.
     - Approve with `lease_inclusion = EX_LEASES` and `basis_evidence = BALANCE_SHEET_PRESENTATION_SEPARATE` **only** when the same source document explicitly presents lease liabilities separately from interest-bearing borrowings, or equivalent deterministic source evidence proves the separation.
     - Otherwise, the alias must remain in status `REQUIRES_CONTEXT` with `lease_inclusion = UNSPECIFIED` and `basis_evidence = UNSPECIFIED`.
   - **`reported_net_debt` / `reported_net_cash`**: Empirical analysis across 5,281 SENS announcements shows that JSE issuers diverge sharply (e.g. Remgro, AECI, Tiger Brands, Premier, CMH explicitly include lease liabilities in Net Debt, whereas Sasol, Netcare, Gold Fields exclude lease liabilities). Therefore:
     - Unqualified/naked labels like `"Net debt"` or `"Reported net debt"` in SENS **cannot** be approved as `EX_LEASES`; they remain in `REQUIRES_CONTEXT` with `lease_inclusion = UNSPECIFIED`.
     - Only labels with **explicit note wording** (e.g. `"Net debt (excluding lease liabilities)"`) are admitted as `APPROVED` with `EX_LEASES` (`basis_evidence = EXPLICIT_NOTE_WORDING`).
     - Or when verified by a **deterministic footnote reconciliation** (e.g. Truworths Note 49 reconciling R720m net cash strictly excluding lease liabilities: `Cash (R1,514m) - Borrowings (R780m) - Charitable Trust (R14m) = R720m`, with `basis_evidence = RECONCILED_SOURCE_FORMULA`).
   - Attempting to approve a debt alias with `lease_inclusion = UNSPECIFIED` or without explicit `basis_evidence` fails closed with a validation error.
5. **Margin Denominator Cannot Be Inferred**:
   Approved margin concepts must explicitly declare their denominator (e.g. `trading_margin` $\to$ `merchandise_sales`). Denominators are never silently assumed. If the denominator is unspecified, the alias remains `REQUIRES_CONTEXT`.

---

## 5. Vocabulary Discovered & Corpus Coverage

### 5.1 Corpus Classification Breakdown

Across the 5,281 SENS announcements:
- **847 distinct normalized candidate labels** were extracted.
- **16,253 total financial label occurrences** were observed.

| Classification | Unique Labels | % of Unique | Total Occurrences | % of Occurrences | Status |
| :--- | ---: | ---:| ---:| ---:| :--- |
| `EXACT_EXISTING_ALIAS` | 24 | 2.83% | 4,865 | 29.93% | `APPROVED` |
| `NORMALIZED_EXISTING_ALIAS` | 24 | 2.83% | 2,858 | 17.58% | `APPROVED` |
| `POTENTIAL_ALIAS` (Candidate) | 585 | 69.07% | 1,658 | 10.20% | `CANDIDATE` |
| `AMBIGUOUS` | 164 | 19.36% | 6,307 | 38.81% | `AMBIGUOUS` |
| `UNKNOWN` | 50 | 5.90% | 565 | 3.48% | `UNKNOWN` |
| **Total** | **847** | **100.00%** | **16,253** | **100.00%** | |

### 5.2 Coverage Statistics

- **Baseline Approved Coverage** (Exact + Harmless Normalization):
  - **48 unique labels** (5.67% of discovered vocabulary)
  - **7,723 occurrences** (**47.52%** of all financial label occurrences in SENS!)
- **Potential Coverage with High-Confidence Candidates**:
  - **633 unique labels** (74.73% of vocabulary)
  - **9,381 occurrences** (**57.72%** of all occurrences)
- **Deliberately Ambiguous (Fails Closed)**:
  - **164 unique labels** (19.36%) accounting for **6,307 occurrences** (**38.81%**).
  - Standalone words such as `sales` (1,781 occurrences), `heps` (672), `eps` (621), `operating profit` (349), `shares in issue` (322), `capital expenditure` (307), `taxation` (296), and `working capital` (237) cannot safely be approved without knowing whether they appear in an income statement, headline summary, note disclosure, or cash flow table.

---

## 6. Investigation of Valuation-Critical Concepts

### 6.1 Revenue & Top-Line Vocabulary
- **Empirical Findings**:
  - `revenue` occurs 2,060 times across 192 distinct issuers.
  - `sales` occurs 1,781 times across 122 issuers (ambiguous between accounting revenue, retail merchandise sales, or volume).
  - `turnover` occurs 151 times across 23 issuers (distinct JSE legacy term).
  - `retail sales` occurs 62 times across 10 specialized retail issuers (TRU, MRP, WHL, PIK, SHP).
  - `sale of merchandise` occurs in clothing/merchandise retailers.
  - Common narrative variants: `revenue increased by` (142), `revenue from continuing operations` (21), `group revenue` (102), `revenue grew by` (30), `revenue declined by` (21).
- **Rule**: `revenue`, `turnover`, `sale of merchandise`, and `retail sales` remain separate concepts.

### 6.2 Operating Earnings (Trading Profit vs Operating Profit vs EBITDA)
- **Empirical Findings**:
  - `ebitda` occurs 659 times across 79 issuers.
  - `adjusted ebitda` occurs 231 times across 27 issuers.
  - `operating profit` occurs 390 times across 87 issuers.
  - `trading profit` occurs in pure retailers (e.g. TRU, BID, MRP).
  - `underlying ebitda` occurs 41 times; `normalised ebitda` occurs 82 times.
  - `operating loss` occurs 45 times across 20 issuers.
- **Rule**: `trading_profit` $\neq$ `operating_profit` $\neq$ `ebit`. EBITDA variants (`adjusted_ebitda`, `normalised_ebitda`) are preserved as separate canonical concepts.

### 6.3 Capex (Cash Capex vs Total Capex Additions)
- **Empirical Findings**:
  - Standalone `capital expenditure` occurs 262 times across 72 tickers.
  - `capex` occurs 95 times across 24 tickers.
  - Disclosed components: `purchases of property, plant and equipment` (cash flow), `acquisition of plant and equipment to expand operations` (expansion), `acquisition of computer software` (intangibles), `additions to ppe` (balance sheet additions).
- **Rule**: Standalone `capital expenditure` is classified as `AMBIGUOUS`. DCF modeling requires explicit `cash_capex` (cash flow basis).

### 6.4 Working Capital
- **Empirical Findings**:
  - `working capital` occurs 242 times across 80 tickers (ambiguous).
  - `working capital movements` occurs 48 times across 22 tickers.
  - Directional phrasing: `change in working capital`, `increase in working capital`, `decrease in working capital`.
- **Rule**: Sign convention must remain explicit (`working_capital_cash_flow`: positive = cash inflow).

### 6.5 Net Cash & Borrowings
- **Empirical Findings**:
  - `net debt` occurs 307 times across 70 tickers.
  - `net cash` occurs 203 times across 62 tickers.
  - `cash and cash equivalents` occurs 80 times across 36 tickers.
  - `borrowings` occurs 77 times across 27 tickers; `interest-bearing debt` occurs 26 times across 15 tickers.
  - `lease liabilities` occurs 34 times.
- **Rule**: `reported_net_cash` is never equated with `cash_and_cash_equivalents`. Lease liabilities remain separate from financial net cash.

### 6.6 Shares & Per-Share Denominators
- **Empirical Findings**:
  - `heps` / `headline earnings per share` occurs over 1,270 times.
  - `eps` / `earnings per share` occurs over 1,170 times.
  - `ordinary shares in issue` occurs 459 times across 97 tickers.
  - `treasury shares` occurs 449 times across 103 tickers.
  - `shares in issue` occurs 408 times across 125 tickers (ambiguous between gross issued and external).
  - `weighted average number of shares` occurs in note disclosures.
- **Rule**: Valuation shares must use external point-in-time shares (`issued_shares_current` less `treasury_shares`), never `weighted_average_basic_shares`.

---

## 7. Ranked Candidate Review List (Top 25)

These high-frequency candidate aliases represent observed JSE reporting terminology suitable for manual review and subsequent promotion to approved status:

| Candidate Label | Occurrences | Distinct Tickers | Suggested Canonical Concept | Phase 1 Status |
| :--- | ---: | ---: | :--- | :--- |
| `revenue increased by` | 142 | 47 | `accounting_revenue` | `CANDIDATE` |
| `loss per share` | 85 | 35 | `eps` | `CANDIDATE` |
| `headline loss per share` | 69 | 31 | `heps` | `CANDIDATE` |
| `operating loss` | 45 | 20 | `operating_profit` | `CANDIDATE` |
| `profit for the year` | 44 | 30 | `profit_for_period` | `CANDIDATE` |
| `underlying ebitda` | 41 | 8 | `adjusted_ebitda` | `CANDIDATE` |
| `basic loss per share` | 34 | 15 | `eps` | `CANDIDATE` |
| `revenue grew by` | 30 | 8 | `accounting_revenue` | `CANDIDATE` |
| `interest-bearing debt` | 26 | 15 | `interest_bearing_borrowings` | `CANDIDATE` |
| `earnings per share increased by` | 23 | 19 | `eps` | `CANDIDATE` |
| `headline earnings per share increased by` | 23 | 18 | `heps` | `CANDIDATE` |
| `revenue from continuing operations` | 21 | 14 | `accounting_revenue` | `CANDIDATE` |
| `revenue declined by` | 21 | 10 | `accounting_revenue` | `CANDIDATE` |
| `revenue decreased by` | 20 | 15 | `accounting_revenue` | `CANDIDATE` |
| `group revenue increased by` | 20 | 13 | `accounting_revenue` | `CANDIDATE` |
| `heps increased by` | 18 | 9 | `heps` | `CANDIDATE` |
| `headline earnings increased by` | 18 | 8 | `headline_earnings` | `CANDIDATE` |
| `ebitda increased by` | 18 | 7 | `ebitda` | `CANDIDATE` |
| `headline earnings for the period` | 14 | 6 | `headline_earnings` | `CANDIDATE` |
| `adjusted ebitda increased by` | 13 | 5 | `adjusted_ebitda` | `CANDIDATE` |
| `heps from continuing operations` | 11 | 7 | `heps` | `CANDIDATE` |
| `revenue rose by` | 11 | 5 | `accounting_revenue` | `CANDIDATE` |
| `attributable earnings` | 11 | 4 | `attributable_earnings` | `CANDIDATE` |
| `net asset value per share increased by` | 10 | 9 | `nav_per_share` | `CANDIDATE` |
| `turnover increased by` | 9 | 6 | `turnover` | `CANDIDATE` |

---

## 8. Highest-Risk Ambiguous Labels (Top 25)

These terms are intentionally marked `AMBIGUOUS` and **must never be auto-resolved** without statement-type or contextual confirmation:

| Ambiguous Label | Occurrences | Tickers | Risk & Disambiguation Required |
| :--- | ---: | ---: | :--- |
| `sales` | 1,781 | 122 | Could denote accounting revenue, retail merchandise sales, or physical volume. |
| `heps` | 672 | 103 | Standalone abbreviation; could be basic HEPS, diluted HEPS, or headline earnings. |
| `eps` | 621 | 105 | Standalone abbreviation; could be basic EPS, diluted EPS, or attributable earnings. |
| `operating profit` | 349 | 80 | Conflated across issuers: some mean trading profit, others EBIT, others statutory PBIT. |
| `shares in issue` | 322 | 94 | Unclear whether gross issued shares or external shares net of treasury. |
| `capital expenditure` | 307 | 72 | Ambiguous between cash payments (cash capex) and balance-sheet additions. |
| `taxation` | 296 | 91 | Ambiguous between income statement tax expense, tax paid (cash flow), or deferred tax. |
| `working capital` | 237 | 80 | Ambiguous between balance-sheet net working capital and cash-flow movement. |
| `pbt` | 206 | 2 | Abbreviation for profit before tax; requires statement confirmation. |
| `basic earnings per share` | 166 | 77 | Often lacks currency or cents unit specification in raw title. |
| `turnover` | 151 | 23 | Distinct from statutory IFRS revenue in companies with excise/concession models. |
| `profit after tax` | 106 | 43 | May refer to total profit, profit from continuing operations, or attributable profit. |
| `capex` | 95 | 24 | Shorthand; requires cash flow vs balance sheet statement context. |
| `depreciation` | 94 | 37 | Unclear if tangible depreciation only or combined with intangible amortisation. |
| `number of shares in issue` | 87 | 60 | Unspecified share class or treasury deduction status. |
| `borrowings` | 77 | 27 | Ambiguous between current, non-current, gross, or net debt. |
| `amortisation` | 75 | 32 | Intangible amortisation only or combined D&A. |
| `diluted earnings per share` | 56 | 24 | Basic diluted vs headline diluted requires qualifying context. |
| `nav per share` | 54 | 16 | Ambiguous between headline NAV and Tangible NAV (TNAV). |
| `sales increased by` | 50 | 15 | Sales metric not qualified by accounting vs retail definition. |
| `profit from operations` | 50 | 5 | May exclude non-operating investment gains or associate profits. |
| `weighted average number of shares` | 39 | 18 | Unclear whether basic or diluted weighted average without table header. |
| `operating profit increased by` | 33 | 19 | Unclear if trading profit or statutory operating profit. |
| `net cash position` | 32 | 16 | May include or exclude restricted cash, client funds, or money market. |
| `effective tax rate` | 25 | 14 | Group effective vs continuing operations effective tax rate. |

---

## 9. Machine-Readable Export Specification

The complete machine-readable dataset is persisted at:

`gui/modules/analysis/data/financial_concept_aliases.json`

The JSON payload contains:
1. `metadata`: Corpus statistics, date bounds, timestamp, and coverage metrics.
2. `canonical_concepts`: Dictionary of all 61 concepts, descriptions, allowed sections, approved aliases, ambiguous aliases, and prohibited equivalences.
3. `aliases`: Array of all 847 observed labels with `raw_label`, `normalized_label`, `canonical_concept`, `status`, `classification`, `occurrence_count`, `ticker_count`, `first_seen`, `last_seen`, `sample_tickers`, `sample_sources`, and `sample_contexts`.

---

## 10. Audit & Reference System Invariants

### 10.1 Production Parser Invariant
Neither `gui/modules/analysis/afs_parser.py` nor `gui/modules/analysis/sens_parser.py` was altered. Production parsing continues to operate via established deterministic rules.

### 10.2 TRU Canonical Backtest Invariant
The canonical Truworths (TRU FY2025 $\to$ FY2026) backtest remains 100% immutable:
- **Historical Backtest ID**: `4230b66f-6be8-480a-878d-77d69eaeacd8`
- **Historical Result ID**: `6768e249-36c9-4f4d-afff-e3bd832e5f6a`
- **Historical Plan ID**: `ba6d3186-8a51-44a3-8f67-3ad34ece3da6`
- **Historical Fair Value**: `R72.8232/share`
- **Enterprise Value**: `R30,356,971,061.15`
- **Equity Value**: `R27,334,971,061.15`
- **Frozen Input Hash**: `ccf6a05b91b47ec458186ad1e73f9a78496d64f34c96f2e99dfbba7c8872f959`
- **Authoritative Outcome Revision**: `Revision 3 (completed)`
