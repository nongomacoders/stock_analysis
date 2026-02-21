import asyncio
import sys
import os
import logging
from dotenv import load_dotenv

# Load environment variables from .env file (now in project root)
load_dotenv()

# --- PATH FIX ---
# This allows the script to import from 'core' and 'modules'
# even though it is inside the 'scripts' folder.
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, ".."))
sys.path.append(project_root)

# --- IMPORTS ---
from core.db.engine import DBEngine
from modules.data.loader import RawFundamentalsLoader
from playwright_scraper.pw import logout_sharedata

logger = logging.getLogger(__name__)


async def main():
    result = None
    try:
        logger.info("%s", '=' * 60)
        logger.info("POPULATING RAW STOCK VALUATIONS TABLE")
        logger.info("%s", '=' * 60)

        # 1. Initialize DB Pool
        logger.info("Initializing Database Connection...")
        await DBEngine.get_pool()

        # 2. Run Loader
        logger.info("Running Fundamentals Loader...")
        loader = RawFundamentalsLoader(log_callback=logger.info)

        # Run the update (tickers=None means "do all tickers in DB")
        result = await loader.run_fundamentals_update(tickers=['NPN.JO'])

        logger.info("%s", '\n' + ('=' * 60))
        logger.info("SUMMARY")
        logger.info("%s", '=' * 60)
        logger.info("Succeeded: %s tickers", result['succeeded'])
        logger.info("Failed: %s tickers", result['failed'])
        logger.info("Total periods inserted: %s", result['total_periods'])

        if result["succeeded"] > 0:
            logger.info("[SUCCESS] Process complete.")
        else:
            logger.warning("[WARNING] No tickers processed successfully.")
    finally:
        # 3. Close Pool
        try:
            await DBEngine.close()
        except Exception:
            logger.exception("Error closing DB")

        # 4. Logout from ShareData to avoid concurrent-login lockouts next run
        try:
            await logout_sharedata(headless=True)
        except Exception:
            logger.exception("Error logging out of ShareData")


if __name__ == "__main__":
    asyncio.run(main())
