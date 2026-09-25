"""Version browser component for Historical Backtest ForecastPlans."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, X, LEFT
from modules.analysis.historical_plan import HistoricalForecastPlan

def historical_plan_header(ticker: str, plan: HistoricalForecastPlan | None, dirty: bool) -> str:
    if plan is None:
        return f"{ticker} Historical Plan — NOT CREATED"
    state = "UNSAVED CHANGES" if dirty else "SAVED"
    return f"{ticker} Historical Plan v{plan.plan_version} {plan.status.value.upper()} — {state}"

class HistoricalPlanBrowser(ttk.LabelFrame):
    def __init__(self, parent, on_view_version, on_clone_version):
        super().__init__(parent, text="Historical Plan Version Browser")
        self.on_view = on_view_version
        self.on_clone = on_clone_version
        self.plans: list[HistoricalForecastPlan] = []
        self._build()

    def _build(self):
        hb = ttk.Frame(self); hb.pack(fill=X, padx=2, pady=2)
        self.table = ttk.Treeview(hb, columns=("version", "status", "created", "plan_id"), show="headings", height=3)
        for col, w in (("version", 60), ("status", 90), ("created", 140), ("plan_id", 240)):
            self.table.heading(col, text=col.upper()); self.table.column(col, width=w)
        self.table.pack(side=LEFT, fill=X, expand=True)
        h_btns = ttk.Frame(self); h_btns.pack(fill=X, pady=2)
        ttk.Button(h_btns, text="View selected version", command=self._view_selected).pack(side=LEFT, padx=3)
        ttk.Button(h_btns, text="Clone approved as new draft", command=self.on_clone).pack(side=LEFT, padx=3)

    def set_plans(self, plans: list[HistoricalForecastPlan]):
        self.plans = plans
        for item in self.table.get_children(): self.table.delete(item)
        for p in plans:
            self.table.insert("", "end", iid=str(p.historical_plan_id), values=(f"v{p.plan_version}", p.status.value.upper(), str(p.created_at)[:19], str(p.historical_plan_id)))

    def _view_selected(self):
        sel = self.table.selection()
        if not sel: return
        pid = sel[0]
        match = next((p for p in self.plans if str(p.historical_plan_id) == pid), None)
        if match: self.on_view(match)
