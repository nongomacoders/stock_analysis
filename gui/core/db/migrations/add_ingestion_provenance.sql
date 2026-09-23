-- Additive ingestion evidence and run state. Existing analytical tables remain readable.
CREATE TABLE IF NOT EXISTS ingestion_runs (
    id uuid PRIMARY KEY, source text NOT NULL, job_type text NOT NULL,
    entity_key text NOT NULL, business_date date NOT NULL, scheduled_for timestamptz NOT NULL,
    started_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz,
    status text NOT NULL CHECK (status IN ('pending','running','success','partial','failed','retry_scheduled','skipped')),
    attempt_no integer NOT NULL CHECK (attempt_no BETWEEN 1 AND 4),
    records_fetched integer NOT NULL DEFAULT 0, records_written integer NOT NULL DEFAULT 0,
    error_code text, error_message text, next_retry_at timestamptz, worker_id text,
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(source,job_type,entity_key,business_date,attempt_no)
);
CREATE INDEX IF NOT EXISTS ingestion_runs_due_idx ON ingestion_runs(status,next_retry_at);

CREATE TABLE IF NOT EXISTS source_documents (
    id uuid PRIMARY KEY, fetch_sequence bigserial UNIQUE, source text NOT NULL, entity_key text NOT NULL, document_type text NOT NULL,
    source_url text, fetched_at timestamptz NOT NULL, source_date date, effective_date date,
    content_hash text NOT NULL, content_type text NOT NULL, raw_content text NOT NULL,
    ingestion_run_id uuid REFERENCES ingestion_runs(id), parser_version text NOT NULL,
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(source,entity_key,document_type,content_hash)
);
CREATE INDEX IF NOT EXISTS source_documents_entity_idx ON source_documents(source,entity_key,fetched_at DESC);

CREATE TABLE IF NOT EXISTS fundamental_observations (
    observation_id uuid PRIMARY KEY, observation_sequence bigserial UNIQUE, source_document_id uuid NOT NULL REFERENCES source_documents(id),
    ticker text NOT NULL, metric text NOT NULL, raw_value text, normalized_value numeric, unit text NOT NULL,
    period_start date, period_end date NOT NULL, period_label text, release_date date,
    source text NOT NULL, observed_at timestamptz NOT NULL, parser_version text NOT NULL,
    valid boolean NOT NULL DEFAULT true, validation_error text, created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(source_document_id,ticker,metric,period_end,parser_version)
);
CREATE INDEX IF NOT EXISTS fundamental_observations_key_idx ON fundamental_observations(ticker,metric,period_end);

CREATE OR REPLACE VIEW canonical_fundamental_observations AS
SELECT DISTINCT ON (o.ticker,o.metric,o.period_end) o.*
FROM fundamental_observations o JOIN source_documents d ON d.id=o.source_document_id
WHERE o.valid
ORDER BY o.ticker,o.metric,o.period_end,
    CASE o.source WHEN 'company_disclosure' THEN 4 WHEN 'exchange_filing' THEN 3
                  WHEN 'sharedata' THEN 2 ELSE 1 END DESC,
    o.release_date DESC NULLS LAST,d.fetch_sequence DESC,o.observation_sequence DESC;

CREATE OR REPLACE VIEW fundamental_revision_history AS
SELECT o.*,
    lag(o.normalized_value) OVER (PARTITION BY o.ticker,o.metric,o.period_end
        ORDER BY d.fetch_sequence,o.observation_sequence) AS prior_value,
    CASE WHEN lag(o.normalized_value) OVER (PARTITION BY o.ticker,o.metric,o.period_end
        ORDER BY d.fetch_sequence,o.observation_sequence) IS DISTINCT FROM o.normalized_value
         AND lag(o.normalized_value) OVER (PARTITION BY o.ticker,o.metric,o.period_end
        ORDER BY d.fetch_sequence,o.observation_sequence) IS NOT NULL
         THEN true ELSE false END AS value_changed
FROM fundamental_observations o JOIN source_documents d ON d.id=o.source_document_id;

CREATE TABLE IF NOT EXISTS price_observations (
    observation_id uuid PRIMARY KEY, source_document_id uuid REFERENCES source_documents(id),
    ticker text NOT NULL, trade_date date NOT NULL, source text NOT NULL,
    open_price numeric, high_price numeric, low_price numeric, close_price numeric NOT NULL,volume bigint,
    content_hash text NOT NULL, observed_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(ticker,trade_date,source,content_hash)
);
CREATE INDEX IF NOT EXISTS price_observations_key_idx ON price_observations(ticker,trade_date);

CREATE TABLE IF NOT EXISTS market_observations (
    observation_id uuid PRIMARY KEY, source_document_id uuid NOT NULL REFERENCES source_documents(id),
    kind text NOT NULL CHECK(kind IN ('commodity','fx')), instrument text NOT NULL,
    source_timestamp timestamptz, source_time_key text NOT NULL,
    observed_at timestamptz NOT NULL, source text NOT NULL,
    value numeric NOT NULL, currency text, unit text, source_url text, content_hash text NOT NULL,
    parser_version text NOT NULL,
    UNIQUE(kind,instrument,source,source_time_key,content_hash)
);
CREATE INDEX IF NOT EXISTS market_observations_key_idx ON market_observations(kind,instrument,source_timestamp DESC);

CREATE TABLE IF NOT EXISTS sens_analyses (
    analysis_id uuid PRIMARY KEY, sens_announcement_id integer NOT NULL REFERENCES sens(sens_id),
    model text NOT NULL, prompt_version text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
    result text, status text NOT NULL CHECK(status IN ('success','failed')), error_message text
);
CREATE INDEX IF NOT EXISTS sens_analyses_announcement_idx ON sens_analyses(sens_announcement_id,created_at DESC);
ALTER TABLE sens ADD COLUMN IF NOT EXISTS source_document_id uuid REFERENCES source_documents(id);
ALTER TABLE raw_stock_valuations ADD COLUMN IF NOT EXISTS source_document_id uuid REFERENCES source_documents(id);
ALTER TABLE raw_stock_valuations ADD COLUMN IF NOT EXISTS parser_version text;
ALTER TABLE raw_stock_valuations ADD COLUMN IF NOT EXISTS observed_at timestamptz;

