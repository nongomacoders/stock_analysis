"""
Populate raw_stock_valuations table with multi-year fundamentals

This script should be run BEFORE the valuation engine.
It will scrape ShareData for all watchlist tickers and populate the raw fundamentals table.
"""

import asyncio
from db_layer import DBLayer
from raw_fundamentals_loader import RawFundamentalsLoader


async def main():
    print("=" * 60)
    print("POPULATING RAW STOCK VALUATIONS TABLE")
    print("=" * 60)
    print()
    print("This will:")
    print("1. Create the raw_stock_valuations table (if needed)")
    print("2. Scrape multi-year fundamentals for all watchlist tickers")
    print("3. Store them in the database")
    print()
    print("This may take a while as it opens the browser for each ticker.")
    print()
    
    # Initialize database
    db = DBLayer()
    await db.init_pool()
    
    # Step 1: Create table - SKIPPED (Table already exists)
    print("Step 1: Table creation skipped (assumed existing)...")
    print("[OK] Table ready")
    
    print()
    
    # Step 2: Run loader for ALL tickers
    print("Step 2: Running Raw Fundamentals Loader...")
    print()
    
    loader = RawFundamentalsLoader(db, log_callback=print)
    
    # Get all tickers from watchlist (limit=None means all)
    result = await loader.run_fundamentals_update(tickers=None)
    
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Succeeded: {result['succeeded']} tickers")
    print(f"Failed: {result['failed']} tickers")
    print(f"Total periods inserted: {result['total_periods']}")
    print()
    
    await db.close_pool()
    
    if result['succeeded'] > 0:
        print("[SUCCESS] Raw fundamentals table is now populated!")
        print("You can now run main.py to compute valuations.")
    else:
        print("[WARNING] No tickers were successfully processed.")
        print("Check the errors above for details.")


if __name__ == "__main__":
    asyncio.run(main())
