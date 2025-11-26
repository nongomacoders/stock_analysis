import sys
import os
from datetime import datetime, date
import re
from bs4 import BeautifulSoup

# Add the playwright directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'playwright'))


class RawFundamentalsLoader:
    """
    Raw Fundamentals Loader - Populates raw_stock_valuations with multi-year data.
    
    Responsibilities:
    - Scrape ShareData financial results pages for multiple years
    - Extract fundamental metrics from SHARE STATISTICS and RATIOS tables
    - Parse period labels to identify year/period end dates
    - Upsert data into raw_stock_valuations (one row per ticker/period)
    - Handle missing metrics gracefully (set to NULL)
    
    Does NOT compute price-based ratios - that's the ValuationEngine's job.
    """
    
    def __init__(self, db_layer, log_callback=None):
        """
        Initialize the loader.
        
        Args:
            db_layer: DBLayer instance for database operations
            log_callback: Optional function(message: str) to log progress
        """
        self.db = db_layer
        self.log = log_callback if log_callback else print
    
    async def run_fundamentals_update(self, tickers=None):
        """
        Main orchestration method for updating raw fundamentals.
        
        Args:
            tickers: List of tickers to update, or None to use database selection
        
        Returns:
            dict: {"succeeded": int, "failed": int, "tickers": list, "total_periods": int}
        """
        self.log("Starting raw fundamentals update...")
        
        # Select tickers if not provided
        if tickers is None:
            self.log("Selecting tickers from database...")
            tickers = await self.db.select_tickers_for_valuation(limit=None)
        
        if not tickers:
            self.log("No tickers to process.")
            return {"succeeded": 0, "failed": 0, "tickers": [], "total_periods": 0}
        
        self.log(f"Processing {len(tickers)} tickers: {', '.join(tickers)}")
        
        succeeded = 0
        failed = 0
        total_periods = 0
        
        for ticker in tickers:
            try:
                self.log(f"\n{'='*60}")
                self.log(f"Processing {ticker}...")
                
                # Scrape multi-year fundamentals
                periods_data = await self._scrape_multi_year_fundamentals(ticker)
                
                if not periods_data:
                    self.log(f"  [ERROR] Failed to scrape data for {ticker}")
                    failed += 1
                    continue
                
                self.log(f"  [OK] Scraped {len(periods_data)} periods for {ticker}")
                
                # Upsert into database
                success = await self._upsert_raw_fundamentals(ticker, periods_data)
                
                if success:
                    self.log(f"  [OK] Upserted {len(periods_data)} periods into raw_stock_valuations")
                    succeeded += 1
                    total_periods += len(periods_data)
                else:
                    self.log(f"  [ERROR] Failed to insert data for {ticker}")
                    failed += 1
                    
            except Exception as e:
                self.log(f"  [ERROR] Error processing {ticker}: {type(e).__name__}: {str(e)}")
                import traceback
                self.log(f"  Traceback: {traceback.format_exc()}")
                failed += 1
                continue
        
        summary = f"\nRaw fundamentals update complete: {succeeded} tickers succeeded, {failed} failed, {total_periods} total periods"
        self.log(summary)
        
        return {
            "succeeded": succeeded,
            "failed": failed,
            "tickers": tickers,
            "total_periods": total_periods
        }
    
    async def _scrape_multi_year_fundamentals(self, ticker: str):
        """
        Scrape multi-year fundamentals for a ticker from ShareData.
        
        Returns list of dicts, one per period:
        [
            {
                "results_period_end": date(2025, 3, 31),
                "results_period_label": "Mar 2025 Final (12m) 23 Jun 2025",
                "heps_12m_zarc": 5574.73,
                "dividend_12m_zarc": 1234.56,
                "cash_gen_ps_zarc": 2345.67,
                "nav_ps_zarc": 12345.67,
                "quick_ratio": 1.23
            },
            ...
        ]
        
        or None on failure
        """
        try:
            # Import inside method to avoid circular dependencies
            from pw import scrape_ticker_fundamentals
            
            # Get HTML tables
            tables = await scrape_ticker_fundamentals(ticker)
            
            if not tables:
                return None
            
            self.log(f"  Found tables: {list(tables.keys())}")
            
            # Parse multi-year data from tables
            periods_data = []
            
            # First, parse SHARE STATISTICS to get period headers and core fundamentals
            if 'fin_S' in tables:
                share_stats_periods = self._parse_multi_year_share_statistics(tables['fin_S'])
                self.log(f"  Parsed {len(share_stats_periods)} periods from SHARE STATISTICS")
                periods_data = share_stats_periods
            else:
                self.log(f"  [WARN] No SHARE STATISTICS table found")
                return None
            
            # Then, parse RATIOS table and merge quick_ratio into periods_data
            if 'fin_R' in tables:
                ratios_periods = self._parse_multi_year_ratios(tables['fin_R'])
                self.log(f"  Parsed {len(ratios_periods)} periods from RATIOS")
                
                # Merge quick_ratio by matching period_end dates
                for period in periods_data:
                    for ratio_period in ratios_periods:
                        if period['results_period_end'] == ratio_period['results_period_end']:
                            period['quick_ratio'] = ratio_period.get('quick_ratio')
                            break
                    else:
                        # No matching period in ratios table - set to NULL
                        period['quick_ratio'] = None
            else:
                self.log(f"  [WARN] No RATIOS table found, quick_ratio will be NULL")
                # Set all quick_ratio to None
                for period in periods_data:
                    period['quick_ratio'] = None
            
            return periods_data if periods_data else None
            
        except Exception as e:
            self.log(f"  Error scraping {ticker}: {e}")
            import traceback
            self.log(f"  Traceback: {traceback.format_exc()}")
            return None
    
    def _parse_multi_year_share_statistics(self, table_html: str):
        """
        Parse SHARE STATISTICS table to extract data for ALL year columns.
        
        Returns list of dicts, one per period:
        [
            {
                "results_period_end": date(2025, 3, 31),
                "results_period_label": "Mar 2025 Final (12m) 23 Jun 2025",
                "heps_12m_zarc": 5574.73,
                "dividend_12m_zarc": 1234.56,
                "cash_gen_ps_zarc": 2345.67,
                "nav_ps_zarc": 12345.67
            },
            ...
        ]
        """
        soup = BeautifulSoup(table_html, 'html.parser')
        rows = soup.find_all('tr')
        
        if not rows:
            return []
        
        # --- HEADER DETECTION ---
        header_row = rows[0]
        headers = [th.get_text(strip=True).replace('\n', ' ') for th in header_row.find_all(['th', 'td'])]
        
        self.log(f"    [DEBUG] Share Stats Headers: {headers}")
        
        # Identify column structure:
        # Index 0: Row label
        # Index 1: Possibly growth/observed column (to skip)
        # Index 2+: Year columns (e.g., "Mar 2025 Final (12m) 23 Jun 2025", "Dec 2024 Final...")
        
        # Find growth column index
        growth_idx = -1
        for i, h in enumerate(headers):
            if i == 0:  # Skip row label column
                continue
            if "Avg." in h or "Growth" in h or "Observed" in h:
                growth_idx = i
                break
        
        if growth_idx == -1 and len(headers) > 2:
            growth_idx = 1  # Assume second column is growth
        
        self.log(f"    [DEBUG] Growth column index: {growth_idx}")
        
        # Identify all year column indices (skip label and growth columns)
        year_indices = []
        for i in range(len(headers)):
            if i == 0:  # Row label
                continue
            if i == growth_idx:  # Growth column
                continue
            year_indices.append(i)
        
        self.log(f"    [DEBUG] Year column indices: {year_indices}")
        
        # Parse period labels from headers
        periods_info = []
        for idx in year_indices:
            if idx < len(headers):
                period_label = headers[idx].strip()

                # Skip empty header cells
                if not period_label:
                    self.log(
                        f"    [WARN] Empty period header at column {idx}, "
                        "skipping this column."
                    )
                    continue

                period_end = self._parse_period_label(period_label)

                # If we can't parse the label into a date, skip it
                if period_end is None:
                    self.log(
                        f"    [WARN] Could not parse valid period from header "
                        f"'{period_label}' (col {idx}), skipping."
                    )
                    continue

                periods_info.append({
                    'column_idx': idx,
                    'results_period_end': period_end,
                    'results_period_label': period_label
                })

        if not periods_info:
            self.log("    [ERROR] No valid period headers found in SHARE STATISTICS.")
            return []

        
        self.log(f"    [DEBUG] Periods info: {periods_info}")
        
        # Initialize data structures for each period
        periods_data = []
        for period_info in periods_info:
            periods_data.append({
                'results_period_end': period_info['results_period_end'],
                'results_period_label': period_info['results_period_label'],
                'heps_12m_zarc': None,
                'dividend_12m_zarc': None,
                'cash_gen_ps_zarc': None,
                'nav_ps_zarc': None
            })
        
        # Mapping of row labels to dict keys
        field_map = {
            "12 Month HEPS": "heps_12m_zarc",
            "12 Month Dividend": "dividend_12m_zarc",
            "Cash Generated Per Share": "cash_gen_ps_zarc",
            "Net Asset Value Per Share (ZARc)": "nav_ps_zarc"
        }
        
        # Parse each data row
        for row in rows[1:]:  # Skip header
            cols = row.find_all(['td', 'th'])
            if not cols:
                continue
            
            # First column is the label
            label = cols[0].get_text(strip=True)
            
            # Check if this is a field we need
            for field_label, field_key in field_map.items():
                if field_label.lower() in label.lower():
                    # Extract values for each period
                    for period_idx, period_info in enumerate(periods_info):
                        col_idx = period_info['column_idx']
                        if col_idx < len(cols):
                            value_text = cols[col_idx].get_text(strip=True)
                            value = self._parse_financial_value(value_text)
                            periods_data[period_idx][field_key] = value
                            
                            if value is None:
                                self.log(f"    [WARN] Missing/invalid '{field_label}' for period '{period_info['results_period_label']}': '{value_text}'")
                    break
        
        return periods_data
    
    def _parse_multi_year_ratios(self, table_html: str):
        """
        Parse RATIOS table to extract Quick Ratio for ALL year columns.
        
        Returns list of dicts, one per period:
        [
            {
                "results_period_end": date(2025, 3, 31),
                "results_period_label": "Mar 2025 Final (12m) 23 Jun 2025",
                "quick_ratio": 1.23
            },
            ...
        ]
        """
        soup = BeautifulSoup(table_html, 'html.parser')
        rows = soup.find_all('tr')
        
        if not rows:
            return []
        
        # --- HEADER DETECTION (same logic as share statistics) ---
        header_row = rows[0]
        headers = [th.get_text(strip=True).replace('\n', ' ') for th in header_row.find_all(['th', 'td'])]
        
        self.log(f"    [DEBUG] Ratios Headers: {headers}")
        
        # Find growth column index
        growth_idx = -1
        for i, h in enumerate(headers):
            if i == 0:
                continue
            if "Avg." in h or "Growth" in h or "Observed" in h:
                growth_idx = i
                break
        
        if growth_idx == -1 and len(headers) > 2:
            growth_idx = 1
        
        # Identify all year column indices
        year_indices = []
        for i in range(len(headers)):
            if i == 0 or i == growth_idx:
                continue
            year_indices.append(i)
        
        # Parse period labels from headers
        periods_info = []
        for idx in year_indices:
            if idx < len(headers):
                period_label = headers[idx].strip()

                if not period_label:
                    self.log(
                        f"    [WARN] Empty period header in RATIOS at column {idx}, "
                        "skipping."
                    )
                    continue

                period_end = self._parse_period_label(period_label)
                if period_end is None:
                    self.log(
                        f"    [WARN] Could not parse valid period from RATIOS header "
                        f"'{period_label}' (col {idx}), skipping."
                    )
                    continue

                periods_info.append({
                    'column_idx': idx,
                    'results_period_end': period_end,
                    'results_period_label': period_label
                })

        if not periods_info:
            self.log("    [ERROR] No valid period headers found in RATIOS.")
            return []

        
        # Initialize data structures for each period
        periods_data = []
        for period_info in periods_info:
            periods_data.append({
                'results_period_end': period_info['results_period_end'],
                'results_period_label': period_info['results_period_label'],
                'quick_ratio': None
            })
        
        # Find the Quick Ratio row
        for row in rows[1:]:
            cols = row.find_all(['td', 'th'])
            if not cols:
                continue
            
            label = cols[0].get_text(strip=True)
            
            if "Quick Ratio".lower() in label.lower():
                # Extract values for each period
                for period_idx, period_info in enumerate(periods_info):
                    col_idx = period_info['column_idx']
                    if col_idx < len(cols):
                        value_text = cols[col_idx].get_text(strip=True)
                        value = self._parse_financial_value(value_text)
                        periods_data[period_idx]['quick_ratio'] = value
                        
                        if value is None:
                            self.log(f"    [WARN] Missing/invalid 'Quick Ratio' for period '{period_info['results_period_label']}': '{value_text}'")
                break
        
        return periods_data
    
    def _parse_period_label(self, header: str):
        """
        Parse period label to extract results_period_end date.
        
        Examples:
        "Mar 2025 Final (12m) 23 Jun 2025" → date(2025, 3, 31)
        "Dec 2024 Final (12m) 11 Mar 2025" → date(2024, 12, 31)
        "Jun 2024 Interim (6m) 12 Sep 2024" → date(2024, 6, 30)
        "Sep 2023 Interim (6m) 12 Dec 2023" → date(2023, 9, 30)
        
        Returns date object representing the last day of the period month
        """
        try:
            # Extract "Mar 2025" or "Dec 2024" portion using regex
            match = re.match(r'([A-Za-z]+)\s+(\d{4})', header)
            
            if not match:
                self.log(f"    [WARN] Could not parse period label: '{header}'")
                return None
            
            month_str = match.group(1)
            year_str = match.group(2)
            
            # Convert month name to number
            month_map = {
                'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
                'january': 1, 'february': 2, 'march': 3, 'april': 4, 'june': 6,
                'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12
            }
            
            month_num = month_map.get(month_str.lower())
            if not month_num:
                self.log(f"    [WARN] Unknown month in period label: '{month_str}'")
                return None
            
            year = int(year_str)
            
            # Get last day of month
            import calendar
            last_day = calendar.monthrange(year, month_num)[1]
            
            return date(year, month_num, last_day)
            
        except Exception as e:
            self.log(f"    [WARN] Error parsing period label '{header}': {e}")
            return None
    
    def _parse_financial_value(self, text: str):
        """
        Parse a financial value from text, handling:
        - Spaces in numbers: "5 574.7300" → 5574.7300
        - Negative values with space: "- 18.03" → -18.03
        - Negative values: "-18.03" → -18.03
        - Empty or non-numeric: None
        - Placeholders: '-', '—', 'N/A' → None
        
        Returns float or None
        """
        if not text or text in ['-', '—', 'N/A', 'n/a', '', ' ']:
            return None
        
        try:
            # Remove all spaces (including non-breaking spaces)
            cleaned = text.replace(' ', '').replace('\xa0', '')
            
            # Handle negative with space: "- 123" → "-123"
            # The replace above already removed the space, so just clean up
            cleaned = cleaned.replace('−', '-')  # Replace minus sign with hyphen
            
            # Try to convert to float
            value = float(cleaned)
            return value
        except (ValueError, AttributeError):
            return None
    
    async def _upsert_raw_fundamentals(self, ticker: str, periods_data: list):
        """
        Upsert raw fundamentals data into database.
        
        Args:
            ticker: Stock ticker
            periods_data: List of period dicts from parsing
        
        Returns True on success, False on failure
        """
        try:
            success = await self.db.upsert_raw_fundamentals(ticker, periods_data)
            return success
        except Exception as e:
            self.log(f"  Error upserting data for {ticker}: {e}")
            return False
