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
    def __init__(self, parent, ticker, async_run):
        # CHANGED: Removed db_layer argument
        super().__init__(parent)
        self.title(f"{ticker} - Price Charts")
        self.geometry("1200x800")

        self.ticker = ticker
        self.async_run = async_run

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
        periods = [
            ("3M", "3 Months", 0, 0),
            ("6M", "6 Months", 0, 1),
            ("1Y", "1 Year", 1, 0),
            ("5Y", "5 Years", 1, 1),
        ]
        for period_key, period_label, row, col in periods:
            chart_frame = ttk.Labelframe(parent_frame, text=period_label, bootstyle="primary")
            chart_frame.grid(row=row, column=col, sticky="nsew", padx=5, pady=5)
            chart_widget = BaseChart(chart_frame, period_label)
            chart_widget.pack(fill=BOTH, expand=True) # Add this line to place the chart widget
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
        """Load and display all charts"""
        logging.getLogger(__name__).debug("[ChartWindow] load_charts called.")
        periods = {"3M": 90, "6M": 180, "1Y": 365, "5Y": 1825}

        # --- Try to load saved horizontal-line prices from the watchlist table ---
        saved_levels = []
        try:
            async_query = """
                SELECT entry_price, stop_loss, target_price
                FROM watchlist
                WHERE ticker = $1
            """
            rows = self.async_run(DBEngine.fetch(async_query, self.ticker))
            if rows:
                row = dict(rows[0])
                raw_entry = row.get("entry_price")
                raw_stop = row.get("stop_loss")
                raw_target = row.get("target_price")

                # DB returns Decimal objects for numeric columns; coerce to float
                if raw_entry is not None:
                    price_r = float(raw_entry) / 100.0
                    saved_levels.append((price_r, "blue", f"Entry: R{price_r:.2f}"))
                if raw_stop is not None:
                    price_r = float(raw_stop) / 100.0
                    saved_levels.append((price_r, "red", f"Stop Loss: R{price_r:.2f}"))
                if raw_target is not None:
                    price_r = float(raw_target) / 100.0
                    saved_levels.append((price_r, "green", f"Target: R{price_r:.2f}"))
        except Exception as ex:
            logging.getLogger(__name__).warning(
                "[ChartWindow]   -> Failed to load saved horizontal line levels: %s", ex
            )
            saved_levels = []

        for period_key, days in periods.items():
            logging.getLogger(__name__).debug(
                "[ChartWindow] Fetching data for %s (%d days)...", period_key, days
            )
            data = self.async_run(get_historical_prices(self.ticker, days))
            if data:
                logging.getLogger(__name__).debug(
                    "[ChartWindow]   -> Fetched %d rows for %s.", len(data), period_key
                )
            else:
                logging.getLogger(__name__).debug(
                    "[ChartWindow]   -> No data fetched for %s.", period_key
                )
            chart = self.charts.get(period_key)
            if chart:
                logging.getLogger(__name__).debug(
                    "[ChartWindow]   -> Plotting %s chart.", period_key
                )
                # If we have saved horizontal-line tuples (price,color,label),
                # assign them directly to the chart instance so they act as
                # stored_hlines for this plot. We avoid calling
                # set_horizontal_lines() here because that method triggers a
                # replot using the chart's stored df (which may be stale) —
                # instead we set the attribute directly and then plot with
                # the data for the current period so the hlines map correctly.
                try:
                    if saved_levels:
                        chart.horizontal_lines = list(saved_levels)
                except Exception:
                    # Fallback: ignore if chart doesn't support attribute
                    pass

                chart.plot(data, period_key)
        # Load metrics
        self.load_metrics()

    def load_metrics(self):
        """Load and display stock metrics"""
        # Clear existing items
        for item in self.metrics_tree.get_children():
            self.metrics_tree.delete(item)
        
        # Fetch metrics data
        metrics = self.async_run(get_stock_metrics(self.ticker))
        
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
