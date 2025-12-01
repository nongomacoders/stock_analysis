import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import matplotlib.pyplot as plt
import pandas as pd
import mplfinance as mpf
from modules.data.market import get_historical_prices
from components.base_chart import BaseChart

class TechnicalAnalysisWindow(ttk.Toplevel):
    def __init__(self, parent, ticker, async_run_bg):
        super().__init__(parent)
        self.title(f"{ticker} - Technical Analysis")
        self.geometry("1000x700")

        self.ticker = ticker
        self.async_run_bg = async_run_bg

        # Configure matplotlib style
        plt.style.use("seaborn-v0_8-darkgrid")

        self.create_widgets()
        self.load_chart("1 Year") # Default to 1 Year

    def create_widgets(self):
        # Top Control Panel
        control_frame = ttk.Frame(self, padding=10)
        control_frame.pack(fill=X)

        ttk.Label(control_frame, text="Period:", font=("Helvetica", 10, "bold")).pack(side=LEFT, padx=(0, 5))

        self.period_var = ttk.StringVar(value="1 Year")
        self.period_combo = ttk.Combobox(
            control_frame, 
            textvariable=self.period_var, 
            values=["3 Months", "6 Months", "9 Months", "1 Year", "2 Years", "5 Years"],
            state="readonly",
            width=15
        )
        self.period_combo.pack(side=LEFT)
        self.period_combo.bind("<<ComboboxSelected>>", self.on_period_change)

        # Chart Area
        self.chart_frame = ttk.Frame(self, padding=10)
        self.chart_frame.pack(fill=BOTH, expand=True)
        
        self.chart = BaseChart(self.chart_frame, "Technical Chart")
        self.chart.pack(fill=BOTH, expand=True)

    def on_period_change(self, event):
        period_label = self.period_var.get()
        self.load_chart(period_label)

    def load_chart(self, period_label):
        # Map period labels to days and keys
        # We fetch extra data to calculate MAs (200 periods buffer)
        period_map = {
            "3 Months": 90,
            "6 Months": 180,
            "9 Months": 270,
            "1 Year": 365,
            "2 Years": 730,
            "5 Years": 1825
        }
        
        view_days = period_map.get(period_label, 365)
        # Fetch enough data for 200 MA. 
        # If we are in Daily mode, we need 200 extra days.
        # If we are in Weekly mode (5Y), we need 200 extra weeks (~1400 days).
        # Let's just fetch a safe amount. Max 10 years (3650 days).
        fetch_days = view_days + 1500 
        
        print(f"[TechAnalysis] Fetching data for {period_label} (View: {view_days}d, Fetch: {fetch_days}d)...")
        
        def on_data_loaded(data):
            if not data:
                 self.chart._show_no_data(f"No data for {period_label}")
                 return

            # 1. Prepare DataFrame
            df = pd.DataFrame(data)
            df["trade_date"] = pd.to_datetime(df["trade_date"])
            df.set_index("trade_date", inplace=True)
            
            # Convert prices
            for col in ["open_price", "high_price", "low_price", "close_price"]:
                df[col] = pd.to_numeric(df[col], errors="coerce") / 100
            
            df = df.rename(columns={"open_price": "Open", "high_price": "High", "low_price": "Low", "close_price": "Close"})
            df = df.dropna(subset=["Open", "High", "Low", "Close"])
            df = df.sort_index()

            # 2. Resample if needed (5 Years -> Weekly)
            # We keep 1Y and 2Y as Daily for better detail in Tech Analysis
            if period_label == "5 Years":
                 df = df.resample("W").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()

            # 3. Calculate Moving Averages
            # We calculate on the full fetched dataset
            ma20 = df["Close"].rolling(window=20).mean()
            ma50 = df["Close"].rolling(window=50).mean()
            ma200 = df["Close"].rolling(window=200).mean()

            # 4. Slice to View Range
            # We take the last N rows corresponding to the view period
            # Estimate rows based on period
            if period_label == "5 Years":
                # Weekly: 5 years * 52 weeks = ~260 rows
                slice_rows = 260
            else:
                # Daily: view_days (approx trading days = view_days * 5/7)
                # But view_days is calendar days.
                # Let's slice by Date index
                start_date = df.index[-1] - pd.Timedelta(days=view_days)
                slice_rows = None # Use date slicing

            if slice_rows:
                df_view = df.iloc[-slice_rows:]
                ma20_view = ma20.iloc[-slice_rows:]
                ma50_view = ma50.iloc[-slice_rows:]
                ma200_view = ma200.iloc[-slice_rows:]
            else:
                # Date slicing
                start_date = df.index.max() - pd.Timedelta(days=view_days)
                df_view = df[df.index > start_date]
                ma20_view = ma20[df.index > start_date]
                ma50_view = ma50[df.index > start_date]
                ma200_view = ma200[df.index > start_date]

            if df_view.empty:
                self.chart._show_no_data("Insufficient data for view")
                return

            # 5. Create AddPlots
            # Colors: 20 (Green), 50 (Blue), 200 (Red)
            # When using external axes in mpf.plot, we must specify the axis in make_addplot
            target_ax = self.chart.ax
            ap = [
                mpf.make_addplot(ma20_view, color='green', width=1.5, ax=target_ax),
                mpf.make_addplot(ma50_view, color='blue', width=1.5, ax=target_ax),
                mpf.make_addplot(ma200_view, color='red', width=1.5, ax=target_ax)
            ]

            # 6. Plot
            # Pass "Custom" as period_key to avoid BaseChart internal resampling
            self.chart.plot(df_view, "Custom", addplot=ap)

        self.async_run_bg(get_historical_prices(self.ticker, fetch_days), callback=on_data_loaded)
