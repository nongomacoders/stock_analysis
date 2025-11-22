import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
import psycopg2
from decimal import Decimal
import datetime # <--- ADDED THIS LINE TO FIX THE ERROR
from database_utils import fetch_all_tickers

class DetailsTab(ttk.Frame):
    """
    This class represents the "Stock Details" tab, for editing
    earnings dates and other stock-specific info.
    """
    def __init__(self, parent, db_config, log_error_func):
        super().__init__(parent, padding=10)
        
        self.db_config = db_config
        self.log_error = log_error_func
        self.selected_ticker = None
        
        # Define the fields we will be editing
        # (var_name, label_text, widget_type)
        self.field_definitions = [
            ('update_q1', 'Update Q1', 'date'),
            ('earnings_q1', 'Earnings Q1', 'date'),
            ('update_q2', 'Update Q2', 'date'),
            ('earnings_q2', 'Earnings Q2', 'date'),
            ('update_q3', 'Update Q3', 'date'),
            ('earnings_q3', 'Earnings Q3', 'date'),
            ('update_q4', 'Update Q4', 'date'),
            ('earnings_q4', 'Earnings Q4', 'date'),
            ('market_cap', 'Market Cap', 'text'),
            ('exchange_name', 'Exchange', 'text'),
            ('priority', 'Priority', 'combo') # New priority field
        ]
        
        self.field_vars = {} # Will store the tk.StringVar() for each field
        self.field_widgets = {} # Will store the Entry/Combobox widgets
        
        self.create_widgets()
        self.load_stock_list()

    def create_widgets(self):
        """Creates the main GUI layout for this tab."""
        
        # --- Create the two-panel layout ---
        self.paned_window = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.paned_window.pack(expand=True, fill='both')

        # --- Left Panel: Stock List ---
        left_panel = ttk.Frame(self.paned_window, padding=5)
        self.paned_window.add(left_panel, weight=1)

        # Treeview for stock list
        cols = ('ticker',)
        self.stock_tree = ttk.Treeview(left_panel, columns=cols, show='headings')
        self.stock_tree.heading('ticker', text='Ticker')
        self.stock_tree.column('ticker', width=150)

        # Scrollbar
        scrollbar = ttk.Scrollbar(left_panel, orient=tk.VERTICAL, command=self.stock_tree.yview)
        self.stock_tree.configure(yscroll=scrollbar.set)
        
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.stock_tree.pack(expand=True, fill='both')
        
        self.stock_tree.bind('<<TreeviewSelect>>', self.on_stock_select)

        # --- Right Panel: Details Editor ---
        right_panel = ttk.Frame(self.paned_window, padding=10)
        self.paned_window.add(right_panel, weight=2)
        
        self.edit_frame = ttk.LabelFrame(right_panel, text="Edit Details for: -", padding=15)
        self.edit_frame.pack(expand=True, fill='both')

        # Create entry widgets based on field_definitions
        row_index = 0
        for var_name, label, widget_type in self.field_definitions:
            # Create the label
            ttk.Label(self.edit_frame, text=f"{label}:").grid(row=row_index, column=0, padx=5, pady=5, sticky=tk.W)
            
            # Create the string variable
            var = tk.StringVar()
            self.field_vars[var_name] = var
            
            # Create the widget
            if widget_type == 'date':
                widget = ttk.Entry(self.edit_frame, textvariable=var, width=40)
                # You could add a calendar popup here later
            elif widget_type == 'combo':
                # This is for the new priority field
                widget = ttk.Combobox(
                    self.edit_frame,
                    textvariable=var,
                    values=["", "High", "Medium", "Low"],
                    width=38
                )
            else: # 'text'
                widget = ttk.Entry(self.edit_frame, textvariable=var, width=40)
            
            widget.grid(row=row_index, column=1, padx=5, pady=5, sticky=tk.W)
            self.field_widgets[var_name] = widget # Store widget
            row_index += 1
            
        # Save Button
        self.save_button = ttk.Button(self.edit_frame, text="Save Changes", command=self.save_stock_details)
        self.save_button.grid(row=row_index, column=1, padx=5, pady=10, sticky=tk.E)
        
        self.set_form_state('disabled') # Disable form by default

    def set_form_state(self, state):
        """Disables or enables all widgets in the edit form."""
        for widget in self.field_widgets.values():
            widget.config(state=state)
        self.save_button.config(state=state)

    # In tab_details.py
    def load_stock_list(self):
        """Fetches all tickers from the stock_details table using a utility."""
        try:
            tickers = fetch_all_tickers(self.db_config)

            # Clear existing items
            for item in self.stock_tree.get_children():
                self.stock_tree.delete(item)

            # Insert new items
            for ticker in tickers:
                self.stock_tree.insert('', tk.END, values=(ticker,))

        except Exception as e:
            self.log_error("Database Error", f"Failed to load stock list for Details tab: {e}")

    def on_stock_select(self, event):
        """Called when a user clicks on a stock in the tree."""
        try:
            selected_item = self.stock_tree.focus()
            if not selected_item:
                return
                
            item = self.stock_tree.item(selected_item)
            self.selected_ticker = item['values'][0]
            
            self.edit_frame.config(text=f"Edit Details for: {self.selected_ticker}")
            
            # Fetch and load the data for this ticker
            self.load_stock_details()
            
        except Exception as e:
            self.log_error("Selection Error", f"Error selecting stock: {e}")
            self.selected_ticker = None
            self.set_form_state('disabled')

    def load_stock_details(self):
        """Loads the details for the self.selected_ticker into the form."""
        if not self.selected_ticker:
            return
            
        # Build the column list for the query
        column_names = [field[0] for field in self.field_definitions] # [update_q1, earnings_q1, ..., priority]
        
        try:
            with psycopg2.connect(**self.db_config) as conn:
                with conn.cursor() as cursor:
                    # Dynamically build query
                    query = f"SELECT {', '.join(column_names)} FROM stock_details WHERE ticker = %s"
                    cursor.execute(query, (self.selected_ticker,))
                    
                    result = cursor.fetchone()
                    cursor.close()
                    
                    if result:
                        # Loop through fields and results at the same time
                        for (var_name, _, _), value in zip(self.field_definitions, result):
                            # Convert None to empty string for display
                            display_value = "" if value is None else str(value)
                            
                            # Handle date display (if they are date objects, not strings)
                            if isinstance(value, datetime.date):
                                display_value = value.strftime('%Y-%m-%d')
                                
                            self.field_vars[var_name].set(display_value)
                        
                        self.set_form_state('normal') # Enable the form
                    else:
                        self.log_error("Data Error", f"No details found for {self.selected_ticker}")
                        self.set_form_state('disabled')
                        
        except Exception as e:
            self.log_error("Database Error", f"Failed to load details for {self.selected_ticker}: {e}")
            self.set_form_state('disabled')

    def save_stock_details(self):
        """Saves the current form data back to the database."""
        if not self.selected_ticker:
            self.log_error("Save Error", "No ticker is selected.")
            return

        conn = None
        try:
            with psycopg2.connect(**self.db_config) as conn:
                with conn.cursor() as cursor:
            
                    # Build SET clause and values list for the query
                    set_clauses = []
                    values = []
                    
                    for var_name, _, _ in self.field_definitions:
                        set_clauses.append(f"{var_name} = %s")
                        
                        value = self.field_vars[var_name].get().strip()
                        
                        # Convert empty strings to None (NULL in DB)
                        if value == "":
                            values.append(None)
                        # Handle numeric fields
                        elif var_name == 'market_cap':
                            try:
                                values.append(Decimal(value.replace(",", "")))
                            except Exception:
                                self.log_error("Input Error", f"Invalid Market Cap: {value}. Must be a number.")
                                return
                        else:
                            values.append(value)
                    
                    # Add the ticker to the end of the values list for the WHERE clause
                    values.append(self.selected_ticker)
                    
                    # Build the final query
                    query = f"UPDATE stock_details SET {', '.join(set_clauses)} WHERE ticker = %s"
                    
                    cursor.execute(query, tuple(values))
                    conn.commit()
                    messagebox.showinfo("Success", f"Details for {self.selected_ticker} updated successfully.")
                    
        except Exception as e:
            if conn:
                conn.rollback()
            self.log_error("Database Error", f"Failed to save details: {e}")
            

