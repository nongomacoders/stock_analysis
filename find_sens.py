import asyncio
import os
import sys
from datetime import datetime

# Add gui to path
sys.path.append(os.path.join(os.getcwd(), 'gui'))

from core.db.engine import DBEngine

async def main():
    ticker = "PPE.JO"
    target_dt = "2026-04-07 16:00:00"
    
    q = "SELECT content FROM SENS WHERE ticker = $1 AND publication_datetime = $2"
    rows = await DBEngine.fetch(q, ticker, datetime.fromisoformat(target_dt))
    
    if rows:
        print("--- CONTENT ---")
        print(rows[0]['content'][:500] + "...")
        print("--- END ---")
    else:
        print("Record not found. Checking nearby...")
        q_near = "SELECT ticker, publication_datetime, content FROM SENS WHERE ticker = $1 ORDER BY ABS(EXTRACT(EPOCH FROM (publication_datetime - $2::timestamp))) LIMIT 5"
        rows_near = await DBEngine.fetch(q_near, ticker, datetime.fromisoformat(target_dt))
        for r in rows_near:
            print(f"{r['ticker']} @ {r['publication_datetime']}")
            # print(r['content'][:100])

if __name__ == "__main__":
    asyncio.run(main())
