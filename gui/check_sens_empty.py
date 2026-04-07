import asyncio
import os
import sys

# Add current dir to path for imports
sys.path.append(os.getcwd())

from core.db.engine import DBEngine

async def check():
    try:
        q = """
            SELECT ticker, publication_datetime, content
            FROM sens 
            WHERE content = 'No content'
            ORDER BY publication_datetime DESC
            LIMIT 10
        """
        rows = await DBEngine.fetch(q)
        print(f"Found {len(rows)} SENS rows with 'No content'")
        for r in rows:
            print(f"Ticker: {r['ticker']} | Time: {r['publication_datetime']}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check())
