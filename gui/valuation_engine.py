import sys
import os

# Add the playwright directory to the path so we can import pw module
sys.path.append(os.path.join(os.path.dirname(__file__), 'playwright'))

from bs4 import BeautifulSoup
from decimal import Decimal
import re


class ValuationEngine:
    """
    Deterministic valuation engine that scrapes fundamentals from ShareData,
    combines with database prices, calculates valuation metrics, and stores
    snapshots in stock_valuations table.
    
    NO LLM/AI MODELS ARE USED. All calculations are pure arithmetic.
    """
    
    def __init__(self, db_layer, log_callback=None):
        """
        Initialize valuation engine.
        
        Args:
            db_layer: DBLayer instance for database operations
            log_callback: Optional function(message: str) to log progress
        """
        self.db = db_layer
        self.log = log_callback if log_callback else print
        
    async def run_valuation_update(self):
        """
        Main orchestration method for valuation updates.
        
        Steps:
        1. Select 3 tickers from database
        2. For each ticker:
           - Scrape fundamentals from ShareData
           - Fetch latest price from database
           - Compute valuation ratios
           - Insert row into stock_valuations
        3. Return summary
        
        Returns:
            dict: {"succeeded": int, "failed": int, "tickers": list}
        """
        self.log("Starting valuation update...")
        self.log("Selecting tickers...")
        
        # Select tickers
        tickers = await self._select_tickers()
        if not tickers:
            self.log("No tickers found for valuation.")
            return {"succeeded": 0, "failed": 0, "tickers": []}
        
        self.log(f"Selected tickers: {', '.join(tickers)}")
        
        succeeded = 0
        failed = 0
        
        for ticker in tickers:
            try:
                self.log(f"Processing {ticker}...")
                
                # Scrape fundamentals
                self.log(f"  Scraping fundamentals for {ticker}...")
                fundamentals = await self._scrape_fundamentals(ticker)
                
                if not fundamentals:
                    self.log(f"  ❌ Failed to scrape fundamentals for {ticker}")
                    failed += 1
                    continue
                
                self.log(f"  ✓ Scraped fundamentals for {ticker}")
                
                # Get latest price
                price_data = await self.db.get_latest_price(ticker)
                if not price_data:
                    self.log(f"  ⚠ No price data found for {ticker}, skipping price-based ratios")
                    # Continue without price-based ratios
                    valuation_date = None
                    price_zarc = None
                else:
                    valuation_date = price_data['trade_date']
                    # Assuming close_price is in cents (ZARc)
                    price_zarc = float(price_data['close_price'])
                    self.log(f"  ✓ Fetched latest price for {ticker}: {valuation_date}, {price_zarc} ZARc")
                
                # Get HEPS growth for PEG ratio
                heps_growth = await self.db.get_heps_growth(ticker)
                if heps_growth:
                    self.log(f"  ✓ HEPS growth for {ticker}: {heps_growth:.2%}")
                else:
                    self.log(f"  ⚠ No HEPS growth data for {ticker}, PEG ratio will be NULL")
                
                # Compute ratios
                ratios = self._compute_ratios(price_zarc, fundamentals, heps_growth)
                self.log(f"  [DEBUG] Computed ratios: {ratios}")
                
                # Build valuation row
                valuation_data = {
                    'ticker': ticker,
                    'valuation_date': valuation_date,
                    'price_zarc': price_zarc,
                    **fundamentals,
                    **ratios
                }
                
                self.log(f"  [DEBUG] Full valuation_data dict: {valuation_data}")
                
                # Insert into database
                success = await self.db.insert_valuation(valuation_data)
                
                if success:
                    self.log(f"  ✓ Computed valuations for {ticker} and inserted 1 row into stock_valuations")
                    succeeded += 1
                else:
                    self.log(f"  ❌ Failed to insert valuation for {ticker}")
                    failed += 1
                    
            except Exception as e:
                self.log(f"  ❌ Error processing {ticker}: {type(e).__name__}: {str(e)}")
                failed += 1
                continue
        
        summary = f"Valuation update finished: {succeeded} succeeded, {failed} failed"
        self.log(summary)
        
        return {
            "succeeded": succeeded,
            "failed": failed,
            "tickers": tickers
        }
    
    async def _select_tickers(self):
        """Select all tickers for valuation using database query."""
        try:
            # Pass limit=None to get all tickers from watchlist
            tickers = await self.db.select_tickers_for_valuation(limit=None)
            return tickers
        except Exception as e:
            self.log(f"Error selecting tickers: {e}")
            return []
    
    async def _scrape_fundamentals(self, ticker: str):
        """
        Scrape fundamentals for a ticker from ShareData.
        
        Returns dict with:
        - heps_12m_zarc
        - dividend_12m_zarc
        - cash_gen_ps_zarc
        - nav_ps_zarc
        - quick_ratio
        
        or None on failure
        """
        try:
            # Import inside method to avoid issues if pw module isn't available
            from pw import scrape_ticker_fundamentals
            
            # Get HTML tables
            tables = await scrape_ticker_fundamentals(ticker)
            
            if not tables:
                return None
            
            # DEBUG: Log which tables were found
            self.log(f"  [DEBUG] Found tables: {list(tables.keys())}")
            
            # Parse SHARE STATISTICS table (fin_S)
            fundamentals = {}
            
            if 'fin_S' in tables:
                share_stats = self._parse_share_statistics(tables['fin_S'])
                self.log(f"  [DEBUG] Parsed SHARE STATISTICS: {share_stats}")
                fundamentals.update(share_stats)
            else:
                self.log(f"  [DEBUG] No fin_S table found")
            
            # Parse RATIOS table (fin_R)
            if 'fin_R' in tables:
                ratios = self._parse_ratios_table(tables['fin_R'])
                self.log(f"  [DEBUG] Parsed RATIOS: {ratios}")
                fundamentals.update(ratios)
            else:
                self.log(f"  [DEBUG] No fin_R table found")
            
            self.log(f"  [DEBUG] Final fundamentals dict: {fundamentals}")
            
            return fundamentals if fundamentals else None
            
        except Exception as e:
            self.log(f"Error scraping {ticker}: {e}")
            import traceback
            self.log(f"  [DEBUG] Traceback: {traceback.format_exc()}")
            return None
    
    def _parse_share_statistics(self, table_html: str):
        """
        Parse SHARE STATISTICS table to extract:
        - 12 Month HEPS
        - 12 Month Dividend
        - Cash Generated Per Share
        - Net Asset Value Per Share (ZARc)
        
        Returns dict with keys: heps_12m_zarc, dividend_12m_zarc, cash_gen_ps_zarc, nav_ps_zarc
        """
        soup = BeautifulSoup(table_html, 'html.parser')
        data = {}
        
        # Mapping of row labels to dict keys
        field_map = {
            "12 Month HEPS": "heps_12m_zarc",
            "12 Month Dividend": "dividend_12m_zarc",
            "Cash Generated Per Share": "cash_gen_ps_zarc",
            "Net Asset Value Per Share (ZARc)": "nav_ps_zarc"
        }
        
        rows = soup.find_all('tr')
        
        for row in rows:
            cols = row.find_all(['td', 'th'])
            if len(cols) < 2:
                continue
            
            # First column is the label
            label = cols[0].get_text(strip=True)
            
            # Check if this is a field we need
            for field_label, field_key in field_map.items():
                if field_label.lower() in label.lower():
                    # Extract value from the "OF" column (index 1 after removing growth column)
                    # We need to find the column with actual data
                    # Based on pw.py logic, after removing growth column, index 1 is "OF" (latest year)
                    if len(cols) >= 2:
                        value_text = cols[1].get_text(strip=True)
                        value = self._parse_financial_value(value_text)
                        data[field_key] = value
                    break
        
        return data
    
    def _parse_ratios_table(self, table_html: str):
        """
        Parse RATIOS table to extract:
        - Quick Ratio
        
        Returns dict with key: quick_ratio
        """
        soup = BeautifulSoup(table_html, 'html.parser')
        data = {}
        
        rows = soup.find_all('tr')
        
        for row in rows:
            cols = row.find_all(['td', 'th'])
            if len(cols) < 2:
                continue
            
            label = cols[0].get_text(strip=True)
            
            if "Quick Ratio".lower() in label.lower():
                if len(cols) >= 2:
                    value_text = cols[1].get_text(strip=True)
                    value = self._parse_financial_value(value_text)
                    data['quick_ratio'] = value
                break
        
        return data
    
    def _parse_financial_value(self, text: str):
        """
        Parse a financial value from text, handling:
        - Spaces in numbers: "5 574.7300" -> 5574.7300
        - Negative values: "- 18.03" -> -18.03
        - Empty or non-numeric: None
        
        Returns float or None
        """
        if not text or text in ['-', '—', 'N/A', 'n/a']:
            return None
        
        try:
            # Remove spaces
            cleaned = text.replace(' ', '')
            
            # Handle negative with space: "- 123" -> "-123"
            cleaned = cleaned.replace('-', '-')
            
            # Try to convert to float
            value = float(cleaned)
            return value
        except (ValueError, AttributeError):
            return None
    
    def _compute_ratios(self, price_zarc, fundamentals, heps_growth):
        """
        Compute all valuation ratios deterministically.
        
        Args:
            price_zarc: float or None - price in ZAR cents
            fundamentals: dict with heps_12m_zarc, dividend_12m_zarc, cash_gen_ps_zarc, nav_ps_zarc
            heps_growth: float or None - HEPS growth rate as decimal (0.15 for 15%)
        
        Returns dict with:
        - earnings_yield
        - dividend_yield
        - cash_flow_yield
        - p_to_nav
        - peg_ratio
        """
        ratios = {}
        
        P = price_zarc
        E = fundamentals.get('heps_12m_zarc')
        D = fundamentals.get('dividend_12m_zarc')
        CF = fundamentals.get('cash_gen_ps_zarc')
        NAV = fundamentals.get('nav_ps_zarc')
        
        # Earnings Yield = E / P
        if P and E and P > 0 and E > 0:
            ratios['earnings_yield'] = E / P
        else:
            ratios['earnings_yield'] = None
        
        # Dividend Yield = D / P
        if P and D is not None and P > 0 and D >= 0:
            ratios['dividend_yield'] = D / P
        else:
            ratios['dividend_yield'] = None
        
        # Cash Flow Yield = CF / P
        if P and CF is not None and P > 0:
            ratios['cash_flow_yield'] = CF / P
        else:
            ratios['cash_flow_yield'] = None
        
        # P/NAV = P / NAV
        if P and NAV and P > 0 and NAV > 0:
            ratios['p_to_nav'] = P / NAV
        else:
            ratios['p_to_nav'] = None
        
        # PEG Ratio = (P/E) / (g * 100)
        # where g is growth rate as decimal (0.15 for 15%)
        if P and E and heps_growth and P > 0 and E > 0 and heps_growth > 0:
            pe = P / E
            # Convert growth to percentage format for PEG
            peg = pe / (heps_growth * 100)
            ratios['peg_ratio'] = peg
        else:
            ratios['peg_ratio'] = None
        
        return ratios
