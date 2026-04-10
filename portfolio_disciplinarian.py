import sys
import os
import tkinter as tk
from tkinter import messagebox

# Add the project directory and gui directory to sys.path for imports
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), 'gui'))

from gui.modules.portfolio import database as db
from gui.modules.portfolio import discipline
from gui.modules.portfolio import views

class PortfolioApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Portfolio Disciplinarian")
        self.root.geometry("850x650")
        self.current_frame = None
        self.portfolio_id = None
        self.portfolio_name = None
        self.metrics = None
        self.show_login()

    def clear_frame(self):
        if self.current_frame: self.current_frame.destroy()

    def show_login(self):
        self.clear_frame()
        self.current_frame = views.LoginFrame(self.root, on_login=self.handle_login, on_create=self.handle_create)
        self.current_frame.pack(expand=True, fill="both")

    def handle_login(self, name: str):
        pid = db.get_portfolio_by_name(name)
        if pid:
            self.portfolio_id, self.portfolio_name = pid, name
            self.refresh_dashboard()
        else: self.current_frame.prompt_create(name)

    def handle_create(self, name: str, deposit: float):
        try:
            self.portfolio_id = db.create_portfolio(name, deposit)
            self.portfolio_name = name
            messagebox.showinfo("Success", f"Portfolio {name} created with R{deposit:,.2f} cash.")
            self.refresh_dashboard()
        except Exception as e: messagebox.showerror("Error", f"Failed to create: {e}")

    def refresh_dashboard(self):
        holdings = db.get_portfolio_holdings(self.portfolio_id)
        self.metrics = discipline.calculate_portfolio_metrics(holdings)
        self.clear_frame()
        self.current_frame = views.DashboardFrame(self.root, portfolio_name=self.portfolio_name, metrics=self.metrics, on_new_transaction=self.show_transaction, on_show_history=self.show_history, on_logout=self.show_login)
        self.current_frame.pack(expand=True, fill="both")

    def show_history(self):
        txs = db.get_portfolio_transactions(self.portfolio_id)
        views.TransactionHistoryWindow(self.root, transactions=txs, on_delete=self.handle_delete_transaction, on_edit=self.show_edit_window)

    def handle_delete_transaction(self, tx_id: int):
        try:
            db.delete_portfolio_transaction(tx_id, self.portfolio_id)
            messagebox.showinfo("Success", "Transaction deleted. Portfolio rebuilt.")
            self.refresh_dashboard()
        except Exception as e: messagebox.showerror("Error", f"Failed: {e}")

    def show_edit_window(self, tx: dict):
        # We can reuse the TransactionWindow logic for editing by passing a different commit handler
        edit_win = views.TransactionWindow(self.root, metrics=self.metrics, on_commit=lambda t, ty, q, p: self.handle_edit_commit(tx["id"], t, ty, q, p), discipline_check_func=discipline.check_transaction_discipline)
        edit_win.title(f"Edit Transaction #{tx['id']}")
        edit_win.ticker_var.set(tx["ticker"])
        edit_win.type_var.set(tx["type"])
        edit_win.qty_var.set(tx["quantity"])
        edit_win.price_var.set(tx["price"])

    def handle_edit_commit(self, tx_id: int, ticker: str, tx_type: str, qty: float, price: float):
        try:
            db.update_portfolio_transaction(tx_id, self.portfolio_id, ticker, tx_type, qty, price)
            messagebox.showinfo("Success", "Transaction updated. Portfolio rebuilt.")
            self.refresh_dashboard()
        except Exception as e: messagebox.showerror("Error", f"Failed: {e}")

    def show_transaction(self):
        views.TransactionWindow(self.root, metrics=self.metrics, on_commit=self.handle_transaction_commit, discipline_check_func=discipline.check_transaction_discipline)

    def handle_transaction_commit(self, ticker: str, tx_type: str, qty: float, price: float):
        try:
            db.record_transaction(self.portfolio_id, ticker, tx_type, qty, price)
            messagebox.showinfo("Success", f"Recorded {tx_type} for {ticker}")
            self.refresh_dashboard()
        except Exception as e: messagebox.showerror("Error", f"Failed: {e}")

if __name__ == "__main__":
    root = tk.Tk(); app = PortfolioApp(root); root.mainloop()
