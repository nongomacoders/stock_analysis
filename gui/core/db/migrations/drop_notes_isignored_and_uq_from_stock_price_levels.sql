-- Migration: Drop notes and is_ignored_on_scan from stock_price_levels, and remove unique constraint

ALTER TABLE IF EXISTS public.stock_price_levels
    DROP CONSTRAINT IF EXISTS uq_ticker_price;

ALTER TABLE IF EXISTS public.stock_price_levels
    DROP COLUMN IF EXISTS notes;

ALTER TABLE IF EXISTS public.stock_price_levels
    DROP COLUMN IF EXISTS is_ignored_on_scan;

-- (Optional) Recreate the index on ticker if it was dropped; index remains unchanged.

-- Add new column is_long to keep whether level is for long or short positions
ALTER TABLE IF EXISTS public.stock_price_levels
    ADD COLUMN IF NOT EXISTS is_long boolean DEFAULT true;

-- Null out the existing price levels as part of a data model change
UPDATE public.stock_price_levels SET price_level = NULL;

-- Create new price level rows from the `watchlist` by using price_level and level_type
-- for entry, target and stoploss. This keeps `stock_price_levels` as a generic
-- listing of individual price levels with an associated type, instead of adding
-- specific columns for entry/target/stop_loss.
-- NOTE: This is idempotent: INSERT only adds rows where price_level is not NULL
INSERT INTO public.stock_price_levels (ticker, price_level, level_type, date_added, is_long)
SELECT w.ticker, w.entry_price, 'entry', COALESCE(w.date_added, CURRENT_DATE), w.is_long
FROM public.watchlist w
WHERE w.entry_price IS NOT NULL
    AND NOT EXISTS (
        SELECT 1 FROM public.stock_price_levels sp WHERE sp.ticker = w.ticker AND sp.level_type = 'entry'
    );

INSERT INTO public.stock_price_levels (ticker, price_level, level_type, date_added, is_long)
SELECT w.ticker, w.target_price, 'target', COALESCE(w.date_added, CURRENT_DATE), w.is_long
FROM public.watchlist w
WHERE w.target_price IS NOT NULL
    AND NOT EXISTS (
        SELECT 1 FROM public.stock_price_levels sp WHERE sp.ticker = w.ticker AND sp.level_type = 'target'
    );

INSERT INTO public.stock_price_levels (ticker, price_level, level_type, date_added, is_long)
SELECT w.ticker, w.stop_loss, 'stop_loss', COALESCE(w.date_added, CURRENT_DATE), w.is_long
FROM public.watchlist w
WHERE w.stop_loss IS NOT NULL
    AND NOT EXISTS (
        SELECT 1 FROM public.stock_price_levels sp WHERE sp.ticker = w.ticker AND sp.level_type = 'stop_loss'
    );

-- Remove duplicates for types which should be unique per ticker (keep the lowest level_id)
DELETE FROM public.stock_price_levels a
USING (
    SELECT ticker, MIN(level_id) as keep_id
    FROM public.stock_price_levels
    WHERE level_type = 'entry'
    GROUP BY ticker
) b
WHERE a.ticker = b.ticker AND a.level_type = 'entry' AND a.level_id <> b.keep_id;

DELETE FROM public.stock_price_levels a
USING (
    SELECT ticker, MIN(level_id) as keep_id
    FROM public.stock_price_levels
    WHERE level_type = 'target'
    GROUP BY ticker
) b
WHERE a.ticker = b.ticker AND a.level_type = 'target' AND a.level_id <> b.keep_id;

DELETE FROM public.stock_price_levels a
USING (
    SELECT ticker, MIN(level_id) as keep_id
    FROM public.stock_price_levels
    WHERE level_type = 'stop_loss'
    GROUP BY ticker
) b
WHERE a.ticker = b.ticker AND a.level_type = 'stop_loss' AND a.level_id <> b.keep_id;

-- Create unique indexes for entry/target/stop_loss so these types are unique per ticker
CREATE UNIQUE INDEX IF NOT EXISTS stock_price_levels_unique_entry ON public.stock_price_levels (ticker) WHERE level_type = 'entry';
CREATE UNIQUE INDEX IF NOT EXISTS stock_price_levels_unique_target ON public.stock_price_levels (ticker) WHERE level_type = 'target';
CREATE UNIQUE INDEX IF NOT EXISTS stock_price_levels_unique_stoploss ON public.stock_price_levels (ticker) WHERE level_type = 'stop_loss';

-- Ensure level_type is only one of the allowed options
ALTER TABLE IF EXISTS public.stock_price_levels
    ADD CONSTRAINT stock_price_levels_level_type_check CHECK (level_type IN ('entry','target','stop_loss','support','resistance'));

-- Remove rows that have no price_level and no level_type (these are legacy rows)
DELETE FROM public.stock_price_levels WHERE price_level IS NULL AND (level_type IS NULL OR level_type = '');
