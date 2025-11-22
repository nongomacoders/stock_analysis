import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import messagebox, simpledialog
import psycopg2
import psycopg2.extras
import yfinance as yf
import pandas as pd
from decimal import Decimal
import threading
from datetime import datetime

# Import database utils
from database_utils import (
    get_portfolio_holdings,
    get_portfolio_transactions,
    add_transaction,
    delete_transaction,
    convert_yf_price_to_cents,
    fetch_all_tickers
)

class PortfolioTab(ttk.Frame):
    """
    Tab for managing and viewing stock portfolios.
    """
    def __init__(self, parent, db_config, log_error_func):
        super().__init__(parent, padding=10)
        self.db_config = db_config
        self.log_error = log_error_func
        
        # Variables
        self.portfolio_id = 1 # Default to ID 1 for now (Single portfolio support)
        self.total_value_var = tk.StringVar(value="R 0.00")
        self.total_cost_var = tk.StringVar(value="R 0.00")
        self.unrealized_pl_var = tk.StringVar(value="R 0.00 (0.00%)")
        self.cash_var = tk.StringVar(value="R 0.00") # Placeholder for future cash tracking

        self.create_widgets()
        self.load_portfolio_data()

    def create_widgets(self):
        """Creates the UI layout."""
        
        # --- Top Panel: Summary ---
        summary_frame = ttk.Labelframe(self, text="Portfolio Summary", padding=10)
        summary_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Grid layout for summary stats
        ttk.Label(summary_frame, text="Total Value:", font=("Helvetica", 12)).grid(row=0, column=0, padx=10, pady=5, sticky=tk.W)
        ttk.Label(summary_frame, textvariable=self.total_value_var, font=("Helvetica", 14, "bold"), bootstyle="success").grid(row=0, column=1, padx=10, pady=5, sticky=tk.W)

        ttk.Label(summary_frame, text="Total Cost:", font=("Helvetica", 10)).grid(row=1, column=0, padx=10, pady=5, sticky=tk.W)
        ttk.Label(summary_frame, textvariable=self.total_cost_var, font=("Helvetica", 10)).grid(row=1, column=1, padx=10, pady=5, sticky=tk.W)

        ttk.Label(summary_frame, text="Unrealized P/L:", font=("Helvetica", 12)).grid(row=0, column=2, padx=10, pady=5, sticky=tk.W)
        self.pl_label = ttk.Label(summary_frame, textvariable=self.unrealized_pl_var, font=("Helvetica", 14, "bold"))
        self.pl_label.grid(row=0, column=3, padx=10, pady=5, sticky=tk.W)

        # --- Middle Panel: Holdings Table ---
        holdings_frame = ttk.Labelframe(self, text="Current Holdings", padding=10)
        holdings_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Toolbar
        toolbar = ttk.Frame(holdings_frame)
        toolbar.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Button(toolbar, text="Refresh Prices", command=self.refresh_prices, bootstyle="info-outline").pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="Add Transaction", command=self.open_add_transaction_dialog, bootstyle="success").pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="AI Analyze Portfolio", command=self.ai_analyze_portfolio, bootstyle="warning-outline").pack(side=tk.RIGHT, padx=5)

        # Treeview
        cols = ("Ticker", "Qty", "Avg Price", "Current Price", "Market Value", "Gain/Loss", "Change %")
        self.holdings_tree = ttk.Treeview(holdings_frame, columns=cols, show="headings", height=10)
        
        for col in cols:
            self.holdings_tree.heading(col, text=col)
            self.holdings_tree.column(col, width=100, anchor=tk.E) # Align numbers to right
        self.holdings_tree.column("Ticker", anchor=tk.W) # Ticker left aligned

        scrollbar = ttk.Scrollbar(holdings_frame, orient=tk.VERTICAL, command=self.holdings_tree.yview)
        self.holdings_tree.configure(yscroll=scrollbar.set)
        
        self.holdings_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # --- Bottom Panel: Transaction History ---
        history_frame = ttk.Labelframe(self, text="Transaction History", padding=10)
        history_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 0))

        # History Toolbar
        h_toolbar = ttk.Frame(history_frame)
        h_toolbar.pack(fill=tk.X, pady=(0, 5))
        ttk.Button(h_toolbar, text="Delete Transaction", command=self.delete_selected_transaction, bootstyle="danger-outline").pack(side=tk.LEFT, padx=5)

        h_cols = ("ID", "Date", "Ticker", "Type", "Qty", "Price", "Fees", "Notes")
        self.history_tree = ttk.Treeview(history_frame, columns=h_cols, show="headings", height=6)
        
        # Configure ID column to be hidden or small
        self.history_tree.heading("ID", text="ID")
        self.history_tree.column("ID", width=0, stretch=False)

        for col in h_cols[1:]: # Skip ID for heading loop
            self.history_tree.heading(col, text=col)
            self.history_tree.column(col, width=80)
        
        h_scroll = ttk.Scrollbar(history_frame, orient=tk.VERTICAL, command=self.history_tree.yview)
        self.history_tree.configure(yscroll=h_scroll.set)
        
        self.history_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        h_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def load_portfolio_data(self):
        """Fetches holdings and transactions from DB."""
        # 1. Load Holdings
        holdings = get_portfolio_holdings(self.db_config, self.portfolio_id)
        self.holdings_data = holdings # Store for price updates
        self.update_holdings_table(holdings)

        # 2. Load Transactions
        transactions = get_portfolio_transactions(self.db_config, self.portfolio_id)
        self.update_history_table(transactions)

        # 3. Calculate Totals (Initial, without live prices)
        self.calculate_totals(holdings)

    def update_holdings_table(self, holdings, current_prices=None):
        """Updates the holdings treeview."""
        for item in self.holdings_tree.get_children():
            self.holdings_tree.delete(item)

        total_value = 0.0
        total_cost = 0.0

        for h in holdings:
            ticker = h['ticker']
            qty = float(h['quantity'])
            avg_price = float(h['average_buy_price'])
            
            cost_basis = qty * avg_price
            total_cost += cost_basis

            current_price = avg_price # Default to cost if no live price
            if current_prices and ticker in current_prices:
                current_price = current_prices[ticker]
            
            market_value = qty * current_price
            total_value += market_value
            
            gain_loss = market_value - cost_basis
            gain_loss_percent = (gain_loss / cost_basis * 100) if cost_basis > 0 else 0.0

            # Format for display
            # Prices in Cents in DB, usually displayed in Rands for user convenience? 
            # The app seems to use Cents for JSE. Let's stick to Cents or convert to Rands?
            # Existing app uses Cents mostly but displays Rands sometimes. 
            # Let's display in Rands (Price / 100) for readability in Portfolio.
            
            avg_price_r = avg_price / 100.0
            current_price_r = current_price / 100.0
            market_value_r = market_value / 100.0
            gain_loss_r = gain_loss / 100.0

            values = (
                ticker,
                f"{qty:.0f}",
                f"R {avg_price_r:.2f}",
                f"R {current_price_r:.2f}",
                f"R {market_value_r:.2f}",
                f"R {gain_loss_r:.2f}",
                f"{gain_loss_percent:.2f}%"
            )
            
            # Color coding
            tag = "profit" if gain_loss >= 0 else "loss"
            self.holdings_tree.insert("", tk.END, values=values, tags=(tag,))

        self.holdings_tree.tag_configure("profit", foreground="lightgreen")
        self.holdings_tree.tag_configure("loss", foreground="salmon")

        # Update Summary
        self.total_value_var.set(f"R {total_value/100:,.2f}")
        self.total_cost_var.set(f"R {total_cost/100:,.2f}")
        
        unrealized = total_value - total_cost
        unrealized_pct = (unrealized / total_cost * 100) if total_cost > 0 else 0.0
        self.unrealized_pl_var.set(f"R {unrealized/100:,.2f} ({unrealized_pct:.2f}%)")
        
        if unrealized >= 0:
            self.pl_label.configure(foreground="lightgreen")
        else:
            self.pl_label.configure(foreground="salmon")

    def update_history_table(self, transactions):
        """Updates the transaction history treeview."""
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)

        for t in transactions:
            # t is a RealDictRow
            date_str = t['transaction_date'].strftime("%Y-%m-%d") if t['transaction_date'] else ""
            price_r = float(t['price']) / 100.0
            fees_r = float(t['fees']) / 100.0
            
            values = (
                t['id'], # Hidden ID column
                date_str,
                t['ticker'],
                t['transaction_type'],
                f"{t['quantity']:.0f}",
                f"R {price_r:.2f}",
                f"R {fees_r:.2f}",
                t['notes']
            )
            self.history_tree.insert("", tk.END, values=values)

    def delete_selected_transaction(self):
        """Deletes the selected transaction."""
        selected_item = self.history_tree.selection()
        if not selected_item:
            messagebox.showwarning("Selection Error", "Please select a transaction to delete.")
            return

        # Get transaction ID from the hidden first column
        item_values = self.history_tree.item(selected_item, "values")
        transaction_id = item_values[0]
        ticker = item_values[2]
        t_type = item_values[3]
        qty = item_values[4]

        confirm = messagebox.askyesno(
            "Confirm Delete", 
            f"Are you sure you want to delete this transaction?\n\n{t_type} {qty} {ticker}\n\nThis will recalculate your entire portfolio history."
        )
        
        if confirm:
            if delete_transaction(self.db_config, transaction_id, self.portfolio_id):
                messagebox.showinfo("Success", "Transaction deleted and portfolio recalculated.")
                self.load_portfolio_data()
            else:
                messagebox.showerror("Error", "Failed to delete transaction.")

    def calculate_totals(self, holdings):
        """Helper to update totals without full table refresh if needed."""
        # Already handled in update_holdings_table
        pass

    def refresh_prices(self):
        """Fetches live prices for all holdings."""
        threading.Thread(target=self._fetch_prices_thread, daemon=True).start()

    def _fetch_prices_thread(self):
        try:
            tickers = [h['ticker'] for h in self.holdings_data]
            if not tickers:
                return

            # Fetch data
            # Using yfinance to get current price. 
            # Note: JSE tickers in yfinance are usually "TICKER.JO"
            
            data = yf.download(tickers, period="1d", progress=False)['Close']
            
            current_prices = {}
            
            # Handle single ticker vs multiple tickers result structure
            if len(tickers) == 1:
                # data is a Series
                price = data.iloc[-1]
                current_prices[tickers[0]] = convert_yf_price_to_cents(price)
            else:
                # data is a DataFrame
                for ticker in tickers:
                    try:
                        price = data[ticker].iloc[-1]
                        current_prices[ticker] = convert_yf_price_to_cents(price)
                    except Exception:
                        pass # Price not found
            
            # Update UI on main thread
            self.after(0, lambda: self.update_holdings_table(self.holdings_data, current_prices))
            
        except Exception as e:
            self.log_error("Price Fetch Error", f"Failed to fetch prices: {e}")

    def open_add_transaction_dialog(self):
        """Opens a custom dialog to add a transaction."""
        dialog = tk.Toplevel(self)
        dialog.title("Add Transaction")
        dialog.geometry("300x500")
        
        ttk.Label(dialog, text="Ticker:").pack(pady=5)
        ticker_var = tk.StringVar()
        
        # --- CHANGED: Use Combobox populated from DB ---
        tickers = fetch_all_tickers(self.db_config)
        ticker_combo = ttk.Combobox(dialog, textvariable=ticker_var, values=tickers)
        ticker_combo.pack(pady=5)
        # -----------------------------------------------
        
        ttk.Label(dialog, text="Type:").pack(pady=5)
        type_var = tk.StringVar(value="BUY")
        ttk.Combobox(dialog, textvariable=type_var, values=["BUY", "SELL"], state="readonly").pack(pady=5)
        
        ttk.Label(dialog, text="Quantity:").pack(pady=5)
        qty_var = tk.DoubleVar()
        ttk.Entry(dialog, textvariable=qty_var).pack(pady=5)
        
        ttk.Label(dialog, text="Price (Cents):").pack(pady=5)
        price_var = tk.IntVar()
        ttk.Entry(dialog, textvariable=price_var).pack(pady=5)
        
        ttk.Label(dialog, text="Fees (Cents):").pack(pady=5)
        fees_var = tk.IntVar(value=0)
        ttk.Entry(dialog, textvariable=fees_var).pack(pady=5)

        ttk.Label(dialog, text="Date:").pack(pady=5)
        date_entry = ttk.DateEntry(dialog, dateformat="%Y-%m-%d")
        date_entry.pack(pady=5)

        def save():
            ticker = ticker_var.get().upper()
            if not ticker.endswith(".JO"): # Auto-append .JO if missing (assuming JSE)
                ticker += ".JO"
                
            t_type = type_var.get()
            qty = qty_var.get()
            
            # Input is now directly in Cents
            price_c = price_var.get()
            fees_c = fees_var.get()
            
            t_date = date_entry.entry.get()

            if add_transaction(self.db_config, self.portfolio_id, ticker, t_type, qty, price_c, fees_c, notes="", transaction_date=t_date):
                messagebox.showinfo("Success", "Transaction added.")
                dialog.destroy()
                self.load_portfolio_data()
            else:
                messagebox.showerror("Error", "Failed to add transaction.")

        ttk.Button(dialog, text="Save", command=save, bootstyle="success").pack(pady=20)

    def ai_analyze_portfolio(self):
        """Placeholder for AI Analysis."""
        messagebox.showinfo("AI Analysis", "AI Portfolio Analysis feature coming soon!\nThis will analyze your diversification, risk, and suggest rebalancing.")
