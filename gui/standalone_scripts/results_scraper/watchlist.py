from __future__ import annotations

import logging


def _try_import_dbengine():
    try:
        from core.db.engine import DBEngine  # type: ignore

        return DBEngine, "core.db.engine"
    except Exception as ex_core_import:
        try:
            from gui.core.db.engine import DBEngine  # type: ignore

            return DBEngine, "gui.core.db.engine"
        except Exception as ex_gui_import:
            logger = logging.getLogger(__name__)
            logger.warning("Failed to import DBEngine from core.db.engine: %s", ex_core_import)
            logger.warning("Failed to import DBEngine from gui.core.db.engine: %s", ex_gui_import)
            return None, None


def _try_import_watchlist_helper():
    try:
        from gui.modules.data.scraper import get_watchlist_tickers_without_deepresearch  # type: ignore

        return get_watchlist_tickers_without_deepresearch, "gui.modules.data.scraper"
    except Exception as ex_gui_helper:
        try:
            from modules.data.scraper import get_watchlist_tickers_without_deepresearch  # type: ignore

            return get_watchlist_tickers_without_deepresearch, "modules.data.scraper"
        except Exception as ex_modules_helper:
            logger = logging.getLogger(__name__)
            logger.warning(
                "Failed to import get_watchlist_tickers_without_deepresearch from gui.modules.data.scraper: %s",
                ex_gui_helper,
            )
            logger.warning(
                "Failed to import get_watchlist_tickers_without_deepresearch from modules.data.scraper: %s",
                ex_modules_helper,
            )
            return None, None


DBEngine, DBENGINE_IMPORT_PATH = _try_import_dbengine()
get_watchlist_tickers_without_deepresearch, WATCHLIST_HELPER_PATH = _try_import_watchlist_helper()


async def get_watchlist_tickers_from_db(limit: int | None = None) -> list[str]:
    """Fallback server-side SQL if the helper module import fails."""
    logger = logging.getLogger(__name__)
    if not DBEngine:
        logger.warning("DBEngine not available; cannot query watchlist directly")
        return []

    query = """
        SELECT w.ticker
        FROM watchlist w
        JOIN stock_details sd ON w.ticker = sd.ticker
        LEFT JOIN stock_analysis sa ON (sa.ticker = w.ticker OR sa.ticker = REPLACE(w.ticker, '.JO', ''))
        WHERE w.status NOT IN ('WL-Sleep')
          AND (sa.deepresearch IS NULL OR TRIM(sa.deepresearch) = '')
        ORDER BY
            CASE WHEN sd.priority = 'A' THEN 1
                 WHEN sd.priority = 'B' THEN 2
                 ELSE 3 END,
            w.ticker
    """
    if limit:
        query += f" LIMIT {limit}"

    rows = await DBEngine.fetch(query)
    tickers = [r["ticker"] for r in rows]
    logger.info("DB fallback: found %d tickers without deepresearch", len(tickers))
    return tickers


async def debug_get_watchlist_rows(limit: int | None = None):
    logger = logging.getLogger(__name__)
    if not DBEngine:
        logger.warning("DBEngine not available; cannot query watchlist directly")
        return []

    query = """
        SELECT w.ticker, sa.deepresearch
        FROM watchlist w
        LEFT JOIN stock_analysis sa ON (sa.ticker = w.ticker OR sa.ticker = REPLACE(w.ticker, '.JO', ''))
        WHERE w.status NOT IN ('WL-Sleep')
        ORDER BY w.ticker
    """
    if limit:
        query += f" LIMIT {limit}"

    rows = await DBEngine.fetch(query)
    return rows


async def resolve_tickers_to_process(ticker: str | None, limit: int | None) -> list[str]:
    logger = logging.getLogger(__name__)

    if ticker:
        return [ticker]

    if get_watchlist_tickers_without_deepresearch:
        return await get_watchlist_tickers_without_deepresearch(limit=limit)

    if DBEngine:
        try:
            return await get_watchlist_tickers_from_db(limit=limit)
        except Exception:
            logger.warning("DB fallback query failed; no tickers to process")
            return []

    logger.warning("No watchlist helper and no DB engine; cannot determine tickers to process")
    return []
