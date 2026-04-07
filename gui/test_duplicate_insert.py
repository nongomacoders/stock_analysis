import asyncio
import os
import sys
from datetime import datetime

# Add current dir to path for imports
sys.path.append(os.getcwd())

from core.db.engine import DBEngine

async def test_duplicate_insert():
    try:
        # First, find an existing record
        q = "SELECT ticker, publication_datetime, content FROM sens LIMIT 1"
        rows = await DBEngine.fetch(q)
        if not rows:
            print("No SENS records to test with.")
            return
            
        r = rows[0]
        ticker = r['ticker']
        pub_date = r['publication_datetime']
        content = r['content']
        
        print(f"Attempting to insert duplicate: {ticker} @ {pub_date}")
        
        # Try to insert exact same data
        ins_q = "INSERT INTO sens (ticker, publication_datetime, content) VALUES ($1, $2, $3)"
        await DBEngine.execute(ins_q, ticker, pub_date, content)
        print("ERROR: Duplicate insert succeeded (should have failed!)")
        
    except Exception as e:
        print(f"SUCCESS: Duplicate insert failed as expected: {e}")

if __name__ == "__main__":
    asyncio.run(test_duplicate_insert())
