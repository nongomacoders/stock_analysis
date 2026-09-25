-- Migration: Add revisioning support to historical_backtest_outcomes
-- Allows append-only revisions of backtest reveal outcomes (partial -> completed)

ALTER TABLE historical_backtest_outcomes
    ADD COLUMN IF NOT EXISTS revision integer NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS supersedes_outcome_id uuid REFERENCES historical_backtest_outcomes(outcome_id),
    ADD COLUMN IF NOT EXISTS outcome_status text NOT NULL DEFAULT 'completed',
    ADD COLUMN IF NOT EXISTS outcome_hash text;

-- Update existing outcome to status 'partial'
UPDATE historical_backtest_outcomes
SET outcome_status = 'partial'
WHERE outcome_id = '709d3dc5-17c1-462f-a9bb-6ffd87530f98'
  AND revision = 1;

-- Update unique constraint to include revision
ALTER TABLE historical_backtest_outcomes
    DROP CONSTRAINT IF EXISTS historical_backtest_outcomes_backtest_id_transition_key_key;

ALTER TABLE historical_backtest_outcomes
    ADD CONSTRAINT historical_backtest_outcomes_backtest_id_transition_key_revision_key
    UNIQUE (backtest_id, transition_key, revision);
