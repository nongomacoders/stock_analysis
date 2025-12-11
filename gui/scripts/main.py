import ttkbootstrap as ttk
from ttkbootstrap.constants import TOP, X, LEFT, W, BOTH
import asyncio
import threading
import subprocess
import sys
import os
import logging
from logging import FileHandler

# Minimal, centralized logging configuration for the GUI application.
# - Default level INFO, configurable via environment variable LOG_LEVEL.
# - Simple timestamped format that is easy to grep in logs.
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
)

# Persistent rotating file handler (defaults to gui/logs/gui.log)
LOG_DIR = os.environ.get("LOG_DIR", os.path.join(os.path.dirname(__file__), "..", "logs"))
LOG_DIR = os.path.abspath(LOG_DIR)
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "gui.log")

# FileHandler will open the log file in write mode (mode='w') which truncates
# the file at startup, ensuring each session starts with a cleared file.

# Add a rotating file handler if not already configured
root_logger = logging.getLogger()
has_file_handler = False
for h in root_logger.handlers:
    # check if a RotatingFileHandler already points to our file
    try:
        if getattr(h, "baseFilename", None) == LOG_FILE:
            has_file_handler = True
            break
    except Exception:
        # some handlers may not have baseFilename
        continue

if not has_file_handler:
    # Use a simple file handler for the session logs (opened in write mode)
    file_handler = FileHandler(LOG_FILE, mode="w", encoding="utf-8")
    file_handler.setLevel(LOG_LEVEL)
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s: %(message)s"))
    root_logger.addHandler(file_handler)

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
        
        # Account for taskbar (typically 40-60 pixels)
        taskbar_height = 80
        usable_height = screen_height - taskbar_height
        
        # Set geometry to left half of screen
        # Format: widthxheight+x+y
        self.geometry(f"{screen_width // 2}x{usable_height}+0+0")

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
        self.async_run(self.notifier.add_listener('action_log_changes', self.on_action_log_notification))

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

    def async_run_bg(self, coro, callback=None):
        """Run async coroutine in background without blocking UI"""
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        
        def on_done(fut):
            try:
                result = fut.result()
                if callable(callback):
                    # Schedule callback on main thread passing result as arg
                    self.after(0, callback, result)
            except Exception as e:
                logging.getLogger(__name__).exception("Background task error: %s", e)
                if callable(callback):
                    self.after(0, callback, None)
        
        future.add_done_callback(on_done)

    def start_market_agent(self):
        """Start market_agent.py as a background daemon process"""
        try:
            # Note: Update this path if you move market_agent.py to modules/ later
            agent_path = os.path.join(os.path.dirname(__file__), "market_agent.py")

            self.market_agent_process = subprocess.Popen([sys.executable, agent_path])
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Failed to start market_agent.py: %s", e
            )

    def create_layout(self):
        # Top HUD
        hud_frame = ttk.Frame(self, height=50, bootstyle="secondary")
        hud_frame.pack(side=TOP, fill=X, padx=5, pady=5)

        ttk.Label(hud_frame, text="[Portfolio Scorecard Placeholder]").pack(
            side=LEFT, anchor=W, padx=10
        )

        # Main Watchlist Grid
        # CHANGE: Removed 'self.db' argument. The widget should now import data modules directly.
        self.watchlist = WatchlistWidget(self, self.on_ticker_select, self.async_run, self.async_run_bg, self.notifier)
        self.watchlist.pack(fill=BOTH, expand=True, padx=5, pady=5)

        # Initial Load
        self.watchlist.refresh()

    def on_ticker_select(self, ticker):
        """Callback when watchlist row is clicked"""
        logging.getLogger(__name__).info("Selected: %s", ticker)
        
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        
        # Account for taskbar
        taskbar_height = 80
        usable_height = screen_height - taskbar_height
        
        # Chart Window - Right Lower Quadrant
        if self.chart_window and self.chart_window.winfo_exists():
            self.chart_window.update_ticker(ticker)
            self.chart_window.lift()
        else:
            self.chart_window = ChartWindow(self, ticker, self.async_run)
            c_w = screen_width // 2
            c_h = usable_height // 2
            c_x = screen_width // 2
            c_y = usable_height // 2 + 20  # Add 10px gap
            self.chart_window.geometry(f"{c_w}x{c_h}+{c_x}+{c_y}")
        
        # Research Window - Right Upper Quadrant
        if self.research_window and self.research_window.winfo_exists():
            self.research_window.update_ticker(ticker)
            self.research_window.lift()
        else:
            self.research_window = ResearchWindow(self, ticker, self.async_run, self.async_run_bg, self.notifier, on_data_change=self.watchlist.refresh)
            r_w = screen_width // 2
            r_h = usable_height // 2
            r_x = screen_width // 2
            r_y = 0
            self.research_window.geometry(f"{r_w}x{r_h}+{r_x}+{r_y}")
    
    def on_action_log_notification(self, payload: str):
        """Handle action_log change notifications from PostgreSQL"""
        # Refresh watchlist when action_log changes
        # Use after() to ensure refresh happens on main thread
        self.after(0, self.watchlist.refresh)

    def on_closing(self):
        """Cleanup when window closes"""
        logging.getLogger(__name__).info("Closing application...")

        # 1. Terminate external processes
        if hasattr(self, "market_agent_process"):
            self.market_agent_process.terminate()

        # 2. Schedule async cleanup and stop the loop
        # We use async_run_bg so we don't block the main thread here.
        async def cleanup_and_stop_loop():
            if hasattr(self, "notifier"):
                await self.notifier.stop_listening()
            await DBEngine.close()
            self.loop.stop()

        asyncio.run_coroutine_threadsafe(cleanup_and_stop_loop(), self.loop)
        self.destroy() # Destroy the window, allowing the mainloop to exit


if __name__ == "__main__":
    app = CommandCenter()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
