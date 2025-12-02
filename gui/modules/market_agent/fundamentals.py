from datetime import date
from core.db.engine import DBEngine
from modules.data.loader import RawFundamentalsLoader


async def get_tickers_needing_update() -> list[str]:
    """
    Identify tickers that need fundamentals updates based on:
    1. Expected release date (from historical gap pattern)
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
                in_watchlist,
                in_portfolio,
                -- Calculate gap between releases (defaults to 180 days if only one release)
                CASE 
                    WHEN second_last_release_date IS NOT NULL THEN 
                        last_release_date - second_last_release_date
                    ELSE 
                        180
                END as release_gap_days,
                -- Expected next release date
                CASE 
                    WHEN second_last_release_date IS NOT NULL THEN 
                        last_release_date + (last_release_date - second_last_release_date)
                    ELSE 
                        last_release_date + 180
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
        SELECT ticker
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
    
    rows = await DBEngine.fetch(query)
    return [row["ticker"] for row in rows]


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
    
    print(f"Found {len(tickers)} ticker(s) needing updates: {', '.join(tickers)}")
    
    # Run the loader for these specific tickers
    loader = RawFundamentalsLoader(log_callback=print)
    result = await loader.run_fundamentals_update(tickers=tickers)
    
    print(f"\nFundamentals Update Summary:")
    print(f"  Succeeded: {result['succeeded']}")
    print(f"  Failed: {result['failed']}")
    print(f"  Total periods: {result['total_periods']}")
