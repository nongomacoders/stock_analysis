import ttkbootstrap as ttk
from ttkbootstrap.constants import LEFT


class TotalsStatusWidget(ttk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.total_value_label = ttk.Label(self, text="Total Value: R0.00")
        self.total_value_label.pack(side=LEFT, padx=8, pady=6)
        self.total_pl_label = ttk.Label(self, text="Total P/L: R0.00")
        self.total_pl_label.pack(side=LEFT, padx=8, pady=6)
        self.total_pl_pct_label = ttk.Label(self, text="(0.00%)")
        self.total_pl_pct_label.pack(side=LEFT, padx=0, pady=6)

    def update_totals(self, total_value: float, total_pl: float, total_pct: float):
        self.total_value_label.configure(text=f"Total Value: R{total_value:,.2f}")
        self.total_pl_label.configure(text=f"Total P/L: R{total_pl:,.2f}")
        self.total_pl_pct_label.configure(text=f"({total_pct:+.2f}%)")
        try:
            if total_pl > 0:
                self.total_pl_label.configure(foreground="#1a7f1a")
            elif total_pl < 0:
                self.total_pl_label.configure(foreground="#c02020")
            else:
                self.total_pl_label.configure(foreground="#000000")
        except Exception:
            pass
