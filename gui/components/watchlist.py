import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, TOP, X, LEFT, RIGHT, VERTICAL, Y, W, E, CENTER, END
from datetime import date, datetime

# --- UPDATED IMPORTS ---
# 1. Utilities moved to core
from core.utils.trading import get_proximity_status

# 2. Data fetching moved to modules
from modules.data.watchlist import fetch_watchlist_data

# 3. Child windows (Note: These will need refactoring next)
from components.chart_window import ChartWindow
from components.research_window import ResearchWindow
from components.technical_analysis_window import TechnicalAnalysisWindow
from components.todo_widget import TodoWidget
def sort_watchlist_records(rows, today=None):
    """Return rows sorted by status priority and days to next event.

    Priority order is: Active-Trade, Pre-Trade, WL-Active. Rows with missing
    next_event_date are placed last within their status group.
    """
    if today is None:
        today = date.today()

    def _status_priority(s):
        order = {"Active-Trade": 0, "Pre-Trade": 1, "WL-Active": 2}
        return order.get(s, 3)

    def _days_to_event(row):
        next_date = row.get("next_event_date")
        if not next_date:
            return 999999
        try:
            return (next_date - today).days
        except Exception:
            try:
                # Support string dates in ISO format as fallback
                return (datetime.strptime(next_date, "%Y-%m-%d").date() - today).days
            except Exception:
                return 999999

    return sorted(rows, key=lambda r: (_status_priority(r.get("status")), _days_to_event(r)))

from components.portfolio_window import PortfolioWindow


