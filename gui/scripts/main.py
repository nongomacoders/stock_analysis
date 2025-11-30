import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import asyncio
import threading
import subprocess
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Updated Imports
from core.db.engine import DBEngine
from core.db.notifier import DBNotifier
from components.watchlist import WatchlistWidget


from components.chart_window import ChartWindow
from components.research_window import ResearchWindow


class CommandCenter(ttk.Window):
    def __init__(self):
        super().__init__(themename="cosmo")
        self.title("JSE Command Center")
        
        # Get screen dimensions
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        
        # Set geometry to left half of screen
        # Format: widthxheight+x+y
        self.geometry(f"{screen_width // 2}x{screen_height}+0+0")

        # 1. Initialize Async Loop
        self.loop = asyncio.new_event_loop()
        self.loop_thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self.loop_thread.start()

        # 2. Initialize Database (Singleton Pattern)
        # We run this on the main thread's interface to the loop
        self.async_run(DBEngine.get_pool())

        # 3. Start Background Services
        self.start_market_agent()
        
        # 4. Initialize Database Notifier
        self.notifier = DBNotifier()
        self.async_run(self.notifier.start_listening('action_log_changes', self.on_action_log_notification))

        # 5. Build UI
        self.create_layout()
        
        # Window References
        self.chart_window = None
        self.research_window = None

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
        
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        
        # Chart Window - Right Upper Quadrant
        if self.chart_window and self.chart_window.winfo_exists():
            self.chart_window.update_ticker(ticker)
            self.chart_window.lift()
        else:
            self.chart_window = ChartWindow(self, ticker, self.async_run)
            c_w = screen_width // 2
            c_h = screen_height // 2
            c_x = screen_width // 2
            c_y = 0
            self.chart_window.geometry(f"{c_w}x{c_h}+{c_x}+{c_y}")
        
        # Research Window - Right Lower Quadrant
        if self.research_window and self.research_window.winfo_exists():
            self.research_window.update_ticker(ticker)
            self.research_window.lift()
        else:
            self.research_window = ResearchWindow(self, ticker, self.async_run, on_data_change=self.watchlist.refresh)
            r_w = screen_width // 2
            r_h = screen_height // 2
            r_x = screen_width // 2
            r_y = screen_height // 2
            self.research_window.geometry(f"{r_w}x{r_h}+{r_x}+{r_y}")
    
    def on_action_log_notification(self, payload: str):
        """Handle action_log change notifications from PostgreSQL"""
        # Refresh watchlist when action_log changes
        # Use after() to ensure refresh happens on main thread
        self.after(0, self.watchlist.refresh)

    def on_closing(self):
        """Cleanup when window closes"""
        if hasattr(self, "market_agent_process"):
            self.market_agent_process.terminate()
        # Stop notifier
        if hasattr(self, "notifier"):
            self.async_run(self.notifier.stop_listening())
        # Close DB Pool
        self.async_run(DBEngine.close())
        self.destroy()


if __name__ == "__main__":
    app = CommandCenter()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
