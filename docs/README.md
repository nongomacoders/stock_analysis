# Stock Analysis Documentation Architecture

Welcome to the Stock Analysis project documentation directory. This architecture is designed to minimize context and token consumption for AI agents while preserving complete engineering history, audit lineages, and benchmark data.

---

## Agent Startup Protocol

When starting a session or switching AI models, follow this minimal reading sequence:

1. **Read [`AGENTS.md`](file:///C:/Users/Dion/Desktop/Projects/stock_analysis/AGENTS.md)** (Repository root): Primary operational rules, path conventions, Python runtime, financial semantic boundaries, and safety policies.
2. **Read this file ([`docs/README.md`](file:///C:/Users/Dion/Desktop/Projects/stock_analysis/docs/README.md))**: Documentation catalog, category definitions, and directory structure.
3. **Read only the relevant active workstream document** under `docs/workstreams/<workstream>.md` (e.g., [`sector_profiles.md`](file:///C:/Users/Dion/Desktop/Projects/stock_analysis/docs/workstreams/sector_profiles.md)).
4. **Consult reference, benchmark, or archive documents only on demand** when directly required by the current task.

Do **NOT** load historical transcripts, handoff snapshots, benchmark tables, or historical runbooks into initial context.

---

## Documentation Categories

### 1. Active Workstreams (`docs/workstreams/`)
- **Purpose**: Living documents representing the *current* state of active engineering initiatives.
- **Content**: Current architecture, completed subtasks, active blockers, regression test fixtures, invariants, and next immediate subtasks.
- **Rules**: Not a conversational transcript or narrative log. Overwritten and updated as tasks progress.
- **Files**:
  - [`sector_profiles.md`](file:///C:/Users/Dion/Desktop/Projects/stock_analysis/docs/workstreams/sector_profiles.md): Multi-sector AFS intake (Retail & Mining), Gemini 3.8 Flash Mode A validation, and table reconciliation refinements.

### 2. Reference (`docs/reference/`)
- **Purpose**: Authoritative, stable domain and technical references.
- **Rules**: Consulted on demand when working on specific subsystem implementations or troubleshooting shell errors.
- **Files**:
  - [`TERMINAL_ERRORS.md`](file:///C:/Users/Dion/Desktop/Projects/stock_analysis/docs/reference/TERMINAL_ERRORS.md): Confirmed fixes for PowerShell, quoting, environment variables, and Python paths.
  - [`FINANCIAL_CONCEPT_DICTIONARY.md`](file:///C:/Users/Dion/Desktop/Projects/stock_analysis/docs/reference/FINANCIAL_CONCEPT_DICTIONARY.md): Canonical financial concept inventory (61 concepts, 847 SENS aliases) and semantic boundaries.
  - [`HISTORICAL_EXTRACTION_PIPELINE.md`](file:///C:/Users/Dion/Desktop/Projects/stock_analysis/docs/reference/HISTORICAL_EXTRACTION_PIPELINE.md): 9-stage deterministic historical extraction and valuation pipeline architecture.

### 3. Benchmarks (`docs/benchmarks/`)
- **Purpose**: Frozen ground-truth datasets, expert review batches, and classification evaluation lineages.
- **Rules**: Never modified during normal analysis workflows. Loaded only when executing benchmark evaluation scripts or scoring models.
- **Files**:
  - `docs/benchmarks/financial_classifier/`:
    - [`BENCHMARK_LINEAGE_AND_RELEASES.md`](file:///C:/Users/Dion/Desktop/Projects/stock_analysis/docs/benchmarks/financial_classifier/BENCHMARK_LINEAGE_AND_RELEASES.md): Authoritative population lineage (581 → 700 → 820), release identity hierarchy (`GOLD-001`), database review schema, freeze protocols, and Kev-0.8B provenance.
    - [`FINANCIAL_CLASSIFIER_BENCHMARK_REVIEW.md`](file:///C:/Users/Dion/Desktop/Projects/stock_analysis/docs/benchmarks/financial_classifier/FINANCIAL_CLASSIFIER_BENCHMARK_REVIEW.md): Stratified evaluation report across the initial 820-row sample.
    - [`FINANCIAL_CLASSIFIER_GOLD_REVIEW_001.md`](file:///C:/Users/Dion/Desktop/Projects/stock_analysis/docs/benchmarks/financial_classifier/FINANCIAL_CLASSIFIER_GOLD_REVIEW_001.md): Expert human review decisions and override rationales for BATCH-001 (rows 1–300).
  - `docs/benchmarks/retired/`:
    - [`FINANCIAL_CLASSIFIER_RETIRED_OCCURRENCES_001.json`](file:///C:/Users/Dion/Desktop/Projects/stock_analysis/docs/benchmarks/retired/FINANCIAL_CLASSIFIER_RETIRED_OCCURRENCES_001.json): Archived duplicate / collapsed candidate occurrences.

### 4. Archive (`docs/archive/`)
- **Purpose**: Historical milestone snapshots, superseded handoff notes, and retired operational runbooks.
- **Rules**: Kept strictly for auditability and historical provenance. Active agents should not read these unless investigating historical decisions.
- **Files**:
  - `docs/archive/handoffs/`: Historical milestone handoff notes (`PROJECT_OVERVIEW.txt`, `historical_tester_handoff.txt`, `HISTORICAL_BACKTEST_SUMMARY.txt`, `valuation_workflow_handoff.txt`, `TRU_FY2025_TESTING_GUIDE.md`).
  - `docs/archive/runbooks/`:
    - [`AGENT_RUNBOOK.md`](file:///C:/Users/Dion/Desktop/Projects/stock_analysis/docs/archive/runbooks/AGENT_RUNBOOK.md): Historical omnibus runbook (superseded by modular reference, workstream, and benchmark docs).
