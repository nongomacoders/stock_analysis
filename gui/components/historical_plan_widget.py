"""Interactive widget for managing Historical Backtest ForecastPlans."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, StringVar, BOTH, X, LEFT
from decimal import Decimal, InvalidOperation
from modules.analysis.forecast_plan import ApprovalState, ForecastAssumption, Origin
from modules.analysis.historical_backtest import HistoricalBacktest
from modules.analysis.historical_plan import (
    HistoricalForecastPlan, HistoricalPlanStatus, create_historical_draft,
    clone_historical_draft, MATERIAL_FIELDS
)
from modules.analysis.historical_retail_bridge import render_historical_baseline_display
from modules.analysis.historical_mapping import (
    map_historical_fy2026_dcf, map_historical_equity_bridge,
    evaluate_historical_plan_readiness, render_historical_plan_readiness
)
from modules.analysis.historical_forecast_txt import parse_historical_forecast_txt
from components.historical_plan_browser import HistoricalPlanBrowser, historical_plan_header
from components.historical_assumption_form import HistoricalAssumptionForm
from components.historical_plan_actions import (
    run_save_plan, run_approve_plan, run_lock_plan, run_reload_history
)

class HistoricalPlanWidget(ttk.Frame):
    def __init__(self, parent, get_backtest_fn, async_run_bg):
        super().__init__(parent)
        self.get_backtest = get_backtest_fn; self.async_run_bg = async_run_bg
        self.plan: HistoricalForecastPlan | None = None; self.dirty = False
        self._build_ui()

    def _build_ui(self):
        top = ttk.Frame(self); top.pack(fill=X, padx=5, pady=4)
        self.header_var = StringVar(value="Historical Plan — NOT CREATED")
        ttk.Label(top, textvariable=self.header_var, font=("Helvetica", 11, "bold")).pack(side=LEFT)
        ttk.Button(top, text="Create historical ForecastPlan", command=self.create_draft_action).pack(side=LEFT, padx=4)
        ttk.Button(top, text="Build historical assumption suggestions", command=self.build_suggestions_action).pack(side=LEFT, padx=3)
        ttk.Button(top, text="Review historical WACC inputs", command=self.market_inputs_action).pack(side=LEFT, padx=3)
        self.save_btn = ttk.Button(top, text="Save historical plan", command=self.save_plan_action, state="disabled"); self.save_btn.pack(side=LEFT, padx=3)
        self.approve_btn = ttk.Button(top, text="Approve historical plan", command=self.approve_plan_action, state="disabled"); self.approve_btn.pack(side=LEFT, padx=3)
        self.lock_btn = ttk.Button(top, text="Lock backtest plan", command=self.lock_plan_action, state="disabled"); self.lock_btn.pack(side=LEFT, padx=3)
        self.reveal_btn = ttk.Button(top, text="Reveal FY2026 actuals", command=self.reveal_actuals_action, state="disabled"); self.reveal_btn.pack(side=LEFT, padx=3)

        body = ttk.PanedWindow(self, orient=tk.HORIZONTAL); body.pack(fill=BOTH, expand=True, padx=5, pady=4)
        left = ttk.Frame(body); body.add(left, weight=1)
        ttk.Label(left, text="FY2025 Source-Backed Baseline (Cutoff: 2025-08-31)", font=("Helvetica", 10, "bold")).pack(anchor="w")
        self.baseline_text = tk.Text(left, width=45, height=16, font=("Consolas", 9)); self.baseline_text.pack(fill=BOTH, expand=True, pady=2)
        ttk.Label(left, text="Deterministic Readiness", font=("Helvetica", 10, "bold")).pack(anchor="w", pady=(4,0))
        self.readiness_text = tk.Text(left, width=45, height=8, font=("Consolas", 9)); self.readiness_text.pack(fill=BOTH, expand=True, pady=2)

        right = ttk.Frame(body); body.add(right, weight=2)
        self.form = HistoricalAssumptionForm(right, on_add=self.add_assumption_action, on_import=self.import_txt_action); self.form.pack(fill=X, padx=2, pady=2)
        self.table = ttk.Treeview(right, columns=("field", "val", "unit", "origin", "approval", "rat"), show="headings", height=7)
        for col, w in (("field", 160), ("val", 80), ("unit", 70), ("origin", 110), ("approval", 80), ("rat", 180)):
            self.table.heading(col, text=col.upper()); self.table.column(col, width=w)
        self.table.pack(fill=BOTH, expand=True, pady=2)

        act = ttk.Frame(right); act.pack(fill=X, pady=2)
        ttk.Button(act, text="Accept selected", command=self.accept_assumption_action).pack(side=LEFT, padx=3)
        ttk.Button(act, text="Discard proposed", command=self.discard_assumption_action).pack(side=LEFT, padx=3)
        ttk.Button(act, text="Map historical FY2026 inputs to DCF", command=self.map_dcf_action).pack(side=LEFT, padx=6)
        ttk.Button(act, text="Map historical equity bridge", command=self.map_equity_action).pack(side=LEFT, padx=3)
        self.browser = HistoricalPlanBrowser(right, on_view_version=self._view_hist, on_clone_version=self.clone_draft_action); self.browser.pack(fill=X, pady=2)

    def set_backtest(self, bt: HistoricalBacktest | None):
        if bt:
            self.baseline_text.delete("1.0", tk.END); self.baseline_text.insert(tk.END, render_historical_baseline_display(bt))
        self.refresh_ui()

    def refresh_ui(self):
        bt = self.get_backtest()
        self.header_var.set(historical_plan_header(bt.ticker if bt else "TRU.JO", self.plan, self.dirty))
        st = "normal" if (self.plan and not self.plan.is_locked) else "disabled"
        self.save_btn.configure(state=st)
        self.approve_btn.configure(state="normal" if (self.plan and self.plan.status == HistoricalPlanStatus.DRAFT and not self.plan.is_locked) else "disabled")
        self.lock_btn.configure(state="normal" if (self.plan and self.plan.status == HistoricalPlanStatus.APPROVED and not self.plan.is_locked) else "disabled")
        self.reveal_btn.configure(state="normal" if (self.plan and self.plan.is_locked) else "disabled")
        for item in self.table.get_children(): self.table.delete(item)
        if self.plan:
            for a in self.plan.assumptions:
                self.table.insert("", "end", iid=str(a.assumption_id), values=(a.field, str(a.value), a.unit, a.origin.value, a.approval_state.value, a.rationale))
            if bt:
                self.readiness_text.delete("1.0", tk.END)
                self.readiness_text.insert(tk.END, render_historical_plan_readiness(evaluate_historical_plan_readiness(self.plan, bt)))

    def create_draft_action(self):
        bt = self.get_backtest()
        if not bt: messagebox.showerror("No Backtest", "Resolve historical baseline first.", parent=self); return
        try:
            self.plan = create_historical_draft(bt, created_by=self.form.get_values()["analyst"])
            self.dirty = True; self.refresh_ui()
            messagebox.showinfo("Draft Created", f"Draft historical ForecastPlan v1 created for {bt.ticker}.\nBaseline: READY\nEnter or import fresh FY2026 assumptions.", parent=self)
        except Exception as e: messagebox.showerror("Creation Failed", str(e), parent=self)

    def build_suggestions_action(self):
        bt = self.get_backtest()
        if not bt: messagebox.showerror("No Backtest", "Resolve historical baseline first.", parent=self); return
        if not self.plan:
            try: self.plan = create_historical_draft(bt, created_by=self.form.get_values()["analyst"])
            except Exception as e: messagebox.showerror("Creation Failed", str(e), parent=self); return
        from components.historical_assistant_dialog import HistoricalAssistantDialog
        def on_applied(updated):
            self.plan = updated; self.dirty = True; self.refresh_ui()
        HistoricalAssistantDialog(self, bt, self.plan, on_applied=on_applied)

    def market_inputs_action(self):
        bt = self.get_backtest()
        if not bt: messagebox.showerror("No Backtest", "Resolve historical baseline first.", parent=self); return
        from components.historical_market_input_dialog import HistoricalMarketInputDialog
        HistoricalMarketInputDialog(self, bt, on_updated=self.refresh_ui)

    def save_plan_action(self): run_save_plan(self, self.plan, self.async_run_bg)
    def approve_plan_action(self): run_approve_plan(self, self.plan, self.form.get_values()["analyst"], self.async_run_bg)
    def lock_plan_action(self): run_lock_plan(self, self.plan, self.get_backtest(), self.async_run_bg)
    def _reload_history(self):
        if self.plan: run_reload_history(self, self.plan.backtest_id, self.async_run_bg)

    def reveal_actuals_action(self):
        if not self.plan or not self.plan.is_locked:
            messagebox.showwarning("Locked Required", "Cannot reveal FY2026 actuals before historical backtest is locked.", parent=self); return
        messagebox.showinfo("Reveal FY2026 Actuals", "Historical plan is locked. Ready to reveal actuals in the evaluation step.", parent=self)

    def add_assumption_action(self):
        if not self.plan or self.plan.is_locked: return
        v = self.form.get_values()
        if not v["field"]: return
        try: val = Decimal(v["value"])
        except (ValueError, InvalidOperation): messagebox.showerror("Invalid Value", "Enter a valid numeric value.", parent=self); return
        if v["field"] in MATERIAL_FIELDS and not v["rationale"]:
            messagebox.showerror("Rationale Required", f"Material assumption {v['field']} requires rationale available by {self.plan.as_of_date}.", parent=self); return
        a = ForecastAssumption(field=v["field"], value=val, unit=v["unit"], period_label="FY2026", operation_segment="Group", case="base", origin=Origin.ANALYST_ASSUMPTION, approval_state=ApprovalState.PROPOSED, rationale=v["rationale"], created_by=v["analyst"], source_date=self.plan.as_of_date)
        self.plan.assumptions = [item for item in self.plan.assumptions if item.field != v["field"]] + [a]; self.dirty = True; self.refresh_ui()

    def import_txt_action(self):
        if not self.plan or self.plan.is_locked: return
        path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
        if not path: return
        try:
            with open(path, "r", encoding="utf-8") as f: content = f.read()
            imported = parse_historical_forecast_txt(content, self.plan)
            fields = {x.field for x in imported}
            self.plan.assumptions = [item for item in self.plan.assumptions if item.field not in fields] + imported; self.dirty = True; self.refresh_ui()
            messagebox.showinfo("Imported", f"Imported {len(imported)} proposed historical assumptions from TXT.", parent=self)
        except Exception as e: messagebox.showerror("Import Failed", str(e), parent=self)

    def accept_assumption_action(self):
        if not self.plan or self.plan.is_locked: return
        sel = self.table.selection()
        if not sel: return
        for a in self.plan.assumptions:
            if str(a.assumption_id) == sel[0]:
                if a.field in MATERIAL_FIELDS and not (a.rationale and a.rationale.strip()):
                    messagebox.showerror("Rationale Required", f"{a.field} requires explicit historical rationale.", parent=self); return
                a.approval_state = ApprovalState.ACCEPTED
        self.dirty = True; self.refresh_ui()

    def discard_assumption_action(self):
        if not self.plan or self.plan.is_locked: return
        sel = self.table.selection()
        if sel:
            self.plan.assumptions = [a for a in self.plan.assumptions if str(a.assumption_id) != sel[0]]; self.dirty = True; self.refresh_ui()

    def map_dcf_action(self):
        if not self.plan or not self.get_backtest() or self.plan.is_locked: return
        try:
            updated, preview = map_historical_fy2026_dcf(self.plan, self.get_backtest())
            self.plan = updated; self.dirty = True; self.refresh_ui()
            messagebox.showinfo("DCF Mapped", f"Mapped FY2026 inputs to DCF:\nWACC: {preview['wacc']}%\nTerminal Growth: {preview['terminal_growth']}%\nEBIT & Revenue derived from FY2025 baseline.", parent=self)
        except Exception as e: messagebox.showerror("DCF Mapping Failed", str(e), parent=self)

    def map_equity_action(self):
        if not self.plan or not self.get_backtest() or self.plan.is_locked: return
        try:
            updated, preview = map_historical_equity_bridge(self.plan, self.get_backtest())
            self.plan = updated; self.dirty = True; self.refresh_ui()
            messagebox.showinfo("Equity Bridge Mapped", f"Mapped FY2025 Equity Bridge:\nNet Cash: R720m\nLease Liabilities: R3.742bn\nShares: 375,360,899\nLease Treatment: {preview['lease_treatment']}", parent=self)
        except Exception as e: messagebox.showerror("Equity Mapping Failed", str(e), parent=self)

    def clone_draft_action(self):
        if not self.plan or self.plan.status != HistoricalPlanStatus.APPROVED:
            messagebox.showwarning("Approved Required", "Clone requires an approved historical plan version.", parent=self); return
        cloned = clone_historical_draft(self.plan, self.form.get_values()["analyst"])
        self.plan = cloned; self.dirty = True; self.refresh_ui()
        messagebox.showinfo("Cloned", f"Cloned v{cloned.plan_version} DRAFT created in memory.", parent=self)

    def _view_hist(self, plan: HistoricalForecastPlan):
        self.plan = plan; self.dirty = False; self.refresh_ui()
