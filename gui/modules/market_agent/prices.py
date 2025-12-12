import yfinance as yf
import pandas as pd
from datetime import date, timedelta
from decimal import Decimal
from core.db.engine import DBEngine
from core.utils.math import convert_yf_price_to_cents
import logging

logger = logging.getLogger(__name__)


async def run_price_update():
    """Downloads prices and triggers alerts."""
    logger.info("+++ Running Price Update +++")

    # 1. Determine Date Range
    last_row = await DBEngine.fetch("SELECT MAX(trade_date) as d FROM daily_stock_data")
    last_date = last_row[0]["d"] if last_row and last_row[0]["d"] else None
    
    logger.debug("Last DB Date: %s", last_date)

    today = date.today()
    params = {"period": "5y"}  # Default to full download if empty

    if last_date:
        diff = (today - last_date).days
        logger.debug("Days since last update: %s", diff)
        if diff <= 2:
            params = {"period": "2d"}
        else:
            params = {
                "start": last_date + timedelta(days=1),
                "end": today + timedelta(days=1),
            }
    
    logger.debug("Download params: %s", params)

    # 2. Get Tickers
    rows = await DBEngine.fetch("SELECT ticker FROM stock_details")
    tickers = [r["ticker"] for r in rows]
    if not tickers:
        logger.debug("No tickers found in DB.")
        return

    # 3. Download
    logger.info("Downloading for %s tickers...", len(tickers))
    try:
        data = yf.download(tickers, auto_adjust=True, progress=False, **params)
        logger.debug("Downloaded data shape: %s", data.shape)
        if data.empty:
            logger.debug("Data is empty.")
    except Exception:
        logger.exception("YFinance Error")
        return

    if data.empty:
        return

    # 4. Process & Save
    records = await _process_and_save(data, tickers)
    logger.debug("Records saved: %s", records)
    if records > 0:
        await DBEngine.execute(
            "INSERT INTO price_update_log (records_saved) VALUES ($1)", records
        )
        # CHANGED: We now await the trigger check directly
        await _check_price_triggers(today)


async def _process_and_save(data, all_tickers):
    # Handle yfinance multi-index complexity
    logger.debug("Data columns type: %s", type(data.columns))
    if isinstance(data.columns, pd.MultiIndex):
        logger.debug("MultiIndex detected. Stacking...")
        # pandas is introducing a new stack implementation
        # use future_stack=True when available to adopt new behavior and silence FutureWarning
        # but fall back to the old call if the pandas version does not support the kw arg
        try:
            df = data.stack(future_stack=True).reset_index()
        except TypeError:
            # older pandas does not accept future_stack kw
            df = data.stack().reset_index()
        logger.debug("Stacked columns: %s", df.columns)
        # Check if 'level_1' is indeed the ticker column or if it's named 'Ticker'
        if "level_1" in df.columns:
            df.rename(columns={"level_1": "ticker"}, inplace=True)
        elif "Ticker" in df.columns:
            df.rename(columns={"Ticker": "ticker"}, inplace=True)
            
    elif "Close" in data.columns:
        logger.debug("Single index detected.")
        df = data.reset_index()
        df["ticker"] = all_tickers[0] if all_tickers else "UNKNOWN"
        df.rename(columns={"Date": "trade_date"}, inplace=True)
    else:
        logger.debug("Unknown data format.")
        return 0

    logger.debug("DF Columns before rename: %s", df.columns)
    df.rename(
        columns={"Open": "o", "High": "h", "Low": "l", "Close": "c", "Volume": "v", "Date": "trade_date"},
        inplace=True,
    )
    logger.debug("DF Columns after rename: %s", df.columns)
    
    # Check if we have the required columns
    required = {'o', 'h', 'l', 'c', 'v', 'ticker', 'trade_date'}
    if not required.issubset(df.columns):
        logger.debug("Missing columns. Have: %s, Need: %s", df.columns, required)
        return 0

    count = 0

    q = """
        INSERT INTO daily_stock_data (ticker, trade_date, open_price, high_price, low_price, close_price, volume)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (ticker, trade_date) DO UPDATE SET close_price = EXCLUDED.close_price
    """

    for _, row in df.iterrows():
        try:
            # Skip if critical data is missing
            if pd.isna(row["c"]):
                continue

            args = (
                row["ticker"],
                row["trade_date"].date(),
                convert_yf_price_to_cents(row["o"]),
                convert_yf_price_to_cents(row["h"]),
                convert_yf_price_to_cents(row["l"]),
                convert_yf_price_to_cents(row["c"]),
                int(row["v"]) if not pd.isna(row["v"]) else 0,
            )
            await DBEngine.execute(q, *args)
            count += 1
        except Exception:
            logger.exception("Error processing row")
            continue
    return count


