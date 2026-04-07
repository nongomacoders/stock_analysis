import asyncio
import os
import sys

# Add current dir to path for imports
sys.path.append(os.getcwd())

from core.db.engine import DBEngine

async def check_duplicates():
    try:
        q = """
            SELECT ticker, publication_datetime, content, COUNT(*) 
            FROM sens 
            GROUP BY ticker, publication_datetime, content 
            HAVING COUNT(*) > 1
        """
        rows = await DBEngine.fetch(q)
        print(f"Found {len(rows)} duplicate groups")
        
        total_dupes = 0
        for r in rows:
            print(f"{r['ticker']} @ {r['publication_datetime']}: {r['count']} copies")
            total_dupes += (r['count'] - 1)
        
        print(f"Total rows to remove: {total_dupes}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_duplicates())
