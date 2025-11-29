import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import asyncio
import threading
import subprocess
import sys
import os

# Updated Imports
from core.db.engine import DBEngine
from components.watchlist import WatchlistWidget


class CommandCenter(ttk.Window):
    def __init__(self):
        super().__init__(themename="cosmo")
        self.title("JSE Command Center")
        self.geometry("1280x800")

        # 1. Initialize Async Loop
        self.loop = asyncio.new_event_loop()
        self.loop_thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self.loop_thread.start()

        # 2. Initialize Database (Singleton Pattern)
        # We run this on the main thread's interface to the loop
        self.async_run(DBEngine.get_pool())

        # 3. Start Background Services
        self.start_market_agent()

        # 4. Build UI
        self.create_layout()

    def _run_event_loop(self):
        """Run the asyncio event loop in a separate thread"""
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def async_run(self, coro):
        """Helper to run async coroutines from sync code"""
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result()

    def start_market_agent(self):
        """Start market_agent.py as a background daemon process"""
        try:
            # Note: Update this path if you move market_agent.py to modules/ later
            agent_path = os.path.join(os.path.dirname(__file__), "market_agent.py")

            self.market_agent_process = subprocess.Popen([sys.executable, agent_path])
            print(f"Market Agent started with PID: {self.market_agent_process.pid}")
        except Exception as e:
            print(f"Failed to start market_agent.py: {e}")

    def create_layout(self):
        # Top HUD
        hud_frame = ttk.Frame(self, height=50, bootstyle="secondary")
        hud_frame.pack(side=TOP, fill=X, padx=5, pady=5)

        ttk.Label(hud_frame, text="[Portfolio Scorecard Placeholder]").pack(
            side=LEFT, anchor=W, padx=10
        )

        # Main Watchlist Grid
        # CHANGE: Removed 'self.db' argument. The widget should now import data modules directly.
        self.watchlist = WatchlistWidget(self, self.on_ticker_select, self.async_run)
        self.watchlist.pack(fill=BOTH, expand=True, padx=5, pady=5)

        # Initial Load
        self.watchlist.refresh()

    def on_ticker_select(self, ticker):
        """Callback when watchlist row is clicked"""
        print(f"Selected: {ticker}")

    def on_closing(self):
        """Cleanup when window closes"""
        if hasattr(self, "market_agent_process"):
            self.market_agent_process.terminate()
        # Close DB Pool
        self.async_run(DBEngine.close())
        self.destroy()


if __name__ == "__main__":
    app = CommandCenter()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
