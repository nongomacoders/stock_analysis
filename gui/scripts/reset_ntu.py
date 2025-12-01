import asyncio
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.db.engine import DBEngine

async def main():
    try :
        print("Deleting NTU.JO SENS entry...")
        # Delete SENS for NTU.JO from today
        q = "DELETE FROM SENS WHERE publication_datetime >= '2025-12-01 00:00:00'"
        await DBEngine.execute(q)
        print("Deleted.")
    except Exception as e:
        print(f"Error deleting NTU.JO SENS entry: {e}")

if __name__ == "__main__":
    asyncio.run(main())
