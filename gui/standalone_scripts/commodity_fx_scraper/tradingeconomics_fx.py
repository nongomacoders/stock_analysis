from __future__ import annotations

import logging
from datetime import date, datetime, time
from typing import Optional, Dict, Any

import aiohttp
from bs4 import BeautifulSoup

URL = "https://tradingeconomics.com/currencies"

# DBEngine import (same fallback style)
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

# DB is authoritative. This map is only “how to find it on TE”.
PAIR_MAP = {
    "USDZAR": {"row_selector": "tr[data-symbol='USDZAR:CUR']"},
    "EURUSD": {"row_selector": "tr[data-symbol='EURUSD:CUR']"},
    "GBPUSD": {"row_selector": "tr[data-symbol='GBPUSD:CUR']"},
}

def _headers() -> dict:
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

def _parse_as_of(text: str) -> Optional[datetime]:
    if not text:
        return None
    s = text.strip()
    if ":" in s:
        try:
            hh, mm = map(int, s.split(":"))
            return datetime.combine(date.today(), time(hh, mm))
        except Exception:
            return None
    return None

async def _fetch_html() -> Optional[str]:
    logger = logging.getLogger(__name__)
    timeout = aiohttp.ClientTimeout(total=30)
    try:
        async with aiohttp.ClientSession(headers=_headers(), timeout=timeout) as session:
            async with session.get(URL) as resp:
                if resp.status != 200:
                    logger.warning("TradingEconomics returned status %s", resp.status)
                    return None
                return await resp.text()
    except Exception:
        logger.exception("Failed to fetch TradingEconomics currencies HTML")
        return None

def _parse_pair(pair: str, html: str) -> Optional[Dict[str, Any]]:
    logger = logging.getLogger(__name__)
    cfg = PAIR_MAP.get(pair)
    if not cfg:
        return None

    soup = BeautifulSoup(html or "", "html.parser")
    row = soup.select_one(cfg["row_selector"])
    if not row:
        logger.warning("Row not found for %s using selector %s", pair, cfg["row_selector"])
        return None

    p_td = row.select_one("td#p")
    d_td = row.select_one("td#date")
    if not p_td:
        logger.warning("Price cell td#p not found for %s", pair)
        return None

    try:
        rate = float(p_td.get_text(strip=True).replace(",", ""))
    except Exception:
        logger.warning("Failed to parse rate for %s", pair)
        return None

    as_of_ts = _parse_as_of(d_td.get_text(strip=True) if d_td else "")
    return {
        "pair": pair,
        "rate": rate,
        "as_of_ts": as_of_ts,
        "source": "TradingEconomics",
        "url": URL,
        "notes": "Parsed from TradingEconomics currencies table",
    }

async def _insert_fx(row: Dict[str, Any]) -> None:
    if not DBEngine:
        raise RuntimeError("DBEngine not available")

    q = """
        INSERT INTO public.fx_rates (pair, rate, as_of_ts, source, url, notes)
        VALUES ($1,$2,$3,$4,$5,$6)
    """
    await DBEngine.execute(q, row["pair"], row["rate"], row["as_of_ts"], row["source"], row["url"], row.get("notes"))

async def run_tradingeconomics_fx(*, pair: str) -> int:
    """
    0 = success OR clean skip (not implemented)
    1 = non-fatal fetch/parse issue
    2 = fatal
    """
    logger = logging.getLogger(__name__)
    pair = (pair or "").strip().upper()

    if pair not in PAIR_MAP:
        logger.warning("FX pair %s not implemented for TradingEconomics yet; skipping.", pair)
        return 0

    if not DBEngine:
        logger.error("DBEngine not available (run via commodity_scraper entrypoint).")
        return 2

    html = await _fetch_html()
    if not html:
        return 1

    row = _parse_pair(pair, html)
    if not row:
        return 1

    try:
        await _insert_fx(row)
        logger.info("Inserted FX %s: %s (as_of=%s)", pair, row["rate"], row["as_of_ts"])
        return 0
    except Exception:
        logger.exception("Failed to insert FX row for %s", pair)
        return 2
