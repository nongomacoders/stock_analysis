"""Assumption entry and TXT import form for Historical ForecastPlans."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, StringVar, X, LEFT
from modules.analysis.historical_forecast_txt import ALLOWED_HISTORICAL_FIELDS

class HistoricalAssumptionForm(ttk.LabelFrame):
    def __init__(self, parent, on_add, on_import):
        super().__init__(parent, text="Assumption Entry / Import (2025-08-31 context)")
        self.on_add = on_add
        self.on_import = on_import
        self._build()

    def _build(self):
        r1 = ttk.Frame(self); r1.pack(fill=X, pady=2)
        ttk.Label(r1, text="Field:").pack(side=LEFT)
        self.field_var = StringVar()
        ttk.Combobox(r1, textvariable=self.field_var, values=sorted(ALLOWED_HISTORICAL_FIELDS), width=24, state="readonly").pack(side=LEFT, padx=3)
        ttk.Label(r1, text="Value:").pack(side=LEFT, padx=3)
        self.val_var = StringVar(); ttk.Entry(r1, textvariable=self.val_var, width=12).pack(side=LEFT)
        ttk.Label(r1, text="Unit:").pack(side=LEFT, padx=3)
        self.unit_var = StringVar(value="percentage"); ttk.Entry(r1, textvariable=self.unit_var, width=10).pack(side=LEFT)
        r2 = ttk.Frame(self); r2.pack(fill=X, pady=2)
        ttk.Label(r2, text="Rationale:").pack(side=LEFT)
        self.rat_var = StringVar(); ttk.Entry(r2, textvariable=self.rat_var, width=35).pack(side=LEFT, padx=3)
        ttk.Label(r2, text="Analyst:").pack(side=LEFT, padx=3)
        self.analyst_var = StringVar(value="analyst"); ttk.Entry(r2, textvariable=self.analyst_var, width=10).pack(side=LEFT)
        ttk.Button(r2, text="Add proposed assumption", command=self.on_add).pack(side=LEFT, padx=4)
        ttk.Button(r2, text="Import from TXT", command=self.on_import).pack(side=LEFT, padx=3)

    def get_values(self):
        return {
            "field": self.field_var.get().strip(), "value": self.val_var.get().strip(),
            "unit": self.unit_var.get().strip() or "percentage", "rationale": self.rat_var.get().strip(),
            "analyst": self.analyst_var.get().strip() or "analyst",
        }
