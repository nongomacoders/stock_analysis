-- Dedicated, additive Historical Market Input storage.
-- Authoritative PostgreSQL store for dated market and macro observations.
CREATE TABLE IF NOT EXISTS historical_market_inputs (
    input_id uuid PRIMARY KEY,
    scope text NOT NULL CHECK (scope IN ('market', 'company')),
    ticker text,
    market_scope text NOT NULL DEFAULT 'ZA',
    concept text NOT NULL,
    value numeric NOT NULL,
    unit text NOT NULL DEFAULT 'percentage',
    observation_date date NOT NULL,
    available_date date NOT NULL,
    provider text NOT NULL,
    source_url text,
    source_methodology text,
    notes text,
    retrieval_timestamp timestamptz NOT NULL DEFAULT NOW(),
    batch_id text,
    lookback_period text,
    frequency text,
    levered boolean,
    debt_method text,
    provenance_quality text NOT NULL DEFAULT 'analyst_entered_historical_observation'
        CHECK (provenance_quality IN (
            'raw_source_fact',
            'derived_from_source_document',
            'historically_anchored_analyst_calculation',
            'analyst_entered_historical_observation',
            'analyst_valuation_assumption',
            'source_document_backed',
            'provider_record_backed',
            'analyst_entered',
            'manually_transcribed',
            'insufficient_provenance'
        )),
    source_document_id text,
    evidence_uri text,
    evidence_hash text,
    revision integer NOT NULL DEFAULT 1 CHECK (revision > 0),
    supersedes_input_id uuid REFERENCES historical_market_inputs(input_id),
    is_active boolean NOT NULL DEFAULT true,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    input_hash text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS historical_market_inputs_concept_date_idx
    ON historical_market_inputs(concept, scope, ticker, available_date DESC, revision DESC)
    WHERE is_active = true;

CREATE INDEX IF NOT EXISTS historical_market_inputs_supersedes_idx
    ON historical_market_inputs(supersedes_input_id);
