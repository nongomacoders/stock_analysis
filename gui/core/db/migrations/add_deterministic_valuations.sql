-- Phase 4: separate append-only deterministic valuations. Never updates legacy report text/target.
CREATE TABLE IF NOT EXISTS deterministic_valuations (
    valuation_id uuid PRIMARY KEY,
    ticker text NOT NULL,
    report_version_id uuid NOT NULL REFERENCES deepresearch_versions(report_id),
    valuation_engine_version text NOT NULL,
    generated_at timestamptz NOT NULL,
    valuation_date date NOT NULL,
    status text NOT NULL CHECK (status IN ('PASS','PASS_WITH_WARNINGS','FAIL','NOT_CALCULABLE')),
    input_ids uuid[] NOT NULL DEFAULT '{}',
    calculation_inputs jsonb NOT NULL DEFAULT '{}'::jsonb,
    preflight jsonb,
    result jsonb NOT NULL,
    published_at timestamptz
);
ALTER TABLE deterministic_valuations ADD COLUMN IF NOT EXISTS published_at timestamptz;
CREATE INDEX IF NOT EXISTS deterministic_valuations_report_idx
    ON deterministic_valuations (report_version_id, generated_at DESC);
CREATE INDEX IF NOT EXISTS deterministic_valuations_ticker_idx
    ON deterministic_valuations (ticker, generated_at DESC);
