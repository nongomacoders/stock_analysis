import logging
import os
import sys

logger = logging.getLogger(__name__)


async def run_market_data_update(mode: str = "all") -> int:
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
        rc = await run_scraper(mode=mode, symbol=None, pair=None, limit=None)
        return rc

    except Exception:
        logger.exception("Market data update failed")
        return 2
