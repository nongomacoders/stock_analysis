"""Async actions and persistence helpers for historical backtest plans."""
from __future__ import annotations
from tkinter import messagebox
from modules.analysis.historical_plan import (
    HistoricalForecastPlan, approve_historical_plan_in_place
)
from modules.data.historical_plans_storage import (
    save_historical_plan_db, approve_historical_plan_db,
    lock_historical_backtest_and_plan_db, list_historical_plans_db
)

def run_save_plan(widget, plan, async_run_bg):
    if not plan: return
    async def work(): return await save_historical_plan_db(plan)
    def done(saved):
        widget.plan = saved; widget.dirty = False; widget.refresh_ui(); widget._reload_history()
        messagebox.showinfo("Saved", f"Historical Plan v{saved.plan_version} saved successfully.\nStatus: {saved.status.value}", parent=widget)
    async_run_bg(work(), callback=done)

def run_approve_plan(widget, plan, reviewer, async_run_bg):
    if not plan: return
    try:
        approved = approve_historical_plan_in_place(plan, reviewer)
        async def work(): return await approve_historical_plan_db(approved, reviewer)
        def done(res):
            widget.plan = res; widget.dirty = False; widget.refresh_ui(); widget._reload_history()
            messagebox.showinfo("Approved", f"Historical Plan v{res.plan_version} APPROVED in place.", parent=widget)
        async_run_bg(work(), callback=done)
    except Exception as e: messagebox.showerror("Approval Failed", str(e), parent=widget)

def run_lock_plan(widget, plan, backtest, async_run_bg):
    if not plan or not backtest: return
    try:
        async def work(): return await lock_historical_backtest_and_plan_db(plan, backtest)
        def done(locked):
            widget.plan = locked; widget.dirty = False; widget.refresh_ui(); widget._reload_history()
            messagebox.showinfo("Locked", "Historical Backtest and Plan are now immutable and LOCKED.\nFY2026 actuals reveal is now unlocked.", parent=widget)
        async_run_bg(work(), callback=done)
    except Exception as e: messagebox.showerror("Lock Failed", str(e), parent=widget)

def run_reload_history(widget, backtest_id, async_run_bg):
    async def work(): return await list_historical_plans_db(backtest_id)
    def done(plans): widget.browser.set_plans(plans)
    async_run_bg(work(), callback=done)
