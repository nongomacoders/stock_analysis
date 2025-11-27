from datetime import date
import pandas as pd
import psycopg2
import psycopg2.extras

# This function enforces the rule that JSE prices must be stored as integers (in Cents).
# It assumes yfinance returns prices already in cents for JSE stocks.
def convert_yf_price_to_cents(price_value):
    """
    Converts a yfinance price value to an integer representing cents.
    Assumes JSE prices from yfinance are already in cents.
    """
    try:
        if pd.isna(price_value) or price_value is None:
            return None
        # Simply convert to integer, enforcing the database rule (e.g., 20111.00 -> 20111)
        return int(float(price_value))
    except Exception:
        return None

def convert_yf_price_to_rand(price_value):
    """
    Converts a yfinance price value to a float representing Rands (Rands = Cents / 100).
    """
    try:
        if pd.isna(price_value) or price_value is None:
            return None
        # This function is not used for saving, but may be useful for display
        return float(price_value) / 100.0
    except Exception:
        return None

def fetch_analysis_record(db_config, ticker):
    """
    Fetches the full analysis record (research, strategy, price_levels) 
    from stock_analysis for a given ticker.
    Returns: (research, strategy, price_levels) or (None, None, None)
    """
    try:
        # We need the full DB_CONFIG to make an independent connection
        with psycopg2.connect(**db_config) as conn:
            # Note: We use the connection object passed from the GUI tabs
            with conn.cursor() as cursor:
                # Query all relevant fields from stock_analysis
                query = "SELECT research, strategy, price_levels FROM stock_analysis WHERE ticker = %s"
                cursor.execute(query, (ticker,))
                return cursor.fetchone()
    except Exception as e:
        print(f"DB UTIL ERROR: Failed to fetch analysis record for {ticker}: {e}")
        return None

def fetch_all_tickers(db_config):
    """
    Fetches all tickers from the stock_details table, ordered by ticker.
    Returns: list of tickers (e.g., ['KAP.JO', 'MRP.JO'])
    """
    try:
        # We need the full DB_CONFIG to make an independent connection
        with psycopg2.connect(**db_config) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT ticker FROM stock_details ORDER BY ticker")
                return [row[0] for row in cursor.fetchall()]
    except Exception as e:
        print(f"DB UTIL ERROR: Failed to fetch ticker list: {e}")
        return []

def create_portfolio_tables(db_config):
    """
    Creates the necessary tables for portfolio management if they don't exist.
    """
    commands = (
        """
        CREATE TABLE IF NOT EXISTS portfolios (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS portfolio_transactions (
            id SERIAL PRIMARY KEY,
            portfolio_id INTEGER REFERENCES portfolios(id) ON DELETE CASCADE,
            ticker VARCHAR(20) NOT NULL,
            transaction_type VARCHAR(10) NOT NULL CHECK (transaction_type IN ('BUY', 'SELL')),
            quantity DECIMAL(15, 4) NOT NULL,
            price DECIMAL(15, 2) NOT NULL,
            transaction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            fees DECIMAL(15, 2) DEFAULT 0.0,
            notes TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS portfolio_holdings (
            id SERIAL PRIMARY KEY,
            portfolio_id INTEGER REFERENCES portfolios(id) ON DELETE CASCADE,
            ticker VARCHAR(20) NOT NULL,
            quantity DECIMAL(15, 4) NOT NULL,
            average_buy_price DECIMAL(15, 2) NOT NULL,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(portfolio_id, ticker)
        )
        """
    )
    try:
        with psycopg2.connect(**db_config) as conn:
            with conn.cursor() as cursor:
                for command in commands:
                    cursor.execute(command)
                conn.commit()
        print("Portfolio tables checked/created successfully.")
    except Exception as e:
        print(f"DB UTIL ERROR: Failed to create portfolio tables: {e}")

