import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from datetime import date

# --- UPDATED IMPORTS ---
# 1. Utilities moved to core
from core.utils.trading import get_proximity_status

# 2. Data fetching moved to modules
from modules.data.watchlist import fetch_watchlist_data

# 3. Child windows (Note: These will need refactoring next)
from components.chart_window import ChartWindow
from components.research_window import ResearchWindow


class WatchlistWidget(ttk.Frame):
    def __init__(self, parent, on_select_callback, async_run, async_run_bg):
        # CHANGED: Removed 'db_layer' from arguments, added async_run_bg
        super().__init__(parent)
        self.on_select = on_select_callback
        self.async_run = async_run
        self.async_run_bg = async_run_bg
        self.create_widgets()

    def create_widgets(self):
        # --- STYLE CONFIGURATION ---
        style = ttk.Style()
        style.configure(
            "Treeview.Heading",
            borderwidth=2,
            relief="groove",
            font=("Helvetica", 10, "bold"),
        )

        # --- COLUMNS ---
        cols = ("Ticker", "Name", "Price", "Status", "Event", "Strategy", "News")
        self.tree = ttk.Treeview(self, columns=cols, show="headings")

        self.tree.heading("Ticker", text="Ticker")
        self.tree.heading(
            "Name", text="Name", command=lambda: self.sort_column("Name", False)
        )
        self.tree.heading("Price", text="Price")
        self.tree.heading("Status", text="Status")
        self.tree.heading(
            "Event", text="Event", command=lambda: self.sort_column("Event", False)
        )
        self.tree.heading("Strategy", text="Strategy")
        self.tree.heading("News", text="News")

        # --- OPTIMIZED WIDTHS ---
        self.tree.column("Ticker", width=60, anchor=W, stretch=False)
        self.tree.column("Name", width=80, anchor=W, stretch=False)
        self.tree.column("Price", width=70, anchor=E, stretch=False)
        self.tree.column("Status", width=113, anchor=W, stretch=False)
        self.tree.column("Event", width=50, anchor=CENTER, stretch=False)
        self.tree.column("Strategy", width=400, anchor=W, stretch=True)
        self.tree.column("News", width=400, anchor=W, stretch=True)

        # Scrollbar
        scrolly = ttk.Scrollbar(self, orient=VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrolly.set)

        scrolly.pack(side=RIGHT, fill=Y)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)

        # --- ROW COLORS ---
        self.tree.tag_configure("holding", background="#d1e7dd", foreground="black")
        self.tree.tag_configure("pretrade", background="#E6E6FA", foreground="black")
        self.tree.tag_configure("unread", background="#ffcccc", foreground="black")

        self.tree.bind("<<TreeviewSelect>>", self._on_row_click)
        self.tree.bind("<Double-Button-1>", self._on_double_click)

    def refresh(self):
        """Refresh watchlist data (non-blocking)."""
        def on_data_loaded(data):
            if not data:
                return
                
            # Clear existing items
            for item in self.tree.get_children():
                self.tree.delete(item)
            
            today = date.today()

            for row in data:
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
                    row["close_price"], row["entry_price"], row["stop_loss"], row["target"]
                )

                # 4. Truncate Text
                strategy_text = str(row.get("strategy", "") or "").replace("\n", " ")
                if len(strategy_text) > 100:
                    strategy_text = strategy_text[:100] + "..."

                news_text = str(row.get("latest_news", "") or "").replace("\n", " ")
                if len(news_text) > 100:
                    news_text = news_text[:100] + "..."

                full_name = row["full_name"] if row["full_name"] else ""
                short_name = full_name[:10]

                price_val = row["close_price"]
                price_str = f"{int(price_val)}" if price_val is not None else "-"

                self.tree.insert(
                    "",
                    "end",
                    values=(
                        row["ticker"],
                        short_name,
                        price_str,
                        prox_text,
                        days_str,
                        strategy_text,
                        news_text,
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
            l.sort(key=lambda t: t[0].lower(), reverse=reverse)
        else:
            l.sort(reverse=reverse)

        for index, (val, k) in enumerate(l):
            self.tree.move(k, "", index)

        self.tree.heading(col, command=lambda: self.sort_column(col, not reverse))
