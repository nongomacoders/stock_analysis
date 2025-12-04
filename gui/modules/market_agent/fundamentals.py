from datetime import date
from core.db.engine import DBEngine
import logging

logger = logging.getLogger(__name__)
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
    
    logger.debug("\n" + '='*80)
    logger.debug("MARKET AGENT - FUNDAMENTALS TICKER SELECTION")
    logger.debug('%s', '='*80)
    
    rows = await DBEngine.fetch(query)
    
    if rows:
        logger.info("CURRENT DATE: %s", rows[0]['today'])
        logger.info('%s', '='*80)
        
        for row in rows:
            ticker = row['ticker']
            last_rel = row['last_release_date']
            second_rel = row['second_last_release_date']
            next_exp = row['expected_next_date']
            days_since = row['days_since_last']
            last_upd = row['last_updated_at']
            today = row['today']
            
            logger.info("%s", '\n' + ('='*80))
            logger.info("TICKER: %s", ticker)
            logger.info('%s', '='*80)
            logger.info("  [1] Most recent release:    %s", last_rel)
            logger.info("  [2] 2nd recent release:     %s", second_rel)
            logger.info("  [*] Last updated (scraped): %s", last_upd)
            
            if second_rel:
                logger.info("\n  CALCULATION:")
                logger.info("    Next Expected = 2nd Recent + 1 Year")
                logger.info("    Next Expected = %s + 1 year", second_rel)
                logger.info("    Next Expected = %s", (next_exp.date() if hasattr(next_exp, 'date') else next_exp))
            else:
                logger.info("\n  CALCULATION:")
                logger.info("    Next Expected = %s (default +180 days)", (next_exp.date() if hasattr(next_exp, 'date') else next_exp))
            
            logger.info("\n  FILTER LOGIC:")
            logger.info("    Current Date:      %s", today)
            logger.info("    Next Expected:     %s", (next_exp.date() if hasattr(next_exp, 'date') else next_exp))
            logger.info("    Days Since Last:   %s", days_since)
            
            if last_rel:
                next_exp_date = next_exp.date() if hasattr(next_exp, 'date') else next_exp
                check1 = today >= next_exp_date
                check2 = days_since >= 150
                logger.info("    Check 1: %s >= %s = %s", today, next_exp_date, check1)
                logger.info("    Check 2: %s >= 150 = %s", days_since, check2)
                logger.info("    Both checks: %s", (check1 and check2))
                status = "[PASS] - Will be loaded" if (check1 and check2) else "[FAIL] - Criteria not met"
            else:
                status = "[PASS] - No data, will be loaded"
                
            logger.info("\n  RESULT: %s", status)
            logger.info('%s', '='*80)
        
        tickers = [row["ticker"] for row in rows]
        logger.info('%s', '\n' + ('='*80))
        logger.info("SELECTED TICKERS (%s): %s", len(tickers), ', '.join(tickers))
        logger.info('%s', '='*80 + '\n')
        return tickers
    else:
        logger.info("No tickers found needing updates")
        logger.info('%s', '='*80 + '\n')
        return []


async def run_fundamentals_check():
    """
    Main worker function to check and update fundamentals.
    Called daily by the market agent.
    """
    logger.info("+++ Running Fundamentals Check +++")
    
    # Get tickers needing update
    tickers = await get_tickers_needing_update()
    
    if not tickers:
        logger.info("No tickers need fundamentals updates today.")
        return
    
    # Run the loader for these specific tickers
    loader = RawFundamentalsLoader(log_callback=logger.info)
    result = await loader.run_fundamentals_update(tickers=tickers)
    
    logger.info("\nFundamentals Update Summary:")
    logger.info("  Succeeded: %s", result['succeeded'])
    logger.info("  Failed: %s", result['failed'])
    logger.info("  Total periods: %s", result['total_periods'])
