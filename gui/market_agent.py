import requests
from bs4 import BeautifulSoup
import psycopg2
import psycopg2.extras
import time
from datetime import datetime, time as dt_time, date, timedelta
from decimal import Decimal
import pandas as pd
import yfinance as yf
import threading
import asyncio
import analysis_engine
from db_layer import DBLayer, convert_yf_price_to_cents  # <-- UPDATED IMPORT
# --- Configuration ---
try:
    # Assumes config.py is in the same directory
    from config import DB_CONFIG
except ImportError:
    print("FATAL ERROR: config.py not found.")
    print("Please create config.py with your DB_CONFIG dictionary.")
    exit()

# Scheduler settings
RUN_START_TIME = dt_time(7, 0)  # 7:00 AM
RUN_END_TIME = dt_time(17, 30)  # 5:30 PM
JSE_CLOSE_TIME = dt_time(17, 30)  # 5:30 PM
MIDNIGHT_RESET_TIME = dt_time(0, 5)  # 12:05 AM
CHECK_INTERVAL_SECONDS = 900  # 15 minutes (15 * 60)
OFF_HOURS_SLEEP_SECONDS = 600  # 10 minutes (10 * 60)

# Scraper settings
BASE_URL = "https://www.moneyweb.co.za"
LIST_URL = f"{BASE_URL}/tools-and-data/moneyweb-sens/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

# --- Database Functions (SENS) ---
# NOTE: These remain synchronous using psycopg2 as they are self-contained

def fetch_tickers_from_db():
    """Fetches all tickers from the stock_details table and strips .JO."""
    tickers = set()
    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT ticker FROM stock_details")
                rows = cursor.fetchall()
                # Strip the '.JO' suffix for SENS filtering
                tickers = {row[0].replace(".JO", "") for row in rows}

    except Exception as e:
        print(f"DB ERROR: Could not fetch tickers: {e}")

    if tickers:
        print(f"Loaded {len(tickers)} tickers from database for SENS filtering.")
    else:
        print("DB WARNING: No tickers found in stock_details table.")
    return tickers


def check_if_sens_exists(conn, ticker, pub_datetime):
    """Checks if a SENS entry already exists."""
    ticker_with_suffix = ticker + ".JO"
    try:
        with conn.cursor() as cursor:
            query = "SELECT 1 FROM SENS WHERE ticker = %s AND publication_datetime = %s"
            cursor.execute(query, (ticker_with_suffix, pub_datetime))
            return cursor.fetchone() is not None
    except Exception as e:
        print(f"DB ERROR: Could not check for SENS: {e}")
        return True  # Assume it exists


def insert_sens_to_db(conn, ticker, pub_datetime, content):
    """Inserts the new SENS entry into the database."""
    ticker_with_suffix = ticker + ".JO"
    try:
        with conn.cursor() as cursor:
            query = """
                INSERT INTO SENS (ticker, publication_datetime, content)
                VALUES (%s, %s, %s)
            """
            cursor.execute(query, (ticker_with_suffix, pub_datetime, content))
        return True
    except Exception as e:
        print(f"DB ERROR: Could not insert SENS for {ticker}: {e}")
        conn.rollback()
        return False


# --- Helper Function ---


def parse_sens_datetime(time_str):
    """Parses SENS time string into a datetime object."""
    try:
        return datetime.strptime(time_str, "%d.%m.%y %H:%M")
    except ValueError:
        try:
            return datetime.strptime(time_str, "%d.%m.%y%H:%M")
        except ValueError:
            print(f"Warning: Could not parse datetime string: {time_str}")
            return None


# --- Main Scraper Logic (SENS) ---


