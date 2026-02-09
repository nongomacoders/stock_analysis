from __future__ import annotations

import hashlib
import logging
from datetime import date
from pathlib import Path


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


def _normalize_path(value: Path | str) -> str:
    if isinstance(value, Path):
        return value.as_posix()
    return str(value).replace("\\", "/")


def _normalize_db_ticker(ticker: str) -> str:
    t = (ticker or "").strip()
    if not t:
        return t
    if t.upper().endswith(".JO"):
        return t
    return t + ".JO"


def _checksum_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def record_results_download(
    *,
    ticker: str,
    release_date: date | None,
    pdf_path: Path | str,
    pdf_url: str | None,
    source: str,
    data: bytes,
) -> bool:
    logger = logging.getLogger(__name__)

    if not DBEngine:
        logger.warning("DBEngine not available; cannot record results download")
        return False

    t = _normalize_db_ticker(ticker)
    if not t:
        logger.warning("Missing ticker; cannot record results download")
        return False

    checksum = _checksum_sha256(data)
    path_value = _normalize_path(pdf_path)

    query = """
        INSERT INTO results_downloads (
            ticker,
            release_date,
            pdf_path,
            pdf_url,
            source,
            checksum
        ) VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (ticker, pdf_path) DO UPDATE SET
            release_date = EXCLUDED.release_date,
            pdf_url = EXCLUDED.pdf_url,
            checksum = EXCLUDED.checksum
    """

    try:
        await DBEngine.execute(
            query,
            t,
            release_date,
            path_value,
            pdf_url,
            source,
            checksum,
        )
        logger.info("Recorded results download for %s (%s)", t, path_value)
        return True
    except Exception:
        logger.exception("Failed to record results download for %s", t)
        return False
