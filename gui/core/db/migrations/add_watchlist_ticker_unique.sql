-- Migration: add unique constraint to watchlist.ticker
-- This migration will remove duplicate watchlist rows (keeping the first row per ticker)
-- and then add a UNIQUE constraint on the ticker column.

BEGIN;

-- 1) Remove duplicate rows, keeping the first row encountered per ticker
WITH duplicates AS (
  SELECT ctid FROM (
    SELECT ctid, ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY ctid) AS rn
    FROM watchlist
  ) s WHERE s.rn > 1
)
DELETE FROM watchlist WHERE ctid IN (SELECT ctid FROM duplicates);

-- 2) Add unique constraint on ticker
ALTER TABLE IF EXISTS watchlist
  DROP CONSTRAINT IF EXISTS watchlist_ticker_unique;

ALTER TABLE watchlist
  ADD CONSTRAINT watchlist_ticker_unique UNIQUE (ticker);

COMMIT;

-- NOTE: This migration assumes the watchlist table exists. It deletes duplicate
-- rows without attempting to merge conflicting data; if you need to preserve
-- non-ticker fields across duplicates you should manually merge rows before
-- running this migration.
