import asyncio
import asyncpg
from typing import Callable, Optional, Dict, List
from core.db.engine import DBEngine
import logging

logger = logging.getLogger(__name__)


class DBNotifier:
    """
    Manages PostgreSQL LISTEN/NOTIFY for real-time database change notifications.
    Uses a dedicated connection to listen for notifications on specified channels.
    """
    
    def __init__(self):
        self._connection: Optional[asyncpg.Connection] = None
        self._listener_tasks: Dict[str, asyncio.Task] = {}
        self._callbacks: Dict[str, List[Callable]] = {}
        
    async def add_listener(self, channel: str, callback: Callable[[str], None]):
        """
        Add a callback for a specific notification channel.
        Starts the underlying PostgreSQL listener if it's not already running for this channel.
        
        Args:
            channel: PostgreSQL notification channel name
            callback: Function to call when notification received (receives payload as string)
        """
        # Add callback to the list for this channel
        if channel not in self._callbacks:
            self._callbacks[channel] = []
        self._callbacks[channel].append(callback)
        
        # If we are not already listening on this channel, start a new listener.
        if channel not in self._listener_tasks:
            # Get a dedicated connection for listening
            pool = await DBEngine.get_pool()
            conn = await pool.acquire()
            
            # Add the actual asyncpg listener
            await conn.add_listener(channel, self._notification_handler)
            
            # Store the task and connection so we can manage them
            self._listener_tasks[channel] = asyncio.create_task(self._keep_alive(conn))
            logger.info("Notifier: Started listening on channel '%s'", channel)

    def _notification_handler(self, connection, pid, channel, payload):
        """Internal handler that dispatches notifications to all registered callbacks for a channel."""
        if channel in self._callbacks:
            loop = asyncio.get_event_loop()
            for callback in self._callbacks[channel]:
                # Schedule each callback to run on the main event loop
                loop.call_soon_threadsafe(self._handle_callback, callback, payload)
        
    def _handle_callback(self, callback: Callable[[str], None], payload: str):
        """
        Executes a single callback, handling both sync and async functions.
        This runs on the main event loop.
        """
        try:
            # Check if the callback is a coroutine function or a regular function.
            if asyncio.iscoroutinefunction(callback):
                # If it's an async function, create a task to run it.
                asyncio.create_task(callback(payload))
            else:
                # If it's a regular function, call it directly.
                callback(payload)
        except Exception:
            logger.exception("Error in notification callback")
        
    async def _keep_alive(self, connection: asyncpg.Connection):
        """Keeps a listener connection alive until cancelled."""
        try:
            # This will wait indefinitely until the task is cancelled.
            await asyncio.Future()
        except asyncio.CancelledError:
            # When cancelled, release the connection back to the pool
            pool = await DBEngine.get_pool()
            await pool.release(connection)
            logger.info("Notifier: Released connection for listener.")
            
    async def stop_listening(self):
        """Stop listening and cleanup resources."""
        for channel, task in self._listener_tasks.items():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            logger.info("Notifier: Stopped listening on channel '%s'", channel)

        self._listener_tasks.clear()
        self._callbacks.clear()
