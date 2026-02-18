import asyncio
from core.db.engine import DBEngine
import logging

logging.basicConfig(level=logging.INFO)

async def check_pan_research():
    try:
        q = "SELECT LENGTH(deepresearch) as len FROM stock_analysis WHERE ticker = 'PAN.JO'"
        rows = await DBEngine.fetch(q)
        if rows:
            print(f"PAN.JO Deep Research length: {rows[0]['len']} characters")
        else:
            print("PAN.JO not found in stock_analysis")
            
        # Check all tickers to see if others are also large
        q_all = "SELECT ticker, LENGTH(deepresearch) as len FROM stock_analysis ORDER BY len DESC LIMIT 5"
        rows_all = await DBEngine.fetch(q_all)
        print("\nTop 5 largest research entries:")
        for r in rows_all:
            print(f"{r['ticker']}: {r['len']} characters")
            
    finally:
        await DBEngine.close()

if __name__ == "__main__":
    asyncio.run(check_pan_research())
