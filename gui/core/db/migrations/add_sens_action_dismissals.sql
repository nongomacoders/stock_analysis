-- Keep user dismissals separate from immutable SENS and analysis evidence.
ALTER TABLE action_log ADD COLUMN IF NOT EXISTS dismissed_at timestamptz;
ALTER TABLE action_log ADD COLUMN IF NOT EXISTS sens_content_hash text;
CREATE TABLE IF NOT EXISTS sens_action_dismissals (
    ticker text NOT NULL,
    content_hash text NOT NULL,
    dismissed_at timestamptz NOT NULL DEFAULT now(),
    source_log_id integer,
    PRIMARY KEY (ticker, content_hash)
);
CREATE INDEX IF NOT EXISTS action_log_visible_idx
    ON action_log (ticker, log_timestamp DESC) WHERE dismissed_at IS NULL;
