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

    def plot(self, data, period_key, lines=None):
        """Plots the candlestick chart with optional horizontal lines."""
        print(f"  [BaseChart:{self.period_label}] Plotting...")
        self.ax.clear()

        if not data:
            self._show_no_data("No data available")
            print(f"  [BaseChart:{self.period_label}] No data provided, showing message.")
            return

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

        # Resample based on period
        if period_key == "5Y":
            df = df.resample("ME").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
        elif period_key == "1Y":
            df = df.resample("W").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()

        if df.empty:
            self._show_no_data("Insufficient data for resampling")
            print(f"  [BaseChart:{self.period_label}] DataFrame is empty after resampling.")
            return

        print(f"  [BaseChart:{self.period_label}] Plotting {len(df)} data points.")
        # Build kwargs for mplfinance plot, only including hlines if it's provided
        plot_kwargs = {
            'type': 'candle',
            'ax': self.ax,
            'style': 'charles',
            'volume': False,
            'show_nontrading': False
        }
        if lines:
            plot_kwargs['hlines'] = lines

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