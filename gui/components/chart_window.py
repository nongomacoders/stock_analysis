import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from datetime import datetime, timedelta
import asyncio

class ChartWindow(ttk.Toplevel):
    def __init__(self, parent, ticker, db_layer, async_run):
        super().__init__(parent)
        self.title(f"{ticker} - Price Charts")
        self.geometry("1200x800")
        
        self.ticker = ticker
        self.db = db_layer
        self.async_run = async_run
        
        # Configure matplotlib style
        plt.style.use('seaborn-v0_8-darkgrid')
        
        self.create_widgets()
        self.load_charts()
    
    def create_widgets(self):
        # Title
        title_frame = ttk.Frame(self, bootstyle="secondary")
        title_frame.pack(side=TOP, fill=X, padx=10, pady=10)
        ttk.Label(
            title_frame, 
            text=f"{self.ticker} - Historical Price Charts",
            font=("Helvetica", 16, "bold")
        ).pack()
        
        # Create 2x2 grid for charts
        chart_frame = ttk.Frame(self)
        chart_frame.pack(fill=BOTH, expand=True, padx=10, pady=10)
        
        # Configure grid
        chart_frame.grid_rowconfigure(0, weight=1)
        chart_frame.grid_rowconfigure(1, weight=1)
        chart_frame.grid_columnconfigure(0, weight=1)
        chart_frame.grid_columnconfigure(1, weight=1)
        
        # Create 4 chart containers
        self.chart_frames = {}
        periods = [
            ("3M", "3 Months", 0, 0),
            ("6M", "6 Months", 0, 1),
            ("1Y", "1 Year", 1, 0),
            ("5Y", "5 Years", 1, 1)
        ]
        
        for period_key, period_label, row, col in periods:
            frame = ttk.Labelframe(chart_frame, text=period_label, bootstyle="primary")
            frame.grid(row=row, column=col, sticky="nsew", padx=5, pady=5)
            self.chart_frames[period_key] = frame
    
    def load_charts(self):
        """Load and display all charts"""
        periods = {
            "3M": 90,
            "6M": 180,
            "1Y": 365,
            "5Y": 1825
        }
        
        for period_key, days in periods.items():
            data = self.async_run(self.db.get_historical_prices(self.ticker, days))
            self.plot_chart(period_key, data)
    
    def plot_chart(self, period_key, data):
        """Plot a candlestick chart"""
        frame = self.chart_frames[period_key]
        
        if data and len(data) > 0:
            # Prepare data for mplfinance
            import pandas as pd
            import mplfinance as mpf
            
            df = pd.DataFrame(data)
            df['trade_date'] = pd.to_datetime(df['trade_date'])
            df.set_index('trade_date', inplace=True)
            
            # Convert prices from cents to rands and filter out nulls
            df['Open'] = pd.to_numeric(df['open_price'], errors='coerce') / 100
            df['High'] = pd.to_numeric(df['high_price'], errors='coerce') / 100
            df['Low'] = pd.to_numeric(df['low_price'], errors='coerce') / 100
            df['Close'] = pd.to_numeric(df['close_price'], errors='coerce') / 100
            
            # Drop rows with any null OHLC values
            df = df.dropna(subset=['Open', 'High', 'Low', 'Close'])
            
            # Resample to weekly for 1Y and monthly for 5Y
            if period_key == '5Y' and len(df) > 0:
                df = df.resample('M').agg({
                    'Open': 'first',
                    'High': 'max',
                    'Low': 'min',
                    'Close': 'last'
                }).dropna()
            elif period_key == '1Y' and len(df) > 0:
                df = df.resample('W').agg({
                    'Open': 'first',
                    'High': 'max',
                    'Low': 'min',
                    'Close': 'last'
                }).dropna()
            
            if len(df) > 0:
                # Create figure
                fig, ax = plt.subplots(figsize=(5, 3), dpi=100)
                
                # Plot candlestick chart
                mpf.plot(
                    df[['Open', 'High', 'Low', 'Close']],
                    type='candle',
                    ax=ax,
                    style='charles',
                    volume=False,
                    show_nontrading=False
                )
                
                # Formatting
                ax.set_xlabel('Date', fontsize=9)
                ax.set_ylabel('Price (ZAR)', fontsize=9)
                ax.tick_params(axis='both', labelsize=8)
                ax.grid(True, alpha=0.3)
                
                # Add price range info and chart type
                min_price = df['Low'].min()
                max_price = df['High'].max()
                price_range = max_price - min_price
                if period_key == '5Y':
                    chart_type = "Monthly"
                elif period_key == '1Y':
                    chart_type = "Weekly"
                else:
                    chart_type = "Daily"
                ax.set_title(
                    f"{chart_type} - Range: R{min_price:.2f} - R{max_price:.2f} (R{price_range:.2f})",
                    fontsize=10
                )
                
                fig.tight_layout()
            else:
                # No valid data after filtering
                fig = Figure(figsize=(5, 3), dpi=100)
                ax = fig.add_subplot(111)
                ax.text(0.5, 0.5, 'No valid OHLC data', 
                       ha='center', va='center', fontsize=12)
                ax.set_title('No Data', fontsize=10)
                fig.tight_layout()
        else:
            # No data available
            fig = Figure(figsize=(5, 3), dpi=100)
            ax = fig.add_subplot(111)
            ax.text(0.5, 0.5, 'No data available', 
                   ha='center', va='center', fontsize=12)
            ax.set_title('No Data', fontsize=10)
            fig.tight_layout()
        
        # Embed in tkinter
        canvas = FigureCanvasTkAgg(fig, master=frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=BOTH, expand=True)
