import asyncio
import os
import sys

# Add current dir to path for imports
sys.path.append(os.getcwd())

from core.db.engine import DBEngine

async def check_uniqueness():
    try:
        q = """
            SELECT ticker, publication_datetime, COUNT(*) 
            FROM sens 
            GROUP BY ticker, publication_datetime
            HAVING COUNT(*) > 1
        """
        rows = await DBEngine.fetch(q)
        print(f"Found {len(rows)} non-unique (ticker, publication_datetime) groups")
        for r in rows:
            print(f"{r['ticker']} @ {r['publication_datetime']}: {r['count']} instances")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_uniqueness())
