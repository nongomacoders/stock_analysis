from __future__ import annotations

import logging
from datetime import date, datetime


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


DBEngine, DBENGINE_IMPORT_PATH = _try_import_dbengine()


def _coerce_to_datetime(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, str):
        v = value.strip()
        if not v:
            return None
        # Best-effort parsing for common DB string formats.
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
        ):
            try:
                dt = datetime.strptime(v[: len(fmt)], fmt)
                return dt
            except Exception:
                continue
    return None


def _normalize_db_ticker(ticker: str) -> str:
    t = (ticker or "").strip()
    if not t:
        return t
    if t.upper().endswith(".JO"):
        return t
    return t + ".JO"


async def fetch_max_results_release_datetime(ticker: str) -> datetime | None:
    """Return max(results_release_date) for raw_stock_valuations for this ticker.

    Uses asyncpg-style parameter placeholders ($1).
    """
    logger = logging.getLogger(__name__)

    if not DBEngine:
        logger.warning("DBEngine not available; cannot query max(results_release_date)")
        return None

    query = """
        SELECT max(results_release_date) AS max_date
        FROM raw_stock_valuations
        WHERE ticker = $1
    """

    candidates = []
    db_ticker = _normalize_db_ticker(ticker)
    if db_ticker:
        candidates.append(db_ticker)
    if ticker and ticker.strip() and ticker.strip() not in candidates:
        candidates.append(ticker.strip())
    if ticker and ticker.strip().upper().endswith(".JO"):
        no_suffix = ticker.strip()[:-3]
        if no_suffix and no_suffix not in candidates:
            candidates.append(no_suffix)

    for cand in candidates:
        rows = await DBEngine.fetch(query, cand)
        if not rows:
            continue

        row0 = rows[0]
        try:
            raw = row0.get("max_date") if hasattr(row0, "get") else row0["max_date"]
        except Exception:
            raw = None

        max_dt = _coerce_to_datetime(raw)
        if max_dt:
            logger.info("Max results_release_date for %s: %s", cand, max_dt.isoformat(sep=" "))
            return max_dt

    logger.info("No results_release_date found for %s", db_ticker)
    return None
