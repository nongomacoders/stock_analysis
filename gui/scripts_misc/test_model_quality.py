import asyncio
import os
import logging
from datetime import datetime, date
from pathlib import Path

# Add the project root to sys.path to allow imports from gui.core and gui.modules
import sys
project_root = Path(__file__).resolve().parents[1]
sys.path.append(str(project_root))

from core.db.engine import DBEngine
from modules.analysis.llm import query_ai
from modules.analysis.prompts import build_sens_prompt

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_models():
    ticker = "MTN.JO"
    today = date.today()
    
    logger.info(f"Testing models for {ticker} on {today}")

    # 1. Fetch SENS for today
    # Adjusting query to match the SENS table structure (ticker, publication_datetime, content)
    query = """
        SELECT content, publication_datetime 
        FROM SENS 
        WHERE ticker = $1 AND publication_datetime::date = $2
        ORDER BY publication_datetime DESC
    """
    sens_rows = await DBEngine.fetch(query, ticker, today)
    
    if not sens_rows:
        logger.warning(f"No SENS found for {ticker} today ({today}).")
        # For testing purposes, if no SENS today, maybe fetch the latest one?
        logger.info("Fetching the most recent SENS instead for testing...")
        query_latest = """
            SELECT content, publication_datetime 
            FROM SENS 
            WHERE ticker = $1 
            ORDER BY publication_datetime DESC 
            LIMIT 1
        """
        sens_rows = await DBEngine.fetch(query_latest, ticker)
        if not sens_rows:
            logger.error(f"No SENS found for {ticker} at all.")
            return

    # 2. Fetch Context (Research and Strategy)
    context_query = "SELECT research, strategy FROM stock_analysis WHERE ticker = $1"
    context_rows = await DBEngine.fetch(context_query, ticker)
    if not context_rows:
        logger.error(f"No research/strategy context found for {ticker}")
        return
    
    research_context = context_rows[0]["research"]
    strategy_context = context_rows[0]["strategy"]

    # 3. Fetch current price (optional, but used in prompt)
    price_query = "SELECT close_price FROM daily_stock_data WHERE ticker = $1 ORDER BY trade_date DESC LIMIT 1"
    price_row = await DBEngine.fetch(price_query, ticker)
    current_price = price_row[0]["close_price"] if price_row else None

    # Prepare findings
    results_file = project_root / "model_comparison_results.txt"
    with open(results_file, "w", encoding="utf-8") as f:
        f.write(f"Model Comparison Test - {datetime.now()}\n")
        f.write(f"Ticker: {ticker}\n")
        f.write("="*50 + "\n\n")

        for idx, row in enumerate(sens_rows):
            content = row["content"]
            pub_date = row["publication_datetime"]
            f.write(f"SENS Item {idx+1} ({pub_date}):\n")
            f.write(f"Content Snippet: {content[:200]}...\n")
            f.write("-" * 30 + "\n")

            # Build prompt
            prompt = build_sens_prompt(research_context, strategy_context, content, current_price)

            # Test both models
            models = ["gemini-3-flash-preview", "gemini-2.5-flash-lite"]
            
            for model_name in models:
                logger.info(f"Querying model: {model_name}")
                try:
                    response_obj = await query_ai(prompt, model=model_name)
                    
                    # Extract text from response object
                    if isinstance(response_obj, str):
                        analysis = response_obj
                    else:
                        analysis = getattr(response_obj, "text", str(response_obj))

                    f.write(f"\nMODEL: {model_name}\n")
                    f.write(f"ANALYSIS:\n{analysis}\n")
                    f.write("-" * 20 + "\n")
                except Exception as e:
                    logger.exception(f"Failed to query {model_name}")
                    f.write(f"\nMODEL: {model_name}\nERROR: {str(e)}\n")

            f.write("="*50 + "\n\n")

    logger.info(f"Test complete. Results saved to {results_file}")

if __name__ == "__main__":
    asyncio.run(test_models())
