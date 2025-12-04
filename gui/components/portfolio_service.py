"""Persistence/service layer for portfolio operations.

Expose an async-compatible service class that encapsulates DB operations and
market data enrichment so the UI code can remain focused on presentation.

This module mirrors the prior async implementations that lived inside the
`PortfolioWindow` but keeps them separate so the UI file remains small.
"""
from typing import List, Dict, Optional
import logging
import asyncio

from core.db.engine import DBEngine
from modules.data.market import get_latest_price

logger = logging.getLogger(__name__)


class PortfolioService:
    """Service that performs async DB operations and data enrichment."""

    async def fetch_portfolios(self) -> List[Dict]:
        try:
            rows = await DBEngine.fetch("SELECT id, name FROM portfolios ORDER BY id")
            return [dict(r) for r in rows]
        except Exception:
            logger.exception("Failed to fetch portfolios")
            return []

    async def fetch_holdings(self, portfolio_id: int) -> List[Dict]:
        try:
            rows = await DBEngine.fetch(
                "SELECT id, ticker, quantity, average_buy_price FROM portfolio_holdings WHERE portfolio_id = $1 ORDER BY id",
                portfolio_id,
            )
            holdings = [dict(r) for r in rows]

            # fetch latest prices concurrently for each ticker (if available)
            tasks = [get_latest_price(h["ticker"]) for h in holdings]
            latests = []
            if tasks:
                latests = await asyncio.gather(*tasks, return_exceptions=True)

            enriched = []
            for h, l in zip(holdings, latests if latests else [{}] * len(holdings)):
                try:
                    latest_price = None
                    if isinstance(l, dict) and l:
                        raw = l.get("close_price")
                        try:
                            latest_price = float(raw) / 100.0 if raw is not None else None
                        except Exception:
                            latest_price = None
                    elif isinstance(l, Exception):
                        latest_price = None

                    avg = h.get("average_buy_price")
                    qty = h.get("quantity")
                    pl = None
                    cost_value = None
                    if avg is not None and qty is not None:
                        try:
                            avg_rands = float(avg) / 100.0
                            cost_value = avg_rands * float(qty)
                        except Exception:
                            cost_value = None

                    pct_pl = None
                    if latest_price is not None and avg is not None and qty is not None:
                        try:
                            avg_rands = float(avg) / 100.0
                            pl = (float(latest_price) - avg_rands) * float(qty)
                            if avg_rands and avg_rands != 0:
                                pct_pl = (float(latest_price) - avg_rands) / avg_rands * 100.0
                            else:
                                pct_pl = None
                        except Exception:
                            pl = None
                            pct_pl = None

                    h["latest_price"] = latest_price
                    h["pl"] = pl
                    h["pct_pl"] = pct_pl
                    h["cost_value"] = cost_value
                except Exception:
                    logger.exception("Error enriching holding with latest price")
                    h["latest_price"] = None
                    h["pl"] = None
                enriched.append(h)

            return enriched
        except Exception:
            logger.exception("Failed to fetch holdings")
            return []

    async def fetch_totals(self):
        try:
            rows = await DBEngine.fetch("SELECT id, ticker, quantity, average_buy_price FROM portfolio_holdings")
            holdings = [dict(r) for r in rows]

            if not holdings:
                return {"total_cost": 0.0, "total_pl": 0.0, "total_pct": 0.0, "total_value": 0.0}

            tasks = [get_latest_price(h["ticker"]) for h in holdings]
            latests = await asyncio.gather(*tasks, return_exceptions=True) if tasks else []

            total_cost = 0.0
            total_pl = 0.0
            total_value = 0.0
            for h, l in zip(holdings, latests if latests else [{}] * len(holdings)):
                latest_price = None
                if isinstance(l, dict) and l:
                    raw = l.get("close_price")
                    try:
                        latest_price = float(raw) / 100.0 if raw is not None else None
                    except Exception:
                        latest_price = None

                avg = h.get("average_buy_price")
                qty = h.get("quantity")
                if avg is None or qty is None:
                    continue
                try:
                    avg_rands = float(avg) / 100.0
                    cost_value = avg_rands * float(qty)
                    total_cost += cost_value
                    if latest_price is not None:
                        total_value += float(latest_price) * float(qty)
                        pl = (float(latest_price) - avg_rands) * float(qty)
                        total_pl += pl
                    else:
                        total_value += cost_value
                except Exception:
                    continue

            total_pct = (total_pl / total_cost * 100.0) if total_cost != 0 else 0.0
            return {"total_cost": total_cost, "total_pl": total_pl, "total_pct": total_pct, "total_value": total_value}
        except Exception:
            logger.exception("Failed to compute totals")
            return {"total_cost": 0.0, "total_pl": 0.0, "total_pct": 0.0, "total_value": 0.0}

    async def upsert_holding(self, portfolio_id: int, ticker: str, qty: float, avg_price: float):
        try:
            exists = await DBEngine.fetch("SELECT id FROM portfolio_holdings WHERE portfolio_id = $1 AND ticker = $2", portfolio_id, ticker)
            if exists:
                ex_id = exists[0].get("id") if isinstance(exists[0], dict) else exists[0]["id"]
                await DBEngine.execute("UPDATE portfolio_holdings SET quantity = $1, average_buy_price = $2 WHERE id = $3", qty, avg_price, ex_id)
                logger.info("Updated holding %s in portfolio %s", ticker, portfolio_id)
            else:
                await DBEngine.execute(
                    "INSERT INTO portfolio_holdings (portfolio_id, ticker, quantity, average_buy_price) VALUES ($1, $2, $3, $4)",
                    portfolio_id,
                    ticker,
                    qty,
                    avg_price,
                )
                logger.info("Added holding %s in portfolio %s", ticker, portfolio_id)
                # If this ticker exists in the watchlist, mark it as Active-Trade
                try:
                    # Try update first, fall back to insert if no rows updated
                    res = await DBEngine.execute("UPDATE watchlist SET status = $1 WHERE ticker = $2", "Active-Trade", ticker)
                    updated = 0
                    if isinstance(res, str) and res.split()[0].upper() == 'UPDATE':
                        try:
                            updated = int(res.split()[1]) if len(res.split()) > 1 else 0
                        except Exception:
                            updated = 0

                    if updated == 0:
                        await DBEngine.execute("INSERT INTO watchlist (ticker, status) VALUES ($1, $2)", ticker, "Active-Trade")
                except Exception:
                    logger.exception("Failed to mark watchlist status for %s", ticker)
        except Exception:
            logger.exception("Upsert holding failed")

    async def update_holding(self, hid: int, ticker: str, qty: float, avg_price: float):
        try:
            await DBEngine.execute(
                "UPDATE portfolio_holdings SET ticker = $1, quantity = $2, average_buy_price = $3 WHERE id = $4",
                ticker,
                qty,
                avg_price,
                int(hid),
            )
            logger.info("Updated holding id=%s -> %s qty=%s avg=%s", hid, ticker, qty, avg_price)
        except Exception:
            logger.exception("Update holding failed")

    async def delete_holding(self, hid: int):
        try:
            await DBEngine.execute("DELETE FROM portfolio_holdings WHERE id = $1", int(hid))
            logger.info("Deleted holding %s", hid)
        except Exception:
            logger.exception("Delete holding failed")

    async def delete_holding_and_mark_wl_active(self, hid: int):
        """Delete a holding by id and ensure the watchlist status for its ticker is set to WL-Active.

        This queries the ticker first, deletes the holding, and then updates or inserts the
        watchlist row so its status becomes WL-Active. Returns the ticker (if known) and
        True on success, False on failure.
        """
        try:
            # Find the ticker for this holding first
            rows = await DBEngine.fetch("SELECT ticker FROM portfolio_holdings WHERE id = $1", int(hid))
            ticker = None
            if rows:
                first = rows[0]
                ticker = first.get("ticker") if isinstance(first, dict) else first["ticker"]

            # Delete the holding
            await DBEngine.execute("DELETE FROM portfolio_holdings WHERE id = $1", int(hid))
            logger.info("Deleted holding %s (ticker=%s)", hid, ticker)

            # If we found a ticker, mark it WL-Active in the watchlist (update then insert fallback)
            if ticker:
                try:
                    res = await DBEngine.execute("UPDATE watchlist SET status = $1 WHERE ticker = $2", "WL-Active", ticker)
                    updated = 0
                    if isinstance(res, str) and res.split()[0].upper() == 'UPDATE':
                        try:
                            updated = int(res.split()[1]) if len(res.split()) > 1 else 0
                        except Exception:
                            updated = 0

                    if updated == 0:
                        await DBEngine.execute("INSERT INTO watchlist (ticker, status) VALUES ($1, $2)", ticker, "WL-Active")

                    logger.info("Marked watchlist status for %s -> WL-Active", ticker)
                except Exception:
                    logger.exception("Failed to mark watchlist status for %s", ticker)

            return True
        except Exception:
            logger.exception("delete_holding_and_mark_wl_active failed for id=%s", hid)
            return False

    async def create_portfolio(self, name: str):
        try:
            await DBEngine.execute("INSERT INTO portfolios (name) VALUES ($1)", name)
            logger.info("Created portfolio %s", name)
        except Exception:
            logger.exception("Create portfolio failed")

    async def rename_portfolio(self, pid: int, new_name: str):
        try:
            await DBEngine.execute("UPDATE portfolios SET name = $1 WHERE id = $2", new_name, pid)
            logger.info("Renamed portfolio %s -> %s", pid, new_name)
        except Exception:
            logger.exception("Rename portfolio failed")

    async def delete_portfolio(self, pid: int):
        try:
            await DBEngine.execute("DELETE FROM portfolio_holdings WHERE portfolio_id = $1", pid)
            await DBEngine.execute("DELETE FROM portfolios WHERE id = $1", pid)
            logger.info("Deleted portfolio %s", pid)
        except Exception:
            logger.exception("Delete portfolio failed")
