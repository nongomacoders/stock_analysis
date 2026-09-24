-- Dedicated, additive Historical Backtest storage. Live reports, plans and valuations are never referenced as mutable targets.
CREATE TABLE IF NOT EXISTS historical_backtests (
    backtest_id uuid PRIMARY KEY,
    ticker text NOT NULL,
    as_of_date date NOT NULL,
    reporting_period_label text,
    reporting_period_end date,
    status text NOT NULL CHECK (status IN ('draft','locked','completed','failed')),
    evidence_snapshot jsonb NOT NULL DEFAULT '[]'::jsonb,
    market_snapshot jsonb NOT NULL DEFAULT '[]'::jsonb,
    evidence_ids text[] NOT NULL DEFAULT '{}',
    market_snapshot_ids text[] NOT NULL DEFAULT '{}',
    source_report_ids uuid[] NOT NULL DEFAULT '{}',
    availability_policy text NOT NULL DEFAULT 'known_on_or_before_as_of',
    created_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    locked_at timestamptz,
    input_hash text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(ticker,as_of_date,input_hash)
);
CREATE INDEX IF NOT EXISTS historical_backtests_ticker_date_idx
    ON historical_backtests(ticker,as_of_date DESC,created_at DESC);

CREATE TABLE IF NOT EXISTS historical_backtest_plans (
    historical_plan_id uuid PRIMARY KEY,
    backtest_id uuid NOT NULL REFERENCES historical_backtests(backtest_id),
    plan_version integer NOT NULL CHECK(plan_version > 0),
    previous_historical_plan_id uuid REFERENCES historical_backtest_plans(historical_plan_id),
    status text NOT NULL CHECK(status IN ('draft','approved','superseded')),
    forecast_plan_snapshot jsonb NOT NULL,
    input_hash text NOT NULL,
    created_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    approved_by text,
    approved_at timestamptz,
    UNIQUE(backtest_id,plan_version)
);
CREATE INDEX IF NOT EXISTS historical_backtest_plans_backtest_idx
    ON historical_backtest_plans(backtest_id,plan_version DESC);

CREATE TABLE IF NOT EXISTS historical_backtest_results (
    historical_result_id uuid PRIMARY KEY,
    backtest_id uuid NOT NULL REFERENCES historical_backtests(backtest_id),
    historical_plan_id uuid NOT NULL REFERENCES historical_backtest_plans(historical_plan_id),
    valuation_engine_version text NOT NULL,
    input_hash text NOT NULL,
    valuation_result jsonb NOT NULL,
    historical_share_price jsonb,
    implied_upside_downside numeric,
    warnings jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    UNIQUE(backtest_id,historical_plan_id,valuation_engine_version,input_hash)
);
CREATE INDEX IF NOT EXISTS historical_backtest_results_backtest_idx
    ON historical_backtest_results(backtest_id,created_at DESC);

CREATE TABLE IF NOT EXISTS historical_backtest_outcomes (
    outcome_id uuid PRIMARY KEY,
    backtest_id uuid NOT NULL REFERENCES historical_backtests(backtest_id),
    historical_result_id uuid NOT NULL REFERENCES historical_backtest_results(historical_result_id),
    transition_key text NOT NULL,
    actual_period_end date NOT NULL,
    actual_evidence_ids text[] NOT NULL DEFAULT '{}',
    forecast_accuracy jsonb NOT NULL DEFAULT '{}'::jsonb,
    valuation_performance jsonb NOT NULL DEFAULT '{}'::jsonb,
    learning_summary jsonb,
    revealed_at timestamptz NOT NULL DEFAULT NOW(),
    UNIQUE(backtest_id,transition_key)
);
CREATE INDEX IF NOT EXISTS historical_backtest_outcomes_transition_idx
    ON historical_backtest_outcomes(transition_key,revealed_at DESC);
