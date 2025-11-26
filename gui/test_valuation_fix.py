import asyncio
import sys
import os

# Add gui directory to path
sys.path.append(os.path.join(os.getcwd(), 'gui'))

from db_layer import DBLayer
from valuation_engine import ValuationEngine

async def run_test():
    print("Initializing DB Layer...")
    db = DBLayer()
    await db.init_pool()
    
    print("Initializing Valuation Engine...")
    engine = ValuationEngine(db, log_callback=print)
    
    # Manually select a ticker that was problematic
    ticker = "GRT.JO" 
    print(f"Testing valuation for {ticker}...")
    
    # We can't easily inject just one ticker into the engine's run loop without modifying it,
    # but we can call the internal methods if we want, or just let it run its selection logic.
    # However, to be sure we test the fix, let's try to invoke the scraping logic directly or 
    # just run the update and hope it picks a relevant ticker, OR we can temporarily modify the engine to pick this ticker.
    # Actually, the engine has a _scrape_fundamentals method. Let's test that first.
    
    print(f"\n--- Testing _scrape_fundamentals for {ticker} ---")
    fundamentals = await engine._scrape_fundamentals(ticker)
    
    if fundamentals:
        print("\n[SUCCESS] Fundamentals Scraped Successfully:")
        for k, v in fundamentals.items():
            print(f"  {k}: {v}")
    else:
        print("\n[FAILED] Failed to scrape fundamentals.")

    await db.close_pool()

if __name__ == "__main__":
    asyncio.run(run_test())
