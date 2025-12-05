-- Verification script for add_watchlist_reward_risk_ratio_calc.sql
-- Run this in a safe/dev environment to validate the trigger/function behaviour.

-- 1) Clean up any previous test rows
DELETE FROM watchlist WHERE ticker LIKE 'TST-RRR-%';

-- 2) Insert a LONG example
INSERT INTO watchlist (ticker, target_price, entry_price, stop_loss, is_long)
VALUES ('TST-RRR-LONG', 150.00, 100.00, 90.00, true);

-- 3) Insert a SHORT example
INSERT INTO watchlist (ticker, target_price, entry_price, stop_loss, is_long)
VALUES ('TST-RRR-SHORT', 80.00, 100.00, 110.00, false);

-- 4) Insert cases with nulls/zero/negative risk
INSERT INTO watchlist (ticker, target_price, entry_price, stop_loss, is_long)
VALUES ('TST-RRR-NULL', NULL, 100.00, 90.00, true);

-- 5) Query results
SELECT ticker, target_price, entry_price, stop_loss, is_long, reward_risk_ratio
FROM watchlist
WHERE ticker LIKE 'TST-RRR-%'
ORDER BY ticker;

-- Expected:
-- - TST-RRR-LONG: reward = 150 - 100 = 50; risk = 100 - 90 = 10; ratio = 5.00
-- - TST-RRR-SHORT: reward = 100 - 80 = 20; risk = 110 - 100 = 10; ratio = 2.00
-- - TST-RRR-NULL: reward_risk_ratio = NULL
