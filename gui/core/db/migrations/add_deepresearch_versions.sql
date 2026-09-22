-- Phase 1: additive report provenance. Apply once before using the new writer.
CREATE TABLE IF NOT EXISTS deepresearch_versions (
    report_id uuid PRIMARY KEY,
    ticker text NOT NULL,
    generated_at timestamptz NOT NULL,
    previous_report_id uuid REFERENCES deepresearch_versions(report_id),
    status text NOT NULL CHECK (status IN ('pending', 'published', 'rejected', 'failed', 'legacy', 'manual')),
    archive_path text,
    inputs jsonb NOT NULL DEFAULT '{}',
    response jsonb,
    report_content text,
    audit jsonb,
    completed_at timestamptz
);
CREATE INDEX IF NOT EXISTS deepresearch_versions_ticker_date
    ON deepresearch_versions (ticker, generated_at DESC);
ALTER TABLE stock_analysis ADD COLUMN IF NOT EXISTS current_report_id uuid
    REFERENCES deepresearch_versions(report_id);

-- Snapshot existing reports without pretending their original inputs are known.
-- The lock also makes repeated/concurrent migration execution safe.
LOCK TABLE stock_analysis IN SHARE ROW EXCLUSIVE MODE;
WITH legacy AS (
    SELECT gen_random_uuid() AS report_id, ticker, deepresearch, deepresearch_date
    FROM stock_analysis
    WHERE current_report_id IS NULL AND NULLIF(BTRIM(deepresearch), '') IS NOT NULL
), inserted AS (
    INSERT INTO deepresearch_versions
        (report_id, ticker, generated_at, status, inputs, report_content, completed_at)
    SELECT report_id, ticker, COALESCE(deepresearch_date::timestamptz, NOW()), 'legacy',
        jsonb_build_object('provenance', 'unavailable: legacy report',
                           'original_report_date', deepresearch_date,
                           'imported_at', NOW()), deepresearch, NOW()
    FROM legacy RETURNING report_id, ticker
)
UPDATE stock_analysis s SET current_report_id = i.report_id
FROM inserted i WHERE s.ticker = i.ticker;
