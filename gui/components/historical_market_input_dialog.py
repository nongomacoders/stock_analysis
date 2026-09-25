"""Dialog for managing, previewing, and auditing historical market & macro inputs."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox, BOTH, X, LEFT, RIGHT, StringVar
from datetime import date
from decimal import Decimal
from modules.analysis.historical_market_inputs import (
    MarketConcept, InputScope, ProvenanceQuality, make_historical_market_input
)
from modules.data.historical_market_storage import (
    save_historical_market_input, batch_import_historical_market_inputs, list_historical_market_inputs
)
from modules.analysis.historical_wacc_resolver import resolve_historical_wacc, resolve_historical_macro

class HistoricalMarketInputDialog(tk.Toplevel):
    def __init__(self, parent, backtest, on_updated=None):
        super().__init__(parent)
        self.title(f"Historical Market & Macro Inputs — {backtest.ticker} (Cutoff: {backtest.as_of_date})")
        self.geometry("1020x640")
        self.transient(parent); self.grab_set()
        self.backtest = backtest; self.on_updated = on_updated
        self._build_ui(); self.refresh()

    def _build_ui(self):
        audit_fr = ttk.LabelFrame(self, text="Historical WACC & Macro Resolver Audit (Cutoff <= as-of-date)")
        audit_fr.pack(fill=X, padx=8, pady=4)
        self.audit_text = tk.Text(audit_fr, height=9, font=("Consolas", 9), wrap="word")
        self.audit_text.pack(fill=BOTH, expand=True, padx=4, pady=4)

        tree_fr = ttk.LabelFrame(self, text="Authoritative Historical Market Inputs (PostgreSQL)")
        tree_fr.pack(fill=BOTH, expand=True, padx=8, pady=4)
        cols = ("concept", "val", "obs_date", "avail_date", "lag", "provenance", "source", "ev_status")
        self.table = ttk.Treeview(tree_fr, columns=cols, show="headings", height=8)
        widths = (("concept", 150), ("val", 65), ("obs_date", 85), ("avail_date", 85),
                  ("lag", 50), ("provenance", 190), ("source", 180), ("ev_status", 140))
        for col, w in widths:
            self.table.heading(col, text=col.upper()); self.table.column(col, width=w)
        self.table.pack(side=LEFT, fill=BOTH, expand=True)
        sb = ttk.Scrollbar(tree_fr, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=sb.set); sb.pack(side=RIGHT, fill="y")

        btn_fr = ttk.Frame(self); btn_fr.pack(fill=X, padx=8, pady=6)
        ttk.Button(btn_fr, text="Add historical market input", command=self._add_input_prompt).pack(side=LEFT, padx=3)
        ttk.Button(btn_fr, text="Import TRU FY2025 Market Pack", command=self._preview_standard_pack).pack(side=LEFT, padx=6)
        ttk.Button(btn_fr, text="Refresh audit", command=self.refresh).pack(side=LEFT, padx=3)
        ttk.Button(btn_fr, text="Close", command=self.destroy).pack(side=RIGHT, padx=3)

    def refresh(self):
        for item in self.table.get_children(): self.table.delete(item)
        items = list_historical_market_inputs(max_available_date=self.backtest.as_of_date)
        for x in items:
            lag = (self.backtest.as_of_date - x.observation_date).days
            prov = x.provenance_quality.value.upper()
            ev_st = "RAW_PDF_STORED" if x.evidence_hash else "NO_RAW_EVIDENCE"
            self.table.insert("", "end", values=(
                x.concept.value, f"{x.value}%", str(x.observation_date), str(x.available_date),
                f"{lag}d", prov, x.provider, ev_st
            ))
        wacc_res = resolve_historical_wacc(self.backtest)
        macro_res = resolve_historical_macro(self.backtest.as_of_date)
        lines = [
            f"Backtest Cutoff: {self.backtest.as_of_date} | Ticker: {self.backtest.ticker}",
            f"Historical WACC Status : {wacc_res.status} " + (f"({wacc_res.calculated_wacc}%)" if wacc_res.calculated_wacc else f"- Missing: {', '.join(wacc_res.missing_components)}"),
            f"Methodological Status  : {wacc_res.methodological_status} (Quality: {wacc_res.evidence_quality})",
            "--------------------------------------------------------------------------------"
        ]
        for key in ("risk_free_rate", "equity_risk_premium", "beta", "cost_of_debt"):
            c = wacc_res.components.get(key)
            if c:
                lines.append(f"{key:22}: {c.value:>6}%  [{c.provenance:<28}] obs={c.observation_date} (lag={c.lag_days}d) src='{c.source}'")
            else: lines.append(f"{key:22}: MISSING")
        inf = macro_res.inflation_long_run; gdp = macro_res.nominal_gdp_growth_long_run
        if inf: lines.append(f"{'inflation_long_run':22}: {inf.value:>6}%  [{inf.provenance:<28}] obs={inf.observation_date} src='{inf.source}'")
        if gdp: lines.append(f"{'gdp_growth_long_run':22}: {gdp.value:>6}%  [{gdp.provenance:<28}] obs={gdp.observation_date} src='{gdp.source}'")
        for n in wacc_res.notes: lines.append(f"  Note: {n}")
        self.audit_text.delete("1.0", tk.END); self.audit_text.insert(tk.END, "\n".join(lines))
        if self.on_updated: self.on_updated()

    def _add_input_prompt(self):
        w = tk.Toplevel(self); w.title("Add Historical Market Input"); w.geometry("460x420"); w.grab_set()
        c_var = StringVar(value="risk_free_rate"); val_var = StringVar(value="10.25")
        obs_var = StringVar(value="2025-08-29"); av_var = StringVar(value="2025-08-29")
        src_var = StringVar(value="SARB / JSE"); meth_var = StringVar(value="R2030 bond yield (4.4Y tenor)")
        f = ttk.Frame(w, padding=8); f.pack(fill=BOTH, expand=True)
        concepts = [c.value for c in MarketConcept]
        for i, (lbl, var) in enumerate([("Concept:", c_var), ("Value (%):", val_var),
                                        ("Obs Date:", obs_var), ("Avail Date:", av_var),
                                        ("Source:", src_var), ("Methodology:", meth_var)]):
            ttk.Label(f, text=lbl).grid(row=i, column=0, sticky="w", pady=3)
            (ttk.Combobox(f, textvariable=var, values=concepts, width=28) if lbl == "Concept:" else
             ttk.Entry(f, textvariable=var, width=30)).grid(row=i, column=1, pady=3)
        def save():
            try:
                obs_d, av_d = date.fromisoformat(obs_var.get().strip()), date.fromisoformat(av_var.get().strip())
                val = Decimal(val_var.get().strip()); concept = MarketConcept(c_var.get().strip())
            except Exception as e: messagebox.showerror("Invalid Input", str(e), parent=w); return
            if av_d > self.backtest.as_of_date:
                messagebox.showerror("Cutoff Error", f"Available date {av_d} exceeds {self.backtest.as_of_date}", parent=w); return
            t_flag = self.backtest.ticker if concept in {MarketConcept.BETA, MarketConcept.COST_OF_DEBT} else None
            item = make_historical_market_input(concept, val, obs_d, av_d, src_var.get().strip(), ticker=t_flag,
                                               source_methodology=meth_var.get().strip(),
                                               provenance_quality=ProvenanceQuality.ANALYST_ENTERED_HISTORICAL_OBSERVATION)
            save_historical_market_input(item); w.destroy(); self.refresh()
        ttk.Button(f, text="Confirm & Save (Manual)", command=save).grid(row=7, column=1, pady=12, sticky="e")

    def _preview_standard_pack(self):
        pw = tk.Toplevel(self); pw.title("Preview TRU FY2025 Market Pack Import"); pw.geometry("820x370"); pw.grab_set()
        ttk.Label(pw, text="Audit Preview — Dated Historical Market Inputs (<= 2025-08-31)", font=("Segoe UI", 10, "bold")).pack(pady=6)
        ttk.Label(pw, text="⚠️ Note: Market inputs without raw PDFs are classified as MANUAL HISTORICAL INPUT.", foreground="#b35a00").pack(pady=2)
        cols = ("concept", "val", "source", "prov", "ev")
        tv = ttk.Treeview(pw, columns=cols, show="headings", height=6)
        for c, w, h in (("concept", 140), ("val", 65), ("source", 170), ("prov", 220), ("ev", 140)):
            tv.heading(c, text=c.upper()); tv.column(c, width=w)
        tv.pack(fill=BOTH, expand=True, padx=8, pady=4)
        pack_specs = [
            (MarketConcept.RISK_FREE_RATE, Decimal("10.25"), date(2025, 8, 29), date(2025, 8, 29), "SARB", "R2030 bond yield; 4.4Y tenor limitation", ProvenanceQuality.ANALYST_ENTERED_HISTORICAL_OBSERVATION, None, None, None),
            (MarketConcept.EQUITY_RISK_PREMIUM, Decimal("6.00"), date(2025, 6, 30), date(2025, 7, 5), "PwC SA Valuation Survey", "Midpoint consensus ERP", ProvenanceQuality.ANALYST_ENTERED_HISTORICAL_OBSERVATION, None, None, None),
            (MarketConcept.BETA, Decimal("0.92"), date(2025, 8, 29), date(2025, 8, 29), "Bloomberg", "2Y weekly levered beta", ProvenanceQuality.ANALYST_ENTERED_HISTORICAL_OBSERVATION, self.backtest.ticker, None, None),
            (MarketConcept.COST_OF_DEBT, Decimal("8.59"), date(2025, 6, 29), date(2025, 8, 28), "TRU FY2025 AFS Note 25.3.2", "Weighted pre-tax rate derived from Note 25.3.2: RCF 8.6%, Green loan 8.9%, Overdraft 8.5%", ProvenanceQuality.DERIVED_FROM_SOURCE_DOCUMENT, self.backtest.ticker, "hist:afs", "7e2389d7"),
            (MarketConcept.INFLATION_LONG_RUN, Decimal("4.50"), date(2025, 8, 15), date(2025, 8, 15), "SARB MPC", "Target midpoint 4.5%", ProvenanceQuality.ANALYST_ENTERED_HISTORICAL_OBSERVATION, None, None, None),
            (MarketConcept.NOMINAL_GDP_GROWTH_LONG_RUN, Decimal("6.00"), date(2025, 6, 30), date(2025, 7, 10), "BER Stellenbosch", "Macro forecast 6.0%", ProvenanceQuality.ANALYST_ENTERED_HISTORICAL_OBSERVATION, None, None, None)
        ]
        for c, val, _, _, src, _, prov, _, doc_id, _ in pack_specs:
            tv.insert("", "end", values=(c.value, f"{val}%", src, prov.value.upper(), "RAW_AFS_PDF_LINKED" if doc_id else "NO_RAW_FILE (MANUAL)"))
        def do_import():
            items = [make_historical_market_input(c, val, od, ad, src, ticker=tkr, source_methodology=meth, provenance_quality=prov, source_document_id=doc, evidence_hash=eh, batch_id="tru_pack_20250831")
                     for c, val, od, ad, src, meth, prov, tkr, doc, eh in pack_specs]
            batch_import_historical_market_inputs(items, batch_id="tru_pack_20250831")
            pw.destroy(); self.refresh()
            messagebox.showinfo("Imported", "Historical market pack persisted to PostgreSQL with immutable provenance classifications.", parent=self)
        btn_f = ttk.Frame(pw); btn_f.pack(fill=X, padx=8, pady=6)
        ttk.Button(btn_f, text="Confirm & Persist to PostgreSQL", command=do_import).pack(side=RIGHT, padx=4)
        ttk.Button(btn_f, text="Cancel", command=pw.destroy).pack(side=RIGHT, padx=4)
