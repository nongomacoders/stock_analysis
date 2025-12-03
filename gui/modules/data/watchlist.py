from core.db.engine import DBEngine


async def fetch_watchlist_data():
    """
    Joins watchlist, details, latest price, and portfolio status.
    """
    query = """
        SELECT 
            w.ticker, sd.full_name, sd.priority, w.status,
            w.entry_price, w.stop_loss, w.target_price as target,
            p.close_price,
            sa.strategy,
            (SELECT trigger_content FROM action_log a 
                WHERE a.ticker = w.ticker AND a.trigger_type = 'SENS' AND a.is_read = false
                ORDER BY a.log_timestamp DESC LIMIT 1) as latest_news,
            (SELECT count(*) FROM portfolio_holdings ph 
                WHERE ph.ticker = w.ticker) > 0 as is_holding,
            (SELECT count(*) FROM action_log a 
                WHERE a.ticker = w.ticker AND a.is_read = false) as unread_log_count,
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
    # Debug query to show all tickers with their next expected dates
    debug_query = """
        WITH ticker_valuation_status AS (
            SELECT 
                w.ticker,
                sd.priority,
                EXISTS(SELECT 1 FROM portfolio_holdings ph WHERE ph.ticker = w.ticker) as in_portfolio,
                (SELECT MAX(results_release_date) FROM raw_stock_valuations rsv WHERE rsv.ticker = w.ticker) as last_valuation_date,
                (SELECT (results_release_date + interval '1 year')::date 
                    FROM raw_stock_valuations rsv 
                    WHERE rsv.ticker = w.ticker 
                    ORDER BY rsv.results_release_date DESC 
                    LIMIT 1 OFFSET 1) as next_expected_date,
                (SELECT results_release_date 
                    FROM raw_stock_valuations rsv 
                    WHERE rsv.ticker = w.ticker 
                    ORDER BY rsv.results_release_date DESC 
                    LIMIT 1) as most_recent_date,
                (SELECT results_release_date 
                    FROM raw_stock_valuations rsv 
                    WHERE rsv.ticker = w.ticker 
                    ORDER BY rsv.results_release_date DESC 
                    LIMIT 1 OFFSET 1) as second_recent_date,
                (SELECT created_at 
                    FROM raw_stock_valuations rsv 
                    WHERE rsv.ticker = w.ticker 
                    ORDER BY rsv.created_at DESC 
                    LIMIT 1) as last_updated_at
            FROM watchlist w
            JOIN stock_details sd ON w.ticker = sd.ticker
        )
        SELECT ticker, next_expected_date, most_recent_date, second_recent_date, last_updated_at, CURRENT_DATE as today
        FROM ticker_valuation_status
        ORDER BY ticker
    """
    
    debug_rows = await DBEngine.fetch(debug_query)
    
    print("\n" + "="*80)
    print("DEBUG: TICKER SELECTION FOR VALUATION - DETAILED ANALYSIS")
    print("="*80)
    print(f"CURRENT DATE: {debug_rows[0]['today'] if debug_rows else 'N/A'}")
    print("="*80)
    
    for row in debug_rows:
        ticker = row['ticker']
        next_exp = row['next_expected_date']
        most_recent = row['most_recent_date']
        second_recent = row['second_recent_date']
        last_updated = row['last_updated_at']
        today = row['today']
        
        print(f"\n{'='*80}")
        print(f"TICKER: {ticker}")
        print(f"{'='*80}")
        print(f"  [1] Most recent results release date:  {most_recent}")
        print(f"  [2] 2nd recent results release date:   {second_recent}")
        print(f"  [*] Last updated (data scraped):       {last_updated}")
        
        if second_recent:
            print(f"\n  CALCULATION:")
            print(f"    Next Expected = 2nd Recent + 1 Year")
            print(f"    Next Expected = {second_recent} + 1 year = {next_exp}")
        else:
            print(f"\n  CALCULATION:")
            print(f"    Next Expected = NULL (insufficient data)")
            
        print(f"\n  FILTER LOGIC:")
        print(f"    Current Date:    {today}")
        print(f"    Next Expected:   {next_exp}")
        
        if next_exp:
            is_eligible = next_exp <= today
            print(f"    Comparison:      {next_exp} <= {today} = {is_eligible}")
            status = "[PASS] - Will be loaded" if is_eligible else "[FAIL] - Too early, will be skipped"
        else:
            is_eligible = True
            status = "[PASS] - No data yet, will be loaded"
            print(f"    Comparison:      NULL (always passes)")
            
        print(f"\n  RESULT: {status}")
        print(f"{'='*80}")
    
    # Now run the actual query with filter
    query = """
        WITH ticker_valuation_status AS (
            SELECT 
                w.ticker,
                sd.priority,
                EXISTS(SELECT 1 FROM portfolio_holdings ph WHERE ph.ticker = w.ticker) as in_portfolio,
                (SELECT MAX(results_release_date) FROM raw_stock_valuations rsv WHERE rsv.ticker = w.ticker) as last_valuation_date,
                (SELECT (results_release_date + interval '1 year')::date 
                    FROM raw_stock_valuations rsv 
                    WHERE rsv.ticker = w.ticker 
                    ORDER BY rsv.results_release_date DESC 
                    LIMIT 1 OFFSET 1) as next_expected_date
            FROM watchlist w
            JOIN stock_details sd ON w.ticker = sd.ticker
        )
        SELECT ticker FROM ticker_valuation_status
        WHERE next_expected_date IS NULL OR next_expected_date <= CURRENT_DATE
        ORDER BY last_valuation_date ASC NULLS FIRST, in_portfolio DESC, priority, ticker
    """
    if limit:
        query += f" LIMIT {limit}"  # Simple limit append for int safety

    rows = await DBEngine.fetch(query)
    selected_tickers = [row["ticker"] for row in rows]
    
    print("\n" + "="*80)
    print(f"SELECTED TICKERS FOR LOADING ({len(selected_tickers)}):")
    print("="*80)
    print(", ".join(selected_tickers) if selected_tickers else "NONE")
    print("="*80 + "\n")
    
    return selected_tickers