def run_sens_check():
    """Main function to run one full SENS check cycle."""
    print(
        f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] --- Running SENS Check ---"
    )

    db_tickers = fetch_tickers_from_db()
    if not db_tickers:
        print("DEBUG (SENS Abort): No tickers found in stock_details.")
        return

    print(f"DEBUG (SENS): Loaded {len(db_tickers)} tickers to filter for: {db_tickers}")

    try:
        response = requests.get(LIST_URL, headers=HEADERS, timeout=10)
        response.raise_for_status()
        print("DEBUG (SENS): Successfully fetched main SENS page.")
    except Exception as e:
        print(f"HTTP ERROR (SENS): Could not fetch main SENS list: {e}")
        return

    soup = BeautifulSoup(response.content, "html.parser")
    sens_rows = soup.find_all("div", class_="sens-row")

    if not sens_rows:
        print("DEBUG (SENS Abort): No SENS rows found on page (class 'sens-row').")
        return

    print(f"DEBUG (SENS): Found {len(sens_rows)} total SENS rows on the page.")

    new_items_saved = 0
    new_sens_for_ai = []  # <-- ADD THIS LINE
    db_conn = None
    try:
        db_conn = psycopg2.connect(**DB_CONFIG)
        print("DEBUG (SENS): Successfully connected to DB for processing.")

        for i, row in enumerate(sens_rows):
            ticker = ""  # Define ticker in outer scope for AI trigger
            sens_content = "N/A"  # Define in outer scope for AI trigger

            try:
                ticker_tag = row.find(
                    "a", title="Visit Click a company for this listing"
                )
                ticker = ticker_tag.get_text(strip=True)
            except AttributeError:
                continue

            print(f"DEBUG (SENS Row {i}): Processing ticker '{ticker}'")

            if ticker not in db_tickers:
                print(
                    f"DEBUG (SENS Row {i}): Skipping '{ticker}' (Not in our DB list)."
                )
                continue

            print(
                f"DEBUG (SENS Row {i}): Ticker '{ticker}' *IS* in our DB list. Proceeding..."
            )

            # --- NEW: Add .JO suffix back here for the AI ---
            ticker_with_suffix = ticker + ".JO"
            # --- END NEW ---

            try:
                time_tag = row.find("time")
                full_time_text = time_tag.get_text(strip=True)
                pub_datetime = parse_sens_datetime(full_time_text)

                if not pub_datetime:
                    print(f"Skipping {ticker}: Could not parse time '{full_time_text}'")
                    continue

            except (AttributeError, IndexError):
                print(f"Skipping {ticker}: Could not find time tag.")
                continue

            print(f"DEBUG (SENS): Checking DB for {ticker} @ {pub_datetime}...")
            # Note: check_if_sens_exists handles its own suffix logic
            if check_if_sens_exists(db_conn, ticker, pub_datetime):
                print(
                    f"DEBUG (SENS): Skipping {ticker} @ {pub_datetime}: Already in DB."
                )
                continue

            print(f"  -> Found NEW SENS for {ticker} at {pub_datetime}")

            try:
                link_tag = row.find("a", title="Go to SENS announcement")
                link = link_tag["href"]
                if link.startswith("/"):
                    link = f"{BASE_URL}{link}"
            except (AttributeError, KeyError):
                print(f"Skipping {ticker}: Could not find link.")
                continue

            print(f"     Fetching content from {link}...")

            try:
                time.sleep(0.5)
                page_response = requests.get(link, headers=HEADERS, timeout=10)
                page_response.raise_for_status()
                page_soup = BeautifulSoup(page_response.content, "html.parser")
                content_div = page_soup.find("div", id="sens-content")

                if content_div:
                    pre_tag = content_div.find("pre")
                    sens_content = (
                        pre_tag.get_text(separator="\n", strip=True)
                        if pre_tag
                        else content_div.get_text(separator="\n", strip=True)
                    )
                else:
                    sens_content = "Content ID 'sens-content' not found."
            except Exception as e:
                sens_content = f"Error fetching content: {e}"

            # Note: insert_sens_to_db handles its own suffix logic
            if insert_sens_to_db(db_conn, ticker, pub_datetime, sens_content):
                print(f"     SUCCESS: Saved new SENS for {ticker}.")
                new_items_saved += 1

                # --- COLLECT AI DATA ---
                new_sens_for_ai.append((ticker_with_suffix, sens_content)) 
                # --- END COLLECT AI DATA --

        if new_items_saved > 0:
            print(f"DEBUG (SENS): Committing {new_items_saved} new items to DB.")
            db_conn.commit()
            # --- POST-COMMIT AI TRIGGER ---
            print(f"DEBUG (SENS): Triggering {len(new_sens_for_ai)} AI analyses...")
            for ticker_with_suffix, sens_content in new_sens_for_ai:
                print(f"     ==> Spawning AI thread for {ticker_with_suffix}...")
                threading.Thread(
                    target=analysis_engine.analyze_new_sens,
                    args=(ticker_with_suffix, sens_content), 
                    daemon=True,
                ).start()
            # --- END POST-COMMIT AI TRIGGER ---
        else:
            print("DEBUG (SENS): No new items to commit.")

    except Exception as e:
        print(f"FATAL ERROR during SENS check: {e}")
        if db_conn:
            db_conn.rollback()
    finally:
        if db_conn:
            db_conn.close()
            print("DEBUG (SENS): Database connection closed.")

    print(f"--- SENS Check Complete. Saved {new_items_saved} new announcements. ---")


