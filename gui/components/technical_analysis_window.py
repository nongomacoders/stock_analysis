import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import matplotlib.pyplot as plt
import pandas as pd
import mplfinance as mpf
from modules.data.market import get_historical_prices
from components.base_chart import BaseChart
from core.db.engine import DBEngine

class TechnicalAnalysisWindow(ttk.Toplevel):
    def __init__(self, parent, ticker, async_run_bg):
        super().__init__(parent)
        self.title(f"{ticker} - Technical Analysis")
        self.geometry("1000x700")

        self.ticker = ticker
        self.async_run_bg = async_run_bg

        # Configure matplotlib style
        plt.style.use("seaborn-v0_8-darkgrid")

        # Price levels for drawing
        self.entry_price = None
        self.stop_loss = None
        self.target_price = None
        self.horizontal_lines = []  # Store line objects for removal

        self.create_widgets()
        self.load_chart("1 Year") # Default to 1 Year
        
        # Bind keypress events
        self.bind_all("<KeyPress>", self.on_key_press)

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
        
        # Store current cursor y-position
        self.current_cursor_y = None
        
        # Connect mouse motion to track cursor position
        self.chart.canvas.mpl_connect("motion_notify_event", self.on_chart_mouse_move)

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
            
            # Redraw existing horizontal lines if any
            self.redraw_horizontal_lines()

        self.async_run_bg(get_historical_prices(self.ticker, fetch_days), callback=on_data_loaded)
    
    def on_chart_mouse_move(self, event):
        """Track cursor y-position on the chart."""
        if event.inaxes == self.chart.ax and event.ydata is not None:
            self.current_cursor_y = event.ydata
    
    def on_key_press(self, event):
        """Handle keypress events to draw horizontal lines."""
        key = event.char.lower()
        
        if key not in ['e', 'l', 't']:
            return
        
        if self.current_cursor_y is None:
            print(f"[TechAnalysis] No cursor position available")
            return
        
        price = round(self.current_cursor_y, 2)
        
        # Set the appropriate price level and color
        if key == 'e':
            self.entry_price = price
            color = 'blue'
            label = f'Entry: R{price:.2f}'
            print(f"[TechAnalysis] Entry price set to R{price:.2f}")
        elif key == 'l':
            self.stop_loss = price
            color = 'red'
            label = f'Stop Loss: R{price:.2f}'
            print(f"[TechAnalysis] Stop loss set to R{price:.2f}")
        elif key == 't':
            self.target_price = price
            color = 'green'
            label = f'Target: R{price:.2f}'
            print(f"[TechAnalysis] Target price set to R{price:.2f}")
        
        # Draw the horizontal line
        self.draw_horizontal_line(price, color, label)
        
        # Save to database if we have all three levels
        if self.entry_price and self.stop_loss and self.target_price:
            self.save_to_watchlist()
    
    def draw_horizontal_line(self, price: float, color: str, label: str):
        """Draw a horizontal line on the chart at the specified price."""
        line = self.chart.ax.axhline(y=price, color=color, linestyle='--', linewidth=1.5, label=label, alpha=0.7)
        self.horizontal_lines.append((price, color, label, line))
        self.chart.ax.legend(loc='upper left', fontsize=8)
        self.chart.canvas.draw()
    
    def redraw_horizontal_lines(self):
        """Redraw all horizontal lines after chart refresh."""
        # Clear old line objects
        temp_lines = [(p, c, l) for p, c, l, _ in self.horizontal_lines]
        self.horizontal_lines.clear()
        
        # Redraw each line
        for price, color, label in temp_lines:
            line = self.chart.ax.axhline(y=price, color=color, linestyle='--', linewidth=1.5, label=label, alpha=0.7)
            self.horizontal_lines.append((price, color, label, line))
        
        if self.horizontal_lines:
            self.chart.ax.legend(loc='upper left', fontsize=8)
            self.chart.canvas.draw()
    
    def save_to_watchlist(self):
        """Save price levels to watchlist database and calculate is_long."""
        # Calculate if trade is long or short
        is_long = self.target_price > self.entry_price
        
        print(f"[TechAnalysis] Saving to watchlist: Entry={self.entry_price}, Stop={self.stop_loss}, Target={self.target_price}, IsLong={is_long}")
        
        async def update_watchlist():
            query = """
                UPDATE watchlist 
                SET entry_price = $1, stop_loss = $2, target_price = $3, is_long = $4
                WHERE ticker = $5
            """
            await DBEngine.execute(query, self.entry_price, self.stop_loss, self.target_price, is_long, self.ticker)
            print(f"[TechAnalysis] Watchlist updated for {self.ticker}")
        
        def on_update_complete(result):
            print(f"[TechAnalysis] Database update completed")
        
        self.async_run_bg(update_watchlist(), callback=on_update_complete)
