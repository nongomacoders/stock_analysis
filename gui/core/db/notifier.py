import asyncio
import asyncpg
from typing import Callable, Optional
from core.db.engine import DBEngine


class DBNotifier:
    """
    Manages PostgreSQL LISTEN/NOTIFY for real-time database change notifications.
    Uses a dedicated connection to listen for notifications on specified channels.
    """
    
    def __init__(self):
        self._connection: Optional[asyncpg.Connection] = None
        self._listener_task: Optional[asyncio.Task] = None
        self._running = False
        
    async def start_listening(self, channel: str, callback: Callable[[str], None]):
        """
        Start listening for notifications on the specified channel.
        
        Args:
            channel: PostgreSQL notification channel name
            callback: Function to call when notification received (receives payload as string)
        """
        if self._running:
            return
            
        # Get connection from pool
        pool = await DBEngine.get_pool()
        self._connection = await pool.acquire()
        
        # Set up notification handler
        def notification_handler(connection, pid, channel, payload):
            # Call the callback with the payload
            callback(payload)
        
        # Add listener
        await self._connection.add_listener(channel, notification_handler)
        
        self._running = True
        
        # Keep the listener alive
        self._listener_task = asyncio.create_task(self._keep_alive())
        
    async def _keep_alive(self):
        """Keep the listener connection alive."""
        try:
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
            
    async def stop_listening(self):
        """Stop listening and cleanup resources."""
        if not self._running:
            return
            
        self._running = False
        
        # Cancel the keep-alive task
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        
        # Remove listener and release connection back to pool
        if self._connection:
            try:
                # Remove all listeners before releasing
                await self._connection.remove_listener('action_log_changes', lambda *args: None)
            except:
                pass  # Ignore errors during cleanup
            
            pool = await DBEngine.get_pool()
            await pool.release(self._connection)
            self._connection = None
