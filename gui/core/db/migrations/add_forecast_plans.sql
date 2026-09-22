-- Phase 5: immutable plan snapshots and explicit valuation publication.
CREATE TABLE IF NOT EXISTS forecast_plans (
    forecast_plan_id uuid PRIMARY KEY,
    ticker text NOT NULL,
    plan_version integer NOT NULL CHECK (plan_version > 0),
    previous_plan_id uuid REFERENCES forecast_plans(forecast_plan_id),
    source_report_version_id uuid NOT NULL REFERENCES deepresearch_versions(report_id),
    valuation_engine_version text NOT NULL,
    status text NOT NULL CHECK (status IN ('draft','review_required','approved','superseded')),
    approval_status text NOT NULL,
    created_by text NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    approved_by text,
    approved_at timestamptz,
    plan jsonb NOT NULL,
    UNIQUE (ticker, plan_version)
);
CREATE INDEX IF NOT EXISTS forecast_plans_ticker_idx ON forecast_plans(ticker, plan_version DESC);
ALTER TABLE deterministic_valuations ADD COLUMN IF NOT EXISTS forecast_plan_id uuid REFERENCES forecast_plans(forecast_plan_id);
ALTER TABLE deterministic_valuations ADD COLUMN IF NOT EXISTS publication_state text NOT NULL DEFAULT 'draft';
DO $$ BEGIN
    ALTER TABLE deterministic_valuations ADD CONSTRAINT deterministic_valuations_publication_state_check
        CHECK (publication_state IN ('draft','approved','published'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
CREATE INDEX IF NOT EXISTS deterministic_valuations_plan_idx ON deterministic_valuations(forecast_plan_id, generated_at DESC);
UPDATE deterministic_valuations SET publication_state='published' WHERE published_at IS NOT NULL AND forecast_plan_id IS NULL AND publication_state='draft';
ALTER TABLE deterministic_valuations ADD COLUMN IF NOT EXISTS valuation_approved_by text;
ALTER TABLE deterministic_valuations ADD COLUMN IF NOT EXISTS valuation_approved_at timestamptz;
ALTER TABLE deterministic_valuations ADD COLUMN IF NOT EXISTS published_by text;
