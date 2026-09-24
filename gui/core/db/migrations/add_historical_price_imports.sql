-- Additive historical-price evidence. Existing compatibility prices are untouched.
CREATE TABLE IF NOT EXISTS historical_price_import_batches (
    batch_id uuid PRIMARY KEY, ticker text NOT NULL, provider text NOT NULL,
    provider_symbol text NOT NULL, requested_start date NOT NULL, requested_end date NOT NULL,
    retrieved_at timestamptz NOT NULL, library_version text, settings jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL CHECK (status IN ('previewed','completed','failed')),
    rows_fetched integer NOT NULL DEFAULT 0, rows_inserted integer NOT NULL DEFAULT 0,
    rows_reused integer NOT NULL DEFAULT 0, rows_conflicted integer NOT NULL DEFAULT 0,
    warnings jsonb NOT NULL DEFAULT '[]'::jsonb, error_message text,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS historical_price_batches_ticker_idx ON historical_price_import_batches(ticker,retrieved_at DESC);
ALTER TABLE price_observations ADD COLUMN IF NOT EXISTS provider_symbol text;
ALTER TABLE price_observations ADD COLUMN IF NOT EXISTS raw_close numeric;
ALTER TABLE price_observations ADD COLUMN IF NOT EXISTS adjusted_close numeric;
ALTER TABLE price_observations ADD COLUMN IF NOT EXISTS currency text;
ALTER TABLE price_observations ADD COLUMN IF NOT EXISTS price_unit text;
ALTER TABLE price_observations ADD COLUMN IF NOT EXISTS price_basis text;
ALTER TABLE price_observations ADD COLUMN IF NOT EXISTS retrieved_at timestamptz;
ALTER TABLE price_observations ADD COLUMN IF NOT EXISTS import_batch_id uuid REFERENCES historical_price_import_batches(batch_id);
ALTER TABLE price_observations ADD COLUMN IF NOT EXISTS provider_metadata jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE price_observations ADD COLUMN IF NOT EXISTS revision_of uuid REFERENCES price_observations(observation_id);
ALTER TABLE price_observations ADD COLUMN IF NOT EXISTS conflict_status text;
CREATE INDEX IF NOT EXISTS price_observations_provider_identity_idx ON price_observations(ticker,source,provider_symbol,trade_date,observed_at DESC);
