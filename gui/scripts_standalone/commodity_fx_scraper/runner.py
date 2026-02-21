from __future__ import annotations

import argparse
import asyncio
import logging
import os
from typing import List, Optional
from dotenv import load_dotenv

# Load environment variables from .env file (now in project root)
load_dotenv()

# DBEngine import (same fallback style used elsewhere in your project)
def _try_import_dbengine():
    try:
        from core.db.engine import DBEngine  # type: ignore
        return DBEngine, "core.db.engine"
    except Exception:
        try:
            from gui.core.db.engine import DBEngine  # type: ignore
            return DBEngine, "gui.core.db.engine"
        except Exception:
            return None, None


DBEngine, DBENGINE_IMPORT_PATH = _try_import_dbengine()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Market data scraper (commodities + FX, DB-driven)")
    p.add_argument(
        "--mode",
        choices=["commodities", "fx", "all"],
        default="all",
        help="What to run: commodities, fx, or all (default)",
    )
    p.add_argument(
        "--symbol",
        default=None,
        help="Run a single commodity symbol (commodities mode only, e.g. XAUUSD)",
    )
    p.add_argument(
        "--pair",
        default=None,
        help="Run a single FX pair (fx mode only, e.g. USDZAR)",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit: run only the first N items by priority",
    )
    return p


async def fetch_active_commodities(limit: Optional[int]) -> List[str]:
    if not DBEngine:
        raise RuntimeError("DBEngine not available")

    q = """
        SELECT symbol
        FROM public.commodity_universe
        WHERE is_active = true
        ORDER BY priority ASC, symbol ASC
    """
    rows = await DBEngine.fetch(q)
    syms = [r["symbol"].strip() for r in rows or [] if r.get("symbol")]

    if limit is not None:
        syms = syms[: max(0, int(limit))]

    return syms


async def fetch_active_fx_pairs(limit: Optional[int]) -> List[str]:
    if not DBEngine:
        raise RuntimeError("DBEngine not available")

    q = """
        SELECT pair
        FROM public.fx_universe
        WHERE is_active = true
        ORDER BY priority ASC, pair ASC
    """
    rows = await DBEngine.fetch(q)
    pairs = [r["pair"].strip() for r in rows or [] if r.get("pair")]

    if limit is not None:
        pairs = pairs[: max(0, int(limit))]

    return pairs


async def run(mode: str, symbol: Optional[str], pair: Optional[str], limit: Optional[int]) -> int:
    logger = logging.getLogger(__name__)
    logger.info("Starting market data scraper (mode=%s, DBEngine=%s)", mode, DBENGINE_IMPORT_PATH or "N/A")

    if not DBEngine:
        logger.error("DBEngine not available. Ensure correct entrypoint.")
        return 2

    failed = 0

    # --------------------------------------------------
    # COMMODITIES
    # --------------------------------------------------
    if mode in ("commodities", "all"):
        from .tradingeconomics import run_tradingeconomics

        if symbol:
            symbols = [symbol.strip().upper()]
        else:
            symbols = await fetch_active_commodities(limit)

        if not symbols:
            logger.warning("No active commodities found")
        else:
            for sym in symbols:
                rc = await run_tradingeconomics(symbol=sym)
                if rc != 0:
                    failed += 1

    # --------------------------------------------------
    # FX
    # --------------------------------------------------
    if mode in ("fx", "all"):
        from .tradingeconomics_fx import run_tradingeconomics_fx

        if pair:
            pairs = [pair.strip().upper()]
        else:
            pairs = await fetch_active_fx_pairs(limit)

        if not pairs:
            logger.warning("No active FX pairs found")
        else:
            for p in pairs:
                rc = await run_tradingeconomics_fx(pair=p)
                if rc != 0:
                    failed += 1

    logger.info("Market data scraper finished. failed=%d", failed)
    return 0 if failed == 0 else 2


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    args = build_parser().parse_args()
    return asyncio.run(run(args.mode, args.symbol, args.pair, args.limit))
