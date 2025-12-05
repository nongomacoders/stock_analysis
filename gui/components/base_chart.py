import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH
import pandas as pd
import mplfinance as mpf
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from typing import List, Tuple, Optional, Any

import logging

from core.utils.chart_drawing_utils import (
    prepare_mpf_hlines,
    add_legend_for_hlines,
    build_ma_addplots,
)
from core.utils.dataframe_utils import prepare_df_source


class BaseChart(ttk.Frame):
    """A base class for a single mplfinance chart.

    Responsibilities:
    - Create/maintain a matplotlib Figure/Axis + tk Canvas
    - Plot OHLC candle data (local normalization and resampling)
    - Provide cursor position state (for consumers that need y cursor)
    - Provide a simple API for horizontal-line management (add/clear/redraw)

    This centralizes chart interactions so windows (e.g. TechnicalAnalysisWindow)
    can stop re-implementing the same plumbing.
    """

    def __init__(self, parent, period_label: str):
        super().__init__(parent)
        self.period_label = period_label

        self.fig = Figure(figsize=(5, 3), dpi=100)
        self.ax = self.fig.add_subplot(111)

        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.get_tk_widget().pack(fill=BOTH, expand=True)

        # Holds a list of (price, color, label)
        self.horizontal_lines: List[Tuple[float, str, str]] = []

        # Dataframes:
        # - df_source: "source" OHLC data (daily or whatever you pass in),
        #              cleaned but BEFORE resampling.
        # - df_display: last plotted dataframe AFTER resampling (used for cursor mapping).
        self.df_source: Optional[pd.DataFrame] = None
        self.df_display: Optional[pd.DataFrame] = None

        # Last used period key (e.g. "1Y", "5Y") for replotting
        self.last_period_key: Optional[str] = None

        # Current cursor y position (float) when inside axes
        self.current_cursor_y: Optional[float] = None

        # Track whether the chart was clicked / has focus for keyboard actions
        self._has_focus: bool = False

        # Bind click events so we know when the chart should accept keypresses
        self.canvas.mpl_connect("button_press_event", self.on_mouse_click)
        # Also ensure the underlying tk widget propagates focus changes
        try:
            tk_widget = self.canvas.get_tk_widget()
            tk_widget.bind("<FocusOut>", lambda e: setattr(self, "_has_focus", False))
        except Exception:
            pass

        # Bind mouse events to update cursor position and show details
        self.canvas.mpl_connect("motion_notify_event", self.on_mouse_move)

    # -------------------------------------------------------------------------
    # Core plotting
    # -------------------------------------------------------------------------
    def plot(
        self,
        data: Optional[Any] = None,
        period_key: Optional[str] = None,
        lines: Optional[Any] = None,
        addplot: Optional[Any] = None,
        _reuse_source: bool = False,
    ):
        """Plots the candlestick chart with optional horizontal lines and addplot.

        The method accepts either:
        - a pandas.DataFrame already in OHLC format (index must be datetime), or
        - a list/dict structure (with trade_date/open_price/high_price/low_price/close_price)
          which it will normalise into a DataFrame.

        If _reuse_source=True, it ignores 'data' and 'period_key' and reuses
        self.df_source + self.last_period_key. This is used internally when
        only the horizontal lines have changed.
        """
        logging.getLogger(__name__).debug(
            "  [BaseChart:%s] Plotting...", self.period_label
        )

        # ---------------------------------------------------------------------
        # 1) Prepare df_source
        # ---------------------------------------------------------------------
        if not _reuse_source:
            # Delegate data preparation/validation to util
            df_source, err = prepare_df_source(data, period_key)
            if err is not None:
                self._show_no_data(err)
                logging.getLogger(__name__).warning(
                    "  [BaseChart:%s] %s", self.period_label, err
                )
                return

            # Store for future replots (e.g. horizontal line changes)
            self.df_source = df_source
            self.last_period_key = period_key

        else:
            # Replot using existing source data and period
            df_source = self.df_source
            period_key = self.last_period_key

            if df_source is None or period_key is None:
                self._show_no_data("No data to replot")
                logging.getLogger(__name__).warning(
                    "  [BaseChart:%s] No df_source/period to reuse.", self.period_label
                )
                return

        # ---------------------------------------------------------------------
        # 2) Build df_display via resampling
        # ---------------------------------------------------------------------
        self.ax.clear()

        assert df_source is not None
        df = df_source.copy()

        # Resample based on period
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

        # Require valid OHLC after resampling
        df = df.dropna(subset=["Open", "High", "Low", "Close"])
        if df.empty:
            self._show_no_data("Insufficient data for resampling")
            logging.getLogger(__name__).warning(
                "  [BaseChart:%s] DataFrame is empty after resampling.", self.period_label
            )
            return

        logging.getLogger(__name__).debug(
            "  [BaseChart:%s] Plotting %d data points.", self.period_label, len(df)
        )

        # ---------------------------------------------------------------------
        # 3) Build moving-average addplots (50d & 200d using last 300 days)
        #     (attach to external Axes via ax=self.ax)
        # ---------------------------------------------------------------------
        ma_addplots = build_ma_addplots(self.df_source, df, self.ax)

        # ---------------------------------------------------------------------
        # 4) Build hlines for mplfinance (from stored_horizontal_lines + lines)
        # ---------------------------------------------------------------------
        hline_kwargs = prepare_mpf_hlines(self.horizontal_lines, lines)

        # ---------------------------------------------------------------------
        # 5) Build final addplot payload (merge caller's addplot with our MAs)
        # ---------------------------------------------------------------------
        final_addplot: Optional[Any] = None

        if addplot is not None and ma_addplots is not None:
            if isinstance(addplot, (list, tuple)):
                final_addplot = list(addplot) + ma_addplots
            else:
                final_addplot = [addplot] + ma_addplots
        elif addplot is not None:
            final_addplot = addplot
        else:
            final_addplot = ma_addplots

        # ---------------------------------------------------------------------
        # 6) Call mplfinance.plot
        # ---------------------------------------------------------------------
        plot_kwargs = {
            "type": "candle",
            "ax": self.ax,
            "style": "charles",
            "volume": False,
            "show_nontrading": False,
        }

        if hline_kwargs:
            plot_kwargs["hlines"] = hline_kwargs

        if final_addplot is not None:
            plot_kwargs["addplot"] = final_addplot

        mpf.plot(df, **plot_kwargs)

        # Axis labels and grid
        self.ax.set_xlabel("Date", fontsize=9)
        self.ax.set_ylabel("Price (ZAR)", fontsize=9)
        self.ax.tick_params(axis="both", labelsize=8)
        self.ax.grid(True, alpha=0.3)

        # Default title range (will be overridden dynamically by mouse move)
        min_p, max_p = df["Low"].min(), df["High"].max()
        self.ax.set_title(f"Range: R{min_p:.2f} - R{max_p:.2f}", fontsize=10)

        # Legend for horizontal lines
        add_legend_for_hlines(self.ax, self.horizontal_lines)

        self.fig.tight_layout()

        # Store display df for cursor mapping
        self.df_display = df

        # Draw canvas
        self.canvas.draw()
        logging.getLogger(__name__).debug(
            "  [BaseChart:%s] Canvas drawn.", self.period_label
        )

    # -------------------------------------------------------------------------
    # Mouse interaction
    # -------------------------------------------------------------------------
    def on_mouse_move(self, event):
        """Handle mouse movement over the chart to keep track of cursor y and update title info."""
        if event.inaxes is not self.ax:
            return

        x, y = event.xdata, event.ydata
        if x is None or y is None:
            return

        self.current_cursor_y = y

        # Try to map x back to a date index for brief summary information
        try:
            idx = int(round(x))
            if self.df_display is not None and 0 <= idx < len(self.df_display):
                date_val = self.df_display.index[idx]
                date_str = date_val.strftime("%Y-%m-%d")

                row = self.df_display.iloc[idx]
                info_text = (
                    f"{date_str} | O: {row['Open']:.2f} H: {row['High']:.2f} "
                    f"L: {row['Low']:.2f} C: {row['Close']:.2f} | Cursor: {y:.2f}"
                )
                self.ax.set_title(info_text, fontsize=10)
                self.canvas.draw_idle()
        except Exception:
            # Be tolerant to mapping errors
            pass

    def on_mouse_click(self, event):
        """Called when the chart canvas is clicked. Marks the chart as having focus
        and sets the underlying tk widget focus so keyboard handlers will be active.
        """
        if event.inaxes is not self.ax:
            return

        # Mark focus and attempt to focus the tk widget
        self._has_focus = True
        try:
            tk_widget = self.canvas.get_tk_widget()
            tk_widget.focus_set()
        except Exception:
            pass

    def has_focus(self) -> bool:
        """Return True when the chart has been clicked and accepts keypresses."""
        return bool(getattr(self, "_has_focus", False))

    # -------------------------------------------------------------------------
    # Horizontal-line management API
    # -------------------------------------------------------------------------
    def _replot_with_current_data(self):
        """Internal helper: replot using current source data + period."""
        if self.df_source is not None and self.last_period_key is not None:
            self.plot(_reuse_source=True)

    def add_horizontal_line(self, price: float, color: str, label: str):
        """Store a horizontal line level and re-plot using mplfinance hlines."""
        try:
            price = float(price)
        except Exception:
            return

        self.horizontal_lines.append((price, color, label))
        self._replot_with_current_data()

    def clear_horizontal_lines(self):
        """Clear all horizontal line levels and re-plot."""
        self.horizontal_lines.clear()
        self._replot_with_current_data()

    def redraw_horizontal_lines(self):
        """Re-plot chart to ensure stored lines are rendered."""
        self._replot_with_current_data()

    def set_horizontal_lines(self, items: List[Tuple[float, str, str]]):
        """Replace stored horizontal lines with the provided items."""
        self.horizontal_lines = list(items)
        self._replot_with_current_data()

    def get_cursor_y(self) -> Optional[float]:
        """Return the latest cursor y-position or None."""
        return self.current_cursor_y

    # -------------------------------------------------------------------------
    # Utility / cleanup
    # -------------------------------------------------------------------------
    def _show_no_data(self, message: str):
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
