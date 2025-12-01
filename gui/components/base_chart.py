import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import pandas as pd
import mplfinance as mpf
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


class BaseChart(ttk.Frame):
    """
    A base class for a single mplfinance chart.
    Encapsulates the figure, canvas, and plotting logic.
    """

    def __init__(self, parent, period_label):
        super().__init__(parent)
        self.period_label = period_label

        self.fig = Figure(figsize=(5, 3), dpi=100)
        self.ax = self.fig.add_subplot(111)

        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.get_tk_widget().pack(fill=BOTH, expand=True)

    def plot(self, data, period_key, lines=None, addplot=None):
        """Plots the candlestick chart with optional horizontal lines and additional plots."""
        print(f"  [BaseChart:{self.period_label}] Plotting...")
        self.ax.clear()

        if data is None or (isinstance(data, list) and not data) or (isinstance(data, pd.DataFrame) and data.empty):
            self._show_no_data("No data available")
            print(f"  [BaseChart:{self.period_label}] No data provided, showing message.")
            return

        if isinstance(data, pd.DataFrame):
            df = data.copy()
        else:
            df = pd.DataFrame(data)
            df["trade_date"] = pd.to_datetime(df["trade_date"])
            df.set_index("trade_date", inplace=True)

            # Convert prices (cents -> rands)
            for col in ["open_price", "high_price", "low_price", "close_price"]:
                df[col] = pd.to_numeric(df[col], errors="coerce") / 100

            df = df.rename(
                columns={
                    "open_price": "Open", "high_price": "High",
                    "low_price": "Low", "close_price": "Close",
                }
            )
        
        df = df.dropna(subset=["Open", "High", "Low", "Close"])

        if df.empty:
            self._show_no_data("No valid OHLC data")
            print(f"  [BaseChart:{self.period_label}] DataFrame is empty after cleaning.")
            return

        # Resample based on period - ONLY if not already resampled/prepared
        if period_key == "5Y":
            df = df.resample("ME").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
        elif period_key == "1Y":
            df = df.resample("W").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()

        if df.empty:
            self._show_no_data("Insufficient data for resampling")
            print(f"  [BaseChart:{self.period_label}] DataFrame is empty after resampling.")
            return

        print(f"  [BaseChart:{self.period_label}] Plotting {len(df)} data points.")
        # Build kwargs for mplfinance plot
        plot_kwargs = {
            'type': 'candle',
            'ax': self.ax,
            'style': 'charles',
            'volume': False,
            'show_nontrading': False
        }
        if lines:
            plot_kwargs['hlines'] = lines
        
        if addplot:
            plot_kwargs['addplot'] = addplot

        mpf.plot(df, **plot_kwargs)

        self.ax.set_xlabel("Date", fontsize=9)
        self.ax.set_ylabel("Price (ZAR)", fontsize=9)
        self.ax.tick_params(axis="both", labelsize=8)
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import pandas as pd
import mplfinance as mpf
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


