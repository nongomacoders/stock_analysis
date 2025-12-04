import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import LEFT, BOTH
from typing import Callable, List, Dict


class PortfolioListWidget(ttk.Frame):
    def __init__(self, parent, select_callback: Callable = None, **kwargs):
        super().__init__(parent, **kwargs)
        ttk.Label(self, text="Portfolios", font=(None, 12, "bold")).pack(anchor="w")
        self.listbox = tk.Listbox(self, height=24, width=36)
        self.listbox.pack(fill=BOTH, expand=False)
        self.select_callback = select_callback
        if select_callback:
            self.listbox.bind("<<ListboxSelect>>", select_callback)

    def set_items(self, items: List[Dict]):
        self.listbox.delete(0, tk.END)
        for p in items:
            self.listbox.insert(tk.END, f"{p['id']} - {p['name']}")

    def bind_select(self, callback: Callable):
        self.select_callback = callback
        self.listbox.bind("<<ListboxSelect>>", callback)

    def get_selected(self):
        sel = self.listbox.curselection()
        if not sel:
            return None
        return self.listbox.get(sel[0])

    def auto_select_first(self):
        if self.listbox.size() > 0:
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(0)
