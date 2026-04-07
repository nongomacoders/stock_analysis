import asyncio
import os
import sys

# Add current dir to path for imports
sys.path.append(os.getcwd())

from core.db.engine import DBEngine

async def create_index():
    try:
        q = """
            CREATE UNIQUE INDEX uq_sens_ticker_date_content_hash 
            ON sens (ticker, publication_datetime, md5(content));
        """
        print("Creating unique index with MD5 hash on sens table...")
        await DBEngine.execute(q)
        print("Index created successfully.")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(create_index())
