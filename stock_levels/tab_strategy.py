import tkinter as tk
from tkinter import ttk
from tkinter import messagebox, simpledialog
import psycopg2
from decimal import Decimal, InvalidOperation
import queue
import threading
import analysis_engine
from datetime import datetime, date # <-- UPDATED IMPORT

class StrategyTab(ttk.Frame):
    """
    This class represents the "Strategy" tab, for editing
    research, strategy, deep research, and viewing SENS history.
    """
    def __init__(self, parent, db_config, log_error_func):
        super().__init__(parent, padding=10)
        
        self.db_config = db_config
        self.log_error = log_error_func
        self.selected_ticker = None
        
        self.ticker_var = tk.StringVar()
        self.levels_var = tk.StringVar()
        self.sens_combo_var = tk.StringVar()
        # --- ADD NEW VARIABLE ---
        self.filter_var = tk.StringVar(value="All Tickers")
        # ------------------------
        self.sens_data_map = {}
        self.research_queue = queue.Queue()
        
        self.create_widgets()
        self.load_stock_list()
        
        self.after(200, self.process_ai_research_queue)

    def create_widgets(self):
        """Creates the main GUI layout for this tab."""
        
        self.paned_window = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.paned_window.pack(expand=True, fill='both')

        # --- Left Panel ---
        left_panel = ttk.Frame(self.paned_window, padding=5)
        self.paned_window.add(left_panel, weight=1)

        # --- FILTER FRAME START ---
        filter_frame = ttk.Frame(left_panel)
        filter_frame.pack(fill='x', expand=False, pady=(0, 5))

        ttk.Label(filter_frame, text="Filter:").pack(side=tk.LEFT, padx=(0, 5))
        self.filter_combo = ttk.Combobox(
            filter_frame,
            textvariable=self.filter_var,
            values=["All Tickers", "Has Deep Research", "No Deep Research"],
            state='readonly',
            width=18
        )
        self.filter_combo.pack(side=tk.LEFT, fill='x', expand=True, padx=5)
        # Bind the selection event to reload the list
        self.filter_combo.bind('<<ComboboxSelected>>', self.load_stock_list)
        # --- FILTER FRAME END ---

        cols = ('ticker',)
        self.stock_tree = ttk.Treeview(left_panel, columns=cols, show='headings')
        self.stock_tree.heading('ticker', text='Ticker')
        self.stock_tree.column('ticker', width=150)

        scrollbar = ttk.Scrollbar(left_panel, orient=tk.VERTICAL, command=self.stock_tree.yview)
        self.stock_tree.configure(yscroll=scrollbar.set)
        
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.stock_tree.pack(expand=True, fill='both')
        
        self.stock_tree.bind('<<TreeviewSelect>>', self.on_stock_select)

        # --- Right Panel ---
        right_panel = ttk.Frame(self.paned_window, padding=10)
        self.paned_window.add(right_panel, weight=3)
        
        self.edit_frame = ttk.LabelFrame(right_panel, text="Analysis for: -", padding=15)
        self.edit_frame.pack(expand=True, fill='both')
        
        # Top Details
        top_details_frame = ttk.Frame(self.edit_frame)
        top_details_frame.pack(fill='x', expand=False, pady=(0, 10))

        ttk.Label(top_details_frame, text="Ticker:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.NW)
        self.ticker_entry = ttk.Entry(top_details_frame, textvariable=self.ticker_var, state='readonly', width=60)
        self.ticker_entry.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)

        ttk.Label(top_details_frame, text="Price Levels:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.NW)
        self.levels_entry = ttk.Entry(top_details_frame, textvariable=self.levels_var, width=60)
        self.levels_entry.grid(row=1, column=1, padx=5, pady=5, sticky=tk.W)
        ttk.Label(top_details_frame, text="(e.g., 150.50, 160, 175.25)").grid(row=2, column=1, padx=5, pady=0, sticky=tk.W)
        
        top_details_frame.columnconfigure(1, weight=1)

        # Notebook
        self.details_notebook = ttk.Notebook(self.edit_frame)
        self.details_notebook.pack(expand=True, fill='both', pady=5)

        # Tab 1: Research
        research_tab = ttk.Frame(self.details_notebook, padding=5)
        self.details_notebook.add(research_tab, text='Master Research')
        self.research_text = tk.Text(research_tab, height=15, width=60, wrap=tk.WORD)
        self.research_text.pack(expand=True, fill='both', side=tk.LEFT)
        research_scroll = ttk.Scrollbar(research_tab, orient=tk.VERTICAL, command=self.research_text.yview)
        self.research_text.configure(yscroll=research_scroll.set)
        research_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Tab 2: Strategy
        strategy_tab = ttk.Frame(self.details_notebook, padding=5)
        self.details_notebook.add(strategy_tab, text='Master Strategy')
        self.strategy_text = tk.Text(strategy_tab, height=15, width=60, wrap=tk.WORD)
        self.strategy_text.pack(expand=True, fill='both', side=tk.LEFT)
        strategy_scroll = ttk.Scrollbar(strategy_tab, orient=tk.VERTICAL, command=self.strategy_text.yview)
        self.strategy_text.configure(yscroll=strategy_scroll.set)
        strategy_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Tab 3: Deep Research
        deep_research_tab = ttk.Frame(self.details_notebook, padding=5)
        self.details_notebook.add(deep_research_tab, text='Deep Research')
        self.deep_research_text = tk.Text(deep_research_tab, height=15, width=60, wrap=tk.WORD)
        self.deep_research_text.pack(expand=True, fill='both', side=tk.LEFT)
        deep_research_scroll = ttk.Scrollbar(deep_research_tab, orient=tk.VERTICAL, command=self.deep_research_text.yview)
        self.deep_research_text.configure(yscroll=deep_research_scroll.set)
        deep_research_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Tab 4: SENS History
        sens_tab = ttk.Frame(self.details_notebook, padding=5)
        self.details_notebook.add(sens_tab, text='SENS History')
        
        sens_controls_frame = ttk.Frame(sens_tab)
        sens_controls_frame.pack(fill='x', expand=False, pady=(0, 5))
        
        ttk.Label(sens_controls_frame, text="Select SENS:").pack(side=tk.LEFT, padx=5)
        self.sens_combo = ttk.Combobox(sens_controls_frame, textvariable=self.sens_combo_var, state='readonly', width=30)
        self.sens_combo.pack(side=tk.LEFT, padx=5)
        self.sens_combo.bind('<<ComboboxSelected>>', self.on_sens_select)
        
        self.add_sens_button = ttk.Button(sens_controls_frame, text="Add New SENS", command=self.open_add_sens_popup)
        self.add_sens_button.pack(side=tk.LEFT, padx=5)
        
        self.delete_sens_button = ttk.Button(sens_controls_frame, text="Delete Selected SENS", command=self.delete_sens_entry)
        self.delete_sens_button.pack(side=tk.LEFT, padx=5)
        
        self.sens_content_text = tk.Text(sens_tab, height=15, width=60, wrap=tk.WORD, state='disabled')
        self.sens_content_text.pack(expand=True, fill='both', side=tk.LEFT)
        sens_scroll = ttk.Scrollbar(sens_tab, orient=tk.VERTICAL, command=self.sens_content_text.yview)
        self.sens_content_text.configure(yscroll=sens_scroll.set)
        sens_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Bottom Buttons
        button_frame = ttk.Frame(self.edit_frame)
        button_frame.pack(fill='x', expand=False, pady=(10, 0))

        self.generate_button = ttk.Button(button_frame, text="Generate Research (AI)", command=self.trigger_research_generation)
        self.generate_button.pack(side=tk.LEFT, padx=(0, 10))

        self.save_button = ttk.Button(button_frame, text="Save Analysis", command=self.save_analysis_data)
        self.save_button.pack(side=tk.LEFT, padx=(0, 5))

        self.delete_button = ttk.Button(button_frame, text="Delete Analysis", command=self.delete_analysis_data)
        self.delete_button.pack(side=tk.LEFT, padx=5)

        self.clear_button = ttk.Button(button_frame, text="Clear Form", command=self.clear_form)
        self.clear_button.pack(side=tk.LEFT, padx=5)
        
        self.edit_frame.rowconfigure(3, weight=1)
        self.edit_frame.rowconfigure(4, weight=1)
        self.edit_frame.columnconfigure(1, weight=1)

    def load_stock_list(self, event=None): 
        """Fetches all tickers from the stock_details table based on the filter."""
        
        filter_mode = self.filter_var.get()
        query = """
            SELECT sd.ticker 
            FROM stock_details sd
            LEFT JOIN stock_analysis sa ON sd.ticker = sa.ticker
        """
        params = []
        
        if filter_mode == "Has Deep Research":
            # Filter for rows where the deepresearch column is NOT NULL
            query += " WHERE sa.deepresearch IS NOT NULL"
            
        elif filter_mode == "No Deep Research":
            # --- MODIFIED LOGIC START ---
            
            # 1. Join the watchlist table (we need its status column)
            query = """
                SELECT sd.ticker 
                FROM stock_details sd
                LEFT JOIN stock_analysis sa ON sd.ticker = sa.ticker
                LEFT JOIN watchlist w ON sd.ticker = w.ticker
            """
            # 2. Filter for: 
            #    a) deepresearch is NULL AND
            #    b) the watchlist status is 'WL-Active'
            #    Note: This handles both implicit NULLs (no sa entry) and explicit NULLs (sa entry exists but column is empty)
            query += """ 
                WHERE sa.deepresearch IS NULL 
                AND w.status = 'WL-Active'
            """
            
            # --- MODIFIED LOGIC END ---
        
        query += " ORDER BY sd.ticker"

        try:
            with psycopg2.connect(**self.db_config) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, tuple(params))
                    self.stock_tree.delete(*self.stock_tree.get_children())
                    for row in cursor.fetchall():
                        self.stock_tree.insert('', tk.END, values=row)
                        
        except Exception as e:
            self.log_error("Database Error", f"Failed to load filtered stock list: {e}")

    def on_stock_select(self, event):
        try:
            selected_item = self.stock_tree.focus()
            if not selected_item: return
            item = self.stock_tree.item(selected_item)
            self.selected_ticker = item['values'][0]
            self.edit_frame.config(text=f"Analysis for: {self.selected_ticker}")
            self.ticker_var.set(self.selected_ticker)
            self.load_analysis_data()
            self.load_sens_history()
        except Exception as e:
            self.log_error("Selection Error", f"Error selecting stock: {e}")
            self.clear_form()

    def load_analysis_data(self):
        self.levels_var.set("")
        self.research_text.delete("1.0", tk.END)
        self.strategy_text.delete("1.0", tk.END)
        self.deep_research_text.delete("1.0", tk.END)
        
        if not self.selected_ticker: return
            
        try:
            with psycopg2.connect(**self.db_config) as conn:
                with conn.cursor() as cursor:
                    query = "SELECT research, strategy, price_levels, deepresearch FROM stock_analysis WHERE ticker = %s"
                    cursor.execute(query, (self.selected_ticker,))
                    result = cursor.fetchone()
            
            if result:
                research, strategy, price_levels_array, deep_research = result
                if research: self.research_text.insert("1.0", research)
                if strategy: self.strategy_text.insert("1.0", strategy)
                if deep_research: self.deep_research_text.insert("1.0", deep_research)
                if price_levels_array:
                    levels_str = ", ".join(map(str, price_levels_array))
                    self.levels_var.set(levels_str)
        except Exception as e:
            self.log_error("Database Error", f"Failed to load analysis: {e}")

    # --- SENS FUNCTIONS ---
    def load_sens_history(self):
        self.sens_combo_var.set("")
        self.sens_combo['values'] = []
        self.sens_data_map.clear()
        self.sens_content_text.config(state='normal')
        self.sens_content_text.delete("1.0", tk.END)
        self.sens_content_text.config(state='disabled')
        
        if not self.selected_ticker: return

        try:
            with psycopg2.connect(**self.db_config) as conn:
                with conn.cursor() as cursor:
                    query = "SELECT sens_id, publication_datetime FROM SENS WHERE ticker = %s ORDER BY publication_datetime DESC"
                    cursor.execute(query, (self.selected_ticker,))
                    results = cursor.fetchall()

            if results:
                display_list = []
                for sens_id, pub_datetime in results:
                    display_str = pub_datetime.strftime("%Y-%m-%d %H:%M")
                    display_list.append(display_str)
                    self.sens_data_map[display_str] = sens_id
                self.sens_combo['values'] = display_list
                self.sens_combo_var.set(display_list[0]) 
                self.on_sens_select() 
        except Exception as e:
            self.log_error("Database Error", f"Failed to load SENS history: {e}")

    def on_sens_select(self, event=None):
        selected_str = self.sens_combo_var.get()
        sens_id = self.sens_data_map.get(selected_str)
        if not sens_id: return

        try:
            with psycopg2.connect(**self.db_config) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT content FROM SENS WHERE sens_id = %s", (sens_id,))
                    result = cursor.fetchone()
            
            self.sens_content_text.config(state='normal')
            self.sens_content_text.delete("1.0", tk.END)
            if result and result[0]: self.sens_content_text.insert("1.0", result[0])
            else: self.sens_content_text.insert("1.0", "--- No content found ---")
            self.sens_content_text.config(state='disabled')
        except Exception as e:
            self.log_error("Database Error", f"Failed to load SENS content: {e}")

    def delete_sens_entry(self):
        selected_str = self.sens_combo_var.get()
        sens_id = self.sens_data_map.get(selected_str)
        if not sens_id: return

        if not messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete the SENS from {selected_str}?"): return
            
        try:
            with psycopg2.connect(**self.db_config) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM SENS WHERE sens_id = %s", (sens_id,))
                    conn.commit()
            self.load_sens_history() 
        except Exception as e:
            self.log_error("Database Error", f"Failed to delete SENS: {e}")

    def open_add_sens_popup(self):
        if not self.selected_ticker:
            self.log_error("Input Error", "Please select a ticker first.")
            return

        popup = tk.Toplevel(self.master)
        popup.title(f"Add New SENS for {self.selected_ticker}")
        popup.geometry("600x400")
        popup.transient(self.master)
        popup.grab_set()

        ttk.Label(popup, text="Date/Time (YYYY-MM-DD HH:MM or YYYY-MM-DD):").pack(pady=(10,0))
        datetime_entry = ttk.Entry(popup, width=30)
        datetime_entry.pack(pady=5)
        
        ttk.Label(popup, text="SENS Content:").pack()
        content_frame = ttk.Frame(popup)
        content_text = tk.Text(content_frame, height=15, width=60, wrap=tk.WORD)
        scrollbar = ttk.Scrollbar(content_frame, orient=tk.VERTICAL, command=content_text.yview)
        content_text.configure(yscroll=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        content_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        content_frame.pack(pady=5, padx=10, fill=tk.BOTH, expand=True)
        
        save_button = ttk.Button(popup, text="Save and Close", 
                                 command=lambda: self._save_new_sens_from_popup(
                                     popup, datetime_entry.get(), content_text.get("1.0", "end-1c")))
        save_button.pack(pady=10)

    def _save_new_sens_from_popup(self, popup, datetime_str, content):
        ticker = self.selected_ticker
        datetime_str = datetime_str.strip()
        content = content.strip()
        
        if not datetime_str or not content:
            messagebox.showerror("Input Error", "Date and Content are required.", parent=popup)
            return

        pub_datetime = None
        try:
            pub_datetime = datetime.strptime(datetime_str, '%Y-%m-%d %H:%M')
        except ValueError:
            try:
                pub_datetime = datetime.strptime(datetime_str, '%Y-%m-%d')
            except ValueError:
                messagebox.showerror("Input Error", "Invalid Date format.", parent=popup)
                return

        try:
            with psycopg2.connect(**self.db_config) as conn:
                with conn.cursor() as cursor:
                    query = "INSERT INTO SENS (ticker, publication_datetime, content) VALUES (%s, %s, %s)"
                    cursor.execute(query, (ticker, pub_datetime, content))
                    conn.commit()
            messagebox.showinfo("Success", "SENS added.")
            popup.destroy()
            self.load_sens_history()
        except Exception as e:
            messagebox.showerror("Database Error", f"Error adding SENS: {e}", parent=popup)

    # --- AI GENERATION FUNCTIONS ---
    
    def trigger_research_generation(self):
        """Starts the AI research generation in a background thread."""
        if not self.selected_ticker:
            self.log_error("AI Error", "No ticker selected.")
            return

        # 1. Check for Deep Research and Date in the Database
        deep_research_content = ""
        sens_cutoff_date = None
        
        try:
            with psycopg2.connect(**self.db_config) as conn:
                with conn.cursor() as cursor:
                    # Retrieve Deep Research text AND the saved date
                    cursor.execute("SELECT deepresearch, deepresearch_date FROM stock_analysis WHERE ticker = %s", (self.selected_ticker,))
                    result = cursor.fetchone()
                    if result:
                        deep_research_content = result[0] if result[0] else ""
                        sens_cutoff_date = result[1] # This will be a date object or None
                        
        except Exception as e:
            self.log_error("Database Error", f"Failed to fetch deep research info: {e}")
            return

        # 2. Build the confirmation message
        prompt_msg = f"Generate new research summary for {self.selected_ticker}?"
        
        if deep_research_content:
            prompt_msg += "\n\n[INFO] Deep Research Found."
            if sens_cutoff_date:
                prompt_msg += f"\nUsing stored report date: {sens_cutoff_date}"
                prompt_msg += "\n(The AI will only look for SENS released AFTER this date.)"
            else:
                prompt_msg += "\n[WARNING] No report date found. The AI will look at ALL recent SENS."
            
        if not messagebox.askyesno("Confirm AI Research", prompt_msg):
            return

        # 3. Update GUI state
        self.research_text.delete("1.0", tk.END)
        self.research_text.insert("1.0", "Generating AI research... Please wait.")
        self.generate_button.config(state="disabled")
        self.save_button.config(state="disabled")
        self.details_notebook.select(self.research_text.master) 

        # 4. Start the thread
        threading.Thread(
            target=self._threaded_generate_research,
            args=(self.selected_ticker, deep_research_content, sens_cutoff_date),
            daemon=True
        ).start()

    def _threaded_generate_research(self, ticker, deep_research_content, sens_cutoff_date):
        """Runs the AI generation in a separate thread."""
        try:
            ai_research = analysis_engine.generate_master_research(ticker, deep_research_content, sens_cutoff_date)
            self.research_queue.put(('SUCCESS', ai_research))
        except Exception as e:
            print(f"ERROR in _threaded_generate_research: {e}")
            self.research_queue.put(('ERROR', f"Failed to generate research: {e}"))

    def process_ai_research_queue(self):
        """Checks the queue for results from the AI thread."""
        try:
            while not self.research_queue.empty():
                message = self.research_queue.get_nowait()
                
                self.generate_button.config(state="normal")
                self.save_button.config(state="normal")
                
                self.research_text.delete("1.0", tk.END)

                if message[0] == 'SUCCESS':
                    self.research_text.insert("1.0", message[1])
                elif message[0] == 'ERROR':
                    self.research_text.insert("1.0", f"--- ERROR ---\n{message[1]}")
                    self.log_error("AI Research Error", message[1])

        except queue.Empty:
            pass 
        finally:
            self.after(200, self.process_ai_research_queue)

    def save_analysis_data(self):
        """Saves (Inserts or Updates) the analysis data for the selected ticker."""
        if not self.selected_ticker:
            self.log_error("Save Error", "No ticker is selected.")
            return

        try:
            ticker = self.selected_ticker
            research = self.research_text.get("1.0", tk.END).strip()
            strategy = self.strategy_text.get("1.0", tk.END).strip()
            deep_research = self.deep_research_text.get("1.0", tk.END).strip()
            levels_str = self.levels_var.get().strip()
            
            # --- NEW: Set the date automatically to today ---
            current_date = date.today()
            
            price_levels_list = []
            if levels_str:
                parts = levels_str.split(',')
                for part in parts:
                    clean_part = part.strip()
                    if clean_part:
                        try:
                            price_levels_list.append(Decimal(clean_part))
                        except InvalidOperation:
                            self.log_error("Input Error", f"Invalid price level: '{clean_part}'. Must be a number.")
                            return
            
            db_price_levels = price_levels_list if price_levels_list else None
            db_research = research if research else None
            db_strategy = strategy if strategy else None
            db_deep_research = deep_research if deep_research else None

            with psycopg2.connect(**self.db_config) as conn:
                with conn.cursor() as cursor:
                    # --- UPDATED QUERY: Include deepresearch_date ---
                    query = """
                        INSERT INTO stock_analysis (ticker, research, strategy, deepresearch, deepresearch_date, price_levels)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (ticker) DO UPDATE SET
                            research = EXCLUDED.research,
                            strategy = EXCLUDED.strategy,
                            deepresearch = EXCLUDED.deepresearch,
                            deepresearch_date = EXCLUDED.deepresearch_date, -- Update date on save
                            price_levels = EXCLUDED.price_levels
                    """
                    params = (ticker, db_research, db_strategy, db_deep_research, current_date, db_price_levels)
                    cursor.execute(query, params)
                    conn.commit()
            
            messagebox.showinfo("Success", f"Analysis for {ticker} saved successfully.")
            
        except Exception as e:
            self.log_error("Database Error", f"Failed to save analysis: {e}")

    def delete_analysis_data(self):
        if not self.selected_ticker:
            self.log_error("Delete Error", "No ticker is selected.")
            return

        if not messagebox.askyesno("Confirm Delete", f"Delete all analysis for {self.selected_ticker}?"): return
            
        try:
            with psycopg2.connect(**self.db_config) as conn:
                with conn.cursor() as cursor:
                    query = "DELETE FROM stock_analysis WHERE ticker = %s"
                    cursor.execute(query, (self.selected_ticker,))
                    conn.commit()
            messagebox.showinfo("Success", "Deleted.")
            self.clear_form(clear_ticker=False) 
        except Exception as e:
            self.log_error("Database Error", f"Failed to delete analysis: {e}")

    def clear_form(self, clear_ticker=True):
        self.levels_var.set("")
        self.research_text.delete("1.0", tk.END)
        self.strategy_text.delete("1.0", tk.END)
        self.deep_research_text.delete("1.0", tk.END)
        
        self.sens_combo_var.set("")
        self.sens_combo['values'] = []
        self.sens_data_map.clear()
        self.sens_content_text.config(state='normal')
        self.sens_content_text.delete("1.0", tk.END)
        self.sens_content_text.config(state='disabled')
        
        if clear_ticker:
            self.selected_ticker = None
            self.ticker_var.set("")
            self.edit_frame.config(text="Analysis for: -")
            for item in self.stock_tree.selection():
                self.stock_tree.selection_remove(item)