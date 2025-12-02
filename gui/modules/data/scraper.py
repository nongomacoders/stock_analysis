from typing import List, Dict, Optional, Any, Callable
from modules.data.parsers import (
    parse_multi_year_share_statistics,
    parse_multi_year_ratios,
)


class FundamentalsScraper:
    """
    Handles scraping and parsing of multi-year fundamental data from ShareData.
    """

    def __init__(self, log_callback: Optional[Callable] = None):
        """
        Initialize the scraper.
        
        Args:
            log_callback: Optional logging function, defaults to print
        """
        self.log = log_callback if log_callback else print

    async def scrape_multi_year_fundamentals(self, ticker: str) -> Optional[List[Dict[str, Any]]]:
        """
        Scrape multi-year fundamentals for a ticker from ShareData.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            List of period data dictionaries, or None if scraping fails
        """
        try:
            # Import here to avoid circular dependency
            from playwright_scraper.pw import scrape_ticker_fundamentals

            table_sets = await scrape_ticker_fundamentals(ticker)
            if not table_sets:
                return None

            self.log(f"  Retrieved {len(table_sets)} sets of tables")

            all_periods_data = []

            for i, tables in enumerate(table_sets):
                set_name = "Finals" if i == 0 else "Interims"
                current_set_periods = []

                # 1. Parse SHARE STATISTICS
                if "fin_S" in tables:
                    current_set_periods = parse_multi_year_share_statistics(
                        tables["fin_S"]
                    )
                else:
                    continue

                # 2. Parse RATIOS and merge
                if "fin_R" in tables:
                    ratios_periods = parse_multi_year_ratios(tables["fin_R"])
                    for period in current_set_periods:
                        period["quick_ratio"] = None
                        for ratio_period in ratios_periods:
                            if (
                                period["results_period_end"]
                                == ratio_period["results_period_end"]
                            ):
                                period["quick_ratio"] = ratio_period.get("quick_ratio")
                                break
                else:
                    for period in current_set_periods:
                        period["quick_ratio"] = None

                all_periods_data.extend(current_set_periods)

            # Deduplicate by date
            unique_periods = {}
            for p in all_periods_data:
                unique_periods[p["results_period_end"]] = p

            return list(unique_periods.values()) if unique_periods else None

        except ImportError:
            self.log(
                "CRITICAL ERROR: Could not find 'playwright_scraper'. Ensure __init__.py exists in that folder."
            )
            return None
        except Exception as e:
            self.log(f"  Error scraping {ticker}: {e}")
            return None
