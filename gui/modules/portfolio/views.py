import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Dict, Any, List

class LoginFrame(tk.Frame):
    def __init__(self, parent, on_login: Callable[[str], None], on_create: Callable[[str, float], None]):
        super().__init__(parent)
        self.on_login = on_login
        self.on_create = on_create
        tk.Label(self, text="Portfolio Disciplinarian", font=("Arial", 18, "bold")).pack(pady=20)
        tk.Label(self, text="Secret Portfolio Name:").pack(pady=5)
        self.name_var = tk.StringVar(); self.entry = tk.Entry(self, textvariable=self.name_var, width=30)
        self.entry.pack(pady=5); self.entry.bind("<Return>", lambda e: self.handle_continue())
        tk.Button(self, text="Continue", command=self.handle_continue, bg="#4CAF50", fg="white", width=15).pack(pady=20)

    def handle_continue(self):
        name = self.name_var.get().strip()
        if name: self.on_login(name)
        else: messagebox.showwarning("Input Error", "Please enter a portfolio name.")

    def prompt_create(self, name: str):
        if messagebox.askyesno("New Portfolio", f"Portfolio '{name}' does not exist. Create it?"):
            dialog = tk.Toplevel(self); dialog.title("Initial Deposit")
            tk.Label(dialog, text=f"Initial Cash Deposit for {name}:").pack(padx=20, pady=10)
            val_var = tk.DoubleVar(value=10000.0); tk.Entry(dialog, textvariable=val_var).pack(padx=20, pady=5)
            def commit():
                try:
                    deposit = val_var.get()
                    if deposit <= 0: raise ValueError
                    dialog.destroy(); self.on_create(name, deposit)
                except Exception: messagebox.showerror("Error", "Please enter a valid positive number.")
            tk.Button(dialog, text="Create", command=commit).pack(pady=10)

class DashboardFrame(tk.Frame):
    def __init__(self, parent, portfolio_name: str, metrics: Dict[str, Any], on_new_transaction: Callable[[], None], on_show_history: Callable[[], None], on_logout: Callable[[], None]):
        super().__init__(parent)
        header = tk.Frame(self); header.pack(fill="x", padx=10, pady=10)
        tk.Label(header, text=f"Dashboard: {portfolio_name}", font=("Arial", 14, "bold")).pack(side="left")
        btn_bar = tk.Frame(header); btn_bar.pack(side="right")
        tk.Button(btn_bar, text="History", command=on_show_history).pack(side="left", padx=5)
        tk.Button(btn_bar, text="Logout", command=on_logout).pack(side="left", padx=5)
        
        metrics_box = tk.LabelFrame(self, text="Discipline Metrics", padx=10, pady=10); metrics_box.pack(fill="x", padx=10, pady=5)
        tk.Label(metrics_box, text=f"TPV: R{metrics['TPV']:,.2f}", font=("Arial", 12)).grid(row=0, column=0, sticky="w", padx=20)
        tk.Label(metrics_box, text=f"Cash Reserve: {metrics['cash_reserve_pct']:.1f}%", fg="green" if metrics["rule1_pass"] else "red", font=("Arial", 10, "bold")).grid(row=0, column=1, padx=20)
        tk.Label(metrics_box, text=f"Max Concentration: {metrics['max_concentration_pct']:.1f}% ({metrics['concentrated_ticker']})", fg="green" if metrics["rule2_pass"] else "red", font=("Arial", 10, "bold")).grid(row=0, column=2, padx=20)
        if metrics["data_stale"]: tk.Label(self, text="⚠️ DATA STALE: Using Buy Price for some valuations", fg="orange").pack()

        self.tree = ttk.Treeview(self, columns=("Ticker", "Qty", "Buy P", "Mkt P", "Valuation", "Profit", "Profit %", "%"), show="headings")
        for col in ("Ticker", "Qty", "Buy P", "Mkt P", "Valuation", "Profit", "Profit %", "%"):
            self.tree.heading(col, text=col); self.tree.column(col, width=85, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=10, pady=10)
        self.tree.tag_configure("gain", foreground="green"); self.tree.tag_configure("loss", foreground="red")
        
        for h in metrics["holdings"]:
            tag = "gain" if h["ticker"] != "ZAR_CASH" and h["profit_zar"] >= 0 else "loss" if h["ticker"] != "ZAR_CASH" else ""
            self.tree.insert("", "end", values=(h["ticker"], f"{h['quantity']:,.2f}", f"R{h['average_buy_price']:,.2f}", f"R{h['effective_price']:,.2f}", f"R{h['valuation']:,.2f}", f"R{h['profit_zar']:,.2f}", f"{h['profit_pct']:.1f}%", f"{h['percent']:.1f}%"), tags=(tag,))
        tk.Button(self, text="New Transaction", command=on_new_transaction, bg="#2196F3", fg="white", height=2).pack(pady=10)

