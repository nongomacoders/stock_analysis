import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from db_layer import DBLayer
from components.watchlist import WatchlistWidget
import asyncio
import threading

class CommandCenter(ttk.Window):
    def __init__(self):
        super().__init__(themename="cosmo")
        self.title("JSE Command Center")
        self.geometry("1280x800")
        
        self.db = DBLayer()
        
        # Initialize async event loop for database operations
        self.loop = asyncio.new_event_loop()
        self.loop_thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self.loop_thread.start()
        
        # Initialize database pool
        asyncio.run_coroutine_threadsafe(self.db.init_pool(), self.loop).result()
        
        self.create_layout()
    
    def _run_event_loop(self):
        """Run the asyncio event loop in a separate thread"""
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()
    
    def async_run(self, coro):
        """Helper to run async coroutines from sync code"""
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result()

    def create_layout(self):
        # 1. Top HUD
        hud_frame = ttk.Frame(self, height=50, bootstyle="secondary")
        hud_frame.pack(side=TOP, fill=X, padx=5, pady=5)
        
        # Left side - Scorecard placeholder
        ttk.Label(hud_frame, text="[Portfolio Scorecard Placeholder]").pack(side=LEFT, anchor=W, padx=10)

        # 2. Main Watchlist Grid (Takes up all remaining space)
        self.watchlist = WatchlistWidget(self, self.db, self.on_ticker_select, self.async_run)
        self.watchlist.pack(fill=BOTH, expand=True, padx=5, pady=5)

        # Initial Load
        self.watchlist.refresh()

    def on_ticker_select(self, ticker):
        """Callback when watchlist row is clicked"""
        print(f"Selected: {ticker}")

if __name__ == "__main__":
    app = CommandCenter()
    app.mainloop()