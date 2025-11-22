import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
import psycopg2
import psycopg2.extras
import threading
import queue
import yfinance as yf
import pandas as pd
from datetime import date, datetime, timedelta, time # <-- ADDED THIS
from utils import calculate_next_event_hit

# Import config (assuming config.py is in the same directory)
# from config import DB_CONFIG 
# (This is commented out, but must be in your real file)

class ScanTab(ttk.Frame):
    """
    This class represents the "Scan" tab, containing all its
    widgets and associated logic.
    """
    def __init__(self, parent, db_config, db_connection, log_error_func, on_scan_select_func):
        super().__init__(parent, padding=10)
        
        self.db_config = db_config 
        self.db_conn = db_connection # Main connection for UI actions like 'ignore'
        self.log_error = log_error_func
        self.on_scan_select = on_scan_select_func
        
        self.log_queue = queue.Queue() # Queue for thread-safe GUI logging
        
        self.create_widgets()
        self.after(100, self.process_log_queue)

    def create_widgets(self):
        """Creates the main GUI layout for this tab."""
        
        # --- Top Frame: Inputs ---
        input_frame = ttk.LabelFrame(self, text="Scan Parameters", padding=15)
        input_frame.pack(fill=tk.X, pady=5)

        # Proximity %
        ttk.Label(input_frame, text="Proximity (%):").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.proximity_var = tk.DoubleVar(value=2.5)
        self.proximity_entry = ttk.Entry(input_frame, textvariable=self.proximity_var, width=10)
        self.proximity_entry.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)

        # Earnings Days
        ttk.Label(input_frame, text="Days to Earnings:").grid(row=0, column=2, padx=15, pady=5, sticky=tk.W)
        self.earnings_days_var = tk.IntVar(value=30)
        self.earnings_days_entry = ttk.Entry(input_frame, textvariable=self.earnings_days_var, width=10)
        self.earnings_days_entry.grid(row=0, column=3, padx=5, pady=5, sticky=tk.W)

        # Scan Button
        self.scan_button = ttk.Button(input_frame, text="Run Scan", command=self.start_scan_thread)
        self.scan_button.grid(row=0, column=4, padx=20, pady=5, sticky=tk.E)

        # Configure grid weights
        input_frame.columnconfigure(4, weight=1)

        # --- Paned Window (Results and Log) ---
        main_paned_window = ttk.PanedWindow(self, orient=tk.VERTICAL)
        main_paned_window.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # --- Top Pane: Results ---
        results_frame = ttk.Frame(main_paned_window, padding=10)
        main_paned_window.add(results_frame, weight=3) # Give more weight to results

        # Results Treeview
        cols = ('ticker', 'priority', 'event', 'details', 'price', 'event_type', 'data_value')
        self.results_tree = ttk.Treeview(results_frame, columns=cols, show='headings')
        
        self.results_tree.heading('ticker', text='Ticker')
        self.results_tree.heading('priority', text='Priority')
        self.results_tree.heading('event', text='Event')
        self.results_tree.heading('details', text='Details')
        self.results_tree.heading('price', text='Current Price')
        
        self.results_tree.column('ticker', width=80, stretch=tk.NO)
        self.results_tree.column('priority', width=80, stretch=tk.NO)
        self.results_tree.column('event', width=120, stretch=tk.NO)
        self.results_tree.column('details', width=250)
        self.results_tree.column('price', width=100, stretch=tk.NO)
        
        # Hidden Columns
        self.results_tree.column('event_type', width=0, stretch=tk.NO)
        self.results_tree.column('data_value', width=0, stretch=tk.NO)

        # Scrollbar
        scrollbar = ttk.Scrollbar(results_frame, orient=tk.VERTICAL, command=self.results_tree.yview)
        self.results_tree.configure(yscroll=scrollbar.set)
        
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.results_tree.pack(fill=tk.BOTH, expand=True)

        # --- Bind double-click event ---
        self.results_tree.bind("<Double-1>", self.on_result_double_click)

        # --- Bind right-click event for context menu ---
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="Ignore this hit", command=self.ignore_selected_hit)
        self.results_tree.bind("<Button-3>", self.on_tree_right_click)

        # --- Bottom Pane: Log ---
        log_frame = ttk.Frame(main_paned_window, padding=10)
        main_paned_window.add(log_frame, weight=1) # Less weight for log

        log_label = ttk.Label(log_frame, text="Scan Log:")
        log_label.pack(fill=tk.X)

        self.log_text = tk.Text(log_frame, height=10, state='disabled', wrap=tk.WORD, font=('TkDefaultFont', 9))
        log_scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscroll=log_scrollbar.set)
        
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def on_result_double_click(self, event):
        """Handles double-clicking on a result row."""
        try:
            selected_item = self.results_tree.focus()
            if not selected_item:
                return
            
            item = self.results_tree.item(selected_item)
            ticker = item['values'][0]
            
            if ticker and self.on_scan_select:
                self.on_scan_select(ticker) # Call the main GUI's function
                
        except Exception as e:
            self.log_error("Scan Error", f"Error handling scan result click: {e}")

    def on_tree_right_click(self, event):
        """Shows the context menu on right-click."""
        row_id = self.results_tree.identify_row(event.y)
        if row_id:
            self.results_tree.focus(row_id)
            self.results_tree.selection_set(row_id)
            self.context_menu.post(event.x_root, event.y_root)

    def ignore_selected_hit(self):
        """Marks the selected scan hit as ignored in the database."""
        try:
            selected_item = self.results_tree.focus()
            if not selected_item:
                return
            
            item = self.results_tree.item(selected_item)
            values = item['values']
            
            ticker = values[0]
            event_type = values[5] # Hidden 'event_type' column
            data_value = values[6] # Hidden 'data_value' column
            
            if not event_type or not data_value:
                self.log_error("Ignore Error", "Could not ignore hit: missing data.")
                return

            cursor = self.db_conn.cursor()
            
            if event_type == 'level':
                level_id = int(data_value)
                query = "UPDATE stock_price_levels SET is_ignored_on_scan = TRUE WHERE level_id = %s"
                cursor.execute(query, (level_id,))
                
            elif event_type == 'earnings' or event_type == 'update':
                query = """
                    INSERT INTO ignored_events (ticker, event_type, event_date)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (ticker, event_type, event_date) DO NOTHING
                """
                cursor.execute(query, (ticker, event_type, data_value))
            
            self.db_conn.commit()
            cursor.close()
            
            self.results_tree.delete(selected_item)
            self.log_to_gui(f"Ignored: {ticker} - {event_type} ({data_value})")

        except Exception as e:
            self.db_conn.rollback()
            self.log_error("Ignore Error", f"Failed to ignore hit: {e}")

    def log_to_gui(self, message):
        """Puts a message in the queue to be safely displayed in the GUI."""
        self.log_queue.put(message)

    def process_log_queue(self):
        """Processes messages from the log queue."""
        try:
            while not self.log_queue.empty():
                message = self.log_queue.get_nowait()
                
                if message == "---SCAN-COMPLETE---":
                    self.scan_button.config(state='normal')
                    self.log_to_gui("\n--- Scan Finished ---")
                elif message == "---SCAN-STARTED---":
                    self.scan_button.config(state='disabled')
                    # Clear log and results table
                    self.log_text.config(state='normal')
                    self.log_text.delete('1.0', tk.END)
                    self.log_text.config(state='disabled')
                    
                    for item in self.results_tree.get_children():
                        self.results_tree.delete(item)
                else:
                    self.log_text.config(state='normal')
                    self.log_text.insert(tk.END, f"{message}\n")
                    self.log_text.see(tk.END) # Auto-scroll
                    self.log_text.config(state='disabled')
                    
        except queue.Empty:
            pass
        finally:
            self.after(100, self.process_log_queue) # Check again

    def start_scan_thread(self):
        """Starts the background thread for the market scan."""
        self.log_queue.put("---SCAN-STARTED---")
        self.log_to_gui("Starting scan thread...")
        
        # Get parameters from GUI
        try:
            proximity_pct = self.proximity_var.get()
            earnings_days = self.earnings_days_var.get()
        except tk.TclError:
            self.log_error("Input Error", "Please enter valid numbers for scan parameters.")
            self.log_queue.put("---SCAN-COMPLETE---") # Re-enable button
            return
            
        # Create and start the thread
        scan_thread = threading.Thread(
            target=self.run_market_scan, 
            args=(proximity_pct, earnings_days), 
            daemon=True
        )
        scan_thread.start()

    def run_market_scan(self, proximity_pct, earnings_days):
        """
        Runs in a background thread to perform the scan.
        """
        worker_conn = None
        try:
            # --- 1. Connect to DB ---
            worker_conn = psycopg2.connect(**self.db_config)
            if not worker_conn:
                self.log_to_gui("Error: Worker thread could not connect to DB.")
                return
            
            self.log_to_gui("Worker thread connected to DB.")
            cursor = worker_conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

            # --- New: Fetch ignored events ---
            self.log_to_gui("Fetching ignored events...")
            cursor.execute("SELECT ticker, event_type, event_date FROM ignored_events")
            ignored_events_set = set()
            for row in cursor.fetchall():
                ignored_events_set.add((row['ticker'], row['event_type'], row['event_date']))
            self.log_to_gui(f"Loaded {len(ignored_events_set)} ignored events.")

            # --- 2. Get Today's Prices ---
            self.log_to_gui("Checking for latest prices in database...")
            today = date.today()
            recent_dates = [today, today - timedelta(days=1)]
            
            cursor.execute("SELECT MAX(trade_date) FROM daily_stock_data")
            latest_date_db = cursor.fetchone()[0]
            
            # --- NEW: Check price_update_log ---
            force_download = False
            jse_open = time(9, 0)
            jse_close = time(17, 0)
            
            cursor.execute("SELECT MAX(update_timestamp) FROM price_update_log")
            latest_update_timestamp = cursor.fetchone()[0]
            
            if latest_date_db not in recent_dates:
                self.log_to_gui("Data is old. Forcing download.")
                force_download = True
            elif latest_update_timestamp is None:
                self.log_to_gui("No download log found. Forcing download.")
                force_download = True
            else:
                last_update_time = latest_update_timestamp.time()
                self.log_to_gui(f"Last price update was at: {latest_update_timestamp.strftime('%Y-%m-%d %H:%M')}")
                # If last update was today *during* market hours, it's incomplete
                if latest_update_timestamp.date() == today and jse_open <= last_update_time <= jse_close:
                    self.log_to_gui("Last update was during market hours. Forcing re-download for final prices.")
                    force_download = True
            # --- END NEW ---

            latest_prices = {} # {TICKER: price}

            if not force_download:
                # --- 2a. Get prices from DB ---
                self.log_to_gui(f"Data for {latest_date_db} is final. Fetching from DB...")
                query = """
                    SELECT ticker, close_price 
                    FROM daily_stock_data
                    WHERE trade_date = %s
                """
                cursor.execute(query, (latest_date_db,))
                for row in cursor.fetchall():
                    latest_prices[row['ticker']] = float(row['close_price'])
                self.log_to_gui(f"Loaded {len(latest_prices)} prices from DB.")
            
            else:
                # --- 2b. Get prices from yfinance ---
                self.log_to_gui("Data is outdated or incomplete. Fetching live prices from yfinance...")
                
                cursor.execute("SELECT ticker FROM stock_details")
                all_tickers = [row['ticker'] for row in cursor.fetchall()]
                
                if not all_tickers:
                    self.log_to_gui("No tickers in 'stock_details' to scan.")
                    return

                data = yf.download(all_tickers, period="1d", auto_adjust=True)
                
                if data.empty:
                    self.log_to_gui("No data returned from yfinance.")
                    return

                # This function saves to DB and returns latest prices in CENTS
                records_saved_count, latest_prices = self.process_and_save_new_data(worker_conn, data, all_tickers)
                self.log_to_gui(f"Loaded {len(latest_prices)} live prices for scanning.")
                
                # --- NEW: Log this update ---
                if records_saved_count > 0:
                    self.log_to_gui("Logging price update timestamp...")
                    cursor.execute(
                        "INSERT INTO price_update_log (records_saved) VALUES (%s)",
                        (records_saved_count,)
                    )
                    worker_conn.commit()
                # --- END NEW ---

            if not latest_prices:
                self.log_to_gui("No price data available to run scan. Exiting.")
                return

            # --- 3. Get Stocks to Scan (Levels & Earnings) ---
            self.log_to_gui("Fetching data for scanning (levels and earnings)...")
            
            # This query now filters out stocks on the watchlist (non-Pending)
            query = """
                SELECT 
                    sd.ticker, 
                    sd.priority,
                    sd.earnings_q1, sd.earnings_q2, sd.earnings_q3, sd.earnings_q4,
                    sd.update_q1, sd.update_q2, sd.update_q3, sd.update_q4,
                    spl.price_level, spl.level_id, spl.is_ignored_on_scan
                FROM stock_details sd
                LEFT JOIN stock_price_levels spl ON sd.ticker = spl.ticker AND spl.price_level IS NOT NULL
                WHERE sd.ticker NOT IN (
                    SELECT ticker FROM watchlist WHERE status != 'Pending'
                )
            """
            
            cursor.execute(query)
            
            stocks_to_scan = {} # {TICKER: {priority, levels, earnings_dates, update_dates}}
            
            for row in cursor.fetchall():
                ticker = row['ticker']
                if ticker not in stocks_to_scan:
                    stocks_to_scan[ticker] = {
                        'priority': row['priority'],
                        'levels': {}, # Use a dict to store level_id and is_ignored
                        'earnings_dates': [d for d in (row['earnings_q1'], row['earnings_q2'], row['earnings_q3'], row['earnings_q4']) if d is not None],
                        'update_dates': [d for d in (row['update_q1'], row.get('update_q2'), row.get('update_q3'), row.get('update_q4')) if d is not None]
                    }
                
                if row['price_level'] and row['level_id'] is not None:
                    stocks_to_scan[ticker]['levels'][float(row['price_level'])] = {
                        'level_id': row['level_id'],
                        'is_ignored': row['is_ignored_on_scan']
                    }
            
            self.log_to_gui(f"Found {len(stocks_to_scan)} stocks to scan.")

            # --- 4. Run Scan ---
            results = []
            priority_map = {"High": 1, "Medium": 2, "Low": 3}
            today = date.today()
            earnings_check_date = today + timedelta(days=earnings_days)

            for ticker, stock_data in stocks_to_scan.items():
                if ticker not in latest_prices:
                    continue # Skip stocks we couldn't get a price for

                current_price = latest_prices[ticker] # Price is in CENTS
                priority = stock_data['priority']

                # --- A. Check Price Levels ---
                for level, level_data in stock_data['levels'].items():
                    
                    if level_data['is_ignored']:
                        continue
                        
                    proximity_threshold = level * (proximity_pct / 100.0)
                    
                    if abs(current_price - level) <= proximity_threshold:
                        percent_diff = ((current_price - level) / level) * 100
                        details = f"Price {current_price:.2f} is {percent_diff:+.2f}% from level {level:.2f}"
                        results.append((
                            priority_map.get(priority, 99),
                            ticker,
                            priority,
                            "Price Level Hit",
                            details,
                            f"{current_price:.2f}",
                            'level',
                            level_data['level_id']
                        ))

                # --- B. Check Earnings Dates ---
                for earnings_date in stock_data['earnings_dates']:
                
                    if (ticker, 'earnings', earnings_date) in ignored_events_set:
                        continue
                    
                    days_away, hit_date = calculate_next_event_hit(
                        earnings_date, today, earnings_days
                    )
                    
                    if hit_date:
                        date_str = hit_date.strftime('%Y-%m-%d')
                        details = f"Earnings on {date_str} ({days_away} days)"
                        results.append((
                            priority_map.get(priority, 99),
                            ticker,
                            priority,
                            "Upcoming Earnings",
                            details,
                            f"{current_price:.2f}",
                            'earnings',
                            earnings_date.strftime('%Y-%m-%d') # Use original base date for ignoring
                        ))

               # --- C. Check Trading Update Dates ---
                for update_date in stock_data['update_dates']:
                    
                    if (ticker, 'update', update_date) in ignored_events_set:
                        continue
                    
                    days_away, hit_date = calculate_next_event_hit(
                        update_date, today, earnings_days
                    )
                        
                    if hit_date:
                        date_str = hit_date.strftime('%Y-%m-%d')
                        details = f"Update on {date_str} ({days_away} days)"
                        results.append((
                            priority_map.get(priority, 99),
                            ticker,
                            priority,
                            "Upcoming Update",
                            details,
                            f"{current_price:.2f}",
                            'update',
                            update_date.strftime('%Y-%m-%d') # Use original base date for ignoring
                        ))

            # --- 5. Sort results and send to GUI ---
            results.sort(key=lambda x: (x[0], x[1])) # Sort by priority, then ticker
            
            if not results:
                self.log_to_gui("No scan hits found.")
            else:
                self.log_to_gui(f"Found {len(results)} scan hits. Populating list...")
                for row in results:
                    self.log_queue.put(row[1:]) # Send all but the sort key

        except Exception as e:
            # Log the full exception to the GUI
            self.log_error("Scan Error", f"An error occurred in the scan thread: {e}")
        finally:
            if worker_conn:
                worker_conn.close()
            # Send signal to re-enable button
            self.log_queue.put("---SCAN-COMPLETE---")

    def process_and_save_new_data(self, worker_conn, data, all_tickers):
        """
        Processes the DataFrame from yfinance, saves it to the DB,
        and returns the latest prices in CENTS.
        
        Returns a tuple: (records_saved_count, latest_prices_dict)
        """
        self.log_to_gui("Processing and saving new data to database...")
        
        df = None
        try:
            if isinstance(data.columns, pd.MultiIndex):
                df = data.stack()
                df.index.names = ['trade_date', 'ticker']
                df = df.reset_index()
            elif 'Close' in data.columns and len(all_tickers) == 1:
                df = data.reset_index()
                df['ticker'] = all_tickers[0]
                df.rename(columns={'Date': 'trade_date'}, inplace=True)
            else:
                self.log_to_gui("Warning: yfinance data format not recognized. Skipping save.")
                return 0, {}
        except Exception as e:
            self.log_to_gui(f"Error processing yfinance data: {e}")
            return 0, {}

        # Clean and format
        df.rename(columns={
            'Open': 'open_price',
            'High': 'high_price',
            'Low': 'low_price',
            'Close': 'close_price',
            'Volume': 'volume'
        }, inplace=True)

        db_cols = ['ticker', 'trade_date', 'open_price', 'high_price', 'low_price', 'close_price', 'volume']
        df = df[[col for col in db_cols if col in df.columns]]
        df.dropna(subset=['close_price', 'open_price', 'high_price', 'low_price'], inplace=True)

        if df.empty:
            self.log_to_gui("No valid data rows to save.")
            return 0, {}

        # Convert to Cents and prepare for insertion
        data_to_insert = []
        latest_prices_cents = {}
        
        for _, row in df.iterrows():
            try:
                # Data is already in Cents
                open_cents = int(row['open_price'])
                high_cents = int(row['high_price'])
                low_cents = int(row['low_price'])
                close_cents = int(row['close_price'])
                
                data_to_insert.append((
                    row['ticker'],
                    row['trade_date'].date(), # Store as date
                    open_cents,
                    high_cents,
                    low_cents,
                    close_cents,
                    int(row['volume'])
                ))
                
                latest_prices_cents[row['ticker']] = close_cents
            except Exception as e:
                self.log_to_gui(f"Warning: Skipping row for {row['ticker']} due to data error: {e}")

        if not data_to_insert:
            self.log_to_gui("No data to insert after processing.")
            return 0, {}

        # Save to DB
        query = """
            INSERT INTO daily_stock_data (ticker, trade_date, open_price, high_price, low_price, close_price, volume)
            VALUES %s
            ON CONFLICT (ticker, trade_date) DO UPDATE SET
                open_price = EXCLUDED.open_price,
                high_price = EXCLUDED.high_price,
                low_price = EXCLUDED.low_price,
                close_price = EXCLUDED.close_price,
                volume = EXCLUDED.volume
        """
        
        try:
            cursor = worker_conn.cursor()
            psycopg2.extras.execute_values(cursor, query, data_to_insert)
            records_saved_count = cursor.rowcount
            worker_conn.commit()
            cursor.close()
            self.log_to_gui(f"Successfully saved {records_saved_count} new price records.")
            return records_saved_count, latest_prices_cents
        except Exception as e:
            worker_conn.rollback()
            self.log_to_gui(f"DB Error saving data: {e}")
            return 0, {}