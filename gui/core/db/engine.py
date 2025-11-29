import asyncpg
from core.config import DB_CONFIG

class DBEngine:
    _pool = None

    @classmethod
    async def get_pool(cls):
        """Returns the connection pool, creating it if necessary."""
        if cls._pool is None:
            try:
                cls._pool = await asyncpg.create_pool(
                    host=DB_CONFIG["host"],
                    database=DB_CONFIG["dbname"],
                    user=DB_CONFIG["user"],
                    password=DB_CONFIG["password"],
                    min_size=2,
                    max_size=10
                )
            except Exception as e:
                print(f"CRITICAL DB ERROR: Could not create pool: {e}")
                raise e
        return cls._pool

    @classmethod
    async def close(cls):
        """Closes the connection pool."""
        if cls._pool:
            await cls._pool.close()
            cls._pool = None

    @classmethod
    async def fetch(cls, query, *args):
        """Helper for running SELECT queries quickly."""
        pool = await cls.get_pool()
        async with pool.acquire() as conn:
            return await conn.fetch(query, *args)
            
    @classmethod
    async def execute(cls, query, *args):
        """Helper for running INSERT/UPDATE queries."""
        pool = await cls.get_pool()
        async with pool.acquire() as conn:
            return await conn.execute(query, *args)