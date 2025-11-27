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
    """
    
    def __init__(self, db_layer, log_callback=None):
        self.db = db_layer
        self.log = log_callback if log_callback else print
    
    async def run_fundamentals_update(self, tickers=None):
        """Main orchestration method for updating raw fundamentals."""
        self.log("Starting raw fundamentals update...")
        
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
                
                # Scrape multi-year fundamentals (Returns a LIST of table sets now)
                all_periods_data = await self._scrape_multi_year_fundamentals(ticker)
                
                if not all_periods_data:
                    self.log(f"  [ERROR] Failed to scrape data for {ticker}")
                    failed += 1
                    continue
                
                self.log(f"  [OK] Extracted total {len(all_periods_data)} periods (Final + Interim) for {ticker}")
                
                # Upsert into database
                success = await self._upsert_raw_fundamentals(ticker, all_periods_data)
                
                if success:
                    self.log(f"  [OK] Upserted {len(all_periods_data)} periods into raw_stock_valuations")
                    succeeded += 1
                    total_periods += len(all_periods_data)
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
        Scrape multi-year fundamentals for a ticker (Finals AND Interims).
        """
        try:
            # Import inside method to avoid circular dependencies
            from pw import scrape_ticker_fundamentals
            
            # Get List of HTML table sets (e.g. [Finals_Dict, Interims_Dict])
            table_sets = await scrape_ticker_fundamentals(ticker)
            
            if not table_sets:
                return None
            
            self.log(f"  Retrieved {len(table_sets)} sets of financial tables (Finals/Interims)")
            
            all_periods_data = []

            # Iterate through each set (Finals, then Interims)
            for i, tables in enumerate(table_sets):
                set_name = "Finals" if i == 0 else "Interims"
                self.log(f"  Processing set: {set_name}")

                current_set_periods = []
                
                # 1. Parse SHARE STATISTICS
                if 'fin_S' in tables:
                    share_stats_periods = self._parse_multi_year_share_statistics(tables['fin_S'])
                    self.log(f"    Found {len(share_stats_periods)} periods in {set_name} Stats")
                    current_set_periods = share_stats_periods
                else:
                    self.log(f"    [WARN] No SHARE STATISTICS table found in {set_name}")
                    continue # Skip this set if no stats
                
                # 2. Parse RATIOS and merge
                if 'fin_R' in tables:
                    ratios_periods = self._parse_multi_year_ratios(tables['fin_R'])
                    self.log(f"    Found {len(ratios_periods)} periods in {set_name} Ratios")
                    
                    # Merge quick_ratio by matching period_end dates
                    for period in current_set_periods:
                        # Default to None
                        period['quick_ratio'] = None
                        
                        for ratio_period in ratios_periods:
                            if period['results_period_end'] == ratio_period['results_period_end']:
                                period['quick_ratio'] = ratio_period.get('quick_ratio')
                                break
                else:
                    # Set all quick_ratio to None if table missing
                    for period in current_set_periods:
                        period['quick_ratio'] = None

                # Add this set's periods to the master list
                all_periods_data.extend(current_set_periods)
            
            # Deduplication check (optional but good practice in case dates overlap)
            # We use a dictionary keyed by date to ensure unique periods
            unique_periods = {}
            for p in all_periods_data:
                d = p['results_period_end']
                # If duplicate exists, overwrite (or keep first). 
                # Usually Final overwrites Interim if they share a date, but here dates should differ.
                unique_periods[d] = p
                
            return list(unique_periods.values()) if unique_periods else None
            
        except Exception as e:
            self.log(f"  Error scraping {ticker}: {e}")
            import traceback
            self.log(f"  Traceback: {traceback.format_exc()}")
            return None
    
    # ... (Rest of the class methods: _parse_multi_year_share_statistics, etc., remain exactly the same)
    
    def _parse_multi_year_share_statistics(self, table_html: str):
        """
        Parse SHARE STATISTICS table to extract data for ALL year columns.
        (Code remains identical to your previous version)
        """
        soup = BeautifulSoup(table_html, 'html.parser')
        rows = soup.find_all('tr')
        
        if not rows:
            return []
        
        # --- ROBUST HEADER DETECTION ---
        header_row = None
        headers = None

        for row in rows:
            cells = row.find_all(['th', 'td'])
            texts = [c.get_text(strip=True).replace('\n', ' ') for c in cells]

            if len(texts) < 2: continue

            non_first = [t for t in texts[1:] if t]
            if not non_first: continue

            has_year_or_month = any(
                re.search(r"\b(19|20)\d{2}\b", t) or
                re.search(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b", t)
                for t in non_first
            )

            if has_year_or_month:
                header_row = row
                headers = texts
                break

        if header_row is None:
            header_row = rows[0]
            headers = [th.get_text(strip=True).replace('\n', ' ')
                    for th in header_row.find_all(['th', 'td'])]

        # Find growth column index
        growth_idx = -1
        for i, h in enumerate(headers):
            if i == 0: continue
            if "Avg." in h or "Growth" in h or "Observed" in h:
                growth_idx = i
                break
        
        if growth_idx == -1 and len(headers) > 2:
            growth_idx = 1
        
        year_indices = []
        for i in range(len(headers)):
            if i == 0: continue
            if i == growth_idx: continue
            year_indices.append(i)
        
        periods_info = []
        for idx in year_indices:
            if idx < len(headers):
                period_label = headers[idx].strip()
                if not period_label: continue

                period_end = self._parse_period_label(period_label)
                release_date = self._parse_release_date(period_label)

                if period_end is None: continue

                periods_info.append({
                    'column_idx': idx,
                    'results_period_end': period_end,
                    'results_period_label': period_label,
                    'results_release_date': release_date,
                })

        if not periods_info: return []

        periods_data = []
        for period_info in periods_info:
            periods_data.append({
                'results_period_end': period_info['results_period_end'],
                'results_period_label': period_info['results_period_label'],
                'results_release_date': period_info['results_release_date'],
                'heps_12m_zarc': None,
                'dividend_12m_zarc': None,
                'cash_gen_ps_zarc': None,
                'nav_ps_zarc': None
            })
        
        field_map = {
            "12 Month HEPS": "heps_12m_zarc",
            "12 Month Dividend": "dividend_12m_zarc",
            "Cash Generated Per Share": "cash_gen_ps_zarc",
            "Net Asset Value Per Share (ZARc)": "nav_ps_zarc"
        }
        
        for row in rows[1:]:
            cols = row.find_all(['td', 'th'])
            if not cols: continue
            label = cols[0].get_text(strip=True)
            
            for field_label, field_key in field_map.items():
                if field_label.lower() in label.lower():
                    for period_idx, period_info in enumerate(periods_info):
                        col_idx = period_info['column_idx']
                        if col_idx < len(cols):
                            value_text = cols[col_idx].get_text(strip=True)
                            value = self._parse_financial_value(value_text)
                            periods_data[period_idx][field_key] = value
                    break
        
        return periods_data

    def _parse_multi_year_ratios(self, table_html: str):
        """
        Parse RATIOS table. (Code remains identical to your previous version)
        """
        soup = BeautifulSoup(table_html, 'html.parser')
        rows = soup.find_all('tr')
        if not rows: return []
        
        header_row = None
        headers = None
        for row in rows:
            cells = row.find_all(['th', 'td'])
            texts = [c.get_text(strip=True).replace('\n', ' ') for c in cells]
            if len(texts) < 2: continue
            non_first = [t for t in texts[1:] if t]
            if not non_first: continue
            has_year_or_month = any(
                re.search(r"\b(19|20)\d{2}\b", t) or
                re.search(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b", t)
                for t in non_first
            )
            if has_year_or_month:
                header_row = row
                headers = texts
                break

        if header_row is None:
            header_row = rows[0]
            headers = [th.get_text(strip=True).replace('\n', ' ')
                    for th in header_row.find_all(['th', 'td'])]

        growth_idx = -1
        for i, h in enumerate(headers):
            if i == 0: continue
            if "Avg." in h or "Growth" in h or "Observed" in h:
                growth_idx = i
                break
        if growth_idx == -1 and len(headers) > 2: growth_idx = 1
        
        year_indices = []
        for i in range(len(headers)):
            if i == 0 or i == growth_idx: continue
            year_indices.append(i)
        
        periods_info = []
        for idx in year_indices:
            if idx < len(headers):
                period_label = headers[idx].strip()
                if not period_label: continue
                period_end = self._parse_period_label(period_label)
                if period_end is None: continue
                periods_info.append({
                    'column_idx': idx,
                    'results_period_end': period_end,
                    'results_period_label': period_label
                })

        if not periods_info: return []
        
        periods_data = []
        for period_info in periods_info:
            periods_data.append({
                'results_period_end': period_info['results_period_end'],
                'results_period_label': period_info['results_period_label'],
                'quick_ratio': None
            })
        
        for row in rows[1:]:
            cols = row.find_all(['td', 'th'])
            if not cols: continue
            label = cols[0].get_text(strip=True)
            if "Quick Ratio".lower() in label.lower():
                for period_idx, period_info in enumerate(periods_info):
                    col_idx = period_info['column_idx']
                    if col_idx < len(cols):
                        value_text = cols[col_idx].get_text(strip=True)
                        value = self._parse_financial_value(value_text)
                        periods_data[period_idx]['quick_ratio'] = value
                break
        
        return periods_data

    def _parse_period_label(self, header: str):
        try:
            match = re.match(r'([A-Za-z]+)\s+(\d{4})', header)
            if not match: return None
            month_str = match.group(1)
            year_str = match.group(2)
            month_map = {
                'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
                'january': 1, 'february': 2, 'march': 3, 'april': 4, 'june': 6,
                'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12
            }
            month_num = month_map.get(month_str.lower())
            if not month_num: return None
            year = int(year_str)
            import calendar
            last_day = calendar.monthrange(year, month_num)[1]
            return date(year, month_num, last_day)
        except Exception:
            return None
    
    def _parse_financial_value(self, text: str):
        if not text or text in ['-', '—', 'N/A', 'n/a', '', ' ']: return None
        try:
            cleaned = text.replace(' ', '').replace('\xa0', '')
            cleaned = cleaned.replace('−', '-')
            return float(cleaned)
        except (ValueError, AttributeError):
            return None

    def _upsert_raw_fundamentals(self, ticker: str, periods_data: list):
        try:
            return asyncio.run(self.db.upsert_raw_fundamentals(ticker, periods_data)) \
                   if not asyncio.get_event_loop().is_running() \
                   else self.db.upsert_raw_fundamentals(ticker, periods_data)
        except Exception as e:
            # Handle sync/async context issues if db call fails directly
            # Assuming db_layer is async, but we are inside an async method
            return self.db.upsert_raw_fundamentals(ticker, periods_data)

    def _parse_release_date(self, header: str):
        m = re.search(r'(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})', header)
        if not m: return None
        day = int(m.group(1))
        month_str = m.group(2).lower()
        year = int(m.group(3))
        month_map = {
            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
            'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
        }
        month = month_map.get(month_str)
        if not month: return None
        return date(year, month, day)