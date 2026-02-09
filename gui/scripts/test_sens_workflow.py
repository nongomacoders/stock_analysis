import asyncio
import logging
from modules.analysis.engine import analyze_new_sens
from core.db.engine import DBEngine

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_sens_analysis():
    ticker = "ANG.JO"
    content = "Anglogold Ashanti has announced record production for the year."
    
    logger.info(f"Testing SENS analysis for {ticker}")
    
    # Check if we have context first
    row = await DBEngine.fetch("SELECT 1 FROM stock_analysis WHERE ticker = $1", ticker)
    if not row:
        logger.error(f"No research/strategy context for {ticker}. Please ensure it exists in 'stock_analysis' table.")
        return

    # Run analysis
    await analyze_new_sens(ticker, content)
    
    # Verify log entry
    log_rows = await DBEngine.fetch("SELECT * FROM action_log WHERE ticker = $1 ORDER BY created_at DESC LIMIT 1", ticker)
    if log_rows:
        log = log_rows[0]
        logger.info(f"Analysis saved: {log['ai_analysis'][:100]}...")
    else:
        logger.error("No analysis log saved.")

if __name__ == "__main__":
    asyncio.run(test_sens_analysis())
