import asyncio
import re
from datetime import date
from bs4 import BeautifulSoup

# --- IMPORTS ---
from core.db.engine import DBEngine
from modules.data.watchlist import select_tickers_for_valuation
from modules.data.fundamentals import upsert_raw_fundamentals


class RawFundamentalsLoader:
    """
    Raw Fundamentals Loader - Populates raw_stock_valuations with multi-year data.
    """

    def __init__(self, log_callback=None):
        self.log = log_callback if log_callback else print

    async def run_fundamentals_update(self, tickers=None):
        """Main orchestration method for updating raw fundamentals."""
        self.log("Starting raw fundamentals update...")

        if tickers is None:
            self.log("Selecting tickers from database...")
            tickers = await select_tickers_for_valuation(limit=None)

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
                all_periods_data = await self._scrape_multi_year_fundamentals(ticker)

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
            "tickers": tickers,
            "total_periods": total_periods,
        }

    async def _scrape_multi_year_fundamentals(self, ticker: str):
        try:
            # --- FIXED IMPORT ---
            # We import here to avoid circular dependency, but use the package path
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
                    current_set_periods = self._parse_multi_year_share_statistics(
                        tables["fin_S"]
                    )
                else:
                    continue

                # 2. Parse RATIOS and merge
                if "fin_R" in tables:
                    ratios_periods = self._parse_multi_year_ratios(tables["fin_R"])
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

    def _parse_multi_year_share_statistics(self, table_html: str):
        soup = BeautifulSoup(table_html, "html.parser")
        rows = soup.find_all("tr")
        if not rows:
            return []

        # Header Logic
        header_row = None
        headers = None
        for row in rows:
            cells = row.find_all(["th", "td"])
            texts = [c.get_text(strip=True).replace("\n", " ") for c in cells]
            if len(texts) < 2:
                continue
            if any(re.search(r"\b(19|20)\d{2}\b", t) for t in texts[1:]):
                header_row = row
                headers = texts
                break

        if not header_row:
            header_row = rows[0]
            headers = [
                c.get_text(strip=True) for c in header_row.find_all(["th", "td"])
            ]

        # Find columns
        year_indices = []
        for i, h in enumerate(headers):
            if i == 0:
                continue
            if "Avg." in h or "Growth" in h:
                continue
            year_indices.append(i)

        periods_info = []
        for idx in year_indices:
            if idx < len(headers):
                p_label = headers[idx].strip()
                p_end = self._parse_period_label(p_label)
                if p_end:
                    periods_info.append(
                        {
                            "column_idx": idx,
                            "results_period_end": p_end,
                            "results_period_label": p_label,
                            "results_release_date": self._parse_release_date(p_label),
                        }
                    )

        if not periods_info:
            return []

        periods_data = [
            {
                "results_period_end": p["results_period_end"],
                "results_period_label": p["results_period_label"],
                "results_release_date": p["results_release_date"],
                "heps_12m_zarc": None,
                "dividend_12m_zarc": None,
                "cash_gen_ps_zarc": None,
                "nav_ps_zarc": None,
            }
            for p in periods_info
        ]

        field_map = {
            "12 Month HEPS": "heps_12m_zarc",
            "12 Month Dividend": "dividend_12m_zarc",
            "Cash Generated Per Share": "cash_gen_ps_zarc",
            "Net Asset Value Per Share (ZARc)": "nav_ps_zarc",
        }

        for row in rows[1:]:
            cols = row.find_all(["td", "th"])
            if not cols:
                continue
            label = cols[0].get_text(strip=True)

            for f_label, f_key in field_map.items():
                if f_label.lower() in label.lower():
                    for p_idx, p_info in enumerate(periods_info):
                        if p_info["column_idx"] < len(cols):
                            val = self._parse_financial_value(
                                cols[p_info["column_idx"]].get_text(strip=True)
                            )
                            periods_data[p_idx][f_key] = val
                    break
        return periods_data

    def _parse_multi_year_ratios(self, table_html: str):
        soup = BeautifulSoup(table_html, "html.parser")
        rows = soup.find_all("tr")
        if not rows:
            return []

        header_row = None
        headers = None
        for row in rows:
            cells = row.find_all(["th", "td"])
            texts = [c.get_text(strip=True).replace("\n", " ") for c in cells]
            if len(texts) < 2:
                continue
            if any(re.search(r"\b(19|20)\d{2}\b", t) for t in texts[1:]):
                header_row = row
                headers = texts
                break

        if not header_row:
            header_row = rows[0]
            headers = [
                c.get_text(strip=True) for c in header_row.find_all(["th", "td"])
            ]

        year_indices = [
            i
            for i, h in enumerate(headers)
            if i > 0 and "Avg" not in h and "Growth" not in h
        ]

        periods_info = []
        for idx in year_indices:
            if idx < len(headers):
                p_end = self._parse_period_label(headers[idx].strip())
                if p_end:
                    periods_info.append(
                        {"column_idx": idx, "results_period_end": p_end}
                    )

        periods_data = [
            {"results_period_end": p["results_period_end"], "quick_ratio": None}
            for p in periods_info
        ]

        for row in rows[1:]:
            cols = row.find_all(["td", "th"])
            if not cols:
                continue
            if "Quick Ratio".lower() in cols[0].get_text(strip=True).lower():
                for p_idx, p_info in enumerate(periods_info):
                    if p_info["column_idx"] < len(cols):
                        val = self._parse_financial_value(
                            cols[p_info["column_idx"]].get_text(strip=True)
                        )
                        periods_data[p_idx]["quick_ratio"] = val
                break
        return periods_data

    def _parse_period_label(self, header):
        try:
            m = re.match(r"([A-Za-z]+)\s+(\d{4})", header)
            if not m:
                return None
            from dateutil import parser

            return parser.parse(header).date()
        except:
            return None

    def _parse_release_date(self, header):
        try:
            m = re.search(r"(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})", header)
            if not m:
                return None
            from dateutil import parser

            return parser.parse(m.group(0)).date()
        except:
            return None

    def _parse_financial_value(self, text):
        if not text or text in ["-", "—", "N/A"]:
            return None
        try:
            return float(text.replace(" ", "").replace("\xa0", "").replace("−", "-"))
        except:
            return None
