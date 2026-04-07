import asyncio
import os
import sys

# Add current dir to path for imports
sys.path.append(os.getcwd())

from core.db.engine import DBEngine

async def cleanup_duplicates():
    try:
        # Strategy: Keep the row with the minimum sens_id for each duplicate group
        q = """
            DELETE FROM sens
            WHERE sens_id NOT IN (
                SELECT MIN(sens_id)
                FROM sens
                GROUP BY ticker, publication_datetime, content
            )
        """
        print("Cleaning up duplicates...")
        await DBEngine.execute(q)
        print("Cleanup complete.")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(cleanup_duplicates())
