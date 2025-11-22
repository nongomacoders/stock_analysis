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
