"""
Simple interactive demo for BaseChart.

Usage:
    python -m gui.tools.demo_base_chart

Keys:
    a - add an 'entry' horizontal line at current cursor y
    s - add a 'stop' horizontal line at current cursor y
    t - add a 'target' horizontal line at current cursor y
    c - clear all lines
    q / Escape - quit

This demo helps manually verify cursor mapping and horizontal-line APIs.
"""

import tkinter as tk
import pandas as pd
import numpy as np
import logging
from components.base_chart import BaseChart


def make_sample_df(n=90):
    dates = pd.date_range(end=pd.Timestamp.today(), periods=n)
    base = 100
    close = base + np.cumsum(np.random.randn(n) * 2).astype(float)
    open_ = close - (np.random.randn(n) * 0.5)
    high = np.maximum(open_, close) + np.abs(np.random.randn(n) * 1.2)
    low = np.minimum(open_, close) - np.abs(np.random.randn(n) * 1.2)

    df = pd.DataFrame({
        "trade_date": dates,
        "open_price": (open_ * 100).astype(int),
        "high_price": (high * 100).astype(int),
        "low_price": (low * 100).astype(int),
        "close_price": (close * 100).astype(int),
    })
    df.set_index("trade_date", inplace=False)
    return df


class DemoApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("BaseChart Demo")
        self.geometry("1000x600")

        self.chart = BaseChart(self, "Demo Chart")
        self.chart.pack(fill=tk.BOTH, expand=True)

        # prepare sample data and plot
        df = make_sample_df(120)
        self.chart.plot(df, '6M')

        self.bind('<Key>', self.on_key)
        self.protocol('WM_DELETE_WINDOW', self.on_close)

        label = tk.Label(self, text=("Keys: a=entry, s=stop, t=target, c=clear, q=quit\n"
                                     "Move your mouse over the plot to update the cursor Y value."))
        label.pack(side=tk.BOTTOM, pady=6)

    def on_key(self, event):
        k = event.keysym.lower()
        y = self.chart.get_cursor_y()
        if k in ('a', 's', 't'):
            if y is None:
                logging.getLogger(__name__).warning(
                    "No cursor y available — move the mouse over the chart first"
                )
                return
            label = 'entry' if k == 'a' else ('stop' if k == 's' else 'target')
            color = 'blue' if label == 'entry' else ('red' if label == 'stop' else 'green')
            self.chart.add_horizontal_line(y, color, label)
            logging.getLogger(__name__).info("Added %s line at %.2f", label, y)
        elif k == 'c':
            self.chart.clear_horizontal_lines()
            logging.getLogger(__name__).info("Cleared all horizontal lines")
        elif k in ('q', 'escape'):
            self.on_close()

    def on_close(self):
        # ensure resources are cleaned up
        try:
            self.chart.destroy()
        except Exception:
            pass
        self.destroy()


if __name__ == '__main__':
    app = DemoApp()
    app.mainloop()
