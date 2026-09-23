from typing import Optional, List, Dict, Any, Callable

# --- IMPORTS ---
from modules.data.watchlist import select_tickers_for_valuation
from modules.data.ingestion_evidence import ingest_sharedata_tables
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
        self, tickers: Optional[List[str]] = None, ingestion_run_id=None
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
        total_written = 0
        failure_codes = []

        for ticker in process_tickers:
            try:
                self.log(f"\n{'='*60}")
                self.log(f"Processing {ticker}...")

                # Scrape multi-year fundamentals
                table_sets = await self.scraper.scrape_tables(ticker)

                if not table_sets:
                    self.log(f"  [ERROR] Failed to scrape data for {ticker}")
                    failed += 1
                    failure_codes.append("source_no_data")
                    continue

                fetched, written = await ingest_sharedata_tables(ticker, table_sets, ingestion_run_id=ingestion_run_id)
                self.log(f"  [OK] Parsed {fetched} observations; wrote {written} new observations")
                succeeded += 1
                total_periods += fetched
                total_written += written

            except Exception as e:
                self.log(f"  [ERROR] Error processing {ticker}: {e}")
                failure_codes.append("parser_failure" if isinstance(e, ValueError) else
                    "database_failure" if type(e).__module__.startswith("asyncpg") else "worker_failure")
                failed += 1
                continue

        return {
            "succeeded": succeeded,
            "failed": failed,
            "skipped": len(skipped_tickers),
            "tickers": process_tickers,
            "skipped_tickers": skipped_tickers,
            "total_periods": total_periods,
            "total_written": total_written,
            "failure_codes": failure_codes,
        }
