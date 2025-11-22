# --- ADD THESE LINES ---
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import messagebox  # Keep this for popups

# --- END OF CHANGES
import psycopg2
import sys
import datetime

# Import tab classes

from tab_scan import ScanTab
from tab_details import DetailsTab
from tab_analysis import AnalysisTab
from tab_earnings import EarningsTab
from tab_strategy import StrategyTab
from tab_logs import LogsTab  # <-- ADD THIS IMPORT
from tab_portfolio import PortfolioTab # <-- ADD THIS IMPORT

# Import config
from config import DB_CONFIG


class StockAnalyzerApp(ttk.Window):
    def __init__(self):
        super().__init__(themename="darkly")

        print("DEBUG: App __init__: Starting application...")
        self.title("JSE Stock Analyzer")
        self.geometry("1200x800")  # Made window larger

        print("DEBUG: App __init__: Connecting to database...")
        self.db_conn = self.connect_to_db()
        self.selected_level_id = None

        if not self.db_conn:
            print("DEBUG: App __init__: Database connection FAILED.")
            messagebox.showerror(
                "Database Error",
                "Could not connect to the database. The application will close.",
            )
            self.destroy()
            return

        print("DEBUG: App __init__: Database connection successful.")

        print("DEBUG: App __init__: Creating widgets...")
        print("DEBUG (GUI): This is stock_analyzer_gui.py. Loading widgets...")
        self.create_widgets()

        print("DEBUG: App __init__: Setting close protocol...")
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def connect_to_db(self):
        """Establishes connection to the PostgreSQL database."""
        print("DEBUG: DB: Attempting to connect...")
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            print("DEBUG: DB: Connection successful.")
            return conn
        except Exception as e:
            print(f"DEBUG: DB: Connection error: {e}")
            return None

    def log_error(self, title, message):
        """Centralized error logging to console and popup."""
        print(f"\n--- ERROR POPUP ---")
        print(f"Title: {title}")
        print(f"Message: {message}")
        print(f"-------------------\n")
        messagebox.showerror(title, message)

    def create_widgets(self):
        """Creates the main GUI layout."""

        print("DEBUG: Widgets: Creating notebook...")
        self.notebook = ttk.Notebook(self)

        print("DEBUG: Widgets: Creating Scan tab...")
        # Pass the cross-tab callback function to the ScanTab

        self.scan_tab = ScanTab(
            self.notebook,
            DB_CONFIG,
            self.db_conn,
            self.log_error,
            self.load_ticker_on_analysis_tab,
        )
        self.notebook.add(self.scan_tab, text="Scan")
        # --- ADD THIS BLOCK ---
        self.earnings_tab = EarningsTab(
            self.notebook, DB_CONFIG, self.log_error
        )  # <-- CHANGE
        self.notebook.add(self.earnings_tab, text="Earnings History")
        # --- ADD THIS BLOCK (e.g., at the top) ---
        self.logs_tab = LogsTab(self.notebook, DB_CONFIG, self.log_error)
        self.notebook.add(self.logs_tab, text='Action Log')
        # --- END BLOCK ---
        # --- ADD THIS BLOCK ---
        self.strategy_tab = StrategyTab(self.notebook, DB_CONFIG, self.log_error)
        self.notebook.add(self.strategy_tab, text="Strategy")
        # --- END BLOCK ---
        
        # --- ADD PORTFOLIO TAB ---
        self.portfolio_tab = PortfolioTab(self.notebook, DB_CONFIG, self.log_error)
        self.notebook.add(self.portfolio_tab, text="Portfolio")
        # --- END BLOCK ---

        self.details_tab = DetailsTab(
            self.notebook, DB_CONFIG, self.log_error
        )  # <-- CHANGE
        self.notebook.add(self.details_tab, text="Stock Details")

        print("DEBUG (GUI): Attempting to create AnalysisTab with DB_CONFIG...")
        self.analysis_tab = AnalysisTab(
            self.notebook, self.db_conn, DB_CONFIG, self.log_error
        )
        self.notebook.add(self.analysis_tab, text="Analysis")

        print("DEBUG: Widgets: Packing notebook.")
        self.notebook.pack(expand=True, fill="both")

    def load_ticker_on_analysis_tab(self, ticker):
        """
        A callback function to switch to the Analysis tab and load a chart.
        """
        if not ticker:
            return

        print(f"DEBUG: GUI: Received request to load ticker {ticker} on Analysis tab.")
        try:
            # 1. Tell the Analysis tab to load the ticker (and check watchlist)
            self.analysis_tab.load_chart_for_ticker(ticker, check_watchlist=True)

            # 2. Switch the notebook to focus on the Analysis tab
            self.notebook.select(self.analysis_tab)

        except Exception as e:
            self.log_error("Cross-Tab Error", f"Failed to load chart from scan: {e}")

    def on_closing(self):
        """Called when the window is closed."""
        print("DEBUG: Closing: 'on_closing' called.")

        print("DEBUG: Closing: Checking for 'db_conn' attribute...")
        if hasattr(self, "db_conn") and self.db_conn:
            print("DEBUG: Closing: 'db_conn' found and is valid. Closing connection.")
            self.db_conn.close()
            print("DEBUG: Closing: Database connection closed.")
        else:
            print("DEBUG: Closing: 'db_conn' not found or is invalid.")

        print("DEBUG: Closing: Calling self.destroy().")
        self.destroy()


if __name__ == "__main__":
    print("DEBUG: Main: Checking dependencies...")
    try:
        import psycopg2

        print("DEBUG: Main: 'psycopg2' OK.")
        import yfinance

        print("DEBUG: Main: 'yfinance' OK.")
        import pandas

        print("DEBUG: Main: 'pandas' OK.")
        import matplotlib
        import mplfinance

        print("DEBUG: Main: 'matplotlib' & 'mplfinance' OK.")
        print("DEBUG: Main: All dependencies found.")
    except ImportError as e:
        print(f"DEBUG: Main: FATAL ERROR - Missing dependency: {e}")
        print(
            "Please install required libraries: psycopg2-binary, yfinance, pandas, matplotlib, mplfinance"
        )
        sys.exit(1)

    print("DEBUG: Main: Creating App instance...")
    app = StockAnalyzerApp()
    print("DEBUG: Main: Starting mainloop...")
    app.mainloop()
    print("DEBUG: Main: Mainloop finished.")


