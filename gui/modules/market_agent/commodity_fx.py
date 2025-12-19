import logging

logger = logging.getLogger(__name__)


async def run_market_data_update(mode: str = "all") -> int:
    """
    Runs the DB-driven commodity + FX scrapers.
    Uses the same process/event loop as the market agent.
    """
    try:
        # Import here so sys.path + DBEngine are already ready (same pattern as your runner)
        from standalone_scripts.commodity_scraper.runner import run as run_scraper

        # Our runner signature: run(mode, symbol, pair, limit)
        rc = await run_scraper(mode=mode, symbol=None, pair=None, limit=None)
        return rc

    except Exception:
        logger.exception("Market data update failed")
        return 2
