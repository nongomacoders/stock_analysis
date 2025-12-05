Migration: add_watchlist_reward_risk_ratio_calc

What this does
-------------
Adds a trigger + function that computes and stores reward_risk_ratio on INSERT/UPDATE of watchlist rows. The computation is:

- For LONG positions (is_long = true): reward = target_price - entry_price; risk = entry_price - stop_loss
- For SHORT positions (is_long = false): reward = entry_price - target_price; risk = stop_loss - entry_price
- If any relevant price is NULL or risk <= 0 then reward_risk_ratio will be NULL. The value is rounded to 2 decimal places.

Why a trigger
------------
Using a trigger keeps this behavior compatible with a wider range of Postgres versions.
If you prefer to use a generated (computed) column and you're on Postgres 12+, that can also be implemented.

How to apply
------------
1. Apply the SQL migration file: core/db/migrations/add_watchlist_reward_risk_ratio_calc.sql
2. Optionally run the verification script core/db/migrations/verify_add_watchlist_reward_risk_ratio_calc.sql in a safe environment.

Notes
-----
- The migration will update existing rows to compute the ratio for any rows where target/entry/stop are present and risk > 0.
- If you want errors for invalid/risky values instead of nulls, you can adjust the function to raise exceptions or set a default value.