async def _check_price_triggers(check_date):
    logger.info("Checking for Price Triggers...")

    # Prices in daily_stock_data are stored in cents (see convert_yf_price_to_cents).
    # Price levels are now stored in public.stock_price_levels (also cents).
    # We check crossings for the latest close vs previous close PER ticker.
    query = """
        WITH latest_prices AS (
            SELECT
                ticker,
                close_price,
                LAG(close_price) OVER (PARTITION BY ticker ORDER BY trade_date) AS prev_price,
                trade_date,
                ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY trade_date DESC) AS rn
            FROM daily_stock_data
        ),
        latest AS (
            SELECT ticker, close_price, prev_price
            FROM latest_prices
            WHERE rn = 1 AND prev_price IS NOT NULL
        ),
        sr_levels AS (
            -- Support/resistance: keep all levels
            SELECT spl.ticker, spl.level_id, spl.level_type, spl.price_level
            FROM public.stock_price_levels spl
            WHERE spl.level_type IN ('support', 'resistance')
        ),
        ets_levels AS (
            -- Entry/target/stop_loss: take the latest level per type
            SELECT DISTINCT ON (spl.ticker, spl.level_type)
                spl.ticker,
                spl.level_id,
                spl.level_type,
                spl.price_level
            FROM public.stock_price_levels spl
            WHERE spl.level_type IN ('entry', 'target', 'stop_loss')
            ORDER BY spl.ticker, spl.level_type, spl.date_added DESC, spl.level_id DESC
        ),
        level_rows AS (
            SELECT * FROM sr_levels
            UNION ALL
            SELECT * FROM ets_levels
        )
        SELECT
            l.ticker,
            l.close_price,
            l.prev_price,
            lr.level_id,
            lr.level_type,
            lr.price_level
        FROM latest l
        JOIN level_rows lr ON lr.ticker = l.ticker
    """

    rows = await DBEngine.fetch(query)

    for row in rows:
        ticker = row["ticker"]

        # cents
        try:
            curr = int(row["close_price"])
        except Exception:
            curr = int(float(row["close_price"]))
        try:
            prev = int(row["prev_price"])
        except Exception:
            prev = int(float(row["prev_price"]))

        level_id = row.get("level_id")
        level_type = row.get("level_type")
        lvl = row.get("price_level")
        if lvl is None:
            continue

        # normalize to integer cents
        try:
            lvl_val = int(lvl)
        except Exception:
            try:
                lvl_val = int(Decimal(str(lvl)))
            except Exception:
                lvl_val = int(float(lvl))

        # Check for Cross (Up or Down)
        crossed_up = prev < lvl_val <= curr
        crossed_down = prev > lvl_val >= curr

        if crossed_up or crossed_down:
            # Prefer a level_id based dedupe (more precise than numeric price).
            # Fall back to ticker+price_level if level_id isn't available.
            if level_id is not None:
                log_check_q = """
                    SELECT 1 FROM price_hit_log
                    WHERE ticker = $1 AND level_id = $2 AND hit_timestamp::date = $3
                """
                try:
                    exists = await DBEngine.fetch(log_check_q, ticker, level_id, check_date)
                except Exception:
                    # Backward-compatible fallback if DB hasn't been migrated yet.
                    exists = None
            else:
                log_check_q = """
                    SELECT 1 FROM price_hit_log
                    WHERE ticker = $1 AND price_level = $2 AND hit_timestamp::date = $3
                """
                exists = await DBEngine.fetch(log_check_q, ticker, lvl_val, check_date)

            if level_id is not None and exists is None:
                log_check_q = """
                    SELECT 1 FROM price_hit_log
                    WHERE ticker = $1 AND price_level = $2 AND hit_timestamp::date = $3
                """
                exists = await DBEngine.fetch(log_check_q, ticker, lvl_val, check_date)

            if not exists:
                logger.info(
                    "  [TRIGGER] %s crossed %s (%s id=%s)",
                    ticker,
                    lvl_val,
                    level_type,
                    level_id,
                )

                # 1. Log the hit. Prefer the new schema (level_type + level_id).
                inserted = False
                try:
                    status = await DBEngine.execute(
                        "INSERT INTO price_hit_log (ticker, price_level, level_type, level_id) VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING",
                        ticker,
                        lvl_val,
                        level_type,
                        level_id,
                    )
                    if isinstance(status, str):
                        parts = status.split()
                        if parts and parts[-1].isdigit():
                            inserted = int(parts[-1]) > 0
                except Exception:
                    # Backward-compatible fallback if DB hasn't been migrated yet.
                    status = await DBEngine.execute(
                        "INSERT INTO price_hit_log (ticker, price_level) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                        ticker,
                        lvl_val,
                    )
                    if isinstance(status, str):
                        parts = status.split()
                        if parts and parts[-1].isdigit():
                            inserted = int(parts[-1]) > 0

                # Also write to action_log (no AI) so existing UI listeners refresh.
                # This preserves the previous behavior where a new action log entry
                # causes watchlist/research windows to update via action_log_changes.
                if inserted:
                    try:
                        trigger_content = (
                            f"Price crossed {lvl_val}c ({level_type}, level_id={level_id}), "
                            f"closing at {curr}c."
                        )
                        await DBEngine.execute(
                            "INSERT INTO action_log (ticker, trigger_type, trigger_content, ai_analysis) VALUES ($1, $2, $3, $4)",
                            ticker,
                            "Price Level",
                            trigger_content,
                            None,
                        )
                    except Exception:
                        logger.exception("Failed to write action_log for %s", ticker)
