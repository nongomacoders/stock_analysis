from datetime import date
from core.db.engine import DBEngine
from modules.data.loader import RawFundamentalsLoader


async def get_tickers_needing_update() -> list[str]:
    """
    Identify tickers that need fundamentals updates based on:
    1. Expected release date (2nd most recent + 1 year, for alternating interim/final pattern)
    2. Minimum 150 days since last update
    3. Priority: no data > watchlist > portfolio > others
    
    Returns:
        List of tickers to update
    """
    query = """
        WITH ticker_release_patterns AS (
            SELECT 
                sd.ticker,
                -- Get last two release dates
                (
                    SELECT results_release_date 
                    FROM raw_stock_valuations rsv 
                    WHERE rsv.ticker = sd.ticker 
                    ORDER BY results_release_date DESC 
                    LIMIT 1
                ) as last_release_date,
                (
                    SELECT results_release_date 
                    FROM raw_stock_valuations rsv 
                    WHERE rsv.ticker = sd.ticker 
                    ORDER BY results_release_date DESC 
                    LIMIT 1 OFFSET 1
                ) as second_last_release_date,
                (
                    SELECT created_at 
                    FROM raw_stock_valuations rsv 
                    WHERE rsv.ticker = sd.ticker 
                    ORDER BY created_at DESC 
                    LIMIT 1
                ) as last_updated_at,
                -- Priority flags
                EXISTS(SELECT 1 FROM watchlist w WHERE w.ticker = sd.ticker) as in_watchlist,
                EXISTS(SELECT 1 FROM portfolio_holdings ph WHERE ph.ticker = sd.ticker) as in_portfolio
            FROM stock_details sd
        ),
        ticker_update_status AS (
            SELECT 
                ticker,
                last_release_date,
                second_last_release_date,
                last_updated_at,
                in_watchlist,
                in_portfolio,
                -- Expected next release date: 2nd last + 1 year (for interim/final alternating pattern)
                CASE 
                    WHEN second_last_release_date IS NOT NULL THEN 
                        second_last_release_date + interval '1 year'
                    ELSE 
                        last_release_date + interval '180 days'
                END as expected_next_date,
                -- Days since last update
                CASE 
                    WHEN last_release_date IS NOT NULL THEN 
                        CURRENT_DATE - last_release_date
                    ELSE 
                        NULL
                END as days_since_last
            FROM ticker_release_patterns
        )
        SELECT ticker, last_release_date, second_last_release_date, expected_next_date, 
               days_since_last, last_updated_at, CURRENT_DATE as today
        FROM ticker_update_status
        WHERE 
            -- Condition 1: No data at all (prioritize)
            last_release_date IS NULL
            OR
            -- Condition 2: Has data but meets update criteria
            (
                CURRENT_DATE >= expected_next_date 
                AND days_since_last >= 150
            )
        ORDER BY 
            -- Priority: no data first
            CASE WHEN last_release_date IS NULL THEN 1 ELSE 2 END,
            -- Then by watchlist/portfolio status
            in_portfolio DESC,
            in_watchlist DESC,
            ticker
    """
    
    print("\n" + "="*80)
    print("DEBUG: MARKET AGENT - FUNDAMENTALS TICKER SELECTION")
    print("="*80)
    
    rows = await DBEngine.fetch(query)
    
    if rows:
        print(f"CURRENT DATE: {rows[0]['today']}")
        print("="*80)
        
        for row in rows:
            ticker = row['ticker']
            last_rel = row['last_release_date']
            second_rel = row['second_last_release_date']
            next_exp = row['expected_next_date']
            days_since = row['days_since_last']
            last_upd = row['last_updated_at']
            today = row['today']
            
            print(f"\n{'='*80}")
            print(f"TICKER: {ticker}")
            print(f"{'='*80}")
            print(f"  [1] Most recent release:    {last_rel}")
            print(f"  [2] 2nd recent release:     {second_rel}")
            print(f"  [*] Last updated (scraped): {last_upd}")
            
            if second_rel:
                print(f"\n  CALCULATION:")
                print(f"    Next Expected = 2nd Recent + 1 Year")
                print(f"    Next Expected = {second_rel} + 1 year")
                print(f"    Next Expected = {next_exp.date() if hasattr(next_exp, 'date') else next_exp}")
            else:
                print(f"\n  CALCULATION:")
                print(f"    Next Expected = {next_exp.date() if hasattr(next_exp, 'date') else next_exp} (default +180 days)")
            
            print(f"\n  FILTER LOGIC:")
            print(f"    Current Date:      {today}")
            print(f"    Next Expected:     {next_exp.date() if hasattr(next_exp, 'date') else next_exp}")
            print(f"    Days Since Last:   {days_since}")
            
            if last_rel:
                next_exp_date = next_exp.date() if hasattr(next_exp, 'date') else next_exp
                check1 = today >= next_exp_date
                check2 = days_since >= 150
                print(f"    Check 1: {today} >= {next_exp_date} = {check1}")
                print(f"    Check 2: {days_since} >= 150 = {check2}")
                print(f"    Both checks: {check1 and check2}")
                status = "[PASS] - Will be loaded" if (check1 and check2) else "[FAIL] - Criteria not met"
            else:
                status = "[PASS] - No data, will be loaded"
                
            print(f"\n  RESULT: {status}")
            print(f"{'='*80}")
        
        tickers = [row["ticker"] for row in rows]
        print("\n" + "="*80)
        print(f"SELECTED TICKERS ({len(tickers)}): {', '.join(tickers)}")
        print("="*80 + "\n")
        return tickers
    else:
        print("No tickers found needing updates")
        print("="*80 + "\n")
        return []


async def run_fundamentals_check():
    """
    Main worker function to check and update fundamentals.
    Called daily by the market agent.
    """
    print("+++ Running Fundamentals Check +++")
    
    # Get tickers needing update
    tickers = await get_tickers_needing_update()
    
    if not tickers:
        print("No tickers need fundamentals updates today.")
        return
    
    # Run the loader for these specific tickers
    loader = RawFundamentalsLoader(log_callback=print)
    result = await loader.run_fundamentals_update(tickers=tickers)
    
    print(f"\nFundamentals Update Summary:")
    print(f"  Succeeded: {result['succeeded']}")
    print(f"  Failed: {result['failed']}")
    print(f"  Total periods: {result['total_periods']}")