# --- UPDATED EOD Price Download Function ---


async def run_eod_price_download(db: DBLayer):
    """
    Downloads EOD prices for ALL tickers in the database.
    This function is "smart" and will back-fill any missed days.
    It will ALSO trigger the AI for any price-level hits.
    """
    print(
        f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] +++ Running EOD Price Download +++"
    )
    db_conn = None
    latest_prices_cents = {}  # Store new prices here

    try:
        db_conn = psycopg2.connect(**DB_CONFIG)
        cursor = db_conn.cursor()

        # 1. Check the last market date in our DB
        cursor.execute("SELECT MAX(trade_date) FROM daily_stock_data")
        last_market_date_in_db = cursor.fetchone()[0]

        if last_market_date_in_db:
            print(f"DEBUG (EOD): Last price date in DB is: {last_market_date_in_db}")
        else:
            print("DEBUG (EOD): No price data found in DB.")

        download_params = {}
        today = date.today()

        if last_market_date_in_db is None:
            # Case 1: Database is empty. Do a full 5-year historical download.
            print("DEBUG (EOD): Performing 5-year historical download.")
            download_params = {"period": "5y"}
        else:
            days_diff = (today - last_market_date_in_db).days
            if days_diff > 2:
                # Case 2: We are out-of-date. Download the missing range.
                start_date = last_market_date_in_db + timedelta(days=1)
                end_date = today + timedelta(days=1)  # yf 'end' is non-inclusive
                print(
                    f"DEBUG (EOD): Data is {days_diff} days old. Downloading from {start_date} to {end_date}."
                )
                download_params = {"start": start_date, "end": end_date}
            else:
                # Case 3: We are up-to-date. Just run a 2-day refresh
                print("DEBUG (EOD): Data is up-to-date. Running 2-day refresh.")
                download_params = {"period": "2d"}

        # 2. Fetch ALL tickers, *with* the .JO suffix for yfinance
        print("DEBUG (EOD): Fetching all tickers for yfinance...")
        cursor.execute("SELECT ticker FROM stock_details")
        all_tickers = [row[0] for row in cursor.fetchall()]

        if not all_tickers:
            print("DEBUG (EOD): No tickers in 'stock_details' to download.")
            return

        print(f"DEBUG (EOD): Downloading price data for {len(all_tickers)} tickers...")

        # 3. Call yfinance with our smart params
        # Note: yf.download is synchronous. In a true async app we might run this in an executor.
        # But for this agent, blocking briefly is okay.
        data = yf.download(all_tickers, auto_adjust=True, **download_params)

        if data.empty:
            print(
                "DEBUG (EOD): No data returned from yfinance (this is normal on weekends/holidays if up-to-date)."
            )
            return

        # 4. Process and save the data
        # --- FIX: We now capture the latest_prices_cents dictionary ---
        records_saved_count, latest_prices_cents = process_and_save_new_data(
            db_conn, data, all_tickers
        )

        # 5. Log this update
        if records_saved_count > 0:
            print(
                f"DEBUG (EOD): Logging {records_saved_count} records to price_update_log..."
            )
            cursor.execute(
                "INSERT INTO price_update_log (records_saved) VALUES (%s)",
                (records_saved_count,),
            )
            db_conn.commit()  # Commit the price data *before* analysis

        # --- NEW: 6. Run Price Trigger Logic ---
        print("DEBUG (EOD): Checking for price-level triggers...")

        # This query gets the latest price, the *previous* price, and
        # the array of research levels for all relevant stocks.
        trigger_query = """
            WITH PrevPrices AS (
                -- Get the close price and the previous day's close price
                SELECT 
                    ticker, 
                    trade_date, 
                    close_price,
                    LAG(close_price, 1) OVER(PARTITION BY ticker ORDER BY trade_date) as prev_close_price
                FROM daily_stock_data
            ),
            LatestData AS (
                -- Filter for *only* the most recent trade date in the DB
                SELECT * FROM PrevPrices 
                WHERE trade_date = (SELECT MAX(trade_date) FROM daily_stock_data)
            )
            -- Join with our research data
            SELECT 
                ld.ticker, 
                ld.close_price as new_price, 
                ld.prev_close_price as prev_price,
                sa.price_levels
            FROM LatestData ld
            JOIN stock_analysis sa ON ld.ticker = sa.ticker
            WHERE sa.price_levels IS NOT NULL AND ld.prev_close_price IS NOT NULL;
        """

        cursor.execute(trigger_query)
        stocks_to_check = cursor.fetchall()

        if not stocks_to_check:
            print("DEBUG (EOD): No stocks with price levels to check.")
            return

        print(f"DEBUG (EOD): Checking {len(stocks_to_check)} stocks for price hits...")
        
        hit_count = 0

        for row in stocks_to_check:
            ticker, new_price, prev_price, levels = row

            # Convert from Decimal/float to a clean float
            new_price = float(new_price)
            prev_price = float(prev_price)

            if not levels:  # Skip if price_levels is empty/NULL
                continue

            for level in levels:
                level = float(level)  # Convert from Decimal
                level_decimal = Decimal(str(level))

                # Check for a "cross"
                crossed_up = prev_price < level <= new_price
                crossed_down = prev_price > level >= new_price

                if crossed_up or crossed_down:
                    # --- NEW: Check if this exact hit has already been logged today ---
                    # UPDATED: Use async db_layer call
                    already_logged = await db.check_if_price_hit_logged_today(ticker, level_decimal, today)
                    
                    if already_logged:
                        print(f"     ==> WARNING: {ticker} hit {level}c already logged today. Skipping AI trigger.")
                        continue # Skip the AI trigger
                    # ------------------------------------------------------------------
                    hit_count += 1
                    print(
                        f"     ==> PRICE HIT: {ticker} crossed {level}c (New: {new_price}c, Prev: {prev_price}c)"
                    )
                    # --- NEW: Log the hit IMMEDIATELY to prevent re-trigger on subsequent runs ---
                    # UPDATED: Use async db_layer call
                    await db.insert_price_hit_log(ticker, level_decimal, new_price) 
                    # -----------------------------------------------------------------------------
                    # Call the AI brain in a separate thread
                    threading.Thread(
                        target=analysis_engine.analyze_price_change,
                        args=(ticker, new_price, level),
                        daemon=True,
                    ).start()

        if hit_count == 0:
            print("DEBUG (EOD): No price level triggers found.")

    except Exception as e:
        print(f"FATAL ERROR during EOD price download: {e}")
        if db_conn:
            db_conn.rollback()
    finally:
        if db_conn:
            db_conn.close()
            print("DEBUG (EOD): Database connection closed.")

    print("+++ EOD Price Download Complete +++")


