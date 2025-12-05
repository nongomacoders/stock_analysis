-- Migration: add trigger to compute reward_risk_ratio for watchlist
-- Computes reward_risk_ratio as (reward / risk) using these rules:
-- - For long positions (is_long = true):
--     reward = target_price - entry_price
--     risk   = entry_price - stop_loss
-- - For short positions (is_long = false):
--     reward = entry_price - target_price
--     risk   = stop_loss - entry_price
-- If any price is NULL or the computed risk <= 0 then reward_risk_ratio is set to NULL.

BEGIN;

-- 1) Add column if it's missing (safe for existing DBs)
ALTER TABLE IF EXISTS watchlist
  ADD COLUMN IF NOT EXISTS reward_risk_ratio numeric(10,2);

-- 2) Create helper function
CREATE OR REPLACE FUNCTION compute_watchlist_reward_risk_ratio()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
  reward numeric;
  risk numeric;
BEGIN
  -- Default to NULL if any of the inputs are missing
  IF NEW.target_price IS NULL OR NEW.entry_price IS NULL OR NEW.stop_loss IS NULL THEN
    NEW.reward_risk_ratio := NULL;
    RETURN NEW;
  END IF;

  IF COALESCE(NEW.is_long, true) THEN
    reward := NEW.target_price - NEW.entry_price;
    risk := NEW.entry_price - NEW.stop_loss;
  ELSE
    reward := NEW.entry_price - NEW.target_price;
    risk := NEW.stop_loss - NEW.entry_price;
  END IF;

  -- Protect against division by zero or negative risk values
  IF risk IS NULL OR risk <= 0 THEN
    NEW.reward_risk_ratio := NULL;
  ELSE
    NEW.reward_risk_ratio := ROUND((reward / risk)::numeric, 2);
  END IF;

  RETURN NEW;
END;
$$;

-- 3) Update existing rows so pre-existing data has a computed ratio
UPDATE watchlist
SET reward_risk_ratio = computed.val
FROM (
  SELECT watchlist_id,
    CASE
      WHEN target_price IS NULL OR entry_price IS NULL OR stop_loss IS NULL THEN NULL
      WHEN COALESCE(is_long, true) AND (entry_price - stop_loss) > 0 THEN ROUND((target_price - entry_price) / (entry_price - stop_loss)::numeric, 2)
      WHEN NOT COALESCE(is_long, true) AND (stop_loss - entry_price) > 0 THEN ROUND((entry_price - target_price) / (stop_loss - entry_price)::numeric, 2)
      ELSE NULL
    END AS val
  FROM watchlist
) AS computed
WHERE watchlist.watchlist_id = computed.watchlist_id;

-- 4) Create trigger to compute column on INSERT or UPDATE
DROP TRIGGER IF EXISTS trg_compute_watchlist_reward_risk_ratio ON watchlist;
CREATE TRIGGER trg_compute_watchlist_reward_risk_ratio
BEFORE INSERT OR UPDATE ON watchlist
FOR EACH ROW
EXECUTE FUNCTION compute_watchlist_reward_risk_ratio();

COMMIT;

-- Notes:
-- - This migration uses a trigger-based approach for compatibility across Postgres versions.
-- - It rounds the computed ratio to 2 decimal places to fit numeric(10,2).
-- - If you prefer a generated (computed) column (Postgres 12+), we can convert this to a
--   generated column instead — but generated columns are not supported on older servers.
