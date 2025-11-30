import asyncio
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.db.engine import DBEngine


async def apply_migration():
    """Apply the action_log notification trigger migration."""
    
    # Read the SQL migration file
    migration_path = os.path.join(
        os.path.dirname(__file__), 
        "..", 
        "core", 
        "db", 
        "migrations", 
        "add_action_log_notify.sql"
    )
    
    with open(migration_path, 'r') as f:
        sql = f.read()
    
    # Execute the migration
    pool = await DBEngine.get_pool()
    async with pool.acquire() as conn:
        await conn.execute(sql)
    
    print("✓ Migration applied successfully!")
    print("✓ Created function: notify_action_log_change()")
    print("✓ Created trigger: action_log_notify_trigger on action_log table")
    
    await DBEngine.close()


if __name__ == "__main__":
    asyncio.run(apply_migration())
