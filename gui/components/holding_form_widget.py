import tkinter as tk
import ttkbootstrap as ttk
from typing import Callable, Optional


class HoldingFormWidget(ttk.Frame):
    def __init__(self, parent, change_callback: Optional[Callable] = None, **kwargs):
        super().__init__(parent, **kwargs)
        ttk.Label(self, text="Ticker").grid(row=0, column=0, sticky="w")
        self.ticker_var = tk.StringVar()
        self.qty_var = tk.StringVar()
        self.avg_var = tk.StringVar()
        self.ticker_entry = ttk.Entry(self, textvariable=self.ticker_var)
        self.ticker_entry.grid(row=0, column=1, padx=6, pady=2, sticky="ew")
        ttk.Label(self, text="Quantity").grid(row=1, column=0, sticky="w")
        self.qty_entry = ttk.Entry(self, textvariable=self.qty_var)
        self.qty_entry.grid(row=1, column=1, padx=6, pady=2, sticky="ew")
        ttk.Label(self, text="Avg Price").grid(row=2, column=0, sticky="w")
        tk_label = ttk.Label(self, text="(in cents)")
        tk_label.grid(row=2, column=2, sticky="w", padx=(6, 0))
        self.avg_entry = ttk.Entry(self, textvariable=self.avg_var)
        self.avg_entry.grid(row=2, column=1, padx=6, pady=2, sticky="ew")
        self.columnconfigure(1, weight=1)
        self.change_callback = change_callback
        if change_callback:
            self.ticker_var.trace_add("write", lambda *a: change_callback())
            self.qty_var.trace_add("write", lambda *a: change_callback())
            self.avg_var.trace_add("write", lambda *a: change_callback())

    def get_values(self):
        return (self.ticker_var.get().strip(), self.qty_var.get(), self.avg_var.get())

    def set_values(self, ticker: str, qty: str, avg: str):
        self.ticker_var.set(ticker or "")
        self.qty_var.set(qty or "")
        self.avg_var.set(avg or "")

    def clear(self):
        self.ticker_var.set("")
        self.qty_var.set("")
        self.avg_var.set("")