class TransactionWindow(tk.Toplevel):
    def __init__(self, parent, metrics: Dict[str, Any], on_commit: Callable[[str, str, float, float], None], discipline_check_func: Callable):
        super().__init__(parent); self.title("New Transaction"); self.metrics = metrics; self.on_commit = on_commit; self.check_func = discipline_check_func
        tk.Label(self, text="Record Transaction", font=("Arial", 12, "bold")).pack(pady=10)
        form = tk.Frame(self); form.pack(padx=20, pady=10)
        tk.Label(form, text="Type:").grid(row=0, column=0, sticky="e")
        self.type_var = tk.StringVar(value="BUY"); ttk.Combobox(form, textvariable=self.type_var, values=["BUY", "SELL"], state="readonly").grid(row=0, column=1)
        tk.Label(form, text="Ticker:").grid(row=1, column=0, sticky="e")
        self.ticker_var = tk.StringVar(); tk.Entry(form, textvariable=self.ticker_var).grid(row=1, column=1)
        tk.Label(form, text="Quantity:").grid(row=2, column=0, sticky="e")
        self.qty_var = tk.DoubleVar(); tk.Entry(form, textvariable=self.qty_var).grid(row=2, column=1)
        tk.Label(form, text="Price:").grid(row=3, column=0, sticky="e")
        self.price_var = tk.DoubleVar(); tk.Entry(form, textvariable=self.price_var).grid(row=3, column=1)
        self.warn_lb = tk.Label(self, text="", fg="red", wraplength=300); self.warn_lb.pack(pady=5)
        self.commit_btn = tk.Button(self, text="Commit Transaction", command=self.handle_commit, bg="#4CAF50", fg="white", state="disabled")
        self.commit_btn.pack(pady=10)
        for var in [self.type_var, self.ticker_var, self.qty_var, self.price_var]: var.trace_add("write", lambda *a: self.validate())

    def validate(self):
        try:
            t, ty, q, p = self.ticker_var.get().upper().strip(), self.type_var.get(), self.qty_var.get(), self.price_var.get()
            if not t or q <= 0 or p <= 0: self.commit_btn.config(state="disabled"); return
            
            is_blocked, warns = self.check_func(self.metrics, t, ty, q, p)
            self.warn_lb.config(text="\n".join(warns), fg="red")
            self.commit_btn.config(state="disabled" if is_blocked else "normal")
        except Exception: self.commit_btn.config(state="disabled")

    def handle_commit(self):
        self.on_commit(self.ticker_var.get().upper().strip(), self.type_var.get(), self.qty_var.get(), self.price_var.get()); self.destroy()

class TransactionHistoryWindow(tk.Toplevel):
    def __init__(self, parent, transactions: List[Dict[str, Any]], on_delete: Callable[[int], None], on_edit: Callable[[Dict[str, Any]], None]):
        super().__init__(parent); self.title("Transaction History"); self.geometry("700x450"); self.on_delete = on_delete; self.on_edit = on_edit
        self.tree = ttk.Treeview(self, columns=("ID", "Date", "Ticker", "Type", "Qty", "Price"), show="headings")
        for col in ("ID", "Date", "Ticker", "Type", "Qty", "Price"): self.tree.heading(col, text=col); self.tree.column(col, width=90, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=10, pady=5)
        for tx in transactions: self.tree.insert("", "end", values=(tx["id"], tx["date"].strftime("%Y-%m-%d %H:%M"), tx["ticker"], tx["type"], f"{tx['quantity']:.2f}", f"{tx['price']:.2f}"))
        btn_frame = tk.Frame(self); btn_frame.pack(fill="x", pady=10)
        tk.Button(btn_frame, text="Edit Selected", command=self.handle_edit, bg="#2196F3", fg="white").pack(side="left", expand=True, padx=5)
        tk.Button(btn_frame, text="Delete Selected", command=self.handle_delete, bg="#f44336", fg="white").pack(side="left", expand=True, padx=5)

    def handle_delete(self):
        sel = self.tree.selection()
        if sel:
            tx_id = self.tree.item(sel[0])['values'][0]
            if messagebox.askyesno("Confirm", f"Delete transaction #{tx_id}?"): self.destroy(); self.on_delete(tx_id)

    def handle_edit(self):
        sel = self.tree.selection()
        if sel:
            vals = self.tree.item(sel[0])['values']
            tx = {"id": vals[0], "ticker": vals[2], "type": vals[3], "quantity": float(vals[4]), "price": float(vals[5])}
            self.destroy(); self.on_edit(tx)
