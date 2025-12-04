import yfinance as yf
import pandas as pd
from datetime import date, timedelta
from decimal import Decimal
from core.db.engine import DBEngine
from core.utils.math import convert_yf_price_to_cents

# CHANGED: Import the new AI Engine module
import modules.analysis.engine as ai_engine
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

    # Logic: Get Latest Price AND Previous Price for every stock
    query = """
        WITH RecentPrices AS (
            SELECT ticker, close_price, 
                   LAG(close_price) OVER(PARTITION BY ticker ORDER BY trade_date) as prev_price,
                   trade_date
            FROM daily_stock_data
        ),
        Latest AS (
            SELECT * FROM RecentPrices WHERE trade_date = (SELECT MAX(trade_date) FROM daily_stock_data)
        )
        SELECT l.ticker, l.close_price, l.prev_price, sa.price_levels
        FROM Latest l
        JOIN stock_analysis sa ON l.ticker = sa.ticker
        WHERE sa.price_levels IS NOT NULL AND l.prev_price IS NOT NULL
    """

    rows = await DBEngine.fetch(query)

    for row in rows:
        ticker = row["ticker"]
        curr = float(row["close_price"])
        prev = float(row["prev_price"])
        levels = row["price_levels"]  # This is a list from DB

        if not levels:
            continue

        for lvl in levels:
            lvl_val = float(lvl)
            # Check for Cross (Up or Down)
            crossed_up = prev < lvl_val <= curr
            crossed_down = prev > lvl_val >= curr

            if crossed_up or crossed_down:
                # Check if we already logged this hit today
                log_check_q = """
                    SELECT 1 FROM price_hit_log 
                    WHERE ticker = $1 AND price_level = $2 AND hit_timestamp::date = $3
                """
                exists = await DBEngine.fetch(log_check_q, ticker, lvl_val, check_date)

                if not exists:
                    logger.info("  [TRIGGER] %s crossed %s", ticker, lvl_val)
                    # 1. Log the hit
                    await DBEngine.execute(
                        "INSERT INTO price_hit_log (ticker, price_level) VALUES ($1, $2)",
                        ticker,
                        lvl_val,
                    )
                    # 2. Trigger AI (Async call replaces Threading)
                    await ai_engine.analyze_price_change(ticker, curr, lvl_val)
