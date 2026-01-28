from typing import Optional, List, Dict, Any, Callable

# --- IMPORTS ---
from modules.data.watchlist import select_tickers_for_valuation
from modules.data.fundamentals import upsert_raw_fundamentals
from modules.data.scraper import FundamentalsScraper


class RawFundamentalsLoader:
    """
    Raw Fundamentals Loader - Orchestrates the population of raw_stock_valuations 
    with multi-year data from ShareData.
    """

    def __init__(self, log_callback: Optional[Callable] = None):
        """
        Initialize the loader.
        
        Args:
            log_callback: Optional logging function, defaults to print
        """
        self.log = log_callback if log_callback else print
        self.scraper = FundamentalsScraper(log_callback=self.log)

    async def run_fundamentals_update(
        self, tickers: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Main orchestration method for updating raw fundamentals.
        
        Args:
            tickers: Optional list of ticker symbols. If None, fetches from database.
            
        Returns:
            Dictionary with update statistics (succeeded, failed, tickers, total_periods)
        """
        self.log("Starting raw fundamentals update...")

        if tickers is None:
            self.log("Selecting tickers from database...")
            tickers = await select_tickers_for_valuation(limit=None)

        if not tickers:
            self.log("No tickers to process.")
            return {"succeeded": 0, "failed": 0, "tickers": [], "total_periods": 0}

        # Indices (eg: '^J200.JO') do not have fundamentals on ShareData.
        # Filter them out early so we don't waste time scraping.
        normalized = [t.strip() for t in tickers if t and t.strip()]
        skipped_tickers = [t for t in normalized if t.startswith("^")]
        process_tickers = [t for t in normalized if not t.startswith("^")]

        if skipped_tickers:
            self.log(
                f"Skipping {len(skipped_tickers)} index tickers (no fundamentals): {', '.join(skipped_tickers)}"
            )

        if not process_tickers:
            self.log("No non-index tickers to process.")
            return {
                "succeeded": 0,
                "failed": 0,
                "skipped": len(skipped_tickers),
                "tickers": [],
                "skipped_tickers": skipped_tickers,
                "total_periods": 0,
            }

        self.log(f"Processing {len(process_tickers)} tickers: {', '.join(process_tickers)}")

        succeeded = 0
        failed = 0
        total_periods = 0

        for ticker in process_tickers:
            try:
                self.log(f"\n{'='*60}")
                self.log(f"Processing {ticker}...")

                # Scrape multi-year fundamentals
                all_periods_data = await self.scraper.scrape_multi_year_fundamentals(
                    ticker
                )

                if not all_periods_data:
                    self.log(f"  [ERROR] Failed to scrape data for {ticker}")
                    failed += 1
                    continue

                self.log(
                    f"  [OK] Extracted total {len(all_periods_data)} periods for {ticker}"
                )

                # Upsert into database
                success = await upsert_raw_fundamentals(ticker, all_periods_data)

                if success:
                    self.log(f"  [OK] Upserted {len(all_periods_data)} periods")
                    succeeded += 1
                    total_periods += len(all_periods_data)
                else:
                    self.log(f"  [ERROR] Failed to insert data for {ticker}")
                    failed += 1

            except Exception as e:
                self.log(f"  [ERROR] Error processing {ticker}: {e}")
                failed += 1
                continue

        return {
            "succeeded": succeeded,
            "failed": failed,
            "skipped": len(skipped_tickers),
            "tickers": process_tickers,
            "skipped_tickers": skipped_tickers,
            "total_periods": total_periods,
        }
