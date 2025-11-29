import asyncio
import sys
import os

# --- PATH FIX ---
# This allows the script to import from 'core' and 'modules'
# even though it is inside the 'scripts' folder.
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, ".."))
sys.path.append(project_root)

# --- IMPORTS ---
from core.db.engine import DBEngine
from modules.data.loader import RawFundamentalsLoader


async def main():
    print("=" * 60)
    print("POPULATING RAW STOCK VALUATIONS TABLE")
    print("=" * 60)

    # 1. Initialize DB Pool
    print("Initializing Database Connection...")
    await DBEngine.get_pool()

    # 2. Run Loader
    print("Running Fundamentals Loader...")
    loader = RawFundamentalsLoader(log_callback=print)

    # Run the update (tickers=None means "do all tickers in DB")
    result = await loader.run_fundamentals_update(tickers=None)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Succeeded: {result['succeeded']} tickers")
    print(f"Failed: {result['failed']} tickers")
    print(f"Total periods inserted: {result['total_periods']}")

    # 3. Close Pool
    await DBEngine.close()

    if result["succeeded"] > 0:
        print("[SUCCESS] Process complete.")
    else:
        print("[WARNING] No tickers processed successfully.")


if __name__ == "__main__":
    asyncio.run(main())
