import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, TOP, X, LEFT, RIGHT, VERTICAL, Y, W, E, CENTER, END
from datetime import date, datetime

# --- UPDATED IMPORTS ---
# 1. Utilities moved to core
from core.utils.trading import get_proximity_status

# 2. Data fetching moved to modules
from modules.data.watchlist import fetch_watchlist_data
from components.watchlist_sorting import sort_watchlist_records, sort_treeview_column

# 3. Child windows (Note: These will need refactoring next)
from components.chart_window import ChartWindow
from components.research_window import ResearchWindow
from components.technical_analysis_window import TechnicalAnalysisWindow
from components.todo_widget import TodoWidget
from components.notification_widget import NotificationWidget
# Sorting logic is implemented in `components.watchlist_sorting` to reduce the
# size of this module and make sorting reusable across the project.

from components.portfolio_window import PortfolioWindow


class WatchlistWidget(ttk.Frame):
    def __init__(self, parent, on_select_callback, async_run, async_run_bg, notifier):
        # CHANGED: Removed 'db_layer' from arguments, added async_run_bg
        super().__init__(parent)
        self.on_select = on_select_callback
        self.async_run = async_run
        self.async_run_bg = async_run_bg
        self.notifier = notifier

        # Cache the last loaded rows so the dropdown filter can re-render
        # without re-querying the DB.
        self._watchlist_last_data = []

        # Tickers whose new-deepresearch highlight has been acknowledged (clicked).
        self._dr_acknowledged: set[str] = set()

        self.create_widgets()

        # Note: Initial data load is triggered by main.py after DB is ready
        # Do NOT call self.refresh() here - it would freeze the UI before DB pool exists

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

        # --- TAB 3: NOTIFICATIONS ---
        notif_frame = NotificationWidget(
            self.notebook,
            self.async_run,
            self.async_run_bg,
            self.notifier,
            on_select_callback=self.on_select,
        )
        self.notebook.add(notif_frame, text="Notifications")

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

        # --- Filter dropdown (client-side only; does not change DB/query) ---
        ttk.Label(toolbar, text="Filter:").pack(side=LEFT, padx=(16, 5))

        # Mirror the lightweight Combobox pattern used elsewhere in the GUI.
        # Default 'active' preserves prior behavior (WL-Sleep excluded from view).
        self.watchlist_filter_var = ttk.StringVar(value="active")
        self.watchlist_filter_combo = ttk.Combobox(
            toolbar,
            textvariable=self.watchlist_filter_var,
            values=["active", "sleep", "unread", "holding", "pre-trade", "no-research", "all"],
            state="readonly",
            width=12,
        )
        self.watchlist_filter_combo.pack(side=LEFT, padx=2)
        self.watchlist_filter_combo.bind("<<ComboboxSelected>>", lambda e: self._render_watchlist())

        # --- COLUMNS ---
        cols = ("Ticker", "Name", "Price", "Proximity", "BTE", "Event", "RR", "PEG", "Upside", "Strategy")
        self.tree = ttk.Treeview(parent_frame, columns=cols, show="headings")

        self.tree.heading("Ticker", text="Ticker")
        self.tree.heading(
            "Name", text="Name", command=lambda: self.sort_column("Name", False)
        )
        self.tree.heading("Price", text="Price")
        # Make Proximity clickable to sort via the centralized helper
        self.tree.heading("Proximity", text="Proximity", command=lambda: self.sort_column("Proximity", False))
        self.tree.heading(
            "Event", text="Event", command=lambda: self.sort_column("Event", False)
        )
        # Make BTE, RR and Upside clickable headings to sort by those columns
        self.tree.heading("BTE", text="BTE", command=lambda: self.sort_column("BTE", False))
        self.tree.heading("RR", text="RR", command=lambda: self.sort_column("RR", False))
        self.tree.heading("PEG", text="PEG", command=lambda: self.sort_column("PEG", False))
        self.tree.heading("Upside", text="Upside", command=lambda: self.sort_column("Upside", False))
        self.tree.heading("Strategy", text="Strategy")

        # --- OPTIMIZED WIDTHS ---
        self.tree.column("Ticker", width=60, anchor=W, stretch=False)
        self.tree.column("Name", width=80, anchor=W, stretch=False)
        self.tree.column("Price", width=70, anchor=E, stretch=False)
        self.tree.column("Proximity", width=130, anchor=W, stretch=False)
        self.tree.column("Event", width=50, anchor=CENTER, stretch=False)
        # BTE (Better Than Entry) - percentage improvement relative to entry
        self.tree.column("BTE", width=90, anchor=CENTER, stretch=False)
        # Add RR and Upside columns and increase strategy width (doubled from 400 -> 800)
        self.tree.column("RR", width=80, anchor=CENTER, stretch=False)
        self.tree.column("PEG", width=70, anchor=CENTER, stretch=False)
        # Upside: percent return if target reached (numeric)
        self.tree.column("Upside", width=90, anchor=CENTER, stretch=False)
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
        self.tree.tag_configure("no_research", background="#EDF16E", foreground="black")  # Yellow for missing deep research
        self.tree.tag_configure("new_deepresearch", background="#FF0000", foreground="white")  # Bright red for freshly generated deep research

        self.tree.bind("<<TreeviewSelect>>", self._on_row_click)
        self.tree.bind("<Double-Button-1>", self._on_double_click)

    def get_ordered_tickers(self):
        """Return the list of tickers in the tree, in display order."""
        try:
            return [self.tree.item(i)["values"][0] for i in self.tree.get_children("")]
        except Exception:
            return []

    def get_adjacent_ticker(self, current_ticker: str, direction: int = 1):
        """Return the next/previous ticker around current_ticker (wraps around)."""
        try:
            return get_adjacent_ticker_from_list(current_ticker, self.get_ordered_tickers(), direction)
        except Exception:
            return None



    def refresh_watchlist(self):
        """Refresh watchlist data (non-blocking)."""
        def on_data_loaded(data):
            # Cache rows for client-side filtering.
            self._watchlist_last_data = data or []

            # Render immediately (applies current dropdown filter).
            self._render_watchlist()

        self.async_run_bg(fetch_watchlist_data(), callback=on_data_loaded)

    def _get_filtered_watchlist_rows(self, rows):
        """Apply the toolbar dropdown filter to watchlist rows."""
        try:
            filter_type = (self.watchlist_filter_var.get() or "all").strip().lower()
        except Exception:
            filter_type = "all"

        if not rows:
            return []

        if filter_type == "all":
            return list(rows)
        if filter_type == "active":
            return [r for r in rows if (r.get("status") != "WL-Sleep")]
        if filter_type == "sleep":
            return [r for r in rows if (r.get("status") == "WL-Sleep")]
        if filter_type == "unread":
            return [r for r in rows if (r.get("unread_log_count", 0) or 0) > 0]
        if filter_type == "holding":
            return [r for r in rows if bool(r.get("is_holding"))]
        if filter_type == "pre-trade":
            return [r for r in rows if (r.get("status") == "Pre-Trade")]
        if filter_type == "no-research":
            def has_research(r):
                v = r.get("deepresearch")
                if v is None:
                    return False
                return str(v).strip() != ""

            return [r for r in rows if not has_research(r)]

        # Unknown selection -> no filtering.
        return list(rows)

    def _render_watchlist(self):
        """Re-render the treeview from cached rows, applying the dropdown filter."""
        data = self._get_filtered_watchlist_rows(self._watchlist_last_data)

        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)

        if not data:
            return

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
            # Check if deep research was generated today.
            dr_date = row.get("deepresearch_date")
            dr_is_new = False
            if dr_date is not None:
                try:
                    if hasattr(dr_date, "date"):
                        dr_is_new = dr_date.date() == today
                    else:
                        dr_is_new = dr_date == today
                except Exception:
                    pass

            if row.get("unread_log_count", 0) > 0:
                row_tag = "unread"
            elif dr_is_new and row["ticker"] not in self._dr_acknowledged:
                row_tag = "new_deepresearch"
            elif row["is_holding"]:
                row_tag = "holding"
            elif row["status"] == "Pre-Trade":
                row_tag = "pretrade"
            elif not row.get("deepresearch"):
                row_tag = "no_research"

            # 3. Proximity Text
            prox_text, _ = get_proximity_status(
                row["close_price"], row["entry_price"], row["stop_loss"], row["target"], row.get("is_long", True)
            )

            # If we have an entry but got no proximity due to missing price data,
            # show a placeholder so the column remains populated and sortable.
            if (prox_text is None or str(prox_text).strip() == "" or str(prox_text).strip().lower() == "no data") and row.get("entry_price") is not None:
                try:
                    import logging
                    logging.getLogger(__name__).debug(
                        "Proximity unavailable for %s (price=%s entry=%s stop=%s target=%s)",
                        row.get("ticker"), row.get("close_price"), row.get("entry_price"), row.get("stop_loss"), row.get("target"),
                    )
                except Exception:
                    pass
                prox_text = "(N/A) Entry"

            # 4. Truncate Text
            strategy_text = str(row.get("strategy", "") or "").replace("\n", " ")
            if len(strategy_text) > 100:
                strategy_text = strategy_text[:100] + "..."

            full_name = row["full_name"] if row["full_name"] else ""
            short_name = full_name[:10]

            price_val = row["close_price"]
            price_str = f"{int(price_val)}" if price_val is not None else "-"

            # 5. BTE (Better Than Entry): how much current price is better than entry
            entry_price = row.get("entry_price")
            is_long = row.get("is_long", True)
            if entry_price is None or price_val is None:
                bte_str = "-"
            else:
                try:
                    # BTE (Better Than Entry) should be positive when the current
                    # price is 'better' relative to entry for the trade direction.
                    # - For long positions: price < entry is better -> diff = entry - price
                    # - For short positions: price > entry is better -> diff = price - entry
                    if is_long:
                        diff = entry_price - price_val
                    else:
                        diff = price_val - entry_price

                    pct = (diff / entry_price) * 100 if entry_price != 0 else 0
                    sign = "+" if pct >= 0 else "-"
                    bte_str = f"{sign}{abs(pct):.2f}%"
                except Exception:
                    bte_str = "-"

            # Format RR (reward_risk_ratio) coming from DB (numeric/Decimal)
            rr_val = row.get("reward_risk_ratio")
            if rr_val is None:
                rr_str = "-"
            else:
                try:
                    rr_str = f"{float(rr_val):.2f}"
                except Exception:
                    rr_str = str(rr_val)

            # PEG: use peg_ratio returned from fetch_watchlist_data if present
            peg_val = row.get("peg_ratio") or row.get("peg_ratio_historical")
            if peg_val is None:
                peg_str = "-"
            else:
                try:
                    peg_str = f"{float(peg_val):.2f}"
                except Exception:
                    peg_str = str(peg_val)

            # 6. Upside: expected percent return if target is reached
            target_val = row.get("target")
            try:
                # Upside should be the percent return from current price -> target
                # For long: (target - current) / current
                # For short: (current - target) / current
                if price_val is None or target_val is None or price_val == 0:
                    upside_str = "-"
                else:
                    if is_long:
                        gain = (target_val - price_val) / price_val * 100
                    else:
                        gain = (price_val - target_val) / price_val * 100
                    upside_str = f"{abs(float(gain)):.2f}%"
            except Exception:
                upside_str = "-"

            self.tree.insert(
                "",
                "end",
                values=(
                    row["ticker"],
                    short_name,
                    price_str,
                    prox_text,
                    bte_str,
                    days_str,
                    rr_str,
                    peg_str,
                    upside_str,
                    strategy_text,
                ),
                tags=(row_tag,),
            )

    def _on_row_click(self, event):
        sel = self.tree.selection()
        if sel:
            item = self.tree.item(sel[0])
            ticker = item["values"][0]

            # Dismiss bright-red deep-research highlight on click.
            if "new_deepresearch" in (item.get("tags") or ()):
                self._dr_acknowledged.add(ticker)
                self.tree.item(sel[0], tags=())

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
        # Delegate the sorting to the centralized utility so this file remains
        # small and the logic can be reused / tested separately.
        sort_treeview_column(self.tree, col, reverse)

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


def get_adjacent_ticker_from_list(current_ticker: str, tickers: list, direction: int = 1):
    """Helper: return next/previous ticker in the list or None if not possible."""
    if not tickers:
        return None
    if current_ticker not in tickers:
        return None
    try:
        idx = tickers.index(current_ticker)
        next_idx = (idx + direction) % len(tickers)
        return tickers[next_idx]
    except Exception:
        return None
