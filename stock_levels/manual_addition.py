import tkinter as tk
from tkinter import ttk, messagebox
import psycopg2
from config import DB_CONFIG  # Imports your database credentials
from datetime import datetime, date
import threading
import analysis_engine
import yfinance as yf  # <-- NEW
import psycopg2.extras # <-- NEW
import pandas as pd    # <-- NEW
import queue         # <-- NEW

class StockEditorApp:
    def __init__(self, master):
        self.master = master
        master.title("Stock Details & SENS Editor")
        master.geometry("700x800")
        
        # --- NEW: Threading & Polling Setup ---
        self.download_queue = queue.Queue()
        
        # --- Variables ---
        self.filter_var = tk.BooleanVar()
        self.sens_datetime_var = tk.StringVar()

        # --- Frames ---
        filter_frame = ttk.Frame(master, padding="10")
        filter_frame.pack(fill="x")

        tree_frame = ttk.Frame(master, padding="10")
        tree_frame.pack(fill="both", expand=True)

        form_frame = ttk.Frame(master, padding="10")
        form_frame.pack(fill="x")

        # --- Filter Frame Widgets ---
        filter_check = ttk.Checkbutton(
            filter_frame,
            text="Show only entries with missing full name",
            variable=self.filter_var,
            command=self.refresh_data,
        )
        filter_check.pack(side="left", padx=5)

        refresh_button = ttk.Button(
            filter_frame, text="Refresh Data", command=self.refresh_data
        )
        refresh_button.pack(side="right", padx=5)

        # --- Treeview Frame (Data Table) ---
        columns = ("ticker", "full_name")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings")
        self.tree.heading("ticker", text="Ticker")
        self.tree.heading("full_name", text="Full Name")

        self.tree.column("ticker", width=100, anchor="w")
        self.tree.column("full_name", width=400, anchor="w")

        vscroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hscroll = ttk.Scrollbar(
            tree_frame, orient="horizontal", command=self.tree.xview
        )
        self.tree.configure(yscrollcommand=vscroll.set, xscrollcommand=hscroll.set)

        vscroll.pack(side="right", fill="y")
        hscroll.pack(side="bottom", fill="x")
        self.tree.pack(fill="both", expand=True)

        # Bind selection event
        print("DEBUG: Binding <<TreeviewSelect>> to on_tree_select")
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        # --- Form Frame (Add/Edit) ---

        # --- Stock Details Sub-Frame ---
        stock_details_frame = ttk.LabelFrame(
            form_frame, text="Stock Details (stock_details table)", padding=10
        )
        stock_details_frame.pack(fill="x")

        ttk.Label(stock_details_frame, text="Ticker (e.g., AGL):").grid(
            row=0, column=0, padx=5, pady=5, sticky="e"
        )
        self.ticker_entry = ttk.Entry(stock_details_frame, width=20)
        self.ticker_entry.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        ttk.Label(stock_details_frame, text="Full Name:").grid(
            row=1, column=0, padx=5, pady=5, sticky="e"
        )
        self.full_name_entry = ttk.Entry(stock_details_frame, width=50)
        self.full_name_entry.grid(
            row=1, column=1, columnspan=3, padx=5, pady=5, sticky="w"
        )
        stock_details_frame.columnconfigure(1, weight=1)

        button_container = ttk.Frame(stock_details_frame)
        button_container.grid(row=2, column=1, columnspan=4, pady=10, sticky="w")

        self.add_button = ttk.Button(
            button_container, text="Add New", command=self.add_stock
        )
        self.add_button.pack(side="left", padx=5)

        self.update_button = ttk.Button(
            button_container, text="Update Selected", command=self.update_stock
        )
        self.update_button.pack(side="left", padx=5)

        self.delete_button = ttk.Button(
            button_container, text="Delete Selected", command=self.delete_stock
        )
        self.delete_button.pack(side="left", padx=5)
        
        # --- NEW DOWNLOAD BUTTON ---
        self.download_button = ttk.Button(
            button_container, text="Download 5Y Price Data", command=self.download_5y_data_ui
        )
        self.download_button.pack(side="left", padx=15)
        
        self.watchlist_button = ttk.Button(
            button_container, text="Add to Watchlist", command=self.add_to_watchlist
        )
        self.watchlist_button.pack(side="left", padx=5)
        # --- END NEW DOWNLOAD BUTTON ---

        self.clear_button = ttk.Button(
            button_container, text="Clear Form", command=self.clear_form_and_selection
        )
        self.clear_button.pack(side="left", padx=5)

        # --- SENS Entry Sub-Frame ---
        sens_frame = ttk.LabelFrame(
            form_frame, text="Manual SENS Entry (SENS table)", padding=10
        )
        sens_frame.pack(fill="x", expand=True, pady=(10, 0))

        # Ticker is shared from above
        ttk.Label(sens_frame, text="Date/Time (YYYY-MM-DD HH:MM):").grid(
            row=0, column=0, padx=5, pady=5, sticky="e"
        )
        self.sens_datetime_entry = ttk.Entry(
            sens_frame, textvariable=self.sens_datetime_var, width=25
        )
        self.sens_datetime_entry.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        ttk.Label(sens_frame, text="SENS Content:").grid(
            row=1, column=0, padx=5, pady=5, sticky="ne"
        )
        self.sens_content_text = tk.Text(sens_frame, height=10, width=60, wrap=tk.WORD)
        self.sens_content_text.grid(row=1, column=1, padx=5, pady=5, sticky="w")

        sens_scroll = ttk.Scrollbar(
            sens_frame, orient=tk.VERTICAL, command=self.sens_content_text.yview
        )
        self.sens_content_text.configure(yscroll=sens_scroll.set)
        sens_scroll.grid(row=1, column=2, sticky="ns")

        sens_frame.columnconfigure(1, weight=1)
        sens_frame.rowconfigure(1, weight=1)

        sens_button_container = ttk.Frame(sens_frame)
        sens_button_container.grid(row=2, column=1, pady=10, sticky="w")

        self.add_sens_button = ttk.Button(
            sens_button_container, text="Save New SENS", command=self.add_sens
        )
        self.add_sens_button.pack(side="left", padx=5)

        self.analyze_sens_button = ttk.Button(
            sens_button_container,
            text="Analyze SENS (AI)",
            command=self.trigger_sens_analysis,
        )
        self.analyze_sens_button.pack(side="left", padx=10)

        # --- Initial Data Load ---
        print("DEBUG: Performing initial data load...")
        self.refresh_data()
        print("DEBUG: Initialization complete.")
        
        # --- Start Poller ---
        # --- CORRECTED LINE ---
        self.master.after(100, self.process_download_queue)

    # --- Database Functions ---

    def get_connection(self):
        """Establishes a new database connection."""
        print("DEBUG: get_connection: Attempting to connect...")
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            print("DEBUG: get_connection: Connection successful.")
            return conn
        except Exception as e:
            print(f"DEBUG: get_connection: FAILED: {e}")
            messagebox.showerror(
                "Database Error", f"Could not connect to database: {e}"
            )
            return None

    def format_ticker(self, ticker_str):
        """Ensures ticker is in the correct .JO format."""
        if not ticker_str:
            return None
        ticker = ticker_str.strip().upper()
        if not ticker.endswith(".JO"):
            ticker = f"{ticker}.JO"
        return ticker

    def refresh_data(self):
        """Fetches data from the DB and populates the treeview."""
        print("DEBUG: refresh_data: Starting...")
        # Clear existing tree
        print("DEBUG: refresh_data: Clearing old tree data.")
        for i in self.tree.get_children():
            self.tree.delete(i)

        conn = self.get_connection()
        if not conn:
            print("DEBUG: refresh_data: Aborting, no DB connection.")
            return

        try:
            with conn.cursor() as cursor:
                if self.filter_var.get():
                    print("DEBUG: refresh_data: Fetching unmatched entries.")
                    query = "SELECT ticker, full_name FROM stock_details WHERE full_name IS NULL OR full_name = '' ORDER BY ticker"
                else:
                    print("DEBUG: refresh_data: Fetching all entries.")
                    query = (
                        "SELECT ticker, full_name FROM stock_details ORDER BY ticker"
                    )

                cursor.execute(query)
                records = cursor.fetchall()
                print(f"DEBUG: refresh_data: Found {len(records)} records.")

                for row in records:
                    self.tree.insert("", "end", values=row)
        except Exception as e:
            print(f"DEBUG: refresh_data: FAILED: {e}")
            messagebox.showerror("Database Error", f"Error fetching data: {e}")
        finally:
            if conn:
                conn.close()
                print("DEBUG: refresh_data: DB connection closed.")
        print("DEBUG: refresh_data: Finished.")

    def add_stock(self):
        """Adds a new stock record to the database."""
        print("DEBUG: add_stock: Starting...")
        ticker = self.format_ticker(self.ticker_entry.get())
        full_name = self.full_name_entry.get().strip()

        if not ticker:
            messagebox.showwarning("Input Error", "Ticker cannot be empty.")
            print("DEBUG: add_stock: Aborted, ticker empty.")
            return

        conn = self.get_connection()
        if not conn:
            print("DEBUG: add_stock: Aborting, no DB connection.")
            return

        try:
            with conn.cursor() as cursor:
                query = "INSERT INTO stock_details (ticker, full_name) VALUES (%s, %s)"
                print(f"DEBUG: add_stock: Executing query with ({ticker}, {full_name})")
                cursor.execute(query, (ticker, full_name))
                conn.commit()

            messagebox.showinfo("Success", f"Successfully added {ticker}.")
            self.refresh_data()
            self.clear_form_and_selection()

        except psycopg2.IntegrityError as e:
            print(f"DEBUG: add_stock: FAILED (IntegrityError): {e}")
            messagebox.showerror(
                "Database Error", f"Error: Ticker '{ticker}' already exists."
            )
        except Exception as e:
            print(f"DEBUG: add_stock: FAILED (Exception): {e}")
            messagebox.showerror("Database Error", f"Error adding record: {e}")
            conn.rollback()
        finally:
            if conn:
                conn.close()
                print("DEBUG: add_stock: DB connection closed.")
        print("DEBUG: add_stock: Finished.")

    def update_stock(self):
        """Updates an existing stock record."""
        print("DEBUG: update_stock: Starting...")
        selected_item = self.tree.focus()
        if not selected_item:
            messagebox.showwarning(
                "Selection Error", "Please select an item from the list to update."
            )
            print("DEBUG: update_stock: Aborted, no item selected.")
            return

        original_ticker = self.tree.item(selected_item)["values"][0]
        new_ticker = self.format_ticker(self.ticker_entry.get())
        new_full_name = self.full_name_entry.get().strip()

        if not new_ticker:
            messagebox.showwarning("Input Error", "Ticker cannot be empty.")
            print("DEBUG: update_stock: Aborted, new ticker is empty.")
            return

        conn = self.get_connection()
        if not conn:
            print("DEBUG: update_stock: Aborting, no DB connection.")
            return

        try:
            with conn.cursor() as cursor:
                query = "UPDATE stock_details SET ticker = %s, full_name = %s WHERE ticker = %s"
                print(
                    f"DEBUG: update_stock: Executing query with ({new_ticker}, {new_full_name}, {original_ticker})"
                )
                cursor.execute(query, (new_ticker, new_full_name, original_ticker))
                conn.commit()

                if cursor.rowcount == 0:
                    messagebox.showwarning(
                        "Update Error", f"No record found for ticker: {original_ticker}"
                    )
                else:
                    messagebox.showinfo(
                        "Success", f"Successfully updated {original_ticker}."
                    )

            self.refresh_data()
            self.clear_form_and_selection()

        except psycopg2.IntegrityError as e:
            print(f"DEBUG: update_stock: FAILED (IntegrityError): {e}")
            messagebox.showerror(
                "Database Error", f"Error: Ticker '{new_ticker}' already exists."
            )
        except Exception as e:
            print(f"DEBUG: update_stock: FAILED (Exception): {e}")
            messagebox.showerror("Database Error", f"Error updating record: {e}")
            conn.rollback()
        finally:
            if conn:
                conn.close()
                print("DEBUG: update_stock: DB connection closed.")
        print("DEBUG: update_stock: Finished.")

    def delete_stock(self):
        """Deletes a selected stock record."""
        print("DEBUG: delete_stock: Starting...")
        selected_item = self.tree.focus()
        if not selected_item:
            messagebox.showwarning(
                "Selection Error", "Please select an item from the list to delete."
            )
            print("DEBUG: delete_stock: Aborted, no item selected.")
            return

        ticker = self.tree.item(selected_item)["values"][0]

        if not messagebox.askyesno(
            "Confirm Delete", f"Are you sure you want to delete {ticker}?"
        ):
            print("DEBUG: delete_stock: User cancelled delete.")
            return

        conn = self.get_connection()
        if not conn:
            print("DEBUG: delete_stock: Aborting, no DB connection.")
            return

        try:
            with conn.cursor() as cursor:
                query = "DELETE FROM stock_details WHERE ticker = %s"
                print(f"DEBUG: delete_stock: Executing query with ({ticker})")
                cursor.execute(query, (ticker,))
                conn.commit()

                if cursor.rowcount == 0:
                    messagebox.showwarning(
                        "Delete Error", f"No record found for ticker: {ticker}"
                    )
                else:
                    messagebox.showinfo("Success", f"Successfully deleted {ticker}.")

            self.refresh_data()
            self.clear_form_and_selection()

        except Exception as e:
            print(f"DEBUG: delete_stock: FAILED (Exception): {e}")
            if "violates foreign key constraint" in str(e):
                messagebox.showerror(
                    "Delete Error",
                    f"Cannot delete {ticker}. It is still referenced by other tables (e.g., SENS, watchlist, daily_data).",
                )
            else:
                messagebox.showerror("Database Error", f"Error deleting record: {e}")
            conn.rollback()
        finally:
            if conn:
                conn.close()
                print("DEBUG: delete_stock: DB connection closed.")
        print("DEBUG: delete_stock: Finished.")

    def add_to_watchlist(self):
        """Adds the current ticker to the watchlist with status 'Pending'."""
        print("DEBUG: add_to_watchlist: Starting...")
        ticker = self.format_ticker(self.ticker_entry.get())

        if not ticker:
            messagebox.showwarning("Input Error", "Ticker cannot be empty.")
            return

        conn = self.get_connection()
        if not conn:
            return

        try:
            with conn.cursor() as cursor:
                query = "INSERT INTO watchlist (ticker, status) VALUES (%s, %s)"
                cursor.execute(query, (ticker, 'Pending'))
                conn.commit()

            messagebox.showinfo("Success", f"Successfully added {ticker} to Watchlist.")

        except Exception as e:
            print(f"DEBUG: add_to_watchlist: FAILED: {e}")
            messagebox.showerror("Database Error", f"Error adding to watchlist: {e}")
            conn.rollback()
        finally:
            if conn:
                conn.close()
        print("DEBUG: add_to_watchlist: Finished.")

    # --- SENS Functions ---

    def add_sens(self):
        """Adds a new SENS record to the database."""
        print("DEBUG: add_sens: Starting...")
        
        # 1. Get Ticker
        ticker = self.format_ticker(self.ticker_entry.get())
        if not ticker:
            messagebox.showwarning("Input Error", "Ticker cannot be empty. Select a stock or type one in the 'Ticker' box.")
            print("DEBUG: add_sens: Aborted, ticker empty.")
            return
            
        # 2. Get Datetime
        datetime_str = self.sens_datetime_var.get().strip()
        if not datetime_str:
            messagebox.showwarning("Input Error", "Date/Time cannot be empty.")
            print("DEBUG: add_sens: Aborted, datetime empty.")
            return
            
        # 3. Get Content
        content = self.sens_content_text.get("1.0", "end-1c").strip()
        if not content:
            messagebox.showwarning("Input Error", "SENS Content cannot be empty.")
            print("DEBUG: add_sens: Aborted, content empty.")
            return

        # 4. Validate Datetime
        pub_datetime = None
        try:
            pub_datetime = datetime.strptime(datetime_str, '%Y-%m-%d %H:%M')
        except ValueError:
            try:
                pub_datetime = datetime.strptime(datetime_str, '%Y-%m-%d')
                print(f"DEBUG: add_sens: Date-only detected. Using {pub_datetime}.")
            except ValueError:
                messagebox.showwarning("Input Error", "Invalid Date/Time format. Please use YYYY-MM-DD HH:MM or just YYYY-MM-DD.")
                print("DEBUG: add_sens: Aborted, invalid datetime format.")
                return

        # 5. Save to Database
        conn = self.get_connection()
        if not conn:
            print("DEBUG: add_sens: Aborting, no DB connection.")
            return
            
        try:
            with conn.cursor() as cursor:
                query = "INSERT INTO SENS (ticker, publication_datetime, content) VALUES (%s, %s, %s)"
                print(f"DEBUG: add_sens: Executing query with ({ticker}, {pub_datetime}, [content])")
                cursor.execute(query, (ticker, pub_datetime, content))
                conn.commit()
            
            messagebox.showinfo("Success", f"Successfully added SENS for {ticker}.")

        except psycopg2.IntegrityError as e:
            print(f"DEBUG: add_sens: FAILED (IntegrityError): {e}")
            if "violates foreign key constraint" in str(e):
                 messagebox.showerror("Database Error", f"Error: Ticker '{ticker}' does not exist in the stock_details table. Please add it first.")
            else:
                messagebox.showerror("Database Error", f"Error: A SENS for this ticker at this exact time may already exist. {e}")
        except Exception as e:
            print(f"DEBUG: add_sens: FAILED (Exception): {e}")
            messagebox.showerror("Database Error", f"Error adding SENS record: {e}")
            conn.rollback()
        finally:
            if conn:
                conn.close()
                print("DEBUG: add_sens: DB connection closed.")
        print("DEBUG: add_sens: Finished.")

    # --- NEW DOWNLOAD LOGIC ---

    def download_5y_data_ui(self):
        """Click handler for the 5Y download button."""
        ticker = self.format_ticker(self.ticker_entry.get())

        if not ticker:
            messagebox.showwarning("Input Error", "Ticker cannot be empty.")
            return
            
        if not messagebox.askyesno("Confirm Download", f"This will download 5 years of historical price data for {ticker} and save it to the database. This may take up to 30 seconds.\n\nContinue?"):
            return

        self.download_button.config(state="disabled", text="Downloading...")
        
        threading.Thread(
            target=self._threaded_download_worker,
            args=(ticker,),
            daemon=True,
        ).start()

    # In manual_addition.py

    def _threaded_download_worker(self, ticker):
        """Worker function to run yfinance download in a separate thread."""
        worker_conn = None
        try:
            worker_conn = self.get_connection()
            if not worker_conn:
                self.download_queue.put(('ERROR', "Could not establish database connection."))
                return

            print(f"DEBUG (DOWNLOAD): Starting 5Y download for {ticker}...")
            data = yf.download(ticker, period="5y", auto_adjust=True)
            
            # --- NEW DEBUG CHECK: If DataFrame is empty ---
            if data.empty:
                self.download_queue.put(('ERROR', f"YFinance returned an empty result for {ticker}. The stock may not exist or the ticker is incorrect."))
                return
            # --- END NEW DEBUG CHECK ---
            
            # --- Use the price saving logic from market_agent.py ---
            records_saved, _ = self._process_and_save_new_data(worker_conn, data, [ticker])
            
            self.download_queue.put(('SUCCESS', f"Successfully downloaded and saved {records_saved} records for {ticker}."))

        except Exception as e:
            # Note: We are capturing the detailed KeyError raised in the helper function below
            print(f"ERROR (DOWNLOAD): Failed to download/save {ticker}: {e}")
            self.download_queue.put(('ERROR', str(e))) # Send the detailed error
        finally:
            if worker_conn:
                worker_conn.close()

    def process_download_queue(self):
        """Poller to update the GUI thread with download results."""
        try:
            while not self.download_queue.empty():
                message_type, message = self.download_queue.get_nowait()

                self.download_button.config(state="normal", text="Download 5Y Price Data")

                if message_type == 'SUCCESS':
                    messagebox.showinfo("Download Success", message)
                elif message_type == 'ERROR':
                    messagebox.showerror("Download Error", message)

        except queue.Empty:
            pass
        finally:
            self.master.after(100, self.process_download_queue)

    # In manual_addition.py

    # In manual_addition.py

    def _process_and_save_new_data(self, worker_conn, data, all_tickers):
        """
        [Helper] Processes the DataFrame from yfinance and saves it to the DB.
        (Adapted from market_agent.py logic)
        """
        try:
            # --- FIX: Simplify MultiIndex columns if present ---
            if isinstance(data.columns, pd.MultiIndex):
                # This drops the ticker name ('VAL.JO') from the column header, 
                # leaving only the metric name ('Close', 'Open', etc.)
                data.columns = data.columns.droplevel(1)
                data.columns.name = None
            # --- END FIX ---

            df = data.reset_index()
            df['ticker'] = all_tickers[0] # Assumes single ticker for this context
            
            # Now the standard renaming works because the headers are simple strings
            df.rename(columns={'Date': 'trade_date', 'Open': 'open_price', 'High': 'high_price', 'Low': 'low_price', 'Close': 'close_price', 'Volume': 'volume'}, inplace=True)
            
            # This line attempts to access the renamed columns:
            df = df[['ticker', 'trade_date', 'open_price', 'high_price', 'low_price', 'close_price', 'volume']]
            
            df.dropna(subset=['close_price', 'open_price', 'high_price', 'low_price'], inplace=True)

            data_to_insert = []
            for _, row in df.iterrows():
                data_to_insert.append((
                    row['ticker'], row['trade_date'].date(), int(row['open_price']), int(row['high_price']), int(row['low_price']), int(row['close_price']), int(row['volume'])
                ))
            
            query = """
                INSERT INTO daily_stock_data (ticker, trade_date, open_price, high_price, low_price, close_price, volume)
                VALUES %s
                ON CONFLICT (ticker, trade_date) DO UPDATE SET
                    open_price = EXCLUDED.open_price, high_price = EXCLUDED.high_price,
                    low_price = EXCLUDED.low_price, close_price = EXCLUDED.close_price,
                    volume = EXCLUDED.volume
            """
            
            cursor = worker_conn.cursor()
            psycopg2.extras.execute_values(cursor, query, data_to_insert)
            records_saved_count = cursor.rowcount
            worker_conn.commit()
            return records_saved_count, {}

        except KeyError as e:
            error_msg = (
                f"Column Error: Required column {e} is missing. "
                f"Columns received from YFinance: {list(data.columns)}"
            )
            raise Exception(error_msg)
        
        except Exception as e:
            worker_conn.rollback()
            raise Exception(f"DB Insert Failure: {e}")


    # --- NEW AI TRIGGER FUNCTION ---

    def trigger_sens_analysis(self):
        """
        Gets the current Ticker and SENS content and sends them
        to the analysis_engine for AI analysis.
        """
        print("DEBUG: trigger_sens_analysis: Starting...")

        # 1. Get Ticker
        ticker = self.format_ticker(self.ticker_entry.get())
        if not ticker:
            messagebox.showwarning(
                "Input Error",
                "Ticker cannot be empty. Select a stock or type one in the 'Ticker' box.",
            )
            print("DEBUG: trigger_sens_analysis: Aborted, ticker empty.")
            return

        # 2. Get Content
        content = self.sens_content_text.get("1.0", "end-1c").strip()
        if not content:
            messagebox.showwarning("Input Error", "SENS Content cannot be empty.")
            print("DEBUG: trigger_sens_analysis: Aborted, content empty.")
            return

        # 3. Confirm with user
        if not messagebox.askyesno(
            "Confirm AI Analysis",
            f"This will run an AI analysis for {ticker} using the content in the text box and save the result to the Action Log.\n\n(Note: This does NOT save the SENS. Click 'Save New SENS' first if you haven't.)\n\nContinue?",
        ):
            print("DEBUG: trigger_sens_analysis: User cancelled.")
            return

        # 4. Start threaded analysis
        try:
            print(f"     ==> Spawning AI thread for {ticker} from GUI...")
            threading.Thread(
                target=analysis_engine.analyze_new_sens,
                args=(ticker, content),  # Pass the .JO ticker
                daemon=True,
            ).start()

            messagebox.showinfo(
                "Analysis Started",
                f"AI analysis for {ticker} has been started in the background. \n\nCheck the 'Action Log' tab in the main app for the result in a few moments.",
            )
            print("DEBUG: trigger_sens_analysis: Thread started.")

        except Exception as e:
            print(f"DEBUG: trigger_sens_analysis: FAILED: {e}")
            messagebox.showerror(
                "Thread Error", f"Failed to start AI analysis thread: {e}"
            )

        print("DEBUG: trigger_sens_analysis: Finished.")


    # --- GUI Event Handlers ---

    def on_tree_select(self, event):
        """Populates the form when a tree item is selected."""
        print("\nDEBUG: on_tree_select: Event triggered.")
        selected_item = self.tree.focus()
        if not selected_item:
            print("DEBUG: on_tree_select: No item focused, exiting.")
            return

        item = self.tree.item(selected_item)
        values = item["values"]
        print(f"DEBUG: on_tree_select: Selected item values: {values}")
        ticker, full_name = values

        print("DEBUG: on_tree_select: Calling clear_entry_boxes()...")
        self.clear_entry_boxes()

        # Strip .JO for cleaner editing
        if ticker.endswith(".JO"):
            ticker = ticker[:-3]

        print(f"DEBUG: on_tree_select: Inserting '{ticker}' into ticker_entry.")
        self.ticker_entry.insert(0, ticker)
        print(f"DEBUG: on_tree_select: Inserting '{full_name}' into full_name_entry.")
        self.full_name_entry.insert(0, full_name if full_name else "")
        print("DEBUG: on_tree_select: Finished.")

    def clear_entry_boxes(self):
        """Clears all text entry boxes in both forms."""
        print("DEBUG: clear_entry_boxes: Clearing text boxes...")
        self.ticker_entry.delete(0, "end")
        self.full_name_entry.delete(0, "end")
        self.sens_datetime_var.set("")
        self.sens_content_text.delete("1.0", "end")
        print("DEBUG: clear_entry_boxes: Finished.")

    def clear_form_and_selection(self):
        """Clears all forms and deselects from the tree."""
        print("DEBUG: clear_form_and_selection: Starting...")
        self.clear_entry_boxes()  # Call the new function

        selected = self.tree.focus()
        if selected:
            print(f"DEBUG: clear_form_and_selection: Deselecting item {selected}")
            self.tree.selection_remove(selected)
        print("DEBUG: clear_form_and_selection: Finished.")


# --- Main execution ---
if __name__ == "__main__":
    root = tk.Tk()
    app = StockEditorApp(root)
    root.mainloop()