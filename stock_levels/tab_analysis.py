import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
import psycopg2
import psycopg2.extras 
import pandas as pd
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation # <-- ADDED InvalidOperation
from datetime import date, timedelta

import threading
import queue
import yfinance as yf

# Import charting libraries
import matplotlib
matplotlib.use('TkAgg') 
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
import mplfinance as mpf

# Add this import:
from utils import calculate_rr_ratio, get_year_from_period, calculate_next_event_hit
from database_utils import convert_yf_price_to_cents
from database_utils import fetch_all_tickers
from database_utils import fetch_analysis_record

class AnalysisTab(ttk.Frame):
    """
    This class represents the "Analysis" tab, for charting and trade analysis.
    The left panel now includes the Master Research Summary and Price Levels.
    """
    def __init__(self, parent, db_connection, db_config, log_error_func):
        super().__init__(parent, padding=10)
        
        self.db_conn = db_connection
        self.db_config = db_config
        self.log_error = log_error_func
        self.refresh_queue = queue.Queue()
        self.peg_queue = queue.Queue()
        # --- Variables for UI/Data Display ---
        self.full_name_var = tk.StringVar(value="") 
        self.peg_var = tk.StringVar(value="--")
        self.peg_1_price_var = tk.StringVar(value="--")
        
        # --- NEW VARIABLES ---
        self.levels_interest_var = tk.StringVar() # For the "Levels to Plot" entry
        # --- END NEW VARIABLES ---

        # --- Style for event label ---
        self.style = ttk.Style()
        self.style.configure("Event.Warning.TLabel", foreground="red", font=('TkDefaultFont', 10, 'bold'))
        self.style.configure("Event.Normal.TLabel", font=('TkDefaultFont', 10, 'bold'))
        
        self.chart_df = None 
        self.trade_lines = [] 
        self.price_levels = [] # Holds hlines for the *active trade entry price* (purple line)
        self.fig = None
        self.ax = None
        self.canvas = None
        
        self.current_mouse_price = None 
        self.watchlist_sort_reverse = False
        self.name_sort_reverse = False # Initialization for sorting

        self.create_widgets()
        self.load_tickers()
        self.load_watchlist() 
        self.after(200, self.process_refresh_queue) 
        self.after(200, self.process_peg_queue) 

    def create_widgets(self):
        """Creates the main GUI layout for this tab."""
        
        # --- Create the two-panel layout ---
        self.paned_window = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.paned_window.pack(expand=True, fill='both')

        # --- Left Panel: Trade Calculator, Research Context & Watchlist ---
        self.left_panel = ttk.Frame(self.paned_window, padding=5)
        self.paned_window.add(self.left_panel, weight=1) 
        
        # --- Trade Calculator ---
        calc_frame = ttk.LabelFrame(self.left_panel, text="Trade Planner & Context", padding=15)
        calc_frame.pack(fill=tk.X, pady=5)
        
        # Rows 0, 1, 2: E, T, L (Trade Inputs)
        ttk.Label(calc_frame, text="Entry Price (E):").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.entry_var = tk.DoubleVar()
        self.entry_entry = ttk.Entry(calc_frame, textvariable=self.entry_var)
        self.entry_entry.grid(row=0, column=1, padx=5, pady=5)
        self.entry_var.trace_add("write", self.calculate_rr)

        ttk.Label(calc_frame, text="Target Price (T):").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        self.target_var = tk.DoubleVar()
        self.target_entry = ttk.Entry(calc_frame, textvariable=self.target_var)
        self.target_entry.grid(row=1, column=1, padx=5, pady=5)
        self.target_var.trace_add("write", self.calculate_rr)

        ttk.Label(calc_frame, text="Stop Loss (L):").grid(row=2, column=0, padx=5, pady=5, sticky=tk.W)
        self.stop_var = tk.DoubleVar()
        self.stop_entry = ttk.Entry(calc_frame, textvariable=self.stop_var)
        self.stop_entry.grid(row=2, column=1, padx=5, pady=5)
        self.stop_var.trace_add("write", self.calculate_rr)
        
        # Row 3, 4: R/R Ratio & Event Date
        ttk.Label(calc_frame, text="Reward/Risk:").grid(row=3, column=0, padx=5, pady=5, sticky=tk.W)
        self.rr_var = tk.StringVar(value="--")
        ttk.Label(calc_frame, textvariable=self.rr_var, font=('TkDefaultFont', 10, 'bold')).grid(row=3, column=1, padx=5, pady=5, sticky=tk.W)

        ttk.Label(calc_frame, text="Next Event:").grid(row=4, column=0, padx=5, pady=5, sticky=tk.W)
        self.event_var = tk.StringVar(value="--")
        self.event_label = ttk.Label(calc_frame, textvariable=self.event_var, style="Event.Normal.TLabel")
        self.event_label.grid(row=4, column=1, padx=5, pady=5, sticky=tk.W)
        
        # In tab_analysis.py, inside create_widgets

        # Row 5: Strategy Context (Replaces Research Context label)
        ttk.Label(calc_frame, text="Strategy Context:").grid(row=5, column=0, padx=5, pady=5, sticky=tk.NW) 
        # --- CHANGE state='disabled' to state='normal' ---
        self.strategy_context_text = tk.Text(calc_frame, height=5, width=30, wrap=tk.WORD, state='normal', font=('TkDefaultFont', 9))
        self.strategy_context_text.grid(row=5, column=1, padx=5, pady=5, sticky=tk.W)
        
        # Row 6: Levels of Interest (NEW)
        ttk.Label(calc_frame, text="Levels to Plot:").grid(row=6, column=0, padx=5, pady=5, sticky=tk.W)
        self.levels_interest_entry = ttk.Entry(calc_frame, textvariable=self.levels_interest_var, width=30)
        self.levels_interest_entry.grid(row=6, column=1, padx=5, pady=5, sticky=tk.W)
        self.levels_interest_entry.bind("<Return>", lambda event: self.draw_trade_lines(redraw=True)) # <-- ADD THIS LINE

        # Row 7, 8: PEG Labels
        ttk.Label(calc_frame, text="PEG Ratio:").grid(row=7, column=0, padx=5, pady=5, sticky=tk.W)
        ttk.Label(calc_frame, textvariable=self.peg_var, font=('TkDefaultFont', 10, 'bold')).grid(row=7, column=1, padx=5, pady=5, sticky=tk.W)

        ttk.Label(calc_frame, text="PEG 1 Price:").grid(row=8, column=0, padx=5, pady=5, sticky=tk.W)
        ttk.Label(calc_frame, textvariable=self.peg_1_price_var, font=('TkDefaultFont', 10, 'bold')).grid(row=8, column=1, padx=5, pady=5, sticky=tk.W)
        
        # Row 9: Calculator buttons
        calc_button_frame = ttk.Frame(calc_frame)
        calc_button_frame.grid(row=9, column=0, columnspan=2, pady=(10,0)) 
        
        self.draw_button = ttk.Button(calc_button_frame, text="Draw Trade", command=self.draw_trade_lines)
        self.draw_button.pack(side=tk.LEFT, padx=5)

        self.save_strategy_button = ttk.Button(calc_button_frame, text="Save Strategy", command=self.save_strategy_and_levels)
        self.save_strategy_button.pack(side=tk.LEFT, padx=5)

        self.add_to_watchlist_button = ttk.Button(calc_button_frame, text="Add to Watchlist", command=self.add_to_watchlist)
        self.add_to_watchlist_button.pack(side=tk.LEFT, padx=5)     

        # --- Trade Watchlist ---
        watchlist_frame = ttk.LabelFrame(self.left_panel, text="Trade Watchlist", padding=15)
        watchlist_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 5))
        
        # Watchlist Filter
        watchlist_filter_frame = ttk.Frame(watchlist_frame)
        watchlist_filter_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(watchlist_filter_frame, text="Filter:").pack(side=tk.LEFT, padx=(0, 5))
        self.watchlist_filter_var = tk.StringVar(value="All")
        self.watchlist_filter_combo = ttk.Combobox(
            watchlist_filter_frame,
            textvariable=self.watchlist_filter_var,
            values=["All", "Active-Trade", "Pre-Trade", "WL-Active", "WL-Sleep", "Pending"],
            state='readonly',
            width=10
        )
        self.watchlist_filter_combo.pack(side=tk.LEFT, padx=5)
        self.watchlist_filter_combo.bind('<<ComboboxSelected>>', self.load_watchlist)
        
        # Watchlist Treeview
        # NOTE: Removed 'notes' column reference
        watchlist_cols = ('id', 'ticker', 'full_name', 'status', 'rr', 'entry', 'stop') 
        self.watchlist_tree = ttk.Treeview(watchlist_frame, columns=watchlist_cols, show='headings')
        
        self.watchlist_tree.heading('ticker', text='Ticker', command=self.sort_watchlist_by_ticker)
        self.watchlist_tree.heading('full_name', text='Full Name', command=self.sort_watchlist_by_name)
        self.watchlist_tree.heading('status', text='Status')
        self.watchlist_tree.heading('rr', text='R/R')
        
        self.watchlist_tree.column('ticker', width=60)
        self.watchlist_tree.column('full_name', width=150)
        self.watchlist_tree.column('status', width=80, stretch=tk.NO)
        self.watchlist_tree.column('rr', width=50, stretch=tk.NO)
        
        self.watchlist_tree.column('id', width=0, stretch=tk.NO)
        self.watchlist_tree.column('entry', width=0, stretch=tk.NO)
        self.watchlist_tree.column('stop', width=0, stretch=tk.NO)
        
        watchlist_scrollbar = ttk.Scrollbar(watchlist_frame, orient=tk.VERTICAL, command=self.watchlist_tree.yview)
        self.watchlist_tree.configure(yscroll=watchlist_scrollbar.set)
        
        watchlist_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.watchlist_tree.pack(fill=tk.BOTH, expand=True)
        self.watchlist_tree.tag_configure('event_danger', foreground='red')
        self.watchlist_tree.tag_configure('event_warning', foreground='green')
        
        self.watchlist_context_menu = tk.Menu(self, tearoff=0)
        self.watchlist_context_menu.add_command(label="Mark as Active-Trade", command=self.set_watchlist_status_active_trade)
        self.watchlist_context_menu.add_command(label="Mark as Pre-Trade", command=self.set_watchlist_status_pretrade)
        self.watchlist_context_menu.add_command(label="Mark as WL-Active", command=self.set_watchlist_status_wl_active)
        self.watchlist_context_menu.add_command(label="Mark as WL-Sleep", command=self.set_watchlist_status_wl_sleep)
        self.watchlist_context_menu.add_command(label="Reset to Pending", command=self.set_watchlist_status_pending)
        self.watchlist_tree.bind("<Button-3>", self.on_watchlist_right_click)
        self.watchlist_tree.bind("<Double-1>", self.load_trade_to_chart)

        watchlist_button_frame = ttk.Frame(watchlist_frame)
        watchlist_button_frame.pack(fill=tk.X, pady=(10,0))

        self.load_to_chart_button = ttk.Button(watchlist_button_frame, text="Load to Chart", command=self.load_trade_to_chart)
        self.load_to_chart_button.pack(side=tk.LEFT, padx=5)

        self.remove_from_watchlist_button = ttk.Button(watchlist_button_frame, text="Remove", command=self.remove_from_watchlist)
        self.remove_from_watchlist_button.pack(side=tk.RIGHT, padx=5)

        # --- Right Panel: Chart ---
        self.right_panel = ttk.Frame(self.paned_window, padding=5)
        self.paned_window.add(self.right_panel, weight=4) 

        # Chart controls
        controls_frame = ttk.Frame(self.right_panel)
        controls_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(controls_frame, text="Select Ticker:").pack(side=tk.LEFT, padx=5)
        self.ticker_combo_var = tk.StringVar()
        self.ticker_combo = ttk.Combobox(controls_frame, textvariable=self.ticker_combo_var, state='readonly', width=10)
        self.ticker_combo.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(controls_frame, text="Date Range:").pack(side=tk.LEFT, padx=5)
        self.range_var = tk.StringVar(value="1 Year")
        self.range_combo = ttk.Combobox(controls_frame, textvariable=self.range_var, state='readonly',
                                        values=["3 Months", "6 Months", "1 Year", "2 Years", "5 Years"], width=10)
        self.range_combo.pack(side=tk.LEFT, padx=5)
        self.load_chart_button = ttk.Button(controls_frame, text="Load Chart", command=self.on_load_chart_button_pressed)
        self.load_chart_button.pack(side=tk.LEFT, padx=10)

        self.refresh_button = ttk.Button(controls_frame, text="Refresh Price", command=self.start_refresh_price_thread)
        self.refresh_button.pack(side=tk.LEFT, padx=5)
        
        # Chart Area
        self.chart_frame = ttk.Frame(self.right_panel, relief=tk.SUNKEN, borderwidth=1)
        self.chart_frame.pack(fill=tk.BOTH, expand=True)

        # Create initial empty figure
        self.fig = Figure(figsize=(5, 4), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax.text(0.5, 0.5, "Select a ticker and click 'Load Chart' to begin.",
                     horizontalalignment='center', verticalalignment='center',
                     transform=self.ax.transAxes, fontdict={'size': 12, 'color': 'gray'})
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.chart_frame)
        self.canvas.draw()
        
        # Add matplotlib toolbar
        self.toolbar = NavigationToolbar2Tk(self.canvas, self.chart_frame, pack_toolbar=False)
        self.toolbar.update()
        self.toolbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=1)

        # Connect initial event handlers
        self.connect_chart_events()

    # --- Event Handlers ---    
    

    def connect_chart_events(self):
        """Connects mouse and keyboard events to the chart canvas."""
        if self.canvas:
            self.canvas.mpl_connect('motion_notify_event', self.on_mouse_move)
            self.canvas.mpl_connect('key_press_event', self.on_key_press)
            self.canvas.get_tk_widget().focus_set()
            self.canvas.mpl_connect('axes_enter_event', lambda event: self.canvas.get_tk_widget().focus_set())

    def on_mouse_move(self, event):
        """Stores the current Y-coordinate (price) of the mouse."""
        if event.inaxes and self.ax and isinstance(self.ax, (list, tuple)) and event.inaxes == self.ax[0]:
            try:
                self.current_mouse_price = float(event.ydata)
            except Exception:
                self.current_mouse_price = None
        else:
            self.current_mouse_price = None

    def on_key_press(self, event):
        """Handles key presses when the mouse is over the chart."""
        if self.current_mouse_price is None:
            return

        key = event.key.lower()
        price = self.current_mouse_price
        
        try:
            # Round to two decimal places
            price_rounded = float(Decimal(price).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
        except Exception:
            price_rounded = price

        key_pressed = None
        if key == 'e':
            self.entry_var.set(price_rounded)
            key_pressed = key
        elif key == 'l':
            self.stop_var.set(price_rounded)
            key_pressed = key
        elif key == 't':
            self.target_var.set(price_rounded)
            key_pressed = key
        
        if key_pressed in ('e', 'l', 't'):
            self.draw_trade_lines(redraw=True)

    def _load_upcoming_event_date(self, ticker):
        """Fetches and displays the closest upcoming earnings/update date."""
        # [No changes to this function needed - uses db_conn directly]
        if not ticker:
            self.event_var.set("--")
            return

        try:
            cursor = self.db_conn.cursor()
            query = """
                SELECT 
                    earnings_q1, earnings_q2, earnings_q3, earnings_q4,
                    update_q1, update_q2, update_q3, update_q4
                FROM stock_details
                WHERE ticker = %s
            """
            cursor.execute(query, (ticker,))
            row = cursor.fetchone()
            cursor.close()

            if not row:
                self.event_var.set("N/A")
                self.event_label.configure(style="Event.Normal.TLabel")
                return

            all_dates = {
                'Earnings': [d for d in row[0:4] if d is not None],
                'Update': [d for d in row[4:8] if d is not None]
            }

            today = date.today()
            closest_event = None
            closest_days = float('inf')
            event_type = ""

            for e_type, dates in all_dates.items():
                for event_date in dates:
                    try:
                        event_this_year = event_date.replace(year=today.year)
                        event_next_year = event_date.replace(year=today.year + 1)
                    except ValueError: 
                        if event_date.month == 2 and event_date.day == 29:
                            event_this_year = event_date.replace(year=today.year, day=28)
                            event_next_year = event_date.replace(year=today.year + 1, day=28)
                        else:
                            continue

                    for dt in [event_this_year, event_next_year]:
                        if dt >= today:
                            days_away = (dt - today).days
                            if days_away < closest_days:
                                closest_days = days_away
                                closest_event = dt
                                event_type = e_type

            if closest_event:
                self.event_var.set(f"{event_type} in {closest_days} days")
                if closest_days <= 30:
                    self.event_label.configure(style="Event.Warning.TLabel")
                else:
                    self.event_label.configure(style="Event.Normal.TLabel")
            else:
                self.event_var.set("No upcoming events")
                self.event_label.configure(style="Event.Normal.TLabel")

        except Exception as e:
            self.log_error("Event Date Error", f"Failed to load event dates: {e}")
            self.event_var.set("Error")
            self.event_label.configure(style="Event.Normal.TLabel")

    def _calculate_days_to_next_event(self, ticker):
        """Fetches dates for watchlist sorting [No changes needed]."""
        # [No changes to this function needed - uses db_conn directly]
        if not ticker:
            return float('inf')

        try:
            cursor = self.db_conn.cursor()
            query = """
                SELECT 
                    earnings_q1, earnings_q2, earnings_q3, earnings_q4,
                    update_q1, update_q2, update_q3, update_q4
                FROM stock_details
                WHERE ticker = %s
            """
            cursor.execute(query, (ticker,))
            row = cursor.fetchone()
            cursor.close()

            if not row:
                return float('inf')

            all_dates = {
                'Earnings': [d for d in row[0:4] if d is not None],
                'Update': [d for d in row[4:8] if d is not None]
            }

            today = date.today()
            closest_days = float('inf')

            for e_type, dates in all_dates.items():
                for event_date in dates:
                    try:
                        event_this_year = event_date.replace(year=today.year)
                        event_next_year = event_date.replace(year=today.year + 1)
                    except ValueError:
                        if event_date.month == 2 and event_date.day == 29:
                            event_this_year = event_date.replace(year=today.year, day=28)
                            event_next_year = event_date.replace(year=today.year + 1, day=28)
                        else:
                            continue

                    for dt in [event_this_year, event_next_year]:
                        if dt >= today:
                            days_away = (dt - today).days
                            if days_away < closest_days:
                                closest_days = days_away
            
            return closest_days

        except Exception as e:
            print(f"Error in _calculate_days_to_next_event for {ticker}: {e}")
            return float('inf')

    def load_chart_for_ticker(self, ticker, check_watchlist=False):
        """
        Public method to allow other tabs to load a chart.
        This is the main function for loading a new ticker.
        """
        if not ticker:
            return
        
        # 1. Clear calculator and context fields
        self.entry_var.set(0.0)
        self.target_var.set(0.0)
        self.stop_var.set(0.0)
        self.rr_var.set("--")
        self.event_var.set("--")
        self.event_label.configure(style="Event.Normal.TLabel")
        
        # Clear the NEW context fields
        self.strategy_context_text.config(state='normal')
        self.strategy_context_text.delete("1.0", tk.END)
        self.strategy_context_text.config(state='normal')
        self.levels_interest_var.set("")
        
        self.peg_var.set("--")
        self.peg_1_price_var.set("--")
        
        # 2. Set the value in the combobox
        self.ticker_combo_var.set(ticker)
        
        # In tab_analysis.py, inside load_chart_for_ticker

        # 3. Load Strategy Context & Custom Levels from stock_analysis
        try:
            # Use the utility to fetch the record
            result = fetch_analysis_record(self.db_config, ticker)

            # Unpack the result tuple
            if result:
                research_summary, strategy_summary, price_levels_array = result 
            else:
                research_summary, strategy_summary, price_levels_array = None, None, None

            self.strategy_context_text.config(state='normal')

            if strategy_summary:
                self.strategy_context_text.insert("1.0", strategy_summary)
            else:
                self.strategy_context_text.insert("1.0", "No master strategy found.") # Updated default text

            if price_levels_array:
                # price_levels_array will be a list/array of Decimal objects
                levels_str = ", ".join(map(str, price_levels_array))
                self.levels_interest_var.set(levels_str)
            else:
                self.levels_interest_var.set("")

            # The 'if result:' check is slightly more robust if the entire row is missing
            if not result:
                self.strategy_context_text.insert("1.0", "No analysis record found.")

            self.strategy_context_text.config(state='normal')

        except Exception as e:
            self.log_error("Analysis Load Error", f"Failed to load strategy data: {e}")
            self.strategy_context_text.config(state='normal')

    # 4. Plot the chart...

        # 4. Plot the chart (this will set self.chart_df and plot levels)
        self.plot_chart()

        # 5. (Optional) Check watchlist and load trade
        if check_watchlist:
            self.check_and_load_from_watchlist(ticker)
            
        # 6. (Always) Calculate and display PEG
        self._calculate_and_display_peg(ticker)

    # --- Watchlist Functions (Notes removed) ---

    def load_watchlist(self, event=None):
        """
        Fetches watchlist items and displays them.
        NOTE: Removed all reference to the 'notes' column.
        """
        try:
            filter_mode = self.watchlist_filter_var.get()
            
            for item in self.watchlist_tree.get_children():
                self.watchlist_tree.delete(item)
            
            cursor = self.db_conn.cursor()
            
            # NOTE: Removed 'w.notes' from SELECT statement
            base_query = """
                SELECT 
                    w.watchlist_id, w.ticker, sd.full_name, w.status, w.reward_risk_ratio, 
                    w.entry_price, w.stop_loss,
                    sd.earnings_q1, sd.earnings_q2, sd.earnings_q3, sd.earnings_q4,
                    sd.update_q1, sd.update_q2, sd.update_q3, sd.update_q4
                FROM watchlist w
                LEFT JOIN stock_details sd ON w.ticker = sd.ticker
            """
            params = []
            if filter_mode != "All":
                base_query += " WHERE w.status = %s"
                params.append(filter_mode)
            
            cursor.execute(base_query, tuple(params))
            all_rows_data = cursor.fetchall()
            cursor.close()

            watchlist_with_days = []
            for row in all_rows_data:
                # row[0-6] are the watchlist/name columns, row[7:] are the 8 date columns
                days_away = self._calculate_days_from_row_data(row[7:])

                # NOTE: Only taking the first 7 columns now
                display_row = row[0:7] 
                
                tag = 'normal'
                if days_away <= 7:
                    tag = 'event_danger'
                elif 7 < days_away <= 30:
                    tag = 'event_warning'
                
                watchlist_with_days.append((days_away, display_row, tag))
            
            watchlist_with_days.sort(key=lambda x: x[0])
            
            for days, row_data, tag in watchlist_with_days:
                self.watchlist_tree.insert('', tk.END, values=row_data, tags=(tag,))
            
        except Exception as e:
            self.log_error("Watchlist Error", f"Failed to load watchlist: {e}")

    def add_to_watchlist(self):
        """
        Saves trade to watchlist (UPDATE) AND overwrites all stock price levels
        with the new Entry Price. Sets status to WL-Active.
        NOTE: Removed notes saving.
        """
        try:
            ticker = self.ticker_combo_var.get()
            entry = self.entry_var.get()
            stop = self.stop_var.get()
            target = self.target_var.get()
            rr_string = self.rr_var.get()
            
            if not ticker or entry <= 0 or stop <= 0 or target <= 0 or rr_string == "--":
                self.log_error("Input Error", "Ticker, Entry, Target, and Stop must be valid to save.")
                return

            rr_value_str = rr_string.split(" ")[0]
            try:
                rr_decimal = Decimal(rr_value_str)
            except Exception:
                self.log_error("Input Error", f"Cannot save trade with invalid R/R: {rr_string}")
                return

            cursor = self.db_conn.cursor()
            
            # NOTE: Removed 'notes = %s' from query and parameter list
            query_watchlist = """
                UPDATE watchlist
                SET price_level = %s, 
                    entry_price = %s, 
                    stop_loss = %s, 
                    reward_risk_ratio = %s, 
                    status = 'WL-Active'
                WHERE ticker = %s
            """
            # NOTE: Removed 'notes' from parameters
            cursor.execute(query_watchlist, (entry, entry, stop, rr_decimal, ticker))
            
            query_delete_levels = "DELETE FROM stock_price_levels WHERE ticker = %s"
            cursor.execute(query_delete_levels, (ticker,))

            query_insert_level = """
                INSERT INTO stock_price_levels (ticker, price_level, notes, is_ignored_on_scan)
                VALUES (%s, %s, %s, FALSE)
            """
            cursor.execute(query_insert_level, (ticker, entry, "From Watchlist",))

            self.db_conn.commit()
            cursor.close()
            
            messagebox.showinfo("Success", f"{ticker} trade saved to watchlist and price level set to {entry}.")
            self.load_watchlist()
            self.plot_chart() 

        except Exception as e:
            self.db_conn.rollback()
            self.log_error("Database Error", f"Failed to add to watchlist: {e}")

    def remove_from_watchlist(self):
        """Resets the selected item in the watchlist to 'Pending'. [No changes needed]."""
        try:
            selected_item = self.watchlist_tree.focus()
            if not selected_item:
                self.log_error("Reset Error", "No trade selected from the watchlist.")
                return
            
            item = self.watchlist_tree.item(selected_item)
            watchlist_id = item['values'][0]
            ticker = item['values'][1]

            if not messagebox.askyesno("Confirm Reset", f"Reset {ticker} trade and set status to 'Pending'?"):
                return
                
            cursor = self.db_conn.cursor()
            # NOTE: Removed 'notes' from NULLing sequence
            query = """
                UPDATE watchlist
                SET price_level = NULL,
                    entry_price = NULL,
                    stop_loss = NULL,
                    reward_risk_ratio = NULL,
                    status = 'Pending'
                WHERE watchlist_id = %s
            """
            cursor.execute(query, (watchlist_id,))
            self.db_conn.commit()
            cursor.close()
            
            self.load_watchlist() 
            
        except Exception as e:
            self.db_conn.rollback()
            self.log_error("Database Error", f"Failed to reset trade: {e}")
            
    def load_trade_to_chart(self, event=None):
        """Loads a selected trade from the watchlist into the calculator AND chart. [Notes loading removed]."""
        try:
            selected_item = self.watchlist_tree.focus()
            if not selected_item:
                self.log_error("Load Error", "No trade selected from the watchlist.")
                return
            
            item = self.watchlist_tree.item(selected_item)
            values = item['values']            
            
            # The structure of 'values' is now: (id, ticker, full_name, status, rr, entry, stop)
            # [0] [1]      [2]         [3]      [4]  [5]     [6]    
            ticker = values[1]
            status = values[3]
            
            self.load_chart_for_ticker(ticker, check_watchlist=False)
            
            if status == 'Pending' or values[5] == "None":
                return

            entry = float(values[5])
            stop = float(values[6])
            rr = float(values[4])
            
            rr_string = "--"
            if entry > stop: 
                risk_amount = entry - stop
                reward_amount = rr * risk_amount
                target = entry + reward_amount
                rr_string = f"{rr:.2f} (Long)"
            elif entry < stop:
                risk_amount = stop - entry
                reward_amount = rr * risk_amount
                target = entry - reward_amount
                rr_string = f"{rr:.2f} (Short)"
            else:
                target = 0.0
                rr_string = "--"

            self.entry_var.set(entry)
            self.stop_var.set(stop)
            self.target_var.set(target)
            self.rr_var.set(rr_string)
        
            self.draw_trade_lines(redraw=True)
        
        except Exception as e:
            self.log_error("Load Error", f"Failed to load trade to chart: {e}")
    def save_strategy_and_levels(self):
        """
        Saves the content of the Strategy Context text box and the custom 
        Levels to Plot entry back to the stock_analysis table.
        """
        ticker = self.ticker_combo_var.get()
        if not ticker:
            self.log_error("Save Error", "No ticker is selected.")
            return

        try:
            # 1. Get Strategy (from Text widget)
            strategy = self.strategy_context_text.get("1.0", tk.END).strip()
            db_strategy = strategy if strategy else None

            # 2. Get Price Levels (from Entry widget)
            custom_levels = self.get_parsed_custom_levels()
            
            # Convert list of floats (custom_levels) to list of strings/Decimals for Postgres array
            # Postgres expects a list of numeric values, psycopg2 handles float/Decimal lists.
            # Convert back to Decimal/float to maintain consistency for the array type.
            db_price_levels = custom_levels if custom_levels else None

            # 3. UPSERT into stock_analysis table
            with psycopg2.connect(**self.db_config) as conn:
                with conn.cursor() as cursor:
                    # Note: We must also UPDATE the 'research' field if we fetched it, 
                    # but since this tab only edits 'strategy' and 'price_levels', 
                    # we must read the existing 'research' field first to avoid deleting it.
                    # Or, simplify the query to only update the fields this tab controls.

                    # --- OPTIMIZED QUERY: Read existing research first ---
                    cursor.execute("SELECT research FROM stock_analysis WHERE ticker = %s", (ticker,))
                    existing_research = cursor.fetchone()
                    db_research = existing_research[0] if existing_research and existing_research[0] else None

                    query = """
                        INSERT INTO stock_analysis (ticker, research, strategy, price_levels)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (ticker) DO UPDATE SET
                            research = EXCLUDED.research,       
                            strategy = EXCLUDED.strategy,
                            price_levels = EXCLUDED.price_levels
                    """
                    # We pass existing_research back in the INSERT VALUES, 
                    # and the ON CONFLICT clause updates the strategy and levels.
                    params = (ticker, db_research, db_strategy, db_price_levels)
                    cursor.execute(query, params)
                    conn.commit()

            messagebox.showinfo(
                "Success", f"Strategy and Price Levels for {ticker} updated successfully."
            )

        except Exception as e:
            self.log_error("Database Error", f"Failed to save strategy and levels: {e}")

    def check_and_load_from_watchlist(self, ticker):
        """Checks if a ticker is in the watchlist. If so, loads it into the calculator. [Notes loading removed]."""
        try:
            cursor = self.db_conn.cursor()
            # NOTE: Removed 'notes' from SELECT statement
            query = """
                SELECT status, reward_risk_ratio, entry_price, stop_loss
                FROM watchlist
                WHERE ticker = %s
            """
            cursor.execute(query, (ticker,))
            row = cursor.fetchone()
            cursor.close()

            if row:
                # Structure is now: (status, rr, entry, stop)
                status = row[0]
                rr = row[1]
                entry = row[2]
                stop = row[3]
                
                if status == 'Pending' or entry is None or stop is None or rr is None:
                    return
                
                entry = float(entry)
                stop = float(stop)
                rr = float(rr)

                rr_string = "--"
                if entry > stop:
                    risk_amount = entry - stop
                    reward_amount = rr * risk_amount
                    target = entry + reward_amount
                    rr_string = f"{rr:.2f} (Long)"
                elif entry < stop:
                    risk_amount = stop - entry
                    reward_amount = rr * risk_amount
                    target = entry - reward_amount
                    rr_string = f"{rr:.2f} (Short)"
                else:
                    target = 0.0
                    rr_string = "--"
                
                self.entry_var.set(entry)
                self.stop_var.set(stop)
                self.target_var.set(target)
                self.rr_var.set(rr_string)
                
                self.draw_trade_lines(redraw=True)
        
        except Exception as e:
            self.log_error("Watchlist Check Error", f"Failed to check watchlist for {ticker}: {e}")

    # --- Charting Functions ---
            
    def get_parsed_custom_levels(self):
        """Parses the custom levels entry into a list of valid Decimal prices."""
        custom_levels = []
        custom_levels_str = self.levels_interest_var.get().strip()
        if custom_levels_str:
            for level_str in custom_levels_str.split(','):
                try:
                    # Rounding to 2 decimals for precision
                    level = float(Decimal(level_str.strip()).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
                    custom_levels.append(level)
                except InvalidOperation:
                    print(f"Warning: Invalid price level '{level_str.strip()}' ignored.")
                except Exception:
                    continue
        return custom_levels


    def draw_trade_lines(self, redraw=True):
        """
        Adds/updates the trade calculator lines (Entry, Target, Stop)
        and redraws the chart.
        """
        if self.chart_df is None: 
            return

        try:
            entry = self.entry_var.get()
            target = self.target_var.get()
            stop = self.stop_var.get()          
            
            self.trade_lines = []
            if entry > 0: self.trade_lines.append(entry)
            if target > 0: self.trade_lines.append(target)
            if stop > 0: self.trade_lines.append(stop)
            
            if redraw:
                self.redraw_chart()
                
        except Exception as e:
            self.trade_lines = []
            
    def redraw_chart(self):
        """Clears and redraws the chart on the canvas, including custom levels."""
        
        if self.chart_df is None:
            return 

        try:
            if self.fig:
                self.fig.clear()
                
            all_hlines = []
            all_hline_colors = []
            all_hline_styles = []

            # 1. Add saved active trade level (purple, solid, thicker) - from stock_price_levels
            if self.price_levels:
                all_hlines.extend(self.price_levels)
                all_hline_colors.extend(['purple'] * len(self.price_levels))
                all_hline_styles.extend(['-'] * len(self.price_levels))

            # 2. Add trade calculator lines (blue, green, red) - from E, T, L inputs
            trade_line_colors = ['b', 'g', 'r']
            if self.trade_lines:
                for i, line_price in enumerate(self.trade_lines):
                    if line_price not in all_hlines: # Avoid duplicates with active trade level
                        all_hlines.append(line_price)
                        all_hline_colors.append(trade_line_colors[i % len(trade_line_colors)])
                        all_hline_styles.append('--')

            # 3. Add NEW Custom Interest Levels (Grey, dotted)
            custom_levels = self.get_parsed_custom_levels()
            if custom_levels:
                for level in custom_levels:
                     if level not in all_hlines:
                        all_hlines.append(level)
                        all_hline_colors.append('gray')
                        all_hline_styles.append('dotted')

            chart_title = f"{self.ticker_combo_var.get()} - {self.full_name_var.get()} - Daily"

            self.fig, self.ax = mpf.plot(
                self.chart_df,
                type='candle',
                style='yahoo',
                title=chart_title,
                ylabel='Price (Cents)',
                volume=True,
                mav=(20, 50, 200),
                hlines=dict(hlines=all_hlines, colors=all_hline_colors, linestyle=all_hline_styles, linewidths=1.4),
                figsize=(10, 6),
                returnfig=True 
            )

            if self.canvas:
                self.canvas.get_tk_widget().destroy()
            if self.toolbar:
                self.toolbar.destroy()
                
            self.canvas = FigureCanvasTkAgg(self.fig, master=self.chart_frame)
            self.canvas.draw()
            
            self.toolbar = NavigationToolbar2Tk(self.canvas, self.chart_frame, pack_toolbar=False)
            self.toolbar.update()
            self.toolbar.pack(side=tk.BOTTOM, fill=tk.X)
            
            self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=1)

            self.connect_chart_events()

        except Exception as e:
            self.log_error("Chart Redraw Error", f"Failed to redraw chart: {e}")

    # --- Other Functions (No changes needed) ---
    def load_tickers(self):
        """Loads tickers from stock_details into the combobox using a utility."""
        try:
            # We must use self.db_config here as AnalysisTab doesn't pass the live
            # connection to the utility function (it only passes DB_CONFIG).
            tickers = fetch_all_tickers(self.db_config)

            self.ticker_combo['values'] = tickers
            if tickers:
                self.ticker_combo_var.set(tickers[0])

        except Exception as e:
            self.log_error("Database Error", f"Failed to load tickers for chart: {e}")

    
            
    def plot_chart(self):
        """Fetches data and plots the candlestick chart."""
        ticker = self.ticker_combo_var.get()
        date_range_str = self.range_var.get()
        
        if not ticker:
            self.log_error("Input Error", "Please select a ticker.")
            return

        date_ranges = {
            "3 Months": 3,
            "6 Months": 6,
            "1 Year": 12,
            "2 Years": 24,
            "5 Years": 60
        }
        months = date_ranges.get(date_range_str, 12)
        start_date = (pd.to_datetime('today') - pd.DateOffset(months=months)).strftime('%Y-%m-%d')

        try:
            sql_query = """
                SELECT trade_date, open_price, high_price, low_price, close_price, volume
                FROM daily_stock_data
                WHERE ticker = %s AND trade_date >= %s
                ORDER BY trade_date ASC
            """
            
            df = pd.read_sql_query(
                sql_query,
                self.db_conn,
                params=(ticker, start_date),
                index_col='trade_date',
                parse_dates=['trade_date']
            )
            
            if df.empty:
                self.log_error("Data Error", f"No data found for {ticker} since {start_date}.")
                return

            df.rename(columns={
                'open_price': 'Open',
                'high_price': 'High',
                'low_price': 'Low',
                'close_price': 'Close',
                'volume': 'Volume'
            }, inplace=True)            
            
            self.chart_df = df
            
            self._load_upcoming_event_date(ticker)

            cursor = self.db_conn.cursor()
            cursor.execute(
                "SELECT price_level FROM stock_price_levels WHERE ticker = %s AND price_level IS NOT NULL",
                (ticker,)
            )
            self.price_levels = [float(row[0]) for row in cursor.fetchall()]
            cursor.close()
            
            self.draw_trade_lines(redraw=False)            

            self.redraw_chart()

        except Exception as e:
            self.log_error("Chart Error", f"Failed to load chart data: {e}")

    def _calculate_and_display_peg(self, ticker):
        """[No changes needed - uses threading logic]"""
        # [PEG calculation is handled in a background thread, logic is external]
        
        # (This function is part of the previous complex threading/DB optimization)
        # Assuming the rest of the threading logic (process_peg_queue, _calculate_peg_in_thread, etc.) remains unchanged.
        # Placeholder to remind that the PEG logic is still active:
        self._start_peg_calculation(ticker)
    def _calculate_peg_in_thread(self, ticker):
        """
        Runs in a background thread to fetch all data and calculate PEG.
        """
        worker_conn = None
        try:
            worker_conn = psycopg2.connect(**self.db_config)
            cursor = worker_conn.cursor()

            # 1. Get P (Current Price)
            query_price = """
                SELECT close_price FROM daily_stock_data
                WHERE ticker = %s ORDER BY trade_date DESC LIMIT 1
            """
            cursor.execute(query_price, (ticker,))
            result = cursor.fetchone()
            
            # Ensure a row was returned AND the value in the row is not None
            if result and result[0] is not None:
                price = float(result[0])
            else:
                price = None
            
            if price is None or price <= 0:
                self.peg_queue.put(('ERROR', "N/A (No Price or Price <= 0)"))
                return

            # 2. Get ALL historical earnings data in ONE query
            query_earnings = """
                SELECT period, results_date, heps FROM historical_earnings
                WHERE ticker = %s ORDER BY results_date DESC
            """
            # Use psycopg2.extras.DictCursor to fetch as dict for easier key access
            with worker_conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as dict_cursor:
                dict_cursor.execute(query_earnings, (ticker,))
                # Fetch as a list of dictionaries for easier processing
                all_earnings = [
                    {'period': row['period'], 'results_date': row['results_date'], 'heps': Decimal(row['heps'])}
                    for row in dict_cursor.fetchall()
                ]

            if not all_earnings:
                self.peg_queue.put(('ERROR', "N/A (No Earnings)"))
                return

            # 3. Get E (TTM HEPS) - calculated in-memory
            ttm_heps = self._thread_calc_ttm_heps(all_earnings)
            if ttm_heps is None or ttm_heps == 0:
                self.peg_queue.put(('ERROR', "N/A (No TTM HEPS)"))
                return

            # 4. Get G (Growth Rate) - calculated in-memory
            growth_result = self._thread_calc_growth(all_earnings)
            if growth_result is None:
                self.peg_queue.put(('ERROR', "N/A (No Growth)"))
                return
                
            growth_rate, growth_type = growth_result
            if growth_rate <= 0:
                self.peg_queue.put(('ERROR', "N/A (Neg Growth)"))
                return

            # 5. Calculate P/E
            # Need to convert Decimal to float for division
            pe_ratio = price / float(ttm_heps) 
            
            # 6. Calculate PEG
            peg_ratio = pe_ratio / growth_rate
            peg_str = f"{peg_ratio:.2f} ({growth_type})"
            
            # 7. Calculate PEG 1 Price (Price = G * E)
            peg_1_price = growth_rate * float(ttm_heps)
            peg_1_price_str = f"{peg_1_price:.2f}c"

            # 8. Send final result to the queue
            self.peg_queue.put(('SUCCESS', peg_str, peg_1_price_str))

        except Exception as e:
            print(f"PEG THREAD ERROR: {e}")
            self.peg_queue.put(('ERROR', "Error"))
        finally:
            if worker_conn:
                worker_conn.close()

    def _thread_calc_ttm_heps(self, all_earnings):
        """In-memory TTM HEPS calculator. all_earnings is sorted DESC."""
        # This function relies on get_year_from_period from utils
        from utils import get_year_from_period 
        
        if not all_earnings:
            return None
            
        latest = all_earnings[0]
        period, heps = latest['period'], latest['heps']
        
        if 'FY' in period:
            return heps # Full year is already TTM
        
        if 'H1' in period:
            current_h1_heps = heps
            year = get_year_from_period(period)
            if year is None: return None
            
            prev_year_str = str(year - 1)
            prev_fy_heps = None
            prev_h1_heps = None
            
            # Find the data in the list (no new queries)
            for entry in all_earnings:
                if (f"FY {prev_year_str}" in entry['period'] or 
                    f"{prev_year_str} FY" in entry['period']):
                    prev_fy_heps = entry['heps']
                if (f"H1 {prev_year_str}" in entry['period'] or 
                    f"{prev_year_str} H1" in entry['period']):
                    prev_h1_heps = entry['heps']
                    
            if prev_fy_heps is not None and prev_h1_heps is not None:
                prev_h2_heps = prev_fy_heps - prev_h1_heps
                ttm_heps = prev_h2_heps + current_h1_heps
                return ttm_heps
        return None

    def _thread_calc_growth(self, all_earnings):
        """In-memory Growth calculator. all_earnings is sorted DESC."""
        # This function relies on get_year_from_period from utils
        from utils import get_year_from_period 

        # 1. Try 1-year H1 growth
        h1_entries = [e for e in all_earnings if 'H1' in e['period']]
        if len(h1_entries) >= 2:
            current_h1 = h1_entries[0]
            prev_h1 = h1_entries[1]
            current_year = get_year_from_period(current_h1['period'])
            prev_year = get_year_from_period(prev_h1['period'])
            
            if current_year and prev_year and current_year == prev_year + 1 and prev_h1['heps'] > 0:
                growth = (current_h1['heps'] / prev_h1['heps']) - 1
                return float(growth * 100), "1Y H1"
                
        # 2. Fallback to FY CAGR
        fy_entries = [e for e in all_earnings if 'FY' in e['period']] # Already sorted DESC
        
        for num_years in [3, 2, 1]:
            if len(fy_entries) >= num_years + 1:
                e_newest = fy_entries[0]['heps']
                e_oldest = fy_entries[num_years]['heps']
                
                if e_oldest > 0:
                    cagr = ((e_newest / e_oldest) ** (Decimal(1) / Decimal(num_years))) - 1
                    return float(cagr * 100), f"{num_years}Y FY"
                    
        return None

    def _start_peg_calculation(self, ticker):
        """Starts the background thread to calculate and display PEG."""
        # Assuming the implementation of this function (not provided in this prompt's context, but known to exist)
        # handles putting the STARTING message into the queue and starting the thread.
        # This placeholder is to ensure load_chart_for_ticker calls the PEG logic.
        if hasattr(self, 'peg_queue'):
             self.peg_queue.put(('STARTING',))
             threading.Thread(
                 target=self._calculate_peg_in_thread, 
                 args=(ticker,), 
                 daemon=True
             ).start()
        else:
             print("Warning: PEG queue not initialized.")
    def process_refresh_queue(self):
        """Processes messages from the refresh thread queue."""
        try:
            while not self.refresh_queue.empty():
                message = self.refresh_queue.get_nowait()
                
                if message == "---REFRESH-COMPLETE---":
                    self.refresh_button.config(state='normal')
                    self.load_chart_button.config(state='normal')
                    # This single call will reload the chart AND recalculate the PEG
                    self.on_load_chart_button_pressed()
                
                elif message == "---REFRESH-STARTED---":
                    self.refresh_button.config(state='disabled')
                    self.load_chart_button.config(state='disabled')
                
        except queue.Empty:
            pass
        finally:
            self.after(200, self.process_refresh_queue)

    def refresh_price_worker(self, ticker):
        """
        Runs in a background thread to download and save latest price
        for a SINGLE stock.
        """
        worker_conn = None
        try:
            worker_conn = psycopg2.connect(**self.db_config)
            cursor = worker_conn.cursor()
            
            data = yf.download(ticker, period="2d", auto_adjust=True)
            
            if data.empty:
                print(f"DEBUG (Refresh Worker): No data returned by yfinance for {ticker}.")
                return

            latest_data = data.iloc[-1]
            trade_date = latest_data.name.date()
            
            # --- START DEBUG BLOCK ---
            # --- CORRECTION: Use .iloc[0] to access the scalar value from the Series object ---
            raw_open = latest_data.get('Open').iloc[0]
            raw_high = latest_data.get('High').iloc[0]
            raw_low = latest_data.get('Low').iloc[0]
            raw_close = latest_data.get('Close').iloc[0]
            raw_volume = latest_data.get('Volume').iloc[0]
            
            print(f"DEBUG (Refresh Worker): Raw yf Data for {trade_date}:")
            print(f"  Open: {raw_open}, High: {raw_high}")
            print(f"  Low: {raw_low}, Close: {raw_close}")
            print(f"  Volume: {raw_volume}")
            
            # Convert prices using the utility
            open_cents = convert_yf_price_to_cents(raw_open)
            high_cents = convert_yf_price_to_cents(raw_high)
            low_cents = convert_yf_price_to_cents(raw_low)
            close_cents = convert_yf_price_to_cents(raw_close)
            
            # Volume conversion is now safe
            try:
                volume = int(raw_volume)
            except Exception:
                volume = None
            
            print(f"DEBUG (Refresh Worker): Cents Conversion Output:")
            print(f"  Open Cents: {open_cents}, Close Cents: {close_cents}")
            print(f"  Volume Int: {volume}")
            
            # --- END DEBUG BLOCK ---

            # 4. Save to DB
            query = """
                INSERT INTO daily_stock_data 
                    (ticker, trade_date, open_price, high_price, low_price, close_price, volume)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticker, trade_date) DO UPDATE SET
                    open_price = EXCLUDED.open_price,
                    high_price = EXCLUDED.high_price,
                    low_price = EXCLUDED.low_price,
                    close_price = EXCLUDED.close_price,
                    volume = EXCLUDED.volume
            """
            # Ensure price fields are only saved if they converted successfully (not None)
            cursor.execute(query, (ticker, trade_date, open_cents, high_cents, low_cents, close_cents, volume))
            worker_conn.commit()
            
        except Exception as e:
            # ... rest of the function ...
            self.log_error("Refresh Error", f"An unexpected error occurred during price refresh: {e}")
            if worker_conn:
                worker_conn.rollback()
        finally:
            if worker_conn:
                worker_conn.close()
            # Send signal to re-enable buttons
            self.refresh_queue.put("---REFRESH-COMPLETE---")
    
    def process_peg_queue(self):
        """Processes PEG calculation results from the background thread."""
        try:
            while not self.peg_queue.empty():
                message = self.peg_queue.get_nowait()
                
                if message[0] == 'SUCCESS':
                    # Unpack the results
                    peg_str, peg_1_price_str = message[1], message[2]
                    self.peg_var.set(peg_str)
                    self.peg_1_price_var.set(peg_1_price_str)
                    
                elif message[0] == 'STARTING':
                    self.peg_var.set("Loading...")
                    self.peg_1_price_var.set("Loading...")
                    
                elif message[0] == 'ERROR':
                    # Set the error string
                    error_message = message[1]
                    self.peg_var.set(error_message)
                    self.peg_1_price_var.set("--")

        except queue.Empty:
            pass
        finally:
            self.after(200, self.process_peg_queue)

    
    
    def start_refresh_price_thread(self):
        """Starts the background thread for refreshing a single price."""
        # Placeholder for price refresh logic
        if hasattr(self, 'refresh_queue'):
            self.refresh_queue.put("---REFRESH-STARTED---")
            threading.Thread(
                target=self.refresh_price_worker, 
                args=(self.ticker_combo_var.get(),), 
                daemon=True
            ).start()
    
    

    

    # [Other utility functions remain the same]
    def sort_watchlist_by_ticker(self):
        """Sorts the watchlist treeview by the ticker column when clicked."""
        print("DEBUG: Sorting watchlist by ticker...")
        
        # 1. Get all items from the tree
        items = self.watchlist_tree.get_children('')
        if not items:
            return

        # 2. Extract data (ticker, and all values)
        data_list = []
        for item in items:
            values = self.watchlist_tree.item(item, 'values')
            tags = self.watchlist_tree.item(item, 'tags')
            # Ticker is at index [1] in the current structure: (id, ticker, full_name, ...)
            data_list.append((values[1], values, tags)) 

        # 3. Sort the data based on the ticker (values[1])
        data_list.sort(key=lambda x: x[0], reverse=self.watchlist_sort_reverse)
        
        # 4. Toggle the sort direction for the next click
        self.watchlist_sort_reverse = not self.watchlist_sort_reverse
        
        # 5. Clear and re-insert items in sorted order
        self.watchlist_tree.delete(*items)
        for (ticker, values, tags) in data_list:
            self.watchlist_tree.insert('', 'end', values=values, tags=tags)

    def sort_watchlist_by_name(self):
        """Sorts the watchlist treeview by the name column when clicked."""
        print("DEBUG: Sorting watchlist by name...")
        
        items = self.watchlist_tree.get_children('')
        if not items:
            return

        data_list = []
        for item in items:
            values = self.watchlist_tree.item(item, 'values')
            tags = self.watchlist_tree.item(item, 'tags')
            # Full Name is at index [2] in the current structure
            data_list.append((values[2], values, tags)) 

        data_list.sort(key=lambda x: x[0], reverse=self.name_sort_reverse)
        
        self.name_sort_reverse = not self.name_sort_reverse
        
        self.watchlist_tree.delete(*items)
        for (name, values, tags) in data_list:
            self.watchlist_tree.insert('', 'end', values=values, tags=tags)

    def _set_selected_watchlist_status(self, status_string):
        """Helper function to update the status of the selected item."""
        try:
            selected_item = self.watchlist_tree.focus()
            if not selected_item:
                return
            
            item = self.watchlist_tree.item(selected_item)
            # The watchlist_id is at index 0
            watchlist_id = item['values'][0]
            
            cursor = self.db_conn.cursor()
            query = "UPDATE watchlist SET status = %s WHERE watchlist_id = %s"
            cursor.execute(query, (status_string, watchlist_id))
            self.db_conn.commit()
            cursor.close()
            
            self.load_watchlist() # Refresh the view
            
        except Exception as e:
            self.db_conn.rollback()
            self.log_error("Watchlist Update Error", f"Failed to update status: {e}")

    def on_watchlist_right_click(self, event):
        """Shows the context menu on right-click."""
        row_id = self.watchlist_tree.identify_row(event.y)
        if row_id:
            self.watchlist_tree.focus(row_id)
            self.watchlist_tree.selection_set(row_id)
            self.watchlist_context_menu.post(event.x_root, event.y_root)

    def set_watchlist_status_active_trade(self):
        """Marks the selected watchlist item as 'Active-Trade'."""
        self._set_selected_watchlist_status('Active-Trade')

    def set_watchlist_status_pretrade(self):
        """Marks the selected watchlist item as 'Pre-Trade'."""
        self._set_selected_watchlist_status('Pre-Trade')

    def set_watchlist_status_wl_active(self):
        """Marks the selected watchlist item as 'WL-Active'."""
        self._set_selected_watchlist_status('WL-Active')

    def set_watchlist_status_wl_sleep(self):
        """Marks the selected watchlist item as 'WL-Sleep'."""
        self._set_selected_watchlist_status('WL-Sleep')

    def set_watchlist_status_pending(self):
        """Marks the selected watchlist item as 'Pending'."""
        self._set_selected_watchlist_status('Pending')

    def on_load_chart_button_pressed(self, event=None):
        """
        Handles the 'Load Chart' button click from the ticker dropdown.
        It calls the main loader, telling it to fetch relevant data.
        """
        ticker = self.ticker_combo_var.get()
        
        # Call the main loader, telling it to check the watchlist (WL-Active, etc.)
        self.load_chart_for_ticker(ticker, check_watchlist=True)
    
    def _calculate_days_from_row_data(self, row_data):
        """
        Calculates days to next event from an existing data row
        (from stock_details) to avoid N+1 queries.
        
        Assumes row_data contains:
        (earnings_q1, earnings_q2, earnings_q3, earnings_q4,
         update_q1, update_q2, update_q3, update_q4)
        """
        try:
            # Assumes the 8 date columns are the last 8 items in the tuple
            all_dates = [d for d in row_data if d is not None]

            today = date.today()
            closest_days = float('inf')
            
            # Use 365 days as the max search range, though any large number would work here
            MAX_DAYS_AWAY = 365             
            
            for event_date in all_dates:
                # Calculate the days away using the shared utility logic
                days_away, _ = calculate_next_event_hit(
                    event_date, today, MAX_DAYS_AWAY
                )
                
                if days_away is not None and days_away < closest_days:
                    closest_days = days_away
            
            return closest_days

        except Exception as e:
            print(f"Error in _calculate_days_from_row_data: {e}")
            return float('inf')
    
    # In tab_analysis.py

    def calculate_rr(self, *args):
        """
        Calculates the Reward/Risk ratio by calling the external utility 
        and updates the GUI label.
        """
        try:
            ratio, type_str = calculate_rr_ratio(
                self.entry_var.get(), 
                self.target_var.get(), 
                self.stop_var.get()
            )
            
            if ratio is not None:
                self.rr_var.set(f"{ratio:.2f} ({type_str})")
            else:
                self.rr_var.set(type_str)

        except Exception:
            self.rr_var.set("--")