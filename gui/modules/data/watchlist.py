from core.db.engine import DBEngine


async def fetch_watchlist_data():
    """
    Joins watchlist, details, latest price, and portfolio status.
    """
    query = """
        SELECT 
            w.ticker, sd.full_name, sd.priority, w.status,
            w.entry_price, w.stop_loss, w.price_level as target,
            p.close_price,
            sa.strategy,
            (SELECT trigger_content FROM action_log a 
                WHERE a.ticker = w.ticker AND a.trigger_type = 'SENS' AND a.is_read = false
                ORDER BY a.log_timestamp DESC LIMIT 1) as latest_news,
            (SELECT count(*) FROM portfolio_holdings ph 
                WHERE ph.ticker = w.ticker) > 0 as is_holding,
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
    rows = await DBEngine.fetch(query)
    return [dict(row) for row in rows]


async def select_tickers_for_valuation(limit=None):
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
        SELECT ticker FROM ticker_valuation_status
        ORDER BY last_valuation_date ASC NULLS FIRST, in_portfolio DESC, priority, ticker
    """
    if limit:
        query += f" LIMIT {limit}"  # Simple limit append for int safety

    rows = await DBEngine.fetch(query)
    return [row["ticker"] for row in rows]
