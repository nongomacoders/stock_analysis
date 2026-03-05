import ttkbootstrap as ttk
from ttkbootstrap.constants import TOP, X, LEFT, RIGHT, BOTH, VERTICAL, Y, W, END
from tkinter import Menu
from datetime import date

# Ensure 'delete_todo' is available in your data module
from modules.data.todos import (
    get_todos,
    update_todo_status,
    add_todo,
    delete_todo,
    update_todo,
)
from modules.data.market import get_all_tickers_and_names


class TodoWidget(ttk.Frame):
    """A widget that displays a list of daily TODO tasks."""

    def __init__(self, parent, async_run, async_run_bg, notifier, on_select_callback=None):
        super().__init__(parent)
        self.async_run = async_run
        self.async_run_bg = async_run_bg
        self.notifier = notifier
        self.on_select = on_select_callback
        self.stock_list = []  # To store [{"ticker": "...", "full_name": "..."}]
        self.stock_name_map = {}

        # Listen for DB notifications to auto-refresh the list (non-blocking)
        try:
            self.async_run_bg(self.notifier.add_listener("daily_todos_changes", self.on_todo_notification))
        except Exception:
            # fallback to synchronous registration if background runner isn't available
            try:
                self.async_run(self.notifier.add_listener("daily_todos_changes", self.on_todo_notification))
            except Exception:
                pass

        self.create_widgets()
        self.refresh_todos()
        self.load_stocks()

    def on_todo_notification(self, payload: str):
        """Callback for DB notifications to reload the TODO list."""
        self.after(0, self.refresh_todos)

    def load_stocks(self):
        """Load tickers and full names for the searchable combo."""

        def on_stocks_loaded(data):
            self.stock_list = data
            self.stock_name_map = {s["ticker"]: s["full_name"] for s in data}
            self.update_combo_values(self.ticker_combo)
            self.refresh_todos()

        self.async_run_bg(get_all_tickers_and_names(), callback=on_stocks_loaded)

    def update_combo_values(self, combo, target_list=None):
        """Update the combobox values based on search query or full list."""
        if target_list is None:
            # Format: 'TICKER - Company Name'
            values = [f"{s['ticker']} - {s['full_name']}" for s in self.stock_list]
        else:
            values = target_list

        combo["values"] = values

    def on_combo_search(self, event, combo):
        """Filter the combobox values based on user input without losing focus."""
        # Skip functional keys
        if event.keysym in ("Up", "Down", "Return", "Escape", "Left", "Right", "Control_L", "Control_R"):
            return

        value = combo.get().strip().upper()
        if not value:
            self.update_combo_values(combo)
        else:
            filtered = [
                f"{s['ticker']} - {s['full_name']}"
                for s in self.stock_list
                if value in s["ticker"].upper() or value in s["full_name"].upper()
            ]
            self.update_combo_values(combo, filtered)

    def extract_ticker(self, combo_value):
        """Extract ticker from 'TICKER - Company Name' string."""
        if " - " in combo_value:
            return combo_value.split(" - ")[0].strip()
        return combo_value.strip()

    def create_widgets(self):
        """Creates the content for the Daily TODO tab."""
        # --- INPUT FRAME (Top) ---
        input_frame = ttk.Frame(self)
        input_frame.pack(side=TOP, fill=X, padx=5, pady=10)

        # 1. Title Input
        ttk.Label(input_frame, text="Task:").pack(side=LEFT, padx=(5, 2))
        self.title_entry = ttk.Entry(input_frame, width=30)
        self.title_entry.pack(side=LEFT, padx=2)
        self.title_entry.bind("<Return>", lambda e: self.add_task())

        # 2. Ticker Input (Searchable Combobox)
        ttk.Label(input_frame, text="Ticker:").pack(side=LEFT, padx=(10, 2))
        self.ticker_combo = ttk.Combobox(input_frame, width=25)
        self.ticker_combo.pack(side=LEFT, padx=2)

        # Bind search behavior
        self.ticker_combo.bind(
            "<KeyRelease>", lambda e: self.on_combo_search(e, self.ticker_combo)
        )

        # 3. Priority Input
        ttk.Label(input_frame, text="Pri:").pack(side=LEFT, padx=(10, 2))
        self.priority_combo = ttk.Combobox(
            input_frame, values=["low", "medium", "high"], state="readonly", width=8
        )
        self.priority_combo.set("medium")
        self.priority_combo.pack(side=LEFT, padx=2)

        # 4. Add Button
        self.add_btn = ttk.Button(
            input_frame, text="Add", command=self.add_task, bootstyle="success"
        )
        self.add_btn.pack(side=LEFT, padx=10)

        # --- TREEVIEW (Main) ---
        cols = ("Date", "Priority", "Title", "Ticker", "Name", "Upside", "Status")
        self.todo_tree = ttk.Treeview(self, columns=cols, show="headings")
        self.todo_tree.heading("Date", text="Date")
        self.todo_tree.heading("Priority", text="Priority")
        self.todo_tree.heading("Title", text="Title")
        self.todo_tree.heading("Ticker", text="Ticker")
        self.todo_tree.heading("Name", text="Name")
        self.todo_tree.heading("Upside", text="Upside")
        self.todo_tree.heading("Status", text="Status")

        self.todo_tree.column("Date", width=100, anchor=W, stretch=False)
        self.todo_tree.column("Priority", width=80, anchor=W, stretch=False)
        self.todo_tree.column("Title", width=350, anchor=W, stretch=True)
        self.todo_tree.column("Ticker", width=80, anchor=W, stretch=False)
        self.todo_tree.column("Name", width=200, anchor=W, stretch=False)
        self.todo_tree.column("Upside", width=120, anchor=W, stretch=False)
        self.todo_tree.column("Status", width=80, anchor=W, stretch=False)

        # Scrollbar
        scrolly = ttk.Scrollbar(self, orient=VERTICAL, command=self.todo_tree.yview)
        self.todo_tree.configure(yscroll=scrolly.set)

        scrolly.pack(side=RIGHT, fill=Y)
        self.todo_tree.pack(fill=BOTH, expand=True)

        # Data map
        self.todo_map = {}

        # --- STYLES & BINDINGS ---
        self.todo_tree.tag_configure("done", foreground="grey")
        self.todo_tree.tag_configure(
            "deferred", foreground="#d97706", font=("Segoe UI", 9, "italic")
        )

        # Bindings
        self.create_context_menu()
        self.todo_tree.bind("<Button-3>", self.show_context_menu)  # Right Click
        self.todo_tree.bind("<<TreeviewSelect>>", self.on_row_click)
        self.todo_tree.bind(
            "<Double-1>", self.on_double_click
        )  # Double Click (Toggle Status)

    def on_row_click(self, event):
        """Handle selection to trigger callback (e.g. show charts/research)."""
        selection = self.todo_tree.selection()
        if not selection or not self.on_select:
            return

        item_id = selection[0]
        if item_id not in self.todo_map:
            return

        ticker = self.todo_map[item_id].get("ticker")
        if ticker and ticker != "-":
            self.on_select(ticker)

    def create_context_menu(self):
        """Creates the right-click menu."""
        self.context_menu = Menu(self, tearoff=0)
        self.context_menu.add_command(
            label="Edit Task", command=self.edit_todo
        )
        self.context_menu.add_separator()
        self.context_menu.add_command(
            label="Mark Active", command=lambda: self.change_status("active")
        )
        self.context_menu.add_command(
            label="Mark Done", command=lambda: self.change_status("done")
        )
        self.context_menu.add_command(
            label="Mark Deferred", command=lambda: self.change_status("deferred")
        )
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Remove Task", command=self.remove_todo)

    def show_context_menu(self, event):
        """Displays the context menu and selects the row under the mouse."""
        iid = self.todo_tree.identify_row(event.y)
        if iid:
            self.todo_tree.selection_set(iid)
            self.context_menu.post(event.x_root, event.y_root)

    def refresh_todos(self):
        """Refresh the Daily TODO list (non-blocking)."""

        def on_todos_loaded(data):
            self.todo_tree.delete(*self.todo_tree.get_children())
            self.todo_map.clear()

            if not data:
                self.todo_tree.insert(
                    "", "end", values=("", "", "No tasks found!", "", "", "")
                )
                return

            for row in data:
                status = row["status"]
                tags = ()
                if status == "done":
                    tags = ("done",)
                elif status == "deferred":
                    tags = ("deferred",)

                task_date_str = row["task_date"].strftime("%Y-%m-%d") if row.get("task_date") else ""
                ticker = row.get("ticker") or "-"
                name = self.stock_name_map.get(ticker, "-") if ticker != "-" else "-"

                upside_str = ""
                if ticker != "-":
                    tp = row.get("target_price")
                    ep = row.get("entry_price")
                    cp = row.get("current_price")
                    
                    if cp is not None:
                        cp_val = float(cp)
                        if cp_val > 0:
                            if tp is not None and float(tp) > cp_val:
                                upside = ((float(tp) - cp_val) / cp_val) * 100
                                upside_str = f"↑ {upside:.1f}%"
                            elif ep is not None and cp_val < float(ep):
                                downside = ((float(ep) - cp_val) / float(ep)) * 100
                                upside_str = f"↓ {downside:.1f}%"

                iid = self.todo_tree.insert(
                    "",
                    "end",
                    values=(
                        task_date_str,
                        row["priority"].title(),
                        row["title"],
                        ticker,
                        name,
                        upside_str,
                        status.title(),
                    ),
                    tags=tags,
                )
                self.todo_map[iid] = row

        self.async_run_bg(get_todos(), callback=on_todos_loaded)

    def add_task(self):
        """Collects input and adds a task."""
        title = self.title_entry.get().strip()
        combo_val = self.ticker_combo.get().strip()
        ticker = self.extract_ticker(combo_val)

        # Validate Title
        if not title:
            self.title_entry.configure(bootstyle="danger")
        else:
            self.title_entry.configure(bootstyle="default")

        # Validate Ticker
        if not ticker:
            self.ticker_combo.configure(bootstyle="danger")
        else:
            self.ticker_combo.configure(bootstyle="default")

        if not title or not ticker:
            return

        # Optional: We assume description is empty for inline adds
        description = ""
        priority = self.priority_combo.get()

        def on_task_added(result):
            self.title_entry.delete(0, END)
            self.ticker_combo.delete(0, END)
            self.priority_combo.set("medium")
            self.title_entry.focus_set()
            self.refresh_todos()

        from components.button_utils import run_bg_with_button

        # Use helper to ensure the Add button is disabled while background work runs
        try:
            run_bg_with_button(self.add_btn, self.async_run_bg, add_todo(
                task_date=date.today(),
                title=title,
                description=description,
                ticker=ticker,
                priority=priority,
            ), callback=on_task_added)
        except Exception:
            # fallback to existing call if helper fails
            self.async_run_bg(
                add_todo(
                    task_date=date.today(),
                    title=title,
                    description=description,
                    ticker=ticker,
                    priority=priority,
                ),
                callback=on_task_added,
            )

    def on_double_click(self, event):
        """Toggle status between active and done on double click."""
        selection = self.todo_tree.selection()
        if not selection:
            return

        item_id = selection[0]
        if item_id not in self.todo_map:
            return

        current_status = self.todo_map[item_id]["status"]

        # Simple toggle logic: If active -> done, otherwise -> active
        new_status = "done" if current_status == "active" else "active"
        self.change_status(new_status)

    def change_status(self, new_status):
        """Updates the status of the selected task to the specific value."""
        selection = self.todo_tree.selection()
        if not selection:
            return

        item_id = selection[0]
        if item_id not in self.todo_map:
            return

        todo_id = self.todo_map[item_id]["id"]

        def on_status_updated(result):
            self.refresh_todos()

        self.async_run_bg(
            update_todo_status(todo_id, new_status), callback=on_status_updated
        )

    def remove_todo(self):
        """Removes the selected TODO item."""
        selection = self.todo_tree.selection()
        if not selection:
            return

        item_id = selection[0]
        if item_id not in self.todo_map:
            return

        todo_id = self.todo_map[item_id]["id"]

        def on_removed(result):
            self.refresh_todos()

        self.async_run_bg(delete_todo(todo_id), callback=on_removed)

    def edit_todo(self):
        """Opens a dialog to edit the selected task."""
        selection = self.todo_tree.selection()
        if not selection:
            return

        item_id = selection[0]
        if item_id not in self.todo_map:
            return

        todo_data = self.todo_map[item_id]
        todo_id = todo_data["id"]

        # 1. Create a transient Top-level Window for the dialog
        dialog = ttk.Toplevel(self)
        dialog.title("Edit Task")
        dialog.geometry("500x350")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        # 2. Main Frame with padding
        main_frame = ttk.Frame(dialog, padding=20)
        main_frame.pack(fill=BOTH, expand=True)

        # Title Field
        ttk.Label(main_frame, text="Task Title:").pack(anchor=W)
        title_var = ttk.StringVar(value=todo_data["title"])
        title_entry = ttk.Entry(main_frame, textvariable=title_var)
        title_entry.pack(fill=X, pady=(2, 10))

        # Ticker Field (Searchable Combobox)
        ttk.Label(main_frame, text="Ticker:").pack(anchor=W)
        ticker_var = ttk.StringVar(value=todo_data.get("ticker", "") or "")
        ticker_combo = ttk.Combobox(main_frame, textvariable=ticker_var)
        ticker_combo.pack(fill=X, pady=(2, 10))

        # Initial populate or search behavior
        self.update_combo_values(ticker_combo)
        ticker_combo.bind(
            "<KeyRelease>", lambda e: self.on_combo_search(e, ticker_combo)
        )

        # Priority Field
        ttk.Label(main_frame, text="Priority:").pack(anchor=W)
        priority_var = ttk.StringVar(value=todo_data["priority"])
        priority_combo = ttk.Combobox(
            main_frame,
            textvariable=priority_var,
            values=["low", "medium", "high"],
            state="readonly",
        )
        priority_combo.pack(fill=X, pady=(2, 20))

        def on_update_done(result):
            dialog.destroy()
            self.refresh_todos()

        def save_changes():
            new_title = title_var.get().strip()
            combo_val = ticker_var.get().strip()
            new_ticker = self.extract_ticker(combo_val)
            new_priority = priority_var.get()

            # Simple validation - same as add
            if not new_title or not new_ticker:
                if not new_title:
                    title_entry.configure(bootstyle="danger")
                if not new_ticker:
                    ticker_combo.configure(bootstyle="danger")
                return

            self.async_run_bg(
                update_todo(todo_id, new_title, new_ticker, new_priority),
                callback=on_update_done,
            )

        # Spacer to push buttons to the bottom
        ttk.Frame(main_frame).pack(fill=BOTH, expand=True)

        # Save and Cancel Buttons Container
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=X, side=TOP, pady=(5, 0))

        # Save Button
        save_btn = ttk.Button(
            btn_frame, text="Save Changes", command=save_changes, bootstyle="success"
        )
        save_btn.pack(side=RIGHT, padx=(5, 0))

        # Cancel Button
        cancel_btn = ttk.Button(
            btn_frame, text="Cancel", command=dialog.destroy, bootstyle="secondary"
        )
        cancel_btn.pack(side=RIGHT)

        # Focus title
        title_entry.focus_set()
