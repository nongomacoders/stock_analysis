# Active Workstream: Sector Profiles & Semantic Extraction Architecture

---

## 1. Overview & Purpose
This workstream governs the development of sector-specific financial extraction adapters while preserving a single, unified AFS pipeline core. It establishes multi-sector semantic intake (starting with Retail and Mining) and validates candidate adjudication before changing the production semantic classification engine.

---

## 2. Invariants & Guardrails
- **Common AFS Core**: The physical document extraction, text chunking, deterministic numeric candidate harvesting, and reconciliation pipeline remain 100% shared across all companies.
- **Classification Hierarchy**: Company and valuation classification sits strictly *above* sector profiles. Sector profiles provide semantic vocabularies, candidate boosts, and mandatory category checklists; they do not fork the core pipeline.
- **Python Numeric Ownership**: Python strictly owns all numeric extraction, regex candidate harvesting, arithmetic derivations, and unit/currency normalizations. The LLM is strictly prohibited from inventing, recalculating, or rounding numbers.
- **Kev Baseline Retained**: Kev-0.8B integration is retained and operational (`AFS_SEMANTIC_ENGINE = "kev"`). The production default has **not** been switched.
- **Benchmark Data Isolation**: Benchmark populations `BATCH-002` and `BATCH-003` are strictly untouched and out of scope for this workstream.
- **Valuation / Plan Isolation**: `ForecastPlan` construction and valuation execution are strictly **not started**.

---

## 3. Current Architecture & Preferred Engine
- **Primary Experimental Engine**: **Gemini 3.8 Flash Mode A** (Candidate Adjudication, `t=0.0`) is the preferred experimental semantic classification path.
- **Mode B Status**: Mode B (Paragraph Fact Extraction) is secondary/discovery-only and cannot overwrite Mode A verified facts.
- **Skeptical Challenge**: Whole-document skeptical challenge runs on `gemini-3.8-flash` (`t=0.2`) across all pages to uncover covenants, off-balance-sheet items, and management caveats.

---

## 4. Regression Fixtures & Current Validation State

