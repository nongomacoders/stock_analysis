import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import pandas as pd
import mplfinance as mpf

# --- NEW IMPORT ---
from modules.data.market import get_historical_prices
from modules.data.metrics import get_stock_metrics


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
        self.ticker = ticker
        self.title(f"{ticker} - Price Charts")
        
        # Update title label
        for widget in self.winfo_children():
            if isinstance(widget, ttk.Frame) and str(widget).endswith("frame"): # Find title frame
                 for child in widget.winfo_children():
                     if isinstance(child, ttk.Label):
                         child.configure(text=f"{self.ticker} - Historical Price Charts")
                         break
        
        # Clear existing charts
        for frame in self.chart_frames.values():
            for widget in frame.winfo_children():
                widget.destroy()
                
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
        chart_tab = ttk.Frame(self.notebook)
        self.notebook.add(chart_tab, text="Charts")

        chart_tab.grid_rowconfigure(0, weight=1)
        chart_tab.grid_rowconfigure(1, weight=1)
        chart_tab.grid_columnconfigure(0, weight=1)
        chart_tab.grid_columnconfigure(1, weight=1)

        self.chart_frames = {}
        periods = [
            ("3M", "3 Months", 0, 0),
            ("6M", "6 Months", 0, 1),
            ("1Y", "1 Year", 1, 0),
            ("5Y", "5 Years", 1, 1),
        ]

        for period_key, period_label, row, col in periods:
            frame = ttk.Labelframe(chart_tab, text=period_label, bootstyle="primary")
            frame.grid(row=row, column=col, sticky="nsew", padx=5, pady=5)
            self.chart_frames[period_key] = frame

        # Metrics Tab
        self.metrics_tab = self.create_metrics_tab()
        self.notebook.add(self.metrics_tab, text="Metrics")

    def create_metrics_tab(self):
        """Create the metrics tab with key stock metrics"""
        frame = ttk.Frame(self.notebook)
        
        # Create a container frame that will be centered
        center_container = ttk.Frame(frame)
        center_container.pack(expand=True, fill=NONE, padx=10, pady=10)
        
        # Create Treeview
        columns = ("metric", "value")
        self.metrics_tree = ttk.Treeview(
            center_container, 
            columns=columns, 
            show="headings", 
            bootstyle="primary",
            height=10  # Set a reasonable height
        )
        
        # Define headings
        self.metrics_tree.heading("metric", text="Metric")
        self.metrics_tree.heading("value", text="Value")
        
        # Define columns with fixed widths
        self.metrics_tree.column("metric", width=200, anchor=W)
        self.metrics_tree.column("value", width=150, anchor=E)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(center_container, orient=VERTICAL, command=self.metrics_tree.yview)
        self.metrics_tree.configure(yscrollcommand=scrollbar.set)
        
        # Pack side-by-side in the centered container
        self.metrics_tree.pack(side=LEFT, fill=Y)
        scrollbar.pack(side=RIGHT, fill=Y)
        
        return frame

    def load_charts(self):
        """Load and display all charts"""
        periods = {"3M": 90, "6M": 180, "1Y": 365, "5Y": 1825}

        for period_key, days in periods.items():
            # CHANGED: Call module function directly
            data = self.async_run(get_historical_prices(self.ticker, days))
            self.plot_chart(period_key, data)
        
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
        def add_row(label, value, fmt="{}"):
            display_val = fmt.format(value) if value is not None else "N/A"
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

    def plot_chart(self, period_key, data):
        """Plot a candlestick chart"""
        frame = self.chart_frames[period_key]

        if not data:
            self._show_no_data(frame, "No data available")
            return

        df = pd.DataFrame(data)
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        df.set_index("trade_date", inplace=True)

        # Convert prices (cents -> rands)
        for col in ["open_price", "high_price", "low_price", "close_price"]:
            df[col] = pd.to_numeric(df[col], errors="coerce") / 100

        # Rename for mplfinance
        df = df.rename(
            columns={
                "open_price": "Open",
                "high_price": "High",
                "low_price": "Low",
                "close_price": "Close",
            }
        )

        df = df.dropna(subset=["Open", "High", "Low", "Close"])

        if df.empty:
            self._show_no_data(frame, "No valid OHLC data")
            return

        # Resample
        if period_key == "5Y":
            df = (
                df.resample("ME")
                .agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"})
                .dropna()
            )
        elif period_key == "1Y":
            df = (
                df.resample("W")
                .agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"})
                .dropna()
            )

        if df.empty:
            self._show_no_data(frame, "Insufficient data for resampling")
            return

        # Create Plot
        fig = Figure(figsize=(5, 3), dpi=100)
        ax = fig.add_subplot(111)
        mpf.plot(
            df,
            type="candle",
            ax=ax,
            style="charles",
            volume=False,
            show_nontrading=False,
        )

        ax.set_xlabel("Date", fontsize=9)
        ax.set_ylabel("Price (ZAR)", fontsize=9)
        ax.tick_params(axis="both", labelsize=8)
        ax.grid(True, alpha=0.3)

        min_p, max_p = df["Low"].min(), df["High"].max()
        ax.set_title(f"Range: R{min_p:.2f} - R{max_p:.2f}", fontsize=10)
        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=BOTH, expand=True)

    def _show_no_data(self, frame, message):
        fig = Figure(figsize=(5, 3), dpi=100)
        ax = fig.add_subplot(111)
        ax.text(0.5, 0.5, message, ha="center", va="center", fontsize=12)
        ax.set_title("No Data", fontsize=10)
        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=BOTH, expand=True)