class BaseChart(ttk.Frame):
    """
    A base class for a single mplfinance chart.
    Encapsulates the figure, canvas, and plotting logic.
    """

    def __init__(self, parent, period_label):
        super().__init__(parent)
        self.period_label = period_label

        self.fig = Figure(figsize=(5, 3), dpi=100)
        self.ax = self.fig.add_subplot(111)

        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.get_tk_widget().pack(fill=BOTH, expand=True)

    def plot(self, data, period_key, lines=None, addplot=None):
        """Plots the candlestick chart with optional horizontal lines and additional plots."""
        print(f"  [BaseChart:{self.period_label}] Plotting...")
        self.ax.clear()

        if data is None or (isinstance(data, list) and not data) or (isinstance(data, pd.DataFrame) and data.empty):
            self._show_no_data("No data available")
            print(f"  [BaseChart:{self.period_label}] No data provided, showing message.")
            return

        if isinstance(data, pd.DataFrame):
            df = data.copy()
        else:
            df = pd.DataFrame(data)
            df["trade_date"] = pd.to_datetime(df["trade_date"])
            df.set_index("trade_date", inplace=True)

            # Convert prices (cents -> rands)
            for col in ["open_price", "high_price", "low_price", "close_price"]:
                df[col] = pd.to_numeric(df[col], errors="coerce") / 100

            df = df.rename(
                columns={
                    "open_price": "Open", "high_price": "High",
                    "low_price": "Low", "close_price": "Close",
                }
            )
        
        df = df.dropna(subset=["Open", "High", "Low", "Close"])

        if df.empty:
            self._show_no_data("No valid OHLC data")
            print(f"  [BaseChart:{self.period_label}] DataFrame is empty after cleaning.")
            return

        # Resample based on period - ONLY if not already resampled/prepared
        if period_key == "5Y":
            df = df.resample("ME").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
        elif period_key == "1Y":
            df = df.resample("W").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()

        if df.empty:
            self._show_no_data("Insufficient data for resampling")
            print(f"  [BaseChart:{self.period_label}] DataFrame is empty after resampling.")
            return

        print(f"  [BaseChart:{self.period_label}] Plotting {len(df)} data points.")
        # Build kwargs for mplfinance plot
        plot_kwargs = {
            'type': 'candle',
            'ax': self.ax,
            'style': 'charles',
            'volume': False,
            'show_nontrading': False
        }
        if lines:
            plot_kwargs['hlines'] = lines
        
        if addplot:
            plot_kwargs['addplot'] = addplot

        mpf.plot(df, **plot_kwargs)

        self.ax.set_xlabel("Date", fontsize=9)
        self.ax.set_ylabel("Price (ZAR)", fontsize=9)
        self.ax.tick_params(axis="both", labelsize=8)
        self.ax.grid(True, alpha=0.3)

        min_p, max_p = df["Low"].min(), df["High"].max()
        self.ax.set_title(f"Range: R{min_p:.2f} - R{max_p:.2f}", fontsize=10)
        self.fig.tight_layout()

        self.canvas.draw()
        print(f"  [BaseChart:{self.period_label}] Canvas drawn.")

        # Store dataframe for cursor interaction
        self.df_display = df
        
        # Connect mouse motion event
        self.canvas.mpl_connect("motion_notify_event", self.on_mouse_move)

    def on_mouse_move(self, event):
        """Handle mouse movement over the chart to display cursor info."""
        if not event.inaxes == self.ax:
            return

        # Get x and y coordinates
        x, y = event.xdata, event.ydata
        
        if x is None or y is None:
            return
            
        # Convert x to date index
        # mplfinance uses integer index for x-axis when show_nontrading=False (default)
        # We need to map this integer back to the date in self.df_display
        try:
            idx = int(round(x))
            if 0 <= idx < len(self.df_display):
                date_val = self.df_display.index[idx]
                date_str = date_val.strftime('%Y-%m-%d')
                
                # Get OHLC data for this date
                row = self.df_display.iloc[idx]
                open_p = row['Open']
                high_p = row['High']
                low_p = row['Low']
                close_p = row['Close']
                
                # Update title or add a text annotation
                # For now, let's update the title with dynamic info
                info_text = f"{date_str} | O: {open_p:.2f} H: {high_p:.2f} L: {low_p:.2f} C: {close_p:.2f} | Cursor: {y:.2f}"
                self.ax.set_title(info_text, fontsize=10)
                self.canvas.draw_idle()
        except Exception as e:
            # print(f"Cursor error: {e}")
            pass

    def _show_no_data(self, message):
        """Displays a message on the chart area when no data is available."""
        self.ax.clear()
        self.ax.text(0.5, 0.5, message, ha="center", va="center", fontsize=12)
        self.ax.set_title("No Data", fontsize=10)
        self.fig.tight_layout()
        self.canvas.draw()

    def destroy(self):
        """Properly clean up the matplotlib figure and canvas."""
        self.fig.clear()
        plt.close(self.fig)
        super().destroy()