# Additive ingestion provenance rollout

`gui/scripts/main.py` starts the GUI and (by default) the separate market agent. The agent formerly used process-memory daily flags, a global price watermark, direct partial fundamental upserts, and SENS analysis before announcement insertion. The new path is **claim -> fetch -> archive -> parse -> validate -> immutable observation -> current projection -> downstream analysis**. Network and Gemini calls occur outside database transactions.

## Deployment order

1. Back up PostgreSQL. Record counts of `daily_stock_data`, `sens`, `raw_stock_valuations`, `commodity_prices`, `fx_rates`, and hashes of current `stock_analysis.deepresearch`.
2. Apply `core/db/migrations/add_ingestion_provenance.sql` before starting the updated agent. The migration is additive; it leaves all existing rows/tables in place. The code requires this migration to collect.
3. Run the rollback-only integration suite with `RUN_DB_INGESTION_TESTS=1`; then start one market-agent process and inspect `python gui/scripts/ingestion_status.py --failed-only`. Keep `AUTO_START_AGENT=0` on other GUI instances during initial rollout.
4. Compare legacy table counts and report hashes. New records should appear only after a collector actually runs. A rollback is code rollback plus stopping the new agent; the additive tables can remain unused.

## Storage roles and natural keys

- `ingestion_runs`: one row per source/job/entity/business date/attempt. A transaction advisory lock and unique key prevent duplicate claims. Success is recorded only after the worker returns after commit. Stale running leases become retryable after 45 minutes. Attempts retry after 15, 30, and 60 minutes, then become terminal failed. `ingestion_status.py` answers what failed.
- `source_documents`: immutable HTML/JSON body, SHA-256 hash, source URL, source/effective/fetch dates and parser version. Identity is source/entity/document type/hash. Identical fetched content **reuses** the first document; the new ingestion-run attempt still records the later fetch. No prior body is overwritten.
- `fundamental_observations`: immutable source-document/metric/reporting-period/parser-version observations with source cell text, normalized numeric value, unit, release date, observed timestamp, and period dates when derivable. `canonical_fundamental_observations` chooses valid observations for the **same ticker, metric and period**, preferring source priority, release date, later document sequence, then reparse sequence.
- `raw_stock_valuations`: compatibility projection from canonical observations. Raw pages commit first; observations and corrected supported fields then commit atomically. A parser failure retains HTML but rolls back numerical facts. `fundamental_revision_history` shows changed versus unchanged re-observations. Legacy rows without source documents remain readable but cannot gain raw provenance retroactively. The old parsed-only upsert is disabled.
- `price_observations`: immutable Yahoo row identity `(ticker, trade_date, source, content_hash)`. `daily_stock_data` remains the current OHLCV projection keyed by `(ticker, trade_date)`. A corrected provider row adds an observation and updates the projection. A compact JSON representation of each provider row is archived rather than the full pandas response.
- `market_observations`: immutable instrument/source/source-time-key/content-hash records with native currency, unit, URL, source and observed timestamps. Existing `commodity_prices` and `fx_rates` remain current-compatible projections. TradingEconomics sometimes omits a timestamp or time zone: the source display text and an unverified-timezone flag are retained; date-only keys are explicitly marked.
- `sens`: the existing `(ticker, publication timestamp, body hash)` uniqueness remains; new records link to archived Moneyweb source pages. `sens_analyses` is append-only with a foreign key to `sens`, model and prompt version. `action_log` remains a GUI-compatible derived-analysis projection. Source collection commits before Gemini is called.

## Price repair and known bounds

Yahoo is queried using each ticker's own last stored date. A daily 35-calendar-day rolling fetch compares provider-returned dates and OHLCV against stored rows, repairing only missing/changed dates. Provider dates serve as the trading calendar, so weekends and holidays absent from Yahoo are not classified as gaps. This cannot discover gaps older than the rolling window; a manual historical backfill tool or exchange calendar is a follow-up. The existing Yahoo-to-cents conversion is preserved.

## Reprocessing and compatibility

Register a new parser implementation/version in `ingestion_evidence.py`, then run `python gui/scripts/reparse_source_document.py DOCUMENT_UUID --parser-version VERSION` to inspect a dry run. `--apply` appends new observations and refreshes the compatibility projection in one transaction. Old observations and archived HTML remain intact. Old research reports are unchanged. New deep-research runs prefer source-linked canonical release dates where present and fall back to the legacy projection before migration or where observations are absent.

No existing historical row is claimed to have raw provenance if it predated this migration. The old ShareData month/year parser inherited the scrape day's day-of-month for period keys; new parsing uses month-end. When refreshing a legacy period, the compatibility row for that month is reused where safe. Review legacy period-date cleanup separately before a bulk historical backfill.