def add_transaction(db_config, portfolio_id, ticker, transaction_type, quantity, price, fees=0.0, notes="", transaction_date=None):
    """
    Adds a transaction and updates the portfolio holdings.
    """
    try:
        with psycopg2.connect(**db_config) as conn:
            with conn.cursor() as cursor:
                # 1. Insert Transaction
                if transaction_date:
                    insert_query = """
                    INSERT INTO portfolio_transactions (portfolio_id, ticker, transaction_type, quantity, price, fees, notes, transaction_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    cursor.execute(insert_query, (portfolio_id, ticker, transaction_type, quantity, price, fees, notes, transaction_date))
                else:
                    insert_query = """
                    INSERT INTO portfolio_transactions (portfolio_id, ticker, transaction_type, quantity, price, fees, notes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """
                    cursor.execute(insert_query, (portfolio_id, ticker, transaction_type, quantity, price, fees, notes))

                # 2. Update Holdings
                # Get current holding
                cursor.execute("SELECT quantity, average_buy_price FROM portfolio_holdings WHERE portfolio_id = %s AND ticker = %s", (portfolio_id, ticker))
                current_holding = cursor.fetchone()

                new_quantity = 0
                new_avg_price = 0.0

                if current_holding:
                    current_qty, current_avg_price = current_holding
                    current_qty = float(current_qty)
                    current_avg_price = float(current_avg_price)
                    
                    if transaction_type == 'BUY':
                        total_cost = (current_qty * current_avg_price) + (quantity * price)
                        new_quantity = current_qty + quantity
                        new_avg_price = total_cost / new_quantity if new_quantity > 0 else 0.0
                    elif transaction_type == 'SELL':
                        new_quantity = current_qty - quantity
                        new_avg_price = current_avg_price # Selling doesn't change avg buy price usually
                else:
                    if transaction_type == 'BUY':
                        new_quantity = quantity
                        new_avg_price = price
                    else:
                        # Selling something we don't have? Allow it for now (shorting?) or just negative qty
                        new_quantity = -quantity
                        new_avg_price = price # Or 0?

                # Upsert holding
                upsert_query = """
                INSERT INTO portfolio_holdings (portfolio_id, ticker, quantity, average_buy_price, last_updated)
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (portfolio_id, ticker) 
                DO UPDATE SET quantity = EXCLUDED.quantity, average_buy_price = EXCLUDED.average_buy_price, last_updated = EXCLUDED.last_updated
                """
                cursor.execute(upsert_query, (portfolio_id, ticker, new_quantity, new_avg_price))
                
                conn.commit()
        return True
    except Exception as e:
        print(f"DB UTIL ERROR: Failed to add transaction: {e}")
        return False

def delete_transaction(db_config, transaction_id, portfolio_id):
    """
    Deletes a transaction and recalculates portfolio holdings.
    """
    try:
        with psycopg2.connect(**db_config) as conn:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM portfolio_transactions WHERE id = %s", (transaction_id,))
                conn.commit()
        
        # Recalculate holdings from scratch to ensure accuracy
        return recalculate_portfolio_holdings(db_config, portfolio_id)
    except Exception as e:
        print(f"DB UTIL ERROR: Failed to delete transaction: {e}")
        return False

def recalculate_portfolio_holdings(db_config, portfolio_id):
    """
    Wipes current holdings for the portfolio and replays all transactions to rebuild them.
    """
    try:
        with psycopg2.connect(**db_config) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                # 1. Clear current holdings
                cursor.execute("DELETE FROM portfolio_holdings WHERE portfolio_id = %s", (portfolio_id,))
                
                # 2. Fetch all transactions ordered by date
                cursor.execute("SELECT * FROM portfolio_transactions WHERE portfolio_id = %s ORDER BY transaction_date ASC, id ASC", (portfolio_id,))
                transactions = cursor.fetchall()
                
                # 3. Replay transactions
                holdings = {} # ticker -> {qty, total_cost}
                
                for t in transactions:
                    ticker = t['ticker']
                    t_type = t['transaction_type']
                    qty = float(t['quantity'])
                    price = float(t['price']) # in cents
                    
                    if ticker not in holdings:
                        holdings[ticker] = {'qty': 0.0, 'total_cost': 0.0}
                    
                    if t_type == 'BUY':
                        holdings[ticker]['total_cost'] += (qty * price)
                        holdings[ticker]['qty'] += qty
                    elif t_type == 'SELL':
                        # When selling, we reduce quantity. 
                        # Cost basis reduction depends on accounting method (FIFO, LIFO, Avg Cost).
                        # We use Average Cost Basis here.
                        current_qty = holdings[ticker]['qty']
                        current_cost = holdings[ticker]['total_cost']
                        avg_price = current_cost / current_qty if current_qty > 0 else 0
                        
                        # Reduce cost by the portion of assets sold
                        cost_removed = qty * avg_price
                        holdings[ticker]['total_cost'] -= cost_removed
                        holdings[ticker]['qty'] -= qty

                # 4. Insert recalculated holdings
                for ticker, data in holdings.items():
                    qty = data['qty']
                    total_cost = data['total_cost']
                    
                    # Filter out negligible quantities (e.g. floating point errors near zero)
                    if abs(qty) < 0.0001:
                        continue
                        
                    avg_price = total_cost / qty if qty > 0 else 0.0
                    
                    cursor.execute("""
                        INSERT INTO portfolio_holdings (portfolio_id, ticker, quantity, average_buy_price, last_updated)
                        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                    """, (portfolio_id, ticker, qty, avg_price))
                
                conn.commit()
        return True
    except Exception as e:
        print(f"DB UTIL ERROR: Failed to recalculate holdings: {e}")
        return False

def get_portfolio_holdings(db_config, portfolio_id):
    """
    Returns a list of holdings for a portfolio.
    """
    try:
        with psycopg2.connect(**db_config) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("SELECT * FROM portfolio_holdings WHERE portfolio_id = %s ORDER BY ticker", (portfolio_id,))
                return cursor.fetchall()
    except Exception as e:
        print(f"DB UTIL ERROR: Failed to get holdings: {e}")
        return []

def get_portfolio_transactions(db_config, portfolio_id, ticker=None):
    """
    Returns a list of transactions for a portfolio.
    """
    try:
        with psycopg2.connect(**db_config) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                if ticker:
                    cursor.execute("SELECT * FROM portfolio_transactions WHERE portfolio_id = %s AND ticker = %s ORDER BY transaction_date DESC", (portfolio_id, ticker))
                else:
                    cursor.execute("SELECT * FROM portfolio_transactions WHERE portfolio_id = %s ORDER BY transaction_date DESC", (portfolio_id,))
                return cursor.fetchall()
    except Exception as e:
        print(f"DB UTIL ERROR: Failed to get transactions: {e}")
        return []

def insert_price_hit_log(db_config, ticker, level, hit_price):
    """Inserts a record into price_hit_log."""
    try:
        with psycopg2.connect(**db_config) as conn:
            with conn.cursor() as cursor:
                query = """
                    INSERT INTO price_hit_log (ticker, price_level)
                    VALUES (%s, %s)
                    ON CONFLICT (ticker, price_level, (hit_timestamp::date)) DO NOTHING
                """
                # Note: We only log the price_level and let the DB handle the timestamp/date
                cursor.execute(query, (ticker, level))
                conn.commit()
                return True
    except Exception as e:
        print(f"DB UTIL ERROR: Failed to insert price hit log: {e}")
        return False

def check_if_price_hit_logged_today(db_config, ticker, level, check_date):
    """
    Checks if a hit for the specific price level has already been logged
    in price_hit_log for the given date.
    """
    try:
        with psycopg2.connect(**db_config) as conn:
            with conn.cursor() as cursor:
                query = """
                    SELECT 1 FROM price_hit_log
                    WHERE ticker = %s
                    AND price_level = %s
                    AND hit_timestamp::date = %s
                """
                cursor.execute(query, (ticker, level, check_date))
                return cursor.fetchone() is not None
    except Exception as e:
        print(f"DB UTIL ERROR: Failed to check price hit log: {e}")
        return True # Default to True to prevent double-triggering on error