### A. Retail Reference Fixture: Truworths International (`TRU_FY2025_AFS.pdf`)
- **Status**: **PASSED (18 / 18 reference facts CORRECT)** — re-validated under TRU-FY2025-MODEA-V2 with shared-logic changes (gate holds, no STOP).
- **Key Resolution**: Effective tax rate (25.4%, Note 29.2, p.92) is guaranteed routing via mandatory category boosts and verified with 100% precision.
- **Review Burden**: 0 unresolved mandatory categories; auto queue 7, conflicting evidence 6 (v1: 0/65).
- **Audit Artifact (frozen v1, preserved)**: [`gui/results_history/TRU/FY2025/afs_experiments/gemini_38_mode_a_audit.json`](file:///C:/Users/Dion/Desktop/Projects/stock_analysis/gui/results_history/TRU/FY2025/afs_experiments/gemini_38_mode_a_audit.json).
- **Regression TRU-FY2025-MODEA-V2 (2026-09-28)**: same staged harness (216 selected → 6 slices; +20-call micro-slice for note-guard remediation). Recon 108 verified / 7 review / 6 conflicting / 94 rejected (v1: 58/0/65/88). Remaining 6: trading-profit segment pairs p.150 (4) + net-cash row pair p.21 (2) — genuine same-identity disagreements. Working-capital miss (17/18 pre-patch) root-caused to note-as-level mis-parse (`33.2` as current), fixed generically, re-adjudicated (2 calls), re-scored 18/18. Cost: 236 calls, 782,469 tokens, $0.071032; challenge 5 chunks, 25 findings, 0 failed. Artifact: `gui/results_history/TRU/FY2025/afs_experiments/gemini_38_mode_a_audit_v2.json` (SHA-256 `5d0940f0…4cc22893`).
- **Regression TRU-FY2025-MODEA-V3 (2026-09-28, clean full run on current code, zero post-hoc repair)**: artifact `gui/results_history/TRU/FY2025/afs_experiments/gemini_38_mode_a_audit_v3.json` (SHA-256 `1ec396fa…431efc26`). **18/18 CORRECT** (working capital 166 via fixed 2-col package `p21_0_s9_c0_curr` note 33.2; tax 25.4% via p.92 table package). Recon 102/8/6/99 (6: trading-profit p.150 segments ×4 + inventories p.51 ×2, all genuine). 0 unresolved mandatory. Cost: 212 calls, 696,407 tokens, $0.063352; challenge 5 chunks, 23 findings, 0 failed. Gate holds with no repair — STOP condition not triggered.

### B. Mining Reference Fixture: Pan African Resources (`PAN_HY2026.pdf`)
- **Status**: **PAN-HY2026-MODEA-V3 COMPLETE — clean post-fix run, 0 missed facts, protocol frozen as GEMINI-AFS-SEMANTIC-001 (switch NOT executed)**.
- **V3 run (2026-09-28, full clean pipeline on current code, v1/v2 preserved)**: artifact `gui/results_history/PAN/HY2026/afs_experiments/gemini_38_mode_a_audit_v3.json` (SHA-256 `17f6d59b…d05b5d`); 267 Mode A calls, staged harness `scratch/run_modea_v2_staged.py` (v3_work).
  - **Scoring (19 facts, equation holds)**: **12 CORRECT / 3 INCORRECT / 0 MISSED / 4 AMBIGUOUS (63.2%)**. Tax 29.6% CORRECT (verify guard + %-level fix validated live); guidance AMBIGUOUS (in review by design, scorer fallback); revenue/net-debt/WANOS AMBIGUOUS (scale pairs in review); grade/recovery/throughput INCORRECT (adjudication quality: wrong column, comparative matched, monthly value).
  - **Failure-case rechecks**: tax 29.6% ✓ verified; guidance evidence in review (not a level) ✓; capex 54.2 vs 55.3M still GENUINE (not forced) ✓; leases 1,050 vs 616 still GENUINE restatement pair ✓; cash-cost scopes separated (1,574 group verified, 200.4 operation separate) ✓; comparative restatements split by temporal/role ✓.
  - **Reconciliation**: 111 verified / 63 review / **4 conflicting** / 94 rejected; unresolved cash/guidance/hedging (tax resolved vs v2).
  - **Challenge**: 11 findings, **rediscovery 8/8** (all distinct, incl. Evander arbitration p.32 and Tennant high-cost p.41 missed by v2).
  - **Cost**: Mode A $0.13148 (1,558,762 tokens), challenge 2 chunks / 12,709 tokens / 0 failed.
- **Metrics Extracted**: Gold produced (128,296 oz), gold sold (127,296 oz), realised gold price (US$3,812/oz), AISC (US$1,874/oz), cash costs (US$1,574/oz), revenue (US$487.1m), attributable profit (US$148.0m), net debt (US$46.2m), WANOS shares (2,027.3m), production guidance (275,000–292,000 oz), effective tax (29.6%).
- **Resolved Root Cause (2026-09-28)**:
  - The Summary of Salient Features (Page 4) presents adjacent columns: `FY26H1` (actual level), `FY25H1` (comparative), and `Movement change %` (e.g. 51.5% production increase).
  - Python's two-column table matcher could not bind three-column rows, so they fell through to narrative parsing: change values (`51.5`) were tagged `STANDALONE` / `DIRECT_LEVEL`, and small comparatives (`58.0`, `48.2`, `46.2`, `9.6`) were eaten as note references.
  - Fix in `numeric_candidates.py`: `_try_parse_salient_three_column_row` tags columns as `CURRENT_PERIOD` / `COMPARATIVE_PERIOD` / `CHANGE_RATE` (`numeric_role="CHANGE_RATE"`, `value_pattern="change_rate_only"`, `temporal_role="CHANGE_RATE"`), with parenthesised negatives, dash-absent changes, split-decimal repair, and a note-vs-level guard preserving genuine two-column note rows. Mode A/B verifiers now reject `historical_actual` for change-only candidates (fail closed).
  - Deterministic re-run over Page 4 salient rows (45 prelim candidates, 15 change-tagged): **45 verified, 0 conflicting** (old-tagging control reproduced 45 conflicts).
- **Non-Salient Triage (2026-09-28, no Gemini, no engine switch, BATCH-002/003 untouched)**:
  - Reconstructed all 223 audit prelims from frozen prompts + parsed outputs; reproduced the audit exactly (**102/102 conflict findings identical**).
  - Root-cause breakdown of the 102 (exactly one category each):
    - `PERIOD_ROLE_ERROR`: **48** — comparative / change / guidance / target values admitted as current `historical_actual` levels (e.g. `gold_sold` 79,926 vs 127,296; `157.3%` vs 487,100,000; guidance 275,000/292,000 vs 128,296).
    - `CONCEPT_UNKNOWN_COLLISION`: **36** — `unknown + unknown` collided on empty identity across different line items and pages (pp.13/20/21/27/31, e.g. Cost of production vs Other income; Silver revenue vs Cash).
    - `SCOPE_ERROR`: **10** — coarse scopes hid operation/attribution splits (AISC 1,700 lower-cost ops vs 2,590 Barberton; group cash costs vs operation column; group profit vs NCI `(125)`).
    - `HARMLESS_NONCOMPARABLE`: **4** — assumption/spot quotes (`gold_price` 5,000/3,500/2,800, temporal `unknown`) and change-vs-change (`-79.8` vs `69.3`).
    - `UNIT_ERROR`: **3** — scale divergence (`2,027.3 million` vs `2,027.3`; `US$55.3m` normalisation).
    - `GENUINE_SAME_CONCEPT_CONFLICT`: **1** — `trade_and_other_receivables` 15,888 (p.12 statement) vs 3,176 (p.30 note).
  - Generic fixes in `reconciliation.py` (+ `detected_label` carried in Mode A/B/Kev qualifiers, no PAN/page/value branches):
    1. Unknown-concept pairs require matching non-empty raw labels, else never peers; same-label divergent unknowns → `REQUIRES_REVIEW`.
    2. Segment-scoped pairs with differing labels never conflict (operation granularity stays separate).
    3. `profit_attribution` / `attribution` must match (splits NCI vs group).
    4. Adjudicated `temporal_classification` must match (current never competes with comparative/change/guidance/target).
    5. Value-role class must match (`LEVEL` vs `CHANGE` via `value_pattern`).
    6. Explicitly stated units/currencies must match per axis (missing stays wildcard).
    7. Identical raw digits with different normalized values → `REQUIRES_REVIEW` (scale/unit divergence, e.g. `487.1` vs `487,100,000`), never a conflict.
    8. Intake fail-closed: `change_only` / `guidance` / `target` / `unknown` temporals → `REQUIRES_REVIEW`, never verified levels.
  - Deterministic re-run on frozen prelims: **102 → 13 conflicting** (verified 46 → 99, review 7 → 37, rejected 77 unchanged).
    - Of the 102: **60 ELIMINATED** (now verified), **29 REQUIRES_REVIEW**, **13 GENUINE** (still conflicting).
    - Of 18 salient-table (p.4) entries in the 102: 11 eliminated, 6 review, 1 genuine (`cash_costs` 1,574 group vs 200.4 operation column).
    - Remaining 13 genuine: `capex_expansion` 54.2 vs 55,300,000; `cash_costs` 1,574 vs 200.4; comparative restatement pairs (`leases` 1,050/616/1,491, 2,039/2,607; `trade` 15,386/15,496); statement-vs-note `trade` 15,888 vs 3,176. All are same-identity value disagreements — the intended use of `CONFLICTING_EVIDENCE`.
  - Known limitations (future work, not blockers): restated-comparative triples (p.12 three-value rows) vs positional 3-column parsing on fresh extraction; operation-level scope taxonomy; note-vs-statement precedence rules.
- **Audit Artifact (frozen v1, preserved)**: [`gui/results_history/PAN/HY2026/afs_experiments/gemini_38_mode_a_audit.json`](file:///C:/Users/Dion/Desktop/Projects/stock_analysis/gui/results_history/PAN/HY2026/afs_experiments/gemini_38_mode_a_audit.json).
- **Full Regression PAN-HY2026-MODEA-V2 (2026-09-28)**:
  - **Config verified**: experimental engine `gemini` / Mode A, requested `gemini-3.8-flash`, returned `gemini-3.8-flash`, Mode A `t=0.0`, challenge `t=0.2`, zero silent fallbacks (attempt-1 success traced; 500/429 retried with provenance), Python numeric extraction + validation authoritative, challenge strictly separate. Production default still `kev` (no switch). Commit `282b74e`, dirty tree recorded in artifact (pipeline + test files only, no benchmark/config changes).
  - **Source**: `gui/results_history/PAN/HY2026/PAN_HY2026.pdf`, SHA-256 `4c13ee4a…69b2d3` MATCHED v1 source before proceeding.
  - **Artifact (new, v1 preserved)**: `gui/results_history/PAN/HY2026/afs_experiments/gemini_38_mode_a_audit_v2.json` (artifact SHA-256 `c5079c9e…4662396`). Decision inputs: `pan_v2_decision_inputs.json`. Kill-safe staged runner: `scratch/run_modea_v2_staged.py` + `scratch/assemble_v2.py` (prep → 7×~40-call slices → assemble; 267 calls total).
  - **Scoring (19 facts, CORRECT/INCORRECT/MISSED/AMBIGUOUS, equation holds; values never injected)**: **11 / 3 / 2 / 3 (57.9%)** vs v1 4/17 (23.5%). CORRECT: gold produced/sold, realised price, AISC, cash costs, adjusted EBITDA, attributable earnings, headline earnings, operating cash flow, total/sustaining capex. AMBIGUOUS (evidence in review, scale pairs): revenue, net debt, WANOS shares. INCORRECT (adjudication quality): underground grade (wrong column 0.29), recovery (comparative 51.6 matched), throughput (monthly 1,060). MISSED: production guidance (275k/292k adjudicated as gold_produced/guidance-temporal → correctly routed to review, unscored by keyword), effective tax 29.6% (adjudicated correctly, REJECTED by strict change-guard overreach — root-caused, %-level fix landed post-run, tests 47 green).
  - **Reconciliation**: OLD 46 verified / 7 review / **102 conflicting** / 77 rejected → NEW **114 / 57 / 4 / 98**. Of the 102 audit identities: 67 fully resolved, 28 reclassified to review, 3 preserved genuine, 9 comparative/change identities not re-selected (selection composition changed with new table parsing; facts covered by current-period evidence), 2 re-observed at other pages. New conflicts introduced: 1 identity (leases 616 p.30, same G3 restatement family). Remaining 4: capex 54.2 vs 55.3M (GENUINE), leases 1,050 vs 616 comparative restatement (GENUINE). Zero false-accepts: no verified candidate carries a non-level temporal; 3 CHANGE_RATE-package verified are all comparative-adjudicated.
  - **13-group audit**: G1 capex GENUINE_CONFLICT; G3 leases-current GENUINE (restatement-basis difference, 1,050 vs 616); G2/G4/G5/G6 RESOLVED_BY_SEMANTIC_QUALIFIER (operation semantics, comparative splits, package-temporal splits — all verified with correct provenance).
  - **Challenge (unchanged pass, 2 chunks, 0 failed)**: 10 findings vs v1 11. Rediscovery 6/8 (breach p.25, MTR p.5, gold-loan p.4, G&A p.36, share-based p.9, ring-fencing p.39 all rediscovered; Evander arbitration + Tennant high-cost NOT rediscovered). Novel: tax surge p.9, grade degradation p.40, 8× capital repayments p.39.
  - **Mining coverage**: 17 RESOLVED (incl. sales, margins, sales_volumes, recovery — all unresolved in v1); tax REQUIRES_REVIEW (29.6% evidence rejected, fix landed); guidance REQUIRES_REVIEW (in review by design); cash REQUIRES_REVIEW (1,649 evidenced but unclassified); hedging NOT_DISCLOSED (2 incidental mentions only).
  - **Review burden**: auto queue 57, conflicting evidence 4, unresolved mandatory 4 (tax/cash/guidance/hedging), manual-required 70 (separate metrics, not combined).
  - **Cost/latency (recorded, no extrapolated arithmetic)**: Mode A 267 calls, 1,557,450 tokens (1,492,654 prompt + 64,796 output), $0.131387, returned `gemini-3.8-flash` throughout; challenge 2 chunks, 12,487 tokens, 0 failed; wall ~27.5 min (Mode A call-latency sum ~70 min @ concurrency 4; transient 500/429 retried).
  - **Post-assembly deterministic patches (no API, challenge/provenance preserved)**: near-duplicate tolerance rule (0.1% after unit-system rescaling; attributable 148.0 vs 147,967 → review; test 46).
  - **Code fixes landed during this run (all generic, tested)**: note-leader bail for integer/mashed note rows (TRU working-capital rescue; tests 48–49), %-level DIRECT_LEVEL rule (test 47). Known residual: from-to %-levels ("reduced to 39.1%") still change-tagged; restated-comparative triples vs positional 3-col parsing; operation-level scope taxonomy; scale-pair intake precedence.

---

## 5. Completed Subtasks
1. Implemented Gemini Mode A (Candidate Adjudication) and Mode B (Paragraph Fact Extraction) in `gemini_semantic_engine.py`.
2. Hardened Vertex AI routing to `gemini-3.8-flash` with zero silent fallbacks and trace provenance.
3. Eliminated top-N ranking truncation for mandatory categories (tax rate, leases, debt, capex).
4. Re-ran TRU FY2025: Achieved 18 / 18 correct facts gate.
5. Inspected Mode B unmapped tokens: Identified single-space table column concatenation in regex as root cause (not hallucination).
6. Added mining concepts (`gold_produced`, `gold_sold`, `aisc_unit_cost`, `gold_price`, `net_debt`, `guidance`, etc.) to canonical taxonomy.
7. Ran 45-page cross-sector pipeline and full skeptical challenge pass on `PAN_HY2026.pdf`.
8. Persisted durable, immutable audit artifacts with SHA-256 signatures for both runs.
9. Implemented salient three-column table parsing (`_try_parse_salient_three_column_row` + note-vs-level guard) with `CHANGE_RATE` tagging for Movement/change% columns.
10. Added Mode A/B fail-closed guards rejecting `historical_actual` for change-only candidates; added regression tests 31–34 (32/32 non-DB suite green).
11. Re-ran reconciliation deterministically on PAN HY2026 salient rows: 45 verified / 0 conflicting (old-tagging control: 45 conflicting).
12. Triaged all 102 non-salient audit conflicts by root cause (48 period-role, 36 unknown-collision, 10 scope, 4 noncomparable, 3 unit, 1 genuine); implemented 8 generic reconciliation identity gates + fail-closed review routing (tests 35–45, 54/54 suite green); deterministic re-run: 102 → 13 genuine conflicts (60 eliminated, 29 review).
13. Ran full PAN-HY2026-MODEA-V2 regression (267 calls, staged kill-safe harness): scoring 11/19 (v1: 4/17), recon 114/57/4/98 (v1: 46/7/102/77), challenge rediscovery 6/8, cost $0.1314. Applied deterministic near-duplicate patch (test 46).
14. Ran TRU-FY2025-MODEA-V2 regression: 18/18 gate holds after generic note-guard remediation of working-capital miss (tests 48–49); recon 108/7/6/94; cost $0.0710.
15. Landed %-level DIRECT_LEVEL rule for rate/margin/recovery percentages (test 47; validated live by PAN v3 tax 29.6% verify) and note-leader bail for integer/mashed rows (tests 48–49).
16. Ran clean post-fix regressions on current code with zero repair: PAN-HY2026-MODEA-V3 (12/3/0/4, recon 111/63/4/94, challenge 8/8, $0.1315) and TRU-FY2025-MODEA-V3 (18/18, recon 102/8/6/99, $0.0634). Suite 58/58 green. Frozen as GEMINI-AFS-SEMANTIC-001; BATCH-002 readiness: READY_FOR_BATCH_002.

---

## 6. Current Blockers & Next Subtasks

### Production-Readiness Decision Report (2026-09-28) — **READY_FOR_DEFAULT_SWITCH_REVIEW** (default NOT switched)

| Dimension | TRU FY2025 retail (v2) | PAN HY2026 mining (v2) |
|---|---|---|
| Reference accuracy | 18/18 (100%) | 11/19 (57.9%; v1: 4/17) |
| Mandatory coverage | 12/12 resolved | 17/21 resolved; tax/cash/guidance review, hedging not disclosed |
| False accepted facts | 0 (verified pool audited) | 0 (no non-level temporals verified; change packages all comparative-adjudicated) |
| Conflict burden | 6 genuine (v1: 65) | 4 genuine (v1: 102) |
| Manual review burden | 7 auto + 6 conflicts, 0 unresolved | 57 auto + 4 conflicts + 4 unresolved + 5 reference gaps = 70 |
| Challenge usefulness | 25 findings (no baseline required) | 6/8 rediscovery + 3 novel material findings |
| Cost | $0.0710, 236 calls, 782k tokens | $0.1314, 267 calls, 1.557M tokens |
| Runtime | ~26 min wall | ~27.5 min wall |

Reasons: retail gate holds under shared-logic changes; mining false conflicts eliminated (102→4, all genuine same-identity disagreements); every non-correct fact is itemized and fail-closed (review/rejected, never silently verified); full request/response provenance with pinned model versions; Kev baseline untouched. Conditions: switch decision stays human; hardening backlog tracked (p.40 adjudication quality, from-to %-levels, restated triples, operation taxonomy, scale-pair intake precedence, guidance/tax scoring).

### Frozen Semantic Protocol: GEMINI-AFS-SEMANTIC-001 (2026-09-28, validated by V3 runs; production default NOT switched)

- **Model**: `gemini-3.8-flash` (requested = returned on every call; zero silent fallbacks, attempt-level trace provenance).
- **Temperatures**: Mode A candidate adjudication `t=0.0`; whole-document skeptical challenge `t=0.2`.
- **Prompt version/hash**: `afs_gemini_mode_a_v1` / `34feecc5…1ab89ad` (unchanged since v1; prompts carry no reference values).
- **Canonical concept schema**: `CANONICAL_CONCEPTS_ALLOWED` incl. mining extension (`gold_produced`, `gold_sold`, `gold_price`, `aisc_unit_cost`, `cash_costs`, `net_debt`, `guidance`, …), schema SHA-256 `52db5b9e…941d62c2`.
- **Qualifier schema**: concept, scope, dilution, tax/capex/lease/margin bases, profit attribution, alias role, value pattern, temporal role, note reference, detected label.
- **Candidate evidence format**: `ContextEvidencePackage` (verbatim token + deterministic normalized value + unit/currency/scale + roles + label + note ref + page/paragraph/sentence provenance + surrounding paragraphs).
- **Python validation rules** (`verify_mode_a_response`, authoritative): verbatim token match; verbatim quote match; taxonomy membership; comparative-package → never `historical_actual`; change-only package (CHANGE_RATE temporal or CHANGE_AMOUNT role) → never `historical_actual`; strict enum validation; `should_abstain` honored.
- **Extraction roles** (Python-owned): 3-col salient CURRENT/COMPARATIVE/CHANGE_RATE; 2-col note binding with integer/mashed-row guards; %-level DIRECT_LEVEL for rate/margin/recovery nouns.
- **Reconciliation rules** (peer identity): concept + period + scope + package temporal + statement-level bucket + dilution + capex basis + adjudicated temporal + value-role class + per-axis unit/currency + attribution + raw-label identity (unknowns, segment scopes); identical-digits scale divergence and ≤0.1% near-duplicates → review, never conflict.
- **Abstention policy**: `should_abstain` or failed verification → REJECTED; non-level temporals (change/guidance/target/unknown) → REQUIRES_REVIEW, never verified levels.
- **Valuation-safety policy**: pipeline stops at reconciled candidates + checklist + challenge; no ForecastPlan construction, no valuation execution, no auto-publication.
- **Code state**: commit `282b74e` + recorded dirty tree (AFS pipeline, selector/vertex routing, tests only); prompt/schema bytes identical to v1 run.

### BATCH-002 Readiness Decision: READY_FOR_BATCH_002

Frozen above is exactly what BATCH-002 may exercise. BATCH-002 is allowed to: run read-only evaluation of GEMINI-AFS-SEMANTIC-001 adjudication against held-out benchmark rows using the frozen prompts/schema/validators (no code changes, no default switch, no ForecastPlans, BATCH-003 untouched). Any gate failure revokes the freeze. Known review-load (not gate failures): p.40 adjudication quality, from-to %-levels, restated triples, operation taxonomy, scale-pair intake precedence.

### BATCH-002 Validation Attempt (2026-09-28) — Decision: BLOCKED (no gold; zero predictions made)

- **Run identity**: `BATCH002-VALIDATION-ATTEMPT-001` (attempt record only; no evaluation run row written, no predictions persisted, no API calls spent).
- **Freeze re-verified pre-run**: prompt `afs_gemini_mode_a_v1` hash `34feecc5…1ab89ad` MATCH; schema hash `52db5b9e…941d62c2` MATCH; candidate `gemini-3.8-flash t=0.0`, challenge `t=0.2`; engine default `kev`; suite 58/58 green; no new tracked code modifications (pre-existing dirty set unchanged).
- **Batch roles confirmed**: BATCH-001 DEVELOPMENT (300 rows, GOLD-001 frozen, 281 evaluable), BATCH-002 VALIDATION, BATCH-003 HOLDOUT (aggregate role metadata only; BATCH-003 rows never inspected).
- **BATCH-002 snapshot**: `BENCH-0301`…`BENCH-0560`, exactly 260 rows, role VALIDATION — but **0/260 rows have any gold or review data** (`review_decision` all NULL, all 13 `gold_*` columns NULL; sole release in DB is GOLD-001). "Not yet gold" status from benchmark lineage confirmed live.
- **STOP rationale**: scoring the frozen release against deterministic seed fallbacks (seeds present on only 142/260, and seed full-label match on reviewed gold was 40.93%) would invert the truth hierarchy and anchor the future human GOLD-002 review — an evaluation-integrity compromise. No implementation defect found; the blocker is a missing precondition (reviewed gold).
- **Metrics**: none computable (no eligible scored rows; nothing predicted). Safety/error/materiality sections intentionally empty — not zero. Cost $0.00, 0 calls.
- **Unblocking condition**: complete human review of BATCH-002 via the restricted reviewer view → publish append-only GOLD-002 release (new release row + hashes; GOLD-001 untouched) → re-attempt validation against effective GOLD-002 labels. BATCH-002 must not be scored against seeds in the interim, nor reviewed with knowledge of any model outputs.

### Current Blocker
- **BATCH-002 has no reviewed gold** (see attempt above). Human review + GOLD-002 release required before validation can proceed. Production default unchanged; BATCH-003 untouched.

### Next Subtask
1. ~~Enhance `numeric_candidates.py` table column header analysis~~ — **DONE** (2026-09-28, tests 31–34 green).
2. ~~Re-run reconciliation on PAN HY2026 candidates~~ — **DONE deterministically** (45 verified / 0 conflicting on salient rows).
3. ~~Triage remaining non-salient audit collisions~~ — **DONE** (2026-09-28, deterministic; 102 → 13 genuine, 60 eliminated, 29 review; tests 35–45 green).
4. ~~Run full PAN Gemini 3.8 Flash Mode A regression~~ — **DONE** (V2 + clean V3 12/19 + TRU V3 18/18; decision READY_FOR_DEFAULT_SWITCH_REVIEW).
5. ~~Final clean post-fix regression + freeze~~ — **DONE** (GEMINI-AFS-SEMANTIC-001; suite 58/58).
6. ~~BATCH-002 validation~~ — **BLOCKED** (no gold; attempt recorded, zero predictions, $0 spent). Unblock via human review + GOLD-002.
7. Do not run BATCH-002 scoring, BATCH-003, or any production-default change unprompted.
