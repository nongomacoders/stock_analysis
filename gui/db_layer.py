import asyncpg
from config import DB_CONFIG

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

    async def fetch_watchlist_data(self):
        """
        Joins watchlist, details, latest price, and portfolio status.
        Filters OUT 'Closed', 'Pending', and 'WL-Sleep'.
        """
        if self.pool is None:
            await self.init_pool()
            
        query = """
            SELECT 
                w.ticker, sd.full_name, sd.priority, w.status,
                w.entry_price, w.stop_loss, w.price_level as target,
                p.close_price,
                sd.earnings_q1, sd.earnings_q2, sd.earnings_q3, sd.earnings_q4,
                sd.update_q1, sd.update_q2, sd.update_q3, sd.update_q4,
                
                -- Strategy
                sa.strategy,

                -- Latest News (SENS)
                (SELECT trigger_content FROM action_log a 
                 WHERE a.ticker = w.ticker AND a.trigger_type = 'SENS' AND a.is_read = false
                 ORDER BY a.log_timestamp DESC LIMIT 1) as latest_news,
                 
                -- Check if currently held in Portfolio
                (SELECT count(*) FROM portfolio_holdings ph 
                 WHERE ph.ticker = w.ticker) > 0 as is_holding

            FROM watchlist w
            JOIN stock_details sd ON w.ticker = sd.ticker
            LEFT JOIN stock_analysis sa ON w.ticker = sa.ticker
            LEFT JOIN LATERAL (
                SELECT close_price FROM daily_stock_data 
                WHERE ticker = w.ticker ORDER BY trade_date DESC LIMIT 1
            ) p ON true
            
            -- --- UPDATED FILTER ---
            WHERE w.status NOT IN ('Closed', 'Pending', 'WL-Sleep')
            -- ----------------------
            
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
        """
        Select tickers for valuation based on:
        1. Prioritize tickers with missing valuations (NULL) FIRST
        2. Then portfolio holdings
        3. Then oldest valuation dates
        4. Then priority (A>B>C)
        5. Then alphabetically
        
        Args:
            limit: Number of tickers to return, or None for all tickers
        
        Returns list of ticker strings
        """
        if self.pool is None:
            await self.init_pool()
            
        query = """
            WITH ticker_valuation_status AS (
                SELECT 
                    w.ticker,
                    sd.priority,
                    -- Check if in portfolio
                    EXISTS(SELECT 1 FROM portfolio_holdings ph WHERE ph.ticker = w.ticker) as in_portfolio,
                    -- Get latest valuation date or NULL
                    (SELECT MAX(valuation_date) FROM stock_valuations sv WHERE sv.ticker = w.ticker) as last_valuation_date
                FROM watchlist w
                JOIN stock_details sd ON w.ticker = sd.ticker
            )
            SELECT ticker
            FROM ticker_valuation_status
            ORDER BY 
                -- First: missing valuations (NULL comes first with NULLS FIRST)
                last_valuation_date ASC NULLS FIRST,
                -- Second: portfolio holdings
                in_portfolio DESC,
                -- Third: priority A > B > C
                CASE 
                    WHEN priority = 'A' THEN 1 
                    WHEN priority = 'B' THEN 2 
                    ELSE 3 
                END,
                -- Fourth: alphabetically
                ticker
        """
        
        # Add LIMIT clause only if limit is specified
        if limit is not None:
            query += " LIMIT $1"
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, limit)
        else:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query)
        
        return [row['ticker'] for row in rows]

    async def get_latest_price(self, ticker: str):
        """
        Get the latest price for a ticker from daily_stock_data.
        
        Returns dict with {'trade_date': date, 'close_price': Decimal} or None
        """
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
        """
        Compute HEPS growth rate from historical_earnings.
        Takes two most recent periods and returns: (latest - previous) / previous
        
        Returns growth rate as decimal (0.15 for 15% growth) or None
        """
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
        """
        Insert a new valuation row into stock_valuations.
        Deletes any existing rows for the ticker first to ensure only one latest row per ticker.
        
        Expected keys in valuation_data:
        - ticker, valuation_date, price_zarc
        - heps_12m_zarc, dividend_12m_zarc, cash_gen_ps_zarc, nav_ps_zarc
        - earnings_yield, dividend_yield, cash_flow_yield
        - quick_ratio, p_to_nav, peg_ratio
        
        Returns True on success, False on failure
        """
        if self.pool is None:
            await self.init_pool()
            
        delete_query = """
            DELETE FROM stock_valuations WHERE ticker = $1
        """
        
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
                # Delete old rows for this ticker
                await conn.execute(delete_query, valuation_data['ticker'])
                
                # Insert new row
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
                return True
        except Exception as e:
            print(f"Error inserting valuation for {valuation_data.get('ticker', 'unknown')}: {e}")
            return False