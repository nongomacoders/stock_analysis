import asyncio
from core.db.engine import DBEngine

async def main():
    print("Checking action_log for NTU.JO...")
    q = "SELECT * FROM action_log WHERE ticker = 'NTU.JO' ORDER BY log_timestamp DESC LIMIT 1"
    rows = await DBEngine.fetch(q)
    if rows:
        log = rows[0]
        print(f"\nFound entry:")
        print(f"  Timestamp: {log['log_timestamp']}")
        print(f"  Type: {log['trigger_type']}")
        print(f"  Content: {log['trigger_content'][:100]}...")
        print(f"  Analysis: {log['ai_analysis'][:200]}...")
    else:
        print("No action_log entry found for NTU.JO")

if __name__ == "__main__":
    asyncio.run(main())
