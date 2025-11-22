import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
import psycopg2
from decimal import Decimal, InvalidOperation
from database_utils import fetch_all_tickers

class EarningsTab(ttk.Frame):
    """
    This class represents the "Earnings History" tab, for
    manually entering historical HEPS data.
    """

    def __init__(self, parent, db_config, log_error_func):
        super().__init__(parent, padding=10)

        self.db_config = db_config
        self.log_error = log_error_func
        self.selected_earnings_id = None  # Track which entry is being edited

        # --- New: Placeholder logic ---
        self.style = ttk.Style()
        self.style.configure("Placeholder.TEntry", foreground="grey")
        self.placeholder_period = "e.g., FY 2024 or H1 2025"
        self.placeholder_date = "YYYY-MM-DD"
        # --- End New ---

        self.create_widgets()
        self.load_stock_list()
        self.clear_form()  # Set initial placeholders

    def create_widgets(self):
        """Creates the main GUI layout for this tab."""

        # --- Create the two-panel layout ---
        self.paned_window = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.paned_window.pack(expand=True, fill="both")

        # --- Left Panel: Stock List ---
        left_panel = ttk.Frame(self.paned_window, padding=5)
        self.paned_window.add(left_panel, weight=1)

        # Treeview for stock list
        cols = ("ticker",)
        self.stock_tree = ttk.Treeview(left_panel, columns=cols, show="headings")
        self.stock_tree.heading("ticker", text="Ticker")
        self.stock_tree.column("ticker", width=150)

        # Scrollbar
        scrollbar = ttk.Scrollbar(
            left_panel, orient=tk.VERTICAL, command=self.stock_tree.yview
        )
        self.stock_tree.configure(yscroll=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.stock_tree.pack(expand=True, fill="both")

        self.stock_tree.bind("<<TreeviewSelect>>", self.on_stock_select)

        # --- Right Panel: Earnings Data ---
        self.right_panel = ttk.Frame(self.paned_window, padding=10)
        self.paned_window.add(self.right_panel, weight=3)  # 'weight=3' makes it larger

        # --- Existing Earnings Table ---
        history_frame = ttk.LabelFrame(
            self.right_panel, text="Existing Earnings History", padding=15
        )
        history_frame.pack(expand=True, fill="both", pady=(0, 10))

        history_cols = ("earnings_id", "period", "results_date", "heps", "notes")
        self.earnings_tree = ttk.Treeview(
            history_frame, columns=history_cols, show="headings"
        )

        self.earnings_tree.heading("period", text="Period")
        self.earnings_tree.heading("results_date", text="Results Date")
        self.earnings_tree.heading("heps", text="HEPS (Cents)")
        self.earnings_tree.heading("notes", text="Notes")

        self.earnings_tree.column(
            "earnings_id", width=0, stretch=tk.NO
        )  # Hide the ID column
        self.earnings_tree.column("period", width=80, stretch=tk.NO)
        self.earnings_tree.column("results_date", width=100, stretch=tk.NO)
        self.earnings_tree.column("heps", width=100, stretch=tk.NO)
        self.earnings_tree.column("notes", width=200)

        history_scrollbar = ttk.Scrollbar(
            history_frame, orient=tk.VERTICAL, command=self.earnings_tree.yview
        )
        self.earnings_tree.configure(yscroll=history_scrollbar.set)

        history_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.earnings_tree.pack(expand=True, fill="both")

        self.earnings_tree.bind("<<TreeviewSelect>>", self.on_earnings_select)

        # Create a LabelFrame for the inputs
        input_frame = ttk.LabelFrame(
            self.right_panel, text="Add/Edit Earnings", padding=15
        )
        input_frame.pack(fill=tk.X, pady=5)

        # Ticker
        ttk.Label(input_frame, text="Ticker:").grid(
            row=0, column=0, padx=5, pady=5, sticky=tk.W
        )
        self.ticker_var = tk.StringVar()
        self.ticker_entry = ttk.Entry(
            input_frame, textvariable=self.ticker_var, state="readonly", width=40
        )
        self.ticker_entry.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)

        # Period
        ttk.Label(input_frame, text="Period:").grid(
            row=1, column=0, padx=5, pady=5, sticky=tk.W
        )
        self.period_var = tk.StringVar()
        self.period_entry = ttk.Entry(
            input_frame, textvariable=self.period_var, width=40
        )
        self.period_entry.grid(row=1, column=1, padx=5, pady=5, sticky=tk.W)

        # --- New: Bindings ---
        self.period_entry.bind("<FocusIn>", self.on_period_focus_in)
        self.period_entry.bind("<FocusOut>", self.on_period_focus_out)

        # Results Date
        ttk.Label(input_frame, text="Results Date:").grid(
            row=2, column=0, padx=5, pady=5, sticky=tk.W
        )
        self.results_date_var = tk.StringVar()
        self.results_date_entry = ttk.Entry(
            input_frame, textvariable=self.results_date_var, width=40
        )
        self.results_date_entry.grid(row=2, column=1, padx=5, pady=5, sticky=tk.W)

        # --- New: Bindings ---
        self.results_date_entry.bind("<FocusIn>", self.on_date_focus_in)
        self.results_date_entry.bind("<FocusOut>", self.on_date_focus_out)

        # HEPS (Cents)
        ttk.Label(input_frame, text="HEPS (Cents):").grid(
            row=3, column=0, padx=5, pady=5, sticky=tk.W
        )
        self.heps_var = tk.DoubleVar()
        self.heps_entry = ttk.Entry(input_frame, textvariable=self.heps_var, width=40)
        self.heps_entry.grid(row=3, column=1, padx=5, pady=5, sticky=tk.W)

        # Notes
        ttk.Label(input_frame, text="Notes:").grid(
            row=4, column=0, padx=5, pady=5, sticky=tk.NW
        )
        self.notes_text = tk.Text(input_frame, height=4, width=30)
        self.notes_text.grid(row=4, column=1, padx=5, pady=5, sticky=tk.W)

        # --- Button Frame ---
        button_frame = ttk.Frame(input_frame)
        button_frame.grid(row=5, column=1, padx=5, pady=10, sticky=tk.E)  # Updated row

        self.save_button = ttk.Button(
            button_frame, text="Save New", command=self.save_earnings
        )
        self.save_button.pack(side=tk.LEFT, padx=(0, 5))

        self.delete_button = ttk.Button(
            button_frame, text="Delete Selected", command=self.delete_earnings
        )
        self.delete_button.pack(side=tk.LEFT, padx=5)

        self.clear_button = ttk.Button(
            button_frame, text="Clear Form", command=self.clear_form
        )
        self.clear_button.pack(side=tk.LEFT, padx=5)

    # In tab_earnings.py
    def load_stock_list(self):
        """Fetches all tickers from the stock_details table using a utility."""
        try:
            tickers = fetch_all_tickers(self.db_config)

            for item in self.stock_tree.get_children():
                self.stock_tree.delete(item)

            for ticker in tickers:
                self.stock_tree.insert("", tk.END, values=(ticker,))

        except Exception as e:
            self.log_error(
                "Database Error", f"Failed to load stock list for Earnings tab: {e}"
            )

    def on_stock_select(self, event):
        """Called when a user clicks on a stock in the tree."""
        try:
            selected_item = self.stock_tree.focus()
            if not selected_item:
                return

            item = self.stock_tree.item(selected_item)
            ticker = item["values"][0]

            self.clear_form()
            self.ticker_var.set(ticker)
            self.load_earnings_history(ticker)

        except Exception as e:
            self.log_error("Selection Error", f"Error selecting stock: {e}")

    def load_earnings_history(self, ticker):
        """Fetches and displays all earnings history for the selected ticker."""
        for item in self.earnings_tree.get_children():
            self.earnings_tree.delete(item)

        if not ticker:
            return

        try:
            with psycopg2.connect(**self.db_config) as conn:
                with conn.cursor() as cursor:
                    query = """
                        SELECT earnings_id, period, results_date, heps, notes
                        FROM historical_earnings
                        WHERE ticker = %s
                        ORDER BY results_date DESC
                    """
                    cursor.execute(query, (ticker,))

                    for row in cursor.fetchall():
                        earnings_id, period, results_date, heps, notes = row

                        date_display = (
                            results_date.strftime("%Y-%m-%d") if results_date else ""
                        )
                        heps_display = f"{heps:.2f}" if heps is not None else ""
                        notes_display = notes if notes else ""

                        self.earnings_tree.insert(
                            "",
                            tk.END,
                            values=(
                                earnings_id,
                                period,
                                date_display,
                                heps_display,
                                notes_display,
                            ),
                        )

                    cursor.close()

        except Exception as e:
            self.log_error(
                "Database Error", f"Failed to load earnings history for {ticker}: {e}"
            )

    def on_earnings_select(self, event):
        """Called when a user clicks on an earnings entry in the history tree."""
        try:
            selected_item = self.earnings_tree.focus()
            if not selected_item:
                return

            item = self.earnings_tree.item(selected_item)
            values = item["values"]

            self.selected_earnings_id = values[0]

            self.period_var.set(values[1])
            self.results_date_var.set(values[2])
            self.heps_var.set(float(values[3]) if values[3] else 0.0)

            self.notes_text.delete("1.0", tk.END)
            self.notes_text.insert("1.0", values[4])

            # --- New: Ensure text is not greyed out ---
            self.period_entry.configure(style="TEntry")
            self.results_date_entry.configure(style="TEntry")

            self.save_button.config(text="Update Entry")

        except Exception as e:
            self.log_error("Selection Error", f"Error on earnings select: {e}")
            self.clear_form()

    def clear_form(self):
        """Clears the earnings input form and resets selection state."""
        self.selected_earnings_id = None
        self.period_var.set("")
        self.results_date_var.set("")
        self.heps_var.set(0.0)
        self.notes_text.delete("1.0", tk.END)
        self.save_button.config(text="Save New")

        # --- Updated: Manually trigger focus out to set placeholders ---
        self.on_period_focus_out(None)
        self.on_date_focus_out(None)

        for item in self.earnings_tree.selection():
            self.earnings_tree.selection_remove(item)

    def save_earnings(self):
        """Saves a new or updates an existing earnings entry."""
        ticker = self.ticker_var.get()
        period = self.period_var.get().strip()
        results_date_str = self.results_date_var.get().strip()
        notes = self.notes_text.get("1.0", tk.END).strip()

        # --- Updated: Check against placeholders ---
        if not ticker:
            self.log_error("Input Error", "Ticker is required.")
            return

        if not period or period == self.placeholder_period:
            self.log_error("Input Error", "Period is required.")
            return
        if not results_date_str or results_date_str == self.placeholder_date:
            self.log_error("Input Error", "Results Date is required.")
            return
        # --- End Update ---

        try:
            heps_val = self.heps_var.get()
            heps = Decimal(heps_val) if heps_val else 0
        except (ValueError, InvalidOperation):
            self.log_error("Input Error", "HEPS must be a valid number.")
            return

        try:
            with psycopg2.connect(**self.db_config) as conn:
                with conn.cursor() as cursor:

                    if self.selected_earnings_id:
                        # --- UPDATE existing entry ---
                        query = """
                            UPDATE historical_earnings
                            SET period = %s, results_date = %s, heps = %s, notes = %s
                            WHERE earnings_id = %s
                        """
                        cursor.execute(
                            query,
                            (
                                period,
                                results_date_str,
                                heps,
                                notes,
                                self.selected_earnings_id,
                            ),
                        )
                        message = f"Earnings entry {self.selected_earnings_id} updated."

                    else:
                        # --- INSERT new entry ---
                        query = """
                            INSERT INTO historical_earnings (ticker, period, results_date, heps, notes)
                            VALUES (%s, %s, %s, %s, %s)
                        """
                        cursor.execute(
                            query, (ticker, period, results_date_str, heps, notes)
                        )
                        message = f"New earnings entry for {ticker} saved."

                    conn.commit()

                    messagebox.showinfo("Success", message)

                    self.load_earnings_history(ticker)  # Refresh the history
                    self.clear_form()

        except psycopg2.errors.UniqueViolation:
            self.log_error(
                "Database Error", "This period already exists for this ticker."
            )
        except Exception as e:
            self.log_error("Database Error", f"Failed to save earnings entry: {e}")

    def delete_earnings(self):
        """Deletes the currently selected earnings entry."""
        if not self.selected_earnings_id:
            self.log_error("Delete Error", "No earnings entry is selected to delete.")
            return

        ticker = self.ticker_var.get()

        if not messagebox.askyesno(
            "Confirm Delete", f"Are you sure you want to delete this entry?"
        ):
            return

        try:
            with psycopg2.connect(**self.db_config) as conn:
                with conn.cursor() as cursor:
                    query = "DELETE FROM historical_earnings WHERE earnings_id = %s"
                    cursor.execute(query, (self.selected_earnings_id,))
                    conn.commit()

            messagebox.showinfo("Success", "Earnings entry deleted successfully.")
            self.load_earnings_history(ticker)
            self.clear_form()

        except Exception as e:
            self.log_error("Database Error", f"Failed to delete earnings entry: {e}")

    def on_period_focus_in(self, event):
        if self.period_var.get() == self.placeholder_period:
            self.period_var.set("")
            self.period_entry.configure(style="TEntry")

    def on_period_focus_out(self, event):
        if self.period_var.get() == "":
            self.period_var.set(self.placeholder_period)
            self.period_entry.configure(style="Placeholder.TEntry")

    def on_date_focus_in(self, event):
        if self.results_date_var.get() == self.placeholder_date:
            self.results_date_var.set("")
            self.results_date_entry.configure(style="TEntry")

    def on_date_focus_out(self, event):
        if self.results_date_var.get() == "":
            self.results_date_var.set(self.placeholder_date)
            self.results_date_entry.configure(style="Placeholder.TEntry")
