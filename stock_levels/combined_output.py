# Combined Python Script
# Generated from files matching: tab*.py


############################################################
# SOURCE FILE: tab_analysis.py
############################################################

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


############################################################
# SOURCE FILE: tab_details.py
############################################################

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
            




############################################################
# SOURCE FILE: tab_earnings.py
############################################################

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



############################################################
# SOURCE FILE: tab_logs.py
############################################################

import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
import psycopg2
from database_utils import fetch_analysis_record

class LogsTab(ttk.Frame):
    """
    This class represents the "Action Log" tab, for reviewing
    AI-generated analysis from the SENS and Price triggers.
    """

    def __init__(self, parent, db_config, log_error_func):
        super().__init__(parent, padding=10)

        self.db_config = db_config
        self.log_error = log_error_func

        # State tracking
        self.selected_log_id = None
        self.selected_ticker = None
        self.current_is_read = None

        self.show_all_var = tk.BooleanVar(value=False)

        self.create_widgets()
        self.load_logs()

    def create_widgets(self):
        """Creates the main GUI layout for this tab."""

        # --- Create the two-panel layout ---
        self.paned_window = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.paned_window.pack(expand=True, fill="both")

        # --- Left Panel: Log List ---
        left_panel = ttk.Frame(self.paned_window, padding=5)
        self.paned_window.add(left_panel, weight=2)  # Give logs more space

        # Filter/Refresh frame
        filter_frame = ttk.Frame(left_panel)
        filter_frame.pack(fill=tk.X, pady=(0, 5))

        self.refresh_button = ttk.Button(
            filter_frame, text="Refresh", command=self.load_logs
        )
        self.refresh_button.pack(side=tk.LEFT, padx=(0, 10))

        self.show_all_check = ttk.Checkbutton(
            filter_frame,
            text="Show All (Include Read)",
            variable=self.show_all_var,
            onvalue=True,
            offvalue=False,
            command=self.load_logs,
        )
        self.show_all_check.pack(side=tk.LEFT)

        # Treeview for log list
        log_cols = (
            "log_id",
            "is_read",
            "timestamp",
            "ticker",
            "trigger_type",
            "headline",
        )
        self.logs_tree = ttk.Treeview(left_panel, columns=log_cols, show="headings")

        self.logs_tree.heading("is_read", text="Read?")
        self.logs_tree.heading("timestamp", text="Date")
        self.logs_tree.heading("ticker", text="Ticker")
        self.logs_tree.heading("trigger_type", text="Trigger")
        self.logs_tree.heading("headline", text="Headline")

        self.logs_tree.column("log_id", width=0, stretch=tk.NO)  # Hidden
        self.logs_tree.column("is_read", width=50, stretch=tk.NO, anchor=tk.CENTER)
        self.logs_tree.column("timestamp", width=130, stretch=tk.NO)
        self.logs_tree.column("ticker", width=80, stretch=tk.NO)
        self.logs_tree.column("trigger_type", width=70, stretch=tk.NO)
        self.logs_tree.column("headline", width=300)

        # Add bold tag for unread items
        self.logs_tree.tag_configure("Unread", font=("TkDefaultFont", 9, "bold"))

        # Scrollbar
        scrollbar = ttk.Scrollbar(
            left_panel, orient=tk.VERTICAL, command=self.logs_tree.yview
        )
        self.logs_tree.configure(yscroll=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.logs_tree.pack(expand=True, fill="both")

        self.logs_tree.bind("<<TreeviewSelect>>", self.on_log_select)

        # --- Right Panel: Details Editor ---
        right_panel = ttk.Frame(self.paned_window, padding=10)
        self.paned_window.add(right_panel, weight=3)  # Give editor more space

        self.details_frame = ttk.LabelFrame(
            right_panel, text="Log Details: -", padding=15
        )
        self.details_frame.pack(expand=True, fill="both")

        # Button frame
        button_frame = ttk.Frame(self.details_frame)
        button_frame.pack(fill=tk.X, pady=(0, 10))

        self.toggle_read_button = ttk.Button(
            button_frame, text="Mark as...", command=self.toggle_log_read_status
        )
        self.toggle_read_button.pack(side=tk.LEFT, padx=(0, 10))

        self.save_button = ttk.Button(
            button_frame,
            text="Save Research/Strategy",
            command=self.save_research_strategy,
        )
        self.save_button.pack(side=tk.RIGHT)

        # --- Details Notebook ---
        self.details_notebook = ttk.Notebook(self.details_frame)
        self.details_notebook.pack(expand=True, fill="both")

        # --- Tab 1: AI Analysis ---
        ai_tab = ttk.Frame(self.details_notebook, padding=5)
        self.details_notebook.add(ai_tab, text="AI Analysis")

        self.ai_text = tk.Text(
            ai_tab, height=15, width=60, wrap=tk.WORD, font=("TkDefaultFont", 9)
        )
        self.ai_text.pack(expand=True, fill="both", side=tk.LEFT)
        ai_scroll = ttk.Scrollbar(
            ai_tab, orient=tk.VERTICAL, command=self.ai_text.yview
        )
        self.ai_text.configure(yscroll=ai_scroll.set)
        ai_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # --- Tab 2: Master Research ---
        research_tab = ttk.Frame(self.details_notebook, padding=5)
        self.details_notebook.add(research_tab, text="Master Research")

        self.research_text = tk.Text(
            research_tab, height=15, width=60, wrap=tk.WORD, font=("TkDefaultFont", 9)
        )
        self.research_text.pack(expand=True, fill="both", side=tk.LEFT)
        research_scroll = ttk.Scrollbar(
            research_tab, orient=tk.VERTICAL, command=self.research_text.yview
        )
        self.research_text.configure(yscroll=research_scroll.set)
        research_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # --- Tab 3: Master Strategy ---
        strategy_tab = ttk.Frame(self.details_notebook, padding=5)
        self.details_notebook.add(strategy_tab, text="Master Strategy")

        self.strategy_text = tk.Text(
            strategy_tab, height=15, width=60, wrap=tk.WORD, font=("TkDefaultFont", 9)
        )
        self.strategy_text.pack(expand=True, fill="both", side=tk.LEFT)
        strategy_scroll = ttk.Scrollbar(
            strategy_tab, orient=tk.VERTICAL, command=self.strategy_text.yview
        )
        self.strategy_text.configure(yscroll=strategy_scroll.set)
        strategy_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # --- Set initial state ---
        self.clear_details_form()

    def set_details_state(self, state):
        """Disables or enables all widgets in the details panel."""
        self.toggle_read_button.config(state=state)
        self.save_button.config(state=state)
        # Notebook tabs must be handled differently
        if state == "disabled":
            # Disable text widgets and hide tabs from notebook
            self.ai_text.config(state="disabled")
            self.research_text.config(state="disabled")
            self.strategy_text.config(state="disabled")
        else:
            # Enable text widgets
            self.ai_text.config(state="normal")  # Will be set to disabled after loading
            self.research_text.config(state="normal")
            self.strategy_text.config(state="normal")

    def clear_details_form(self):
        """Clears all text boxes and disables the panel."""
        self.details_frame.config(text="Log Details: -")

        self.set_details_state("normal")  # Enable to clear
        self.ai_text.delete("1.0", tk.END)
        self.research_text.delete("1.0", tk.END)
        self.strategy_text.delete("1.0", tk.END)
        self.set_details_state("disabled")  # Disable

        self.toggle_read_button.config(text="Mark as...")

        self.selected_log_id = None
        self.selected_ticker = None
        self.current_is_read = None

    def load_logs(self):
        """Fetches logs from the action_log table and populates the tree."""
        self.clear_details_form()

        try:
            with psycopg2.connect(**self.db_config) as conn:
                with conn.cursor() as cursor:

                    base_query = """
                        SELECT log_id, log_timestamp, ticker, trigger_type, trigger_content, is_read 
                        FROM action_log
                    """
                    if not self.show_all_var.get():
                        base_query += " WHERE is_read = FALSE"

                    base_query += " ORDER BY log_timestamp DESC"

                    cursor.execute(base_query)

                    # Clear existing items
                    self.logs_tree.delete(*self.logs_tree.get_children())

                    # Insert new items
                    for row in cursor.fetchall():
                        log_id, ts, ticker, trigger, content, is_read = row

                        read_str = "Yes" if is_read else "No"
                        tag = "Read" if is_read else "Unread"
                        ts_str = ts.strftime("%Y-%m-%d %H:%M:%S")

                        values = (log_id, read_str, ts_str, ticker, trigger, content)
                        self.logs_tree.insert("", tk.END, values=values, tags=(tag,))

        except Exception as e:
            self.log_error("Database Error", f"Failed to load action log: {e}")

    def on_log_select(self, event):
        """Called when a user clicks on a log in the tree."""
        try:
            selected_item = self.logs_tree.focus()
            if not selected_item:
                return

            item = self.logs_tree.item(selected_item)
            values = item["values"]

            # (log_id, is_read, timestamp, ticker, trigger_type, headline)
            self.selected_log_id = values[0]
            self.current_is_read = values[1] == "Yes"  # Store as boolean
            self.selected_ticker = values[3]

            self.details_frame.config(
                text=f"Log Details: {self.selected_ticker} ({values[4]} @ {values[2]})"
            )

            # Set button text
            if self.current_is_read:
                self.toggle_read_button.config(text="Mark as UNREAD")
            else:
                self.toggle_read_button.config(text="Mark as READ")

            # Enable panel
            self.set_details_state("normal")

            # --- Load Data ---
            # Clear text boxes
            self.ai_text.delete("1.0", tk.END)
            self.research_text.delete("1.0", tk.END)
            self.strategy_text.delete("1.0", tk.END)

            with psycopg2.connect(**self.db_config) as conn:
                with conn.cursor() as cursor:
                    # 1. Get full AI analysis
                    cursor.execute(
                        "SELECT ai_analysis FROM action_log WHERE log_id = %s",
                        (self.selected_log_id,),
                    )
                    ai_result = cursor.fetchone()
                    if ai_result:
                        self.ai_text.insert("1.0", ai_result[0])

                    # 2. Get Research & Strategy using utility
                    analysis_result = fetch_analysis_record(self.db_config, self.selected_ticker)

                    if analysis_result:
                        # analysis_result is (research, strategy, price_levels)
                        research, strategy, _ = analysis_result 

                        if research:
                            self.research_text.insert("1.0", research)
                        if strategy:
                            self.strategy_text.insert("1.0", strategy)

            # Set AI text to read-only *after* inserting
            self.ai_text.config(state="disabled")

        except Exception as e:
            self.log_error("Selection Error", f"Error loading log details: {e}")
            self.clear_details_form()

    def toggle_log_read_status(self):
        """Toggles the is_read flag for the selected log item."""
        if self.selected_log_id is None or self.current_is_read is None:
            self.log_error("Input Error", "No log item selected.")
            return

        new_status = not self.current_is_read  # Flip the boolean

        try:
            with psycopg2.connect(**self.db_config) as conn:
                with conn.cursor() as cursor:
                    query = "UPDATE action_log SET is_read = %s WHERE log_id = %s"
                    cursor.execute(query, (new_status, self.selected_log_id))
                    conn.commit()

            # Refresh the list to show the change
            self.load_logs()

        except Exception as e:
            self.log_error("Database Error", f"Failed to update log status: {e}")

    def save_research_strategy(self):
        """Saves the content of the Research and Strategy text boxes."""
        if not self.selected_ticker:
            self.log_error("Save Error", "No ticker is selected.")
            return

        try:
            # Get data from widgets
            research = self.research_text.get("1.0", tk.END).strip()
            strategy = self.strategy_text.get("1.0", tk.END).strip()

            # Convert empty text to None for the database
            db_research = research if research else None
            db_strategy = strategy if strategy else None

            # Use an UPSERT (INSERT ON CONFLICT) command
            with psycopg2.connect(**self.db_config) as conn:
                with conn.cursor() as cursor:
                    query = """
                        INSERT INTO stock_analysis (ticker, research, strategy)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (ticker) DO UPDATE SET
                            research = EXCLUDED.research,
                            strategy = EXCLUDED.strategy
                    """
                    params = (self.selected_ticker, db_research, db_strategy)
                    cursor.execute(query, params)
                    conn.commit()

            messagebox.showinfo(
                "Success", f"Master analysis for {self.selected_ticker} saved."
            )

        except Exception as e:
            self.log_error("Database Error", f"Failed to save analysis: {e}")



############################################################
# SOURCE FILE: tab_portfolio.py
############################################################

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



############################################################
# SOURCE FILE: tab_scan.py
############################################################

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


############################################################
# SOURCE FILE: tab_strategy.py
############################################################

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

