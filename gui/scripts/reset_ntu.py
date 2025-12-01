import asyncio
from core.db.engine import DBEngine

async def main():
    print("Deleting NTU.JO SENS entry...")
    # Delete SENS for NTU.JO from today
    q = "DELETE FROM SENS WHERE ticker = 'NTU.JO' AND publication_datetime >= '2025-12-01 00:00:00'"
    await DBEngine.execute(q)
    print("Deleted.")

if __name__ == "__main__":
    asyncio.run(main())
