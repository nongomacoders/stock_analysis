"""Review modal for Historical Assumption Assistant proposals."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, BOTH, X, LEFT, RIGHT
from modules.analysis.forecast_plan import ApprovalState
from modules.analysis.historical_assistant import (
    HistoricalAssumptionProposal, HistoricalAssistantAudit, generate_historical_assumptions
)
from modules.analysis.historical_assistant_txt import export_proposals_to_txt, proposals_to_forecast_assumptions
from modules.analysis.historical_assistant_audit import (
    create_proposal_audit_records, attach_assistant_audit_to_plan
)
from modules.analysis.historical_plan import HistoricalForecastPlan

class HistoricalAssistantDialog(tk.Toplevel):
    def __init__(self, parent, backtest, plan: HistoricalForecastPlan, on_applied=None):
        super().__init__(parent)
        self.title("Historical Assumption Assistant (Cutoff: 2025-08-31)")
        self.geometry("980x600")
        self.transient(parent); self.grab_set()
        self.backtest = backtest; self.plan = plan; self.on_applied = on_applied
        self.proposals, self.audit = generate_historical_assumptions(backtest)
        self.reviewed_ids: set[str] = set()
        self._build_ui(); self._populate()

    def _build_ui(self):
        audit_fr = ttk.LabelFrame(self, text="Hindsight Leakage Barrier & Audit Snapshot (<= 2025-08-31)")
        audit_fr.pack(fill=X, padx=8, pady=4)
        a_txt = (f"Eligible Sources: {self.audit.eligible_source_count}  |  "
                 f"Excluded Later: {self.audit.excluded_later_source_count}  |  "
                 f"Unknown-Date Excluded: {self.audit.unknown_date_exclusions}  |  "
                 f"Market Obs: {self.audit.market_observations_used}\n"
                 f"Snapshot Hash: {self.audit.snapshot_hash[:24]}...  |  Cutoff: {self.audit.as_of_date}")
        ttk.Label(audit_fr, text=a_txt, font=("Consolas", 9)).pack(anchor="w", padx=6, pady=4)

        tree_fr = ttk.Frame(self); tree_fr.pack(fill=BOTH, expand=True, padx=8, pady=2)
        cols = ("field", "anchor", "proposed", "basis", "quality", "status")
        self.table = ttk.Treeview(tree_fr, columns=cols, show="headings", height=10)
        widths = (("field", 140, "FIELD"), ("anchor", 200, "HISTORICAL ANCHOR (FACT)"),
                  ("proposed", 90, "PROPOSED"), ("basis", 130, "FORECAST BASIS"),
                  ("quality", 150, "QUALITY / CLASSIFICATION"), ("status", 80, "STATUS"))
        for col, w, t in widths:
            self.table.heading(col, text=t); self.table.column(col, width=w)
        self.table.pack(side=LEFT, fill=BOTH, expand=True)
        sb = ttk.Scrollbar(tree_fr, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=sb.set); sb.pack(side=RIGHT, fill="y")
        self.table.bind("<<TreeviewSelect>>", self._on_select)

        det_fr = ttk.LabelFrame(self, text="Proposal Details: Historical Anchor vs Forecast Assumption")
        det_fr.pack(fill=X, padx=8, pady=4)
        self.detail_text = tk.Text(det_fr, height=5, font=("Consolas", 9), wrap="word")
        self.detail_text.pack(fill=BOTH, expand=True, padx=4, pady=4)

        btn_fr = ttk.Frame(self); btn_fr.pack(fill=X, padx=8, pady=6)
        ttk.Button(btn_fr, text="Accept selected", command=self._accept_selected).pack(side=LEFT, padx=3)
        ttk.Button(btn_fr, text="Reject selected", command=self._reject_selected).pack(side=LEFT, padx=3)
        ttk.Button(btn_fr, text="Accept all reviewed", command=self._accept_reviewed).pack(side=LEFT, padx=3)
        ttk.Button(btn_fr, text="Export proposals to TXT", command=self._export_txt).pack(side=LEFT, padx=8)
        ttk.Button(btn_fr, text="Apply proposals to Draft Plan", command=self._apply_to_plan).pack(side=RIGHT, padx=3)
        ttk.Button(btn_fr, text="Close", command=self.destroy).pack(side=RIGHT, padx=3)

    def _populate(self):
        for item in self.table.get_children(): self.table.delete(item)
        for p in self.proposals:
            val_str = f"{p.proposed_value} {p.unit}" if p.proposed_value is not None else "N/A"
            self.table.insert("", "end", iid=str(p.proposal_id), values=(
                p.field, p.historical_anchor, val_str, p.assumption_type.value, p.quality.value, p.approval_state.value
            ))

    def _on_select(self, _event=None):
        sel = self.table.selection()
        if not sel: return
        p_id = sel[0]; self.reviewed_ids.add(p_id)
        prop = next((p for p in self.proposals if str(p.proposal_id) == p_id), None)
        if not prop: return
        self.detail_text.delete("1.0", tk.END)
        dates_str = ", ".join(str(d) for d in prop.evidence_dates) or str(self.audit.as_of_date)
        ev_str = ", ".join(prop.evidence_ids) if prop.evidence_ids else "historical context"
        info = (f"Field: {prop.field}\n"
                f"Historical Anchor (Fact): {prop.historical_anchor}\n"
                f"Proposed FY2026 Assumption: {prop.proposed_value} {prop.unit}\n"
                f"Forecast Basis: {prop.assumption_type.value} | Classification: {prop.quality.value}\n"
                f"Evidence: {ev_str} ({dates_str})\n"
                f"Rationale: {prop.rationale}")
        if prop.missing_components:
            info += f"\nMissing persisted market/macro components: {', '.join(prop.missing_components)}"
        self.detail_text.insert(tk.END, info)

    def _accept_selected(self):
        sel = self.table.selection()
        if not sel: return
        for p in self.proposals:
            if str(p.proposal_id) in sel: p.approval_state = ApprovalState.ACCEPTED
        self._populate()

    def _reject_selected(self):
        sel = self.table.selection()
        if not sel: return
        for p in self.proposals:
            if str(p.proposal_id) in sel: p.approval_state = ApprovalState.REJECTED
        self._populate()

    def _accept_reviewed(self):
        if not self.reviewed_ids:
            messagebox.showinfo("Review Required", "Please click on proposals to review their rationale first.", parent=self); return
        for p in self.proposals:
            if str(p.proposal_id) in self.reviewed_ids: p.approval_state = ApprovalState.ACCEPTED
        self._populate()

    def _export_txt(self):
        path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text files", "*.txt")],
                                            initialfile=f"TRU_FY2026_HISTORICAL_ASSUMPTIONS_{self.audit.as_of_date}.txt")
        if not path: return
        try:
            content = export_proposals_to_txt(self.proposals, self.backtest.ticker, self.audit.as_of_date)
            with open(path, "w", encoding="utf-8") as f: f.write(content)
            messagebox.showinfo("Exported", f"Proposals exported to {path}.\nNote: Export does not imply acceptance.", parent=self)
        except Exception as e: messagebox.showerror("Export Failed", str(e), parent=self)

    def _apply_to_plan(self):
        non_rejected = [p for p in self.proposals if p.approval_state != ApprovalState.REJECTED]
        if not non_rejected:
            messagebox.showwarning("No Proposals", "All proposals are rejected.", parent=self); return
        assumptions = proposals_to_forecast_assumptions(non_rejected, self.plan, state=ApprovalState.PROPOSED)
        audit_records = create_proposal_audit_records(self.proposals, self.audit)
        updated_plan = attach_assistant_audit_to_plan(self.plan, self.audit, audit_records)
        prop_fields = {a.field for a in assumptions}
        updated_plan.assumptions = [a for a in updated_plan.assumptions if a.field not in prop_fields] + assumptions
        if self.on_applied: self.on_applied(updated_plan)
        messagebox.showinfo("Applied", f"Applied {len(assumptions)} proposals to draft plan as PROPOSED.\nAnalyst must explicitly review & approve before locking.", parent=self)
        self.destroy()
