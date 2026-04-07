import asyncio
import os
import sys

# Add current dir to path for imports
sys.path.append(os.getcwd())

from core.db.engine import DBEngine

async def check():
    try:
        q = """
            SELECT log_id, ticker, log_timestamp, trigger_content, ai_analysis 
            FROM action_log 
            WHERE trigger_content = 'No content'
            ORDER BY log_timestamp DESC
            LIMIT 10
        """
        rows = await DBEngine.fetch(q)
        print(f"Found {len(rows)} entries with 'No content'")
        for r in rows:
            print(f"ID: {r['log_id']} | Ticker: {r['ticker']} | Time: {r['log_timestamp']}")
            print(f"Analysis (first 100 char): {r['ai_analysis'][:100]}...")
            print("-" * 20)
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check())