def process_and_save_new_data(worker_conn, data, all_tickers):
    """
    Processes the DataFrame from yfinance, saves it to the DB,
    and returns the latest prices in CENTS.
    """
    print("DEBUG (EOD): Processing and saving new price data...")

    df = None
    try:
        if isinstance(data.columns, pd.MultiIndex):
            df = data.stack()
            df.index.names = ["trade_date", "ticker"]
            df = df.reset_index()
        elif "Close" in data.columns and len(all_tickers) == 1:
            df = data.reset_index()
            df["ticker"] = all_tickers[0]
            df.rename(columns={"Date": "trade_date"}, inplace=True)
        else:
            print("DEBUG (EOD): yfinance data format not recognized. Trying to fix...")
            # Handle case where yf returns single-index columns for multiple tickers
            df = data["Close"].stack().reset_index()
            df.rename(columns={"level_1": "ticker", 0: "Close"}, inplace=True)
            df["Open"] = data["Open"].stack().values
            df["High"] = data["High"].stack().values
            df["Low"] = data["Low"].stack().values
            df["Volume"] = data["Volume"].stack().values

    except Exception as e:
        print(f"DEBUG (EOD): Error processing yfinance data: {e}")
        # Fallback for single-ticker download
        if "Close" in data.columns and not data.index.name == "Date":
            df = data.reset_index()
            df.rename(columns={"Date": "trade_date"}, inplace=True)
            df["ticker"] = all_tickers[0]
        else:
            print("DEBUG (EOD): Could not process yfinance DataFrame.")
            return 0, {}

    # Clean and format
    df.rename(
        columns={
            "Open": "open_price",
            "High": "high_price",
            "Low": "low_price",
            "Close": "close_price",
            "Volume": "volume",
        },
        inplace=True,
    )

    db_cols = [
        "ticker",
        "trade_date",
        "open_price",
        "high_price",
        "low_price",
        "close_price",
        "volume",
    ]
    # Filter df to only include columns we need
    df = df[[col for col in db_cols if col in df.columns]]
    df.dropna(
        subset=["close_price", "open_price", "high_price", "low_price"], inplace=True
    )

    if df.empty:
        print("DEBUG (EOD): No valid data rows to save.")
        return 0, {}

    # Convert to Cents and prepare for insertion
    data_to_insert = []
    latest_prices_cents = {}

    for _, row in df.iterrows():
        try:
            # Convert to cents (integer) using the centralized utility function
            open_cents = convert_yf_price_to_cents(row["open_price"])
            high_cents = convert_yf_price_to_cents(row["high_price"])
            low_cents = convert_yf_price_to_cents(row["low_price"])
            close_cents = convert_yf_price_to_cents(row["close_price"])

            data_to_insert.append(
                (
                    row["ticker"],
                    row["trade_date"].date(),  # Store as date
                    open_cents,
                    high_cents,
                    low_cents,
                    close_cents,
                    int(row["volume"]),
                )
            )

            latest_prices_cents[row["ticker"]] = close_cents
        except Exception as e:
            print(
                f"Warning (EOD): Skipping row for {row['ticker']} due to data error: {e}"
            )

    if not data_to_insert:
        print("DEBUG (EOD): No data to insert after processing.")
        return 0, {}

    # Save to DB
    query = """
        INSERT INTO daily_stock_data (ticker, trade_date, open_price, high_price, low_price, close_price, volume)
        VALUES %s
        ON CONFLICT (ticker, trade_date) DO UPDATE SET
            open_price = EXCLUDED.open_price,
            high_price = EXCLUDED.high_price,
            low_price = EXCLUDED.low_price,
            close_price = EXCLUDED.close_price,
            volume = EXCLUDED.volume
    """

    try:
        cursor = worker_conn.cursor()
        psycopg2.extras.execute_values(cursor, query, data_to_insert)
        records_saved_count = cursor.rowcount
        worker_conn.commit()
        cursor.close()
        print(
            f"DEBUG (EOD): Successfully saved {records_saved_count} new price records."
        )
        return records_saved_count, latest_prices_cents
    except Exception as e:
        worker_conn.rollback()
        print(f"DB Error (EOD) saving data: {e}")
        return 0, {}


