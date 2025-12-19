from __future__ import annotations

import logging
from datetime import date, datetime, time
from typing import Optional, Dict, Any

import aiohttp
from bs4 import BeautifulSoup


# --- DBEngine import (same fallback pattern you already use) ---
def _try_import_dbengine():
    try:
        from core.db.engine import DBEngine  # type: ignore
        return DBEngine
    except Exception:
        try:
            from gui.core.db.engine import DBEngine  # type: ignore
            return DBEngine
        except Exception:
            return None


DBEngine = _try_import_dbengine()

URL = "https://tradingeconomics.com/commodities"

# Map your internal symbol -> how to find it on TradingEconomics.
# Add new commodities by adding entries here.
SYMBOL_MAP = {
    # Precious metals (CUR)
    "XAUUSD": {"commodity": "Gold",     "unit": "USD/oz", "row_selector": "tr[data-symbol='XAUUSD:CUR']"},
    "XPTUSD": {"commodity": "Platinum", "unit": "USD/oz", "row_selector": "tr[data-symbol='XPTUSD:CUR']"},
    "XPDUSD": {"commodity": "Palladium","unit": "USD/oz", "row_selector": "tr[data-symbol='XPDUSD:CUR']"},

    # Bulk / industrial (COM)
    "SCO":    {"commodity": "Iron Ore", "unit": "USD/t",  "row_selector": "tr[data-symbol='SCO:COM']"},
    "HG1":    {"commodity": "Copper",   "unit": "USD/lb", "row_selector": "tr[data-symbol='HG1:COM']"},
    "CO1":    {"commodity": "Brent",    "unit": "USD/bbl","row_selector": "tr[data-symbol='CO1:COM']"},
    "XRH":    {"commodity": "Rhodium",  "unit": "USD/oz", "row_selector": "tr[data-symbol='XRH:COM']"},
}


def _request_headers() -> dict:
    # TE blocks default Python user agents; present a normal browser identity.
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://tradingeconomics.com/",
        "Connection": "keep-alive",
    }


async def _fetch_te_html() -> Optional[str]:
    logger = logging.getLogger(__name__)
    timeout = aiohttp.ClientTimeout(total=30)

    try:
        async with aiohttp.ClientSession(headers=_request_headers(), timeout=timeout) as session:
            async with session.get(URL) as resp:
                if resp.status != 200:
                    logger.warning("TradingEconomics returned status %s", resp.status)
                    return None
                return await resp.text()
    except Exception:
        logger.exception("Failed to fetch TradingEconomics HTML")
        return None


def _parse_row_to_price(symbol: str, html: str) -> Optional[dict]:
    logger = logging.getLogger(__name__)

    cfg = SYMBOL_MAP.get(symbol)
    if not cfg:
        return None

    soup = BeautifulSoup(html or "", "html.parser")
    row = soup.select_one(cfg["row_selector"])
    if not row:
        logger.warning("Row not found for %s using selector: %s", symbol, cfg["row_selector"])
        return None

    price_td = row.select_one("td#p")
    time_td = row.select_one("td#date")

    if not price_td:
        logger.warning("Price cell td#p not found for %s", symbol)
        return None

    try:
        price = float(price_td.get_text(strip=True).replace(",", ""))
    except Exception:
        logger.warning("Failed to parse price for %s", symbol)
        return None

    # TE table often provides only HH:MM; store today's date + HH:MM as as_of_ts.
    as_of_ts = None
    if time_td:
        as_of_ts = _parse_as_of(time_td.get_text(strip=True))


    return {
        "symbol": symbol,
        "commodity": cfg["commodity"],
        "price": price,
        "unit": cfg["unit"],
        "currency": "USD",
        "as_of_ts": as_of_ts,
        "source": "TradingEconomics",
        "url": URL,
        "quality": "spot",
        "notes": "Parsed from TradingEconomics commodities table",
    }


async def _insert_price(row: Dict[str, Any]) -> None:
    if not DBEngine:
        raise RuntimeError("DBEngine not available")

    query = """
        INSERT INTO commodity_prices
        (symbol, commodity, price, unit, currency, as_of_ts, source, url, quality, notes)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
    """
    await DBEngine.execute(
        query,
        row["symbol"],
        row["commodity"],
        row["price"],
        row["unit"],
        row["currency"],
        row["as_of_ts"],
        row["source"],
        row["url"],
        row.get("quality"),
        row.get("notes"),
    )


async def run_tradingeconomics(*, symbol: str) -> int:
    """
    Return codes:
      0 = success OR clean skip (not implemented)
      1 = fetched but could not parse/insert (non-fatal)
      2 = fatal error
    """
    logger = logging.getLogger(__name__)
    symbol = (symbol or "").strip().upper()

    if symbol not in SYMBOL_MAP:
        logger.warning("Symbol %s not implemented for TradingEconomics yet; skipping.", symbol)
        return 0

    if not DBEngine:
        logger.error("DBEngine not available (run via standalone_scripts/commodity_scraper.py entrypoint).")
        return 2

    html = await _fetch_te_html()
    if not html:
        logger.warning("No HTML fetched for TradingEconomics; %s skipped", symbol)
        return 1

    row = _parse_row_to_price(symbol, html)
    if not row:
        logger.warning("No data parsed for %s", symbol)
        return 1

    try:
        await _insert_price(row)
        logger.info("Inserted %s: %s %s (as_of=%s)", row["commodity"], row["price"], row["unit"], row["as_of_ts"])
        return 0
    except Exception:
        logger.exception("Failed to insert price row for %s", symbol)
        return 2
    
def _parse_as_of(text: str) -> Optional[datetime]:
    """
    TradingEconomics table 'date' cell is sometimes:
      - "HH:MM" (intraday time)
      - "Dec/18" (month/day)
    We store a best-effort datetime.
    """
    if not text:
        return None
    s = text.strip()

    # Case 1: HH:MM
    if ":" in s:
        try:
            hh, mm = map(int, s.split(":"))
            return datetime.combine(date.today(), time(hh, mm))
        except Exception:
            return None

    # Case 2: Mon/DD e.g. Dec/18
    try:
        dt = datetime.strptime(s, "%b/%d")
        return dt.replace(year=date.today().year)
    except Exception:
        return None

