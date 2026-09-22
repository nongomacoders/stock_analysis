-- Phase 2: append-only, typed candidate facts attached to each report version.
-- No valuation formulas or current-report projection change.
CREATE TABLE IF NOT EXISTS financial_metrics (
    metric_id uuid PRIMARY KEY,
    ticker text NOT NULL,
    report_id uuid NOT NULL REFERENCES deepresearch_versions(report_id),
    created_at timestamptz NOT NULL DEFAULT NOW(),
    metric jsonb NOT NULL,
    warnings jsonb NOT NULL DEFAULT '[]'::jsonb
);
CREATE INDEX IF NOT EXISTS financial_metrics_report_id_idx
    ON financial_metrics (report_id);
CREATE INDEX IF NOT EXISTS financial_metrics_ticker_report_idx
    ON financial_metrics (ticker, report_id);
