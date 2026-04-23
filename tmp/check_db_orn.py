import asyncio
import sys
from pathlib import Path

# Setup paths
root = Path.cwd()
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "gui"))

from scripts_standalone.results_scraper.watchlist import resolve_tickers_to_process

async def check():
    tickers = await resolve_tickers_to_process('ORN.JO', None)
    print(f"Tickers to process: {tickers}")

if __name__ == "__main__":
    asyncio.run(check())