class WatchlistWidget(ttk.Frame):
    def __init__(self, parent, on_select_callback, async_run, async_run_bg, notifier):
        # CHANGED: Removed 'db_layer' from arguments, added async_run_bg
        super().__init__(parent)
        self.on_select = on_select_callback
        self.async_run = async_run
        self.async_run_bg = async_run_bg
        self.notifier = notifier

        self.create_widgets()

        # Initial data load
        self.refresh()

    def refresh(self):
        """Refresh the watchlist tab."""
        self.refresh_watchlist()

    def on_tab_change(self, event):
        """Callback for when the notebook tab is changed."""
        selected_tab = self.notebook.index(self.notebook.select())
        # You can add logic here if certain tabs need to refresh on view

    def create_widgets(self):
        # --- STYLE CONFIGURATION ---
        style = ttk.Style()
        style.configure(
            "Treeview.Heading",
            borderwidth=2,
            relief="groove",
            font=("Helvetica", 10, "bold"),
        )

        # --- NOTEBOOK FOR TABS ---
        self.notebook = ttk.Notebook(self, bootstyle="primary")
        self.notebook.pack(fill=BOTH, expand=True)
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_change)

        # --- TAB 1: WATCHLIST ---
        watchlist_frame = ttk.Frame(self.notebook)
        self.notebook.add(watchlist_frame, text="Watchlist")
        self.create_watchlist_tab(watchlist_frame)

        # --- TAB 2: DAILY TODO ---
        todo_frame = TodoWidget(self.notebook, self.async_run, self.async_run_bg, self.notifier)
        self.notebook.add(todo_frame, text="Todo")

    def create_watchlist_tab(self, parent_frame):
        """Creates the content for the Watchlist tab."""
        # --- TOOLBAR ---
        toolbar = ttk.Frame(parent_frame, padding=5)
        toolbar.pack(side=TOP, fill=X)
        
        ttk.Button(
            toolbar, 
            text="Technical Analysis", 
            command=self.open_technical_analysis,
            bootstyle="info-outline"
        ).pack(side=LEFT)

        ttk.Button(
            toolbar,
            text="Portfolio",
            command=self.open_portfolio_manager,
            bootstyle="secondary-outline",
        ).pack(side=LEFT, padx=(6, 0))

        # --- Refresh Button ---
        ttk.Button(
            toolbar,
            text="Refresh",
            command=self.refresh,
            bootstyle="success-outline",
        ).pack(side=LEFT, padx=(6, 0))

        # --- COLUMNS ---
        cols = ("Ticker", "Name", "Price", "Proximity", "Event", "RR", "Strategy")
        self.tree = ttk.Treeview(parent_frame, columns=cols, show="headings")

        self.tree.heading("Ticker", text="Ticker")
        self.tree.heading(
            "Name", text="Name", command=lambda: self.sort_column("Name", False)
        )
        self.tree.heading("Price", text="Price")
        self.tree.heading("Proximity", text="Proximity")
        self.tree.heading(
            "Event", text="Event", command=lambda: self.sort_column("Event", False)
        )
        self.tree.heading("RR", text="RR")
        self.tree.heading("Strategy", text="Strategy")

        # --- OPTIMIZED WIDTHS ---
        self.tree.column("Ticker", width=60, anchor=W, stretch=False)
        self.tree.column("Name", width=80, anchor=W, stretch=False)
        self.tree.column("Price", width=70, anchor=E, stretch=False)
        self.tree.column("Proximity", width=130, anchor=W, stretch=False)
        self.tree.column("Event", width=50, anchor=CENTER, stretch=False)
        # Add RR column and increase strategy width (doubled from 400 -> 800)
        self.tree.column("RR", width=80, anchor=CENTER, stretch=False)
        self.tree.column("Strategy", width=800, anchor=W, stretch=True)

        # Scrollbar
        scrolly = ttk.Scrollbar(parent_frame, orient=VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrolly.set)

        scrolly.pack(side=RIGHT, fill=Y)
        self.tree.pack(fill=BOTH, expand=True)

        # --- ROW COLORS ---
        self.tree.tag_configure("holding", background="#d1e7dd", foreground="black")
        self.tree.tag_configure("pretrade", background="#E6E6FA", foreground="black")
        self.tree.tag_configure("unread", background="#ffcccc", foreground="black")

        self.tree.bind("<<TreeviewSelect>>", self._on_row_click)
        self.tree.bind("<Double-Button-1>", self._on_double_click)

    def refresh_watchlist(self):
        """Refresh watchlist data (non-blocking)."""
        def on_data_loaded(data):
            if not data:
                return
                
            # Clear existing items
            for item in self.tree.get_children():
                self.tree.delete(item)
            
            today = date.today()

            # Sort incoming data so Treeview shows the most important status groups in the desired order
            for row in sort_watchlist_records(data):
                # 1. Event Days
                next_date = row.get("next_event_date")
                days_str = "-"

                if next_date:
                    days = (next_date - today).days
                    days_str = f"{days}d"

                # 2. Background Tag
                row_tag = ""
                if row.get("unread_log_count", 0) > 0:
                    row_tag = "unread"
                elif row["is_holding"]:
                    row_tag = "holding"
                elif row["status"] == "Pre-Trade":
                    row_tag = "pretrade"

                # 3. Proximity Text
                prox_text, _ = get_proximity_status(
                    row["close_price"], row["entry_price"], row["stop_loss"], row["target"], row.get("is_long", True)
                )

                # 4. Truncate Text
                strategy_text = str(row.get("strategy", "") or "").replace("\n", " ")
                if len(strategy_text) > 100:
                    strategy_text = strategy_text[:100] + "..."


                full_name = row["full_name"] if row["full_name"] else ""
                short_name = full_name[:10]

                price_val = row["close_price"]
                price_str = f"{int(price_val)}" if price_val is not None else "-"

                # Format RR (reward_risk_ratio) coming from DB (numeric/Decimal)
                rr_val = row.get("reward_risk_ratio")
                if rr_val is None:
                    rr_str = "-"
                else:
                    try:
                        rr_str = f"{float(rr_val):.2f}"
                    except Exception:
                        rr_str = str(rr_val)

                self.tree.insert(
                    "",
                    "end",
                    values=(
                        row["ticker"],
                        short_name,
                        price_str,
                        prox_text,
                        days_str,
                        rr_str,
                        strategy_text,
                    ),
                    tags=(row_tag,),
                )

        self.async_run_bg(fetch_watchlist_data(), callback=on_data_loaded)

    def _on_row_click(self, event):
        sel = self.tree.selection()
        if sel:
            item = self.tree.item(sel[0])
            ticker = item["values"][0]
            self.on_select(ticker)

    def _on_double_click(self, event):
        """Open chart and research windows when row is double-clicked"""
        sel = self.tree.selection()
        if sel:
            item = self.tree.item(sel[0])
            ticker = item["values"][0]

            # Open Chart and Research windows, creating them if they don't exist.
            # This logic is similar to on_ticker_select in main.py but is triggered by a double-click.
            # We can simply call the on_select callback to reuse the logic from main.py.
            self.on_select(ticker)

    def sort_column(self, col, reverse):
        l = [(self.tree.set(k, col), k) for k in self.tree.get_children("")]

        if col == "Event":

            def event_key(item):
                val = item[0]
                if val == "-":
                    return 999999
                try:
                    return int(val.replace("d", ""))
                except ValueError:
                    return 999999

            l.sort(key=event_key, reverse=reverse)
        elif col == "Name":
            # Ensure the value is coerced to string before calling lower()
            l.sort(key=lambda t: str(t[0]).lower(), reverse=reverse)
        else:
            l.sort(reverse=reverse)

        for index, (val, k) in enumerate(l):
            self.tree.move(k, "", index)

        self.tree.heading(col, command=lambda: self.sort_column(col, not reverse))

    def open_technical_analysis(self):
        """Open the Technical Analysis window for the selected ticker."""
        sel = self.tree.selection()
        if not sel:
            return

        item = self.tree.item(sel[0])
        ticker = item["values"][0]
        
        TechnicalAnalysisWindow(self, ticker, self.async_run_bg, on_status_saved_callback=self.refresh)

    def open_portfolio_manager(self):
        # Open the portfolio manager window
        PortfolioWindow(self, self.async_run, self.async_run_bg)