# --- Scheduler Loop ---


async def main():
    print("SENS & EOD Price Scraper Started.")
    print(f"Monitoring SENS between {RUN_START_TIME} and {RUN_END_TIME}, Mon-Fri.")
    print(f"Will run EOD price download once per day after {JSE_CLOSE_TIME}, Mon-Fri.")
    print(f"Check interval: {CHECK_INTERVAL_SECONDS // 60} minutes.")

    # Initialize Async DB Layer
    db = DBLayer()
    await db.init_pool()

    # This flag ensures EOD download only runs ONCE per day
    eod_download_done_today = False

    try:
        while True:
            now = datetime.now()
            is_weekday = 0 <= now.weekday() <= 4  # 0=Mon, 4=Fri
            is_sens_time = RUN_START_TIME <= now.time() <= RUN_END_TIME
            is_after_market_close = now.time() > JSE_CLOSE_TIME

            # --- TEST LINES ---
            # is_weekday = True
            # is_sens_time = True
            # is_after_market_close = True
            # --- END TEST LINES ---

            # 1. Check for Nightly Reset first
            if now.time() > MIDNIGHT_RESET_TIME and now.time() < RUN_START_TIME:
                if eod_download_done_today:
                    print("Past midnight. Resetting EOD download flag for today.")
                    eod_download_done_today = False

            # 2. Check for SENS
            if is_weekday and is_sens_time:
                # SENS check is synchronous, which is fine for now
                run_sens_check()
                # We do NOT sleep here anymore.

            # 3. Check for EOD Price Download
            if is_weekday and is_after_market_close and not eod_download_done_today:
                print("Market is closed. Triggering EOD price download...")
                await run_eod_price_download(db)
                eod_download_done_today = True  # Mark as done

            # 4. Decide how long to sleep
            if is_weekday and is_sens_time:
                # We are in the main SENS-checking window.
                print(f"Sleeping for {CHECK_INTERVAL_SECONDS // 60} minutes...")
                await asyncio.sleep(CHECK_INTERVAL_SECONDS)
            else:
                # We are off-hours (weekend, or after 17:30).
                print(
                    f"Off-hours. Sleeping for {OFF_HOURS_SLEEP_SECONDS // 60} minutes..."
                )
                await asyncio.sleep(OFF_HOURS_SLEEP_SECONDS)

    except KeyboardInterrupt:
        print("\nUser requested exit. Shutting down.")
    except Exception as e:
        print(f"CRITICAL ERROR in main loop: {e}")
        print("Restarting loop in 60 seconds...")
        await asyncio.sleep(60)
    finally:
        await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
