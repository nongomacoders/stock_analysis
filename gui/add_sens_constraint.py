import asyncio
import os
import sys

# Add current dir to path for imports
sys.path.append(os.getcwd())

from core.db.engine import DBEngine

async def add_constraint():
    try:
        # Check if constraint exists already (though unlikely)
        # We'll just try to add it.
        q = """
            ALTER TABLE sens 
            ADD CONSTRAINT uq_sens_ticker_date_content 
            UNIQUE (ticker, publication_datetime, content)
        """
        print("Adding unique constraint to sens table...")
        await DBEngine.execute(q)
        print("Constraint added successfully.")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(add_constraint())
