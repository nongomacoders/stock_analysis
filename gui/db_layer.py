import psycopg2
from psycopg2.extras import DictCursor
from config import DB_CONFIG

class DBLayer:
    def __init__(self):
        self.config = DB_CONFIG

    def get_connection(self):
        return psycopg2.connect(**self.config)

    def fetch_watchlist_data(self):
        """
        Joins watchlist, details, latest price, and portfolio status.
        Filters OUT 'Closed', 'Pending', and 'WL-Sleep'.
        """
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
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute(query)
                return [dict(row) for row in cur.fetchall()]

    def fetch_strategy(self, ticker):
        query = "SELECT strategy FROM stock_analysis WHERE ticker = %s"
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (ticker,))
                res = cur.fetchone()
                return res[0] if res else "No strategy defined."
    

    def fetch_sens_feed(self):
        """Fetches unread SENS triggers."""
        query = """
            SELECT a.log_timestamp, a.ticker, a.trigger_content 
            FROM action_log a 
            WHERE a.trigger_type = 'SENS' AND a.is_read = false
            ORDER BY a.log_timestamp DESC
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                return cur.fetchall()