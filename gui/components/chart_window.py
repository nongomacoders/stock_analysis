import ttkbootstrap as ttk
from ttkbootstrap.constants import TOP, X, BOTH, NONE, W, E, VERTICAL, LEFT, RIGHT, Y, END
import matplotlib.pyplot as plt
import logging
from datetime import date

# --- NEW IMPORT ---
from modules.data.market import get_historical_prices
from modules.data.metrics import get_stock_metrics
from core.db.engine import DBEngine
from components.base_chart import BaseChart


class ChartWindow(ttk.Toplevel):
    def __init__(self, parent, ticker, async_run, async_run_bg=None):
        # CHANGED: Removed db_layer argument
        super().__init__(parent)
        self.title(f"{ticker} - Price Charts")
        self.geometry("1200x800")

        self.ticker = ticker
        self.async_run = async_run
        self.async_run_bg = async_run_bg

        # Configure matplotlib style
        plt.style.use("seaborn-v0_8-darkgrid")

        self.create_widgets()
        self.load_charts()

    def update_ticker(self, ticker):
        """Update the window with a new ticker"""
        logging.getLogger(__name__).info("\n[ChartWindow] Updating to ticker: %s", ticker)
        self.ticker = ticker
        self.title(f"{ticker} - Price Charts")
        
        # Update title label
        for widget in self.winfo_children():
            if isinstance(widget, ttk.Frame) and str(widget).endswith("frame"): # Find title frame
                 for child in widget.winfo_children():
                     if isinstance(child, ttk.Label):
                         child.configure(text=f"{self.ticker} - Historical Price Charts")
                         break
        
        # Reload data for the new ticker
        logging.getLogger(__name__).debug("[ChartWindow] Triggering chart load.")
        self.load_charts()

    def create_widgets(self):
        # Title
        title_frame = ttk.Frame(self, bootstyle="secondary")
        title_frame.pack(side=TOP, fill=X, padx=10, pady=10)
        ttk.Label(
            title_frame,
            text=f"{self.ticker} - Historical Price Charts",
            font=("Helvetica", 16, "bold"),
        ).pack()

        # Create Notebook for tabs
        self.notebook = ttk.Notebook(self, bootstyle="primary")
        self.notebook.pack(fill=BOTH, expand=True, padx=10, pady=10)

        # Charts Tab
        self.chart_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.chart_tab, text="Charts")

        self.chart_tab.grid_rowconfigure(0, weight=1)
        self.chart_tab.grid_rowconfigure(1, weight=1)
        self.chart_tab.grid_columnconfigure(0, weight=1)
        self.chart_tab.grid_columnconfigure(1, weight=1)
        
        self.create_chart_widgets(self.chart_tab)

        # Metrics Tab
        self.metrics_tab = self.create_metrics_tab()
        self.notebook.add(self.metrics_tab, text="Metrics")

    def create_chart_widgets(self, parent_frame):
        """Creates and grids the individual BaseChart widgets."""
        self.charts = {}
        # Single Chart: 3 Months
        period_key = "3M"
        period_label = "3 Months"
        
        chart_frame = ttk.Labelframe(parent_frame, text=period_label, bootstyle="primary")
        chart_frame.pack(fill=BOTH, expand=True, padx=5, pady=5)
        
        chart_widget = BaseChart(chart_frame, period_label)
        chart_widget.pack(fill=BOTH, expand=True)
        
        self.charts[period_key] = chart_widget

    def create_metrics_tab(self):
        """Create the metrics tab with key stock metrics"""
        frame = ttk.Frame(self.notebook)
        
        # Create a container frame that will be centered
        center_container = ttk.Frame(frame)
        center_container.pack(expand=True, fill=NONE, padx=10, pady=10)
        
        # Configure style for larger font
        style = ttk.Style()
        style.configure("Metrics.Treeview", font=("Helvetica", 14), rowheight=30)
        style.configure("Metrics.Treeview.Heading", font=("Helvetica", 15, "bold"))
        
        # Create Treeview
        columns = ("metric", "value")
        self.metrics_tree = ttk.Treeview(
            center_container, 
            columns=columns, 
            show="headings", 
            style="Metrics.Treeview",
            height=10  # Set a reasonable height
        )
        
        # Define headings
        self.metrics_tree.heading("metric", text="Metric")
        self.metrics_tree.heading("value", text="Value")
        
        # Define columns with fixed widths
        self.metrics_tree.column("metric", width=200, anchor=W)
        self.metrics_tree.column("value", width=150, anchor=E)

        # Highlight tags
        self.metrics_tree.tag_configure("soon_release", foreground="red")
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(center_container, orient=VERTICAL, command=self.metrics_tree.yview)
        self.metrics_tree.configure(yscrollcommand=scrollbar.set)
        
        # Pack side-by-side in the centered container
        self.metrics_tree.pack(side=LEFT, fill=Y)
        scrollbar.pack(side=RIGHT, fill=Y)
        
        return frame

    def load_charts(self):
        """Load and display all charts asynchronously to avoid blocking the GUI."""
        logging.getLogger(__name__).debug("[ChartWindow] load_charts called.")
        periods = {"3M": 90}

        async def _fetch():
            # Fetch saved horizontal-line prices
            saved_levels = []
            try:
                async_query = """
                    SELECT 
                        w.entry_price, w.stop_loss, w.target_price,
                        (SELECT array_agg(spl.price_level) FROM stock_price_levels spl WHERE spl.ticker = w.ticker AND spl.level_type = 'support') as support_levels,
                        (SELECT array_agg(spl.price_level) FROM stock_price_levels spl WHERE spl.ticker = w.ticker AND spl.level_type = 'resistance') as resistance_levels
                    FROM watchlist w
                    WHERE w.ticker = $1
                """
                rows = await DBEngine.fetch(async_query, self.ticker)
                if rows:
                    row = dict(rows[0])
                    raw_entry = row.get("entry_price")
                    raw_stop = row.get("stop_loss")
                    raw_target = row.get("target_price")
                    raw_supports = row.get("support_levels") or []
                    raw_resistances = row.get("resistance_levels") or []

                    if raw_entry is not None:
                        price_r = float(raw_entry) / 100.0
                        saved_levels.append((price_r, "blue", f"Entry: R{price_r:.2f}"))
                    if raw_stop is not None:
                        price_r = float(raw_stop) / 100.0
                        saved_levels.append((price_r, "red", f"Stop Loss: R{price_r:.2f}"))
                    if raw_target is not None:
                        price_r = float(raw_target) / 100.0
                        saved_levels.append((price_r, "green", f"Target: R{price_r:.2f}"))

                    for p in raw_supports:
                        if p is not None:
                            price_r = float(p) / 100.0
                            saved_levels.append((price_r, "green", f"Support: R{price_r:.2f}"))

                    for p in raw_resistances:
                        if p is not None:
                            price_r = float(p) / 100.0
                            saved_levels.append((price_r, "red", f"Resistance: R{price_r:.2f}"))
            except Exception:
                saved_levels = []

            # Fetch period data
            period_results = {}
            for period_key, days in periods.items():
                data = await get_historical_prices(self.ticker, days)
                period_results[period_key] = data

            # Fetch metrics
            metrics = await get_stock_metrics(self.ticker)

            return {"saved_levels": saved_levels, "periods": period_results, "metrics": metrics}

        def _on_loaded(result):
            saved_levels = result.get("saved_levels", [])
            for period_key, data in result.get("periods", {}).items():
                chart = self.charts.get(period_key)
                if chart:
                    try:
                        if saved_levels:
                            chart.horizontal_lines = list(saved_levels)
                    except Exception:
                        pass
                    chart.plot(data, period_key)

            # Load metrics using fetched metrics
            self.load_metrics(metrics=result.get("metrics"))

        try:
            self.async_run_bg(_fetch(), callback=_on_loaded)
        except Exception:
            # fallback to synchronous behavior if background runner fails
            try:
                saved_levels = []
                async_query = """
                    SELECT 
                        w.entry_price, w.stop_loss, w.target_price,
                        (SELECT array_agg(spl.price_level) FROM stock_price_levels spl WHERE spl.ticker = w.ticker AND spl.level_type = 'support') as support_levels,
                        (SELECT array_agg(spl.price_level) FROM stock_price_levels spl WHERE spl.ticker = w.ticker AND spl.level_type = 'resistance') as resistance_levels
                    FROM watchlist w
                    WHERE w.ticker = $1
                """
                rows = self.async_run(DBEngine.fetch(async_query, self.ticker))
                if rows:
                    row = dict(rows[0])
                    raw_entry = row.get("entry_price")
                    if raw_entry is not None:
                        price_r = float(raw_entry) / 100.0
                        saved_levels.append((price_r, "blue", f"Entry: R{price_r:.2f}"))
                for period_key, days in periods.items():
                    data = self.async_run(get_historical_prices(self.ticker, days))
                    chart = self.charts.get(period_key)
                    if chart:
                        try:
                            if saved_levels:
                                chart.horizontal_lines = list(saved_levels)
                        except Exception:
                            pass
                        chart.plot(data, period_key)
                self.load_metrics()
            except Exception:
                logging.getLogger(__name__).warning("[ChartWindow]   -> Failed to load charts (fallback): %s", exc_info=True)
    def load_metrics(self, metrics=None):
        """Load and display stock metrics. If metrics are provided, use them; otherwise fetch asynchronously."""
        # Clear existing items
        for item in self.metrics_tree.get_children():
            self.metrics_tree.delete(item)

        def _render_metrics(metrics):
            if not metrics:
                self.metrics_tree.insert("", END, values=("Status", "No metrics data available"))
                return

            # Helper to format and insert
            def add_row(label, value, fmt="{}", tags=None):
                display_val = fmt.format(value) if value is not None else "N/A"
                if tags:
                    self.metrics_tree.insert("", END, values=(label, display_val), tags=tags)
                else:
                    self.metrics_tree.insert("", END, values=(label, display_val))

            # Current Price
            price = metrics.get('current_price')
            add_row("Current Price", price/100 if price else None, "R {:.2f}")

            # P/E Ratio
            add_row("P/E Ratio", metrics.get('pe_ratio'), "{:.2f}")

            # Dividend Yield
            add_row("Dividend Yield", metrics.get('div_yield_perc'), "{:.2f}%")

            # PEG Ratio (Historical)
            add_row("PEG Ratio (Hist)", metrics.get('peg_ratio_historical'), "{:.2f}")

            # Graham Fair Value
            gfv = metrics.get('graham_fair_value')
            add_row("Graham Fair Value", gfv/100 if gfv else None, "R {:.2f}")

            # Valuation Premium
            add_row("Valuation Premium", metrics.get('valuation_premium_perc'), "{:.2f}%")

            # Historical Growth CAGR
            add_row("Hist. Growth CAGR", metrics.get('historical_growth_cagr'), "{:.2f}%")
            
            # Financials Date
            add_row("Financials Date", metrics.get('financials_date'), "{}")

        if metrics is not None:
            _render_metrics(metrics)
            return

        # Fetch metrics asynchronously
        try:
            # Prefer background runner if available
            if hasattr(self, 'async_run_bg') and self.async_run_bg:
                self.async_run_bg(get_stock_metrics(self.ticker), callback=_render_metrics)
            else:
                # Fallback to synchronous fetch if background runner is not available
                metrics = self.async_run(get_stock_metrics(self.ticker))
                _render_metrics(metrics)
        except Exception:
            try:
                metrics = self.async_run(get_stock_metrics(self.ticker))
            except Exception:
                metrics = None
            _render_metrics(metrics)
        # Next results release date (estimated): same logic as fetch_watchlist_data
        # Uses the 2nd most recent results_release_date + 1 year.
        try:
            next_release_q = """
                SELECT (results_release_date + interval '1 year')::date AS next_event_date
                FROM raw_stock_valuations
                WHERE ticker = $1
                ORDER BY results_release_date DESC
                LIMIT 1 OFFSET 1
            """
            rows = self.async_run(DBEngine.fetch(next_release_q, self.ticker))
            next_event_date = None
            if rows:
                next_event_date = rows[0].get("next_event_date")

            soon_tags = None
            try:
                if next_event_date is not None:
                    # DB typically returns datetime.date here
                    next_d = next_event_date
                    if hasattr(next_event_date, "date"):
                        next_d = next_event_date.date()
                    days_to = (next_d - date.today()).days
                    if 0 <= days_to < 30:
                        soon_tags = ("soon_release",)
            except Exception:
                soon_tags = None

            add_row("Next Release Date", next_event_date, "{}", tags=soon_tags)
        except Exception:
            logging.getLogger(__name__).exception(
                "[ChartWindow] Failed to load next release date for %s", self.ticker
            )
            add_row("Next Release Date", None, "{}")
