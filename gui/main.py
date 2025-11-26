import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from db_layer import DBLayer
from components.watchlist import WatchlistWidget
from components.admin import AdminWindow
import asyncio
import threading
# We will add Scorecard and SensFeed later to keep it simple for now

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
        
        # Admin window reference
        self.admin_window = None
    
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
        
        # Right side - Admin button
        admin_btn = ttk.Button(
            hud_frame,
            text="Admin",
            bootstyle="info-outline",
            command=self.open_admin,
            width=10
        )
        admin_btn.pack(side=RIGHT, padx=10)

        # 2. Main Watchlist Grid (Takes up all remaining space)
        self.watchlist = WatchlistWidget(self, self.db, self.on_ticker_select, self.async_run)
        self.watchlist.pack(fill=BOTH, expand=True, padx=5, pady=5)

        # Initial Load
        self.watchlist.refresh()
    
    def open_admin(self):
        """Open the admin panel window"""
        # Only allow one admin window at a time
        if self.admin_window is None or not self.admin_window.winfo_exists():
            self.admin_window = AdminWindow(self, self.db, self.loop)
        else:
            # If window already exists, bring it to focus
            self.admin_window.focus()

    def on_ticker_select(self, ticker):
        """Callback when watchlist row is clicked"""
        # Currently no action needed as Strategy Panel is removed
        print(f"Selected: {ticker}")

if __name__ == "__main__":
    app = CommandCenter()
    app.mainloop()