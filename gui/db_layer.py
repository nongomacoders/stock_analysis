import asyncpg
import pandas as pd
from datetime import date
from core.config import DB_CONFIG

# --- Helper Functions ---

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

class DBLayer:
    def __init__(self):
        self.config = DB_CONFIG
        self.pool = None

    async def init_pool(self):
        """Initialize the asyncpg connection pool."""
        if self.pool is None:
            try:
                # Validate required config keys
                required_keys = ["host", "dbname", "user", "password"]
                missing_keys = [key for key in required_keys if key not in self.config]
                
                if missing_keys:
                    print(f"ERROR: Missing required DB configuration keys: {missing_keys}")
                    exit(1)
                
                # Create connection pool
                self.pool = await asyncpg.create_pool(
                    host=self.config["host"],
                    database=self.config["dbname"],
                    user=self.config["user"],
                    password=self.config["password"],
                    min_size=2,
                    max_size=10
                )
            except Exception as e:
                print(f"ERROR: Failed to create database connection pool: {e}")
                exit(1)

    async def close_pool(self):
        """Close the connection pool."""
        if self.pool:
            await self.pool.close()
            self.pool = None

    async def insert_price_hit_log(self, ticker, level, hit_price):
        """Inserts a record into price_hit_log."""
        if self.pool is None:
            await self.init_pool()
        
        query = """
            INSERT INTO price_hit_log (ticker, price_level)
            VALUES ($1, $2)
            ON CONFLICT (ticker, price_level, (hit_timestamp::date)) DO NOTHING
        """
        try:
            async with self.pool.acquire() as conn:
                # Note: We only log the price_level and let the DB handle the timestamp/date
                await conn.execute(query, ticker, level)
                return True
        except Exception as e:
            print(f"DB UTIL ERROR: Failed to insert price hit log: {e}")
            return False

    async def check_if_price_hit_logged_today(self, ticker, level, check_date):
        """
        Checks if a hit for the specific price level has already been logged
        in price_hit_log for the given date.
        """
        if self.pool is None:
            await self.init_pool()
            
        query = """
            SELECT 1 FROM price_hit_log
            WHERE ticker = $1
            AND price_level = $2
            AND hit_timestamp::date = $3
        """
        try:
            async with self.pool.acquire() as conn:
                val = await conn.fetchval(query, ticker, level, check_date)
                return val is not None
        except Exception as e:
            print(f"DB UTIL ERROR: Failed to check price hit log: {e}")
            return True # Default to True to prevent double-triggering on error

    async def fetch_watchlist_data(self):
        """
        Joins watchlist, details, latest price, and portfolio status.
        Uses raw_stock_valuations to project the next financial event based on the PENULTIMATE release + 1 year.
        Filters OUT 'Closed', 'Pending', and 'WL-Sleep'.
        """
        if self.pool is None:
            await self.init_pool()
            
        query = """
            SELECT 
                w.ticker, sd.full_name, sd.priority, w.status,
                w.entry_price, w.stop_loss, w.price_level as target,
                p.close_price,
                
                -- Strategy
                sa.strategy,

                -- Latest News (SENS)
                (SELECT trigger_content FROM action_log a 
                 WHERE a.ticker = w.ticker AND a.trigger_type = 'SENS' AND a.is_read = false
                 ORDER BY a.log_timestamp DESC LIMIT 1) as latest_news,
                 
                -- Check if currently held in Portfolio
                (SELECT count(*) FROM portfolio_holdings ph 
                 WHERE ph.ticker = w.ticker) > 0 as is_holding,

                -- Projected Next Event (Penultimate Release + 1 Year)
                -- We select the 2nd most recent release date (OFFSET 1) and add 1 year
                (SELECT (results_release_date + interval '1 year')::date 
                 FROM raw_stock_valuations rsv 
                 WHERE rsv.ticker = w.ticker 
                 ORDER BY rsv.results_release_date DESC 
                 LIMIT 1 OFFSET 1) as next_event_date

            FROM watchlist w
            JOIN stock_details sd ON w.ticker = sd.ticker
            LEFT JOIN stock_analysis sa ON w.ticker = sa.ticker
            LEFT JOIN LATERAL (
                SELECT close_price FROM daily_stock_data 
                WHERE ticker = w.ticker ORDER BY trade_date DESC LIMIT 1
            ) p ON true
            
            WHERE w.status NOT IN ('Closed', 'Pending', 'WL-Sleep')
            
            ORDER BY 
                CASE WHEN sd.priority = 'A' THEN 1 
                     WHEN sd.priority = 'B' THEN 2 
                     ELSE 3 END, 
                w.ticker
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query)
            return [dict(row) for row in rows]

    async def fetch_strategy(self, ticker):
        """Fetch strategy for a given ticker."""
        if self.pool is None:
            await self.init_pool()
            
        query = "SELECT strategy FROM stock_analysis WHERE ticker = $1"
        async with self.pool.acquire() as conn:
            res = await conn.fetchval(query, ticker)
            return res if res else "No strategy defined."

    async def fetch_sens_feed(self):
        """Fetches unread SENS triggers."""
        if self.pool is None:
            await self.init_pool()
            
        query = """
            SELECT a.log_timestamp, a.ticker, a.trigger_content 
            FROM action_log a 
            WHERE a.trigger_type = 'SENS' AND a.is_read = false  
            ORDER BY a.log_timestamp DESC
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query)
            return [tuple(row.values()) for row in rows]

    async def select_tickers_for_valuation(self, limit=None):
        """Select tickers for valuation based on priority and missing data."""
        if self.pool is None:
            await self.init_pool()
            
        query = """
            WITH ticker_valuation_status AS (
                SELECT 
                    w.ticker,
                    sd.priority,
                    EXISTS(SELECT 1 FROM portfolio_holdings ph WHERE ph.ticker = w.ticker) as in_portfolio,
                    (SELECT MAX(valuation_date) FROM stock_valuations sv WHERE sv.ticker = w.ticker) as last_valuation_date
                FROM watchlist w
                JOIN stock_details sd ON w.ticker = sd.ticker
            )
            SELECT ticker
            FROM ticker_valuation_status
            ORDER BY 
                last_valuation_date ASC NULLS FIRST,
                in_portfolio DESC,
                CASE 
                    WHEN priority = 'A' THEN 1 
                    WHEN priority = 'B' THEN 2 
                    ELSE 3 
                END,
                ticker
        """
        
        if limit is not None:
            query += " LIMIT $1"
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, limit)
        else:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query)
        
        return [row['ticker'] for row in rows]

    async def get_latest_price(self, ticker: str):
        """Get the latest price for a ticker."""
        if self.pool is None:
            await self.init_pool()
            
        query = """
            SELECT trade_date, close_price 
            FROM daily_stock_data 
            WHERE ticker = $1 
            ORDER BY trade_date DESC 
            LIMIT 1
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, ticker)
            return dict(row) if row else None

    async def get_heps_growth(self, ticker: str):
        """Compute HEPS growth rate from historical_earnings."""
        if self.pool is None:
            await self.init_pool()
            
        query = """
            SELECT heps
            FROM historical_earnings
            WHERE ticker = $1
            ORDER BY results_date DESC
            LIMIT 2
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, ticker)
            
            if len(rows) < 2:
                return None
            
            latest_heps = float(rows[0]['heps'])
            previous_heps = float(rows[1]['heps'])
            
            if previous_heps <= 0:
                return None
            
            growth = (latest_heps / previous_heps) - 1
            return growth

    async def insert_valuation(self, valuation_data: dict):
        """Insert a new valuation row into stock_valuations."""
        if self.pool is None:
            await self.init_pool()
            
        delete_query = "DELETE FROM stock_valuations WHERE ticker = $1"
        
        insert_query = """
            INSERT INTO stock_valuations (
                ticker, valuation_date, price_zarc,
                heps_12m_zarc, dividend_12m_zarc, cash_gen_ps_zarc, nav_ps_zarc,
                earnings_yield, dividend_yield, cash_flow_yield,
                quick_ratio, p_to_nav, peg_ratio
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13
            )
        """
        
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(delete_query, valuation_data['ticker'])
                await conn.execute(
                    insert_query,
                    valuation_data['ticker'],
                    valuation_data['valuation_date'],
                    valuation_data.get('price_zarc'),
                    valuation_data.get('heps_12m_zarc'),
                    valuation_data.get('dividend_12m_zarc'),
                    valuation_data.get('cash_gen_ps_zarc'),
                    valuation_data.get('nav_ps_zarc'),
                    valuation_data.get('earnings_yield'),
                    valuation_data.get('dividend_yield'),
                    valuation_data.get('cash_flow_yield'),
                    valuation_data.get('quick_ratio'),
                    valuation_data.get('p_to_nav'),
                    valuation_data.get('peg_ratio')
                )
                print(f"  [DB DEBUG] Successfully committed valuation for {valuation_data['ticker']}")
                return True
        except Exception as e:
            print(f"Error inserting valuation for {valuation_data.get('ticker', 'unknown')}: {e}")
            return False
    
    async def upsert_raw_fundamentals(self, ticker: str, periods_data: list):
        """Insert or update raw_stock_valuations for multiple periods."""
        if self.pool is None:
            await self.init_pool()
        
        upsert_query = """
        INSERT INTO raw_stock_valuations (
            ticker, results_period_end, results_period_label,
            results_release_date,
            heps_12m_zarc, dividend_12m_zarc, cash_gen_ps_zarc, nav_ps_zarc,
            quick_ratio, source
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10
        )
        ON CONFLICT (ticker, results_period_end) 
        DO UPDATE SET
            results_period_label = EXCLUDED.results_period_label,
            results_release_date = EXCLUDED.results_release_date,
            heps_12m_zarc = EXCLUDED.heps_12m_zarc,
            dividend_12m_zarc = EXCLUDED.dividend_12m_zarc,
            cash_gen_ps_zarc = EXCLUDED.cash_gen_ps_zarc,
            nav_ps_zarc = EXCLUDED.nav_ps_zarc,
            quick_ratio = EXCLUDED.quick_ratio,
            source = EXCLUDED.source
        """
        
        try:
            async with self.pool.acquire() as conn:
                for period in periods_data:
                    await conn.execute(
                        upsert_query,
                        ticker,
                        period['results_period_end'],
                        period['results_period_label'],
                        period.get('results_release_date'),
                        period.get('heps_12m_zarc'),
                        period.get('dividend_12m_zarc'),
                        period.get('cash_gen_ps_zarc'),
                        period.get('nav_ps_zarc'),
                        period.get('quick_ratio'),
                        'sharedata'
                    )
                
                print(f"  [DB DEBUG] Successfully upserted {len(periods_data)} periods for {ticker}")
                return True
        except Exception as e:
            print(f"Error upserting raw fundamentals for {ticker}: {e}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            return False
    
    async def get_latest_raw_fundamentals(self, ticker: str):
        """Get the most recent period fundamentals for a ticker."""
        if self.pool is None:
            await self.init_pool()
        
        query = """
            SELECT * FROM raw_stock_valuations
            WHERE ticker = $1
            ORDER BY results_period_end DESC
            LIMIT 1
        """
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, ticker)
            return dict(row) if row else None
    
    async def get_historical_prices(self, ticker: str, days: int):
        """Get historical OHLC prices for a ticker over the specified number of days."""
        if self.pool is None:
            await self.init_pool()
        
        query = """
            SELECT trade_date, open_price, high_price, low_price, close_price
            FROM daily_stock_data
            WHERE ticker = $1
              AND trade_date >= CURRENT_DATE - INTERVAL '1 day' * $2
            ORDER BY trade_date ASC
        """
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, ticker, days)
            return [dict(row) for row in rows]
    
    async def get_research_data(self, ticker: str):
        """Get all research data for a ticker from stock_analysis table."""
        if self.pool is None:
            await self.init_pool()
        
        query = """
            SELECT 
                strategy,
                research,
                deepresearch,
                deepresearch_date
            FROM stock_analysis
            WHERE ticker = $1
        """
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, ticker)
            return dict(row) if row else None

    async def get_sens_for_ticker(self, ticker: str, limit=50):
        """Get SENS announcements for a ticker."""
        if self.pool is None:
            await self.init_pool()
        
        query = """
            SELECT publication_datetime, content
            FROM SENS
            WHERE ticker = $1
            ORDER BY publication_datetime DESC
            LIMIT $2
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, ticker, limit)
            return [dict(row) for row in rows]