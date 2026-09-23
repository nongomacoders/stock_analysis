import logging
import os
import sys

logger = logging.getLogger(__name__)


async def run_market_data_update(mode: str = "all", *, ingestion_run_id=None):
    """
    Runs the DB-driven commodity + FX scrapers.
    Uses the same process/event loop as the market agent.
    """
    try:
        # Ensure the GUI root (which contains `standalone_scripts/`) is on sys.path.
        # This allows imports like `standalone_scripts.*` to work regardless of
        # whether the process was started from the repository root or elsewhere.
        _gui_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        if _gui_root not in sys.path:
            sys.path.insert(0, _gui_root)

        # Import here so sys.path + DBEngine are already ready (same pattern as your runner)
        from scripts_standalone.commodity_scraper.runner import run as run_scraper

        # Our runner signature: run(mode, symbol, pair, limit)
        detail = await run_scraper(mode=mode, symbol=None, pair=None, limit=None,
                                   ingestion_run_id=ingestion_run_id, return_details=True)
        from modules.data.ingestion_runs import IngestionResult
        if detail.get("configured",1)==0:
            return IngestionResult("skipped")
        if detail["failed"] or detail["fetched"] == 0:
            errors=set(detail.get("errors",[]))
            code=next(iter(errors)) if len(errors)==1 else "mixed_failures" if errors else "source_no_data"
            return IngestionResult.failure(code,
                f"{detail['failed']} instruments failed; {detail['fetched']} fetched",
                retryable=code not in {"parser_failure","validation_failure"},
                fetched=detail["fetched"], written=detail["written"])
        return IngestionResult.success(detail["fetched"], detail["written"])

    except Exception:
        logger.exception("Market data update failed")
        from modules.data.ingestion_runs import IngestionResult
        return IngestionResult.failure("market_worker_failure", "Market data update failed")
