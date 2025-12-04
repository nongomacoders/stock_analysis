import ttkbootstrap as ttk
import tkinter as tk
from ttkbootstrap.constants import BOTH
from typing import Callable, List, Dict


class HoldingsWidget(ttk.Frame):
    def __init__(self, parent, select_callback: Callable = None, **kwargs):
        super().__init__(parent, **kwargs)
        self.tree = ttk.Treeview(
            self,
            columns=("ticker", "qty", "avg", "cost", "latest", "pl", "pct"),
            show="headings",
            height=20,
        )
        self.tree.heading("ticker", text="Ticker")
        self.tree.heading("qty", text="Quantity")
        self.tree.heading("avg", text="Avg Price (c)")
        self.tree.heading("cost", text="Portfolio Cost Value (R)")
        self.tree.heading("latest", text="Latest")
        self.tree.heading("pl", text="P/L (R)")
        self.tree.heading("pct", text="P/L (%)")
        self.tree.pack(fill=BOTH, expand=True)

        try:
            self.tree.tag_configure("pl_pos", foreground="#1a7f1a")
            self.tree.tag_configure("pl_neg", foreground="#c02020")
            self.tree.tag_configure("pl_zero", foreground="#000000")
        except Exception:
            pass

        if select_callback:
            self.tree.bind("<<TreeviewSelect>>", select_callback)

    def set_holdings(self, rows: List[Dict]):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for r in rows:
            latest = r.get("latest_price")
            pl = r.get("pl")
            cost_value = r.get("cost_value")
            latest_display = "" if latest is None else f"R{float(latest):,.2f}"
            pl_display = "" if pl is None else f"R{float(pl):,.2f}"
            pct = r.get("pct_pl")
            pct_display = "" if pct is None else f"{float(pct):+.2f}%"
            cost_display = "" if cost_value is None else f"R{float(cost_value):,.2f}"
            tag = ()
            try:
                if pl is None:
                    tag = ("pl_zero",)
                else:
                    val = float(pl)
                    if val > 0:
                        tag = ("pl_pos",)
                    elif val < 0:
                        tag = ("pl_neg",)
                    else:
                        tag = ("pl_zero",)
            except Exception:
                tag = ("pl_zero",)
            self.tree.insert(
                "",
                index='end',
                iid=str(r.get("id", "")),
                values=(r.get("ticker"), r.get("quantity"), r.get("average_buy_price"), cost_display, latest_display, pl_display, pct_display),
                tags=tag,
            )

    def bind_select(self, callback: Callable):
        self.tree.bind("<<TreeviewSelect>>", callback)

    def get_selection_iid(self):
        sel = self.tree.selection()
        if not sel:
            return None
        return sel[0]

    def get_item_values(self, iid: str):
        return self.tree.item(iid, "values") if iid else ()

    def clear_selection(self):
        for s in self.tree.selection():
            try:
                self.tree.selection_remove(s)
            except Exception:
                pass
