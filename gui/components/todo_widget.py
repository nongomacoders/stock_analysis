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
)


class TodoWidget(ttk.Frame):
    """A widget that displays a list of daily TODO tasks."""

    def __init__(self, parent, async_run, async_run_bg, notifier):
        super().__init__(parent)
        self.async_run = async_run
        self.async_run_bg = async_run_bg
        self.notifier = notifier

        # Listen for DB notifications to auto-refresh the list
        self.async_run(
            self.notifier.add_listener("daily_todos_changes", self.on_todo_notification)
        )

        self.create_widgets()
        self.refresh_todos()

    def on_todo_notification(self, payload: str):
        """Callback for DB notifications to reload the TODO list."""
        self.after(0, self.refresh_todos)

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

        # 2. Ticker Input
        ttk.Label(input_frame, text="Ticker:").pack(side=LEFT, padx=(10, 2))
        self.ticker_entry = ttk.Entry(input_frame, width=10)
        self.ticker_entry.pack(side=LEFT, padx=2)

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
        cols = ("Date", "Priority", "Title", "Ticker", "Status")
        self.todo_tree = ttk.Treeview(self, columns=cols, show="headings")
        self.todo_tree.heading("Date", text="Date")
        self.todo_tree.heading("Priority", text="Priority")
        self.todo_tree.heading("Title", text="Title")
        self.todo_tree.heading("Ticker", text="Ticker")
        self.todo_tree.heading("Status", text="Status")

        self.todo_tree.column("Date", width=100, anchor=W, stretch=False)
        self.todo_tree.column("Priority", width=80, anchor=W, stretch=False)
        self.todo_tree.column("Title", width=400, anchor=W, stretch=True)
        self.todo_tree.column("Ticker", width=100, anchor=W, stretch=False)
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
        self.todo_tree.bind(
            "<Double-1>", self.on_double_click
        )  # Double Click (Toggle Status)

    def create_context_menu(self):
        """Creates the right-click menu."""
        self.context_menu = Menu(self, tearoff=0)
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
                    "", "end", values=("", "", "No tasks found!", "", "")
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

                iid = self.todo_tree.insert(
                    "",
                    "end",
                    values=(
                        task_date_str,
                        row["priority"].title(),
                        row["title"],
                        row.get("ticker") or "-",
                        status.title(),
                    ),
                    tags=tags,
                )
                self.todo_map[iid] = row

        self.async_run_bg(get_todos(), callback=on_todos_loaded)

    def add_task(self):
        """Collects input and adds a task."""
        title = self.title_entry.get()
        if not title:
            self.title_entry.configure(bootstyle="danger")
            return

        self.title_entry.configure(bootstyle="default")

        # Optional: We assume description is empty for inline adds
        description = ""
        ticker = self.ticker_entry.get()
        priority = self.priority_combo.get()

        def on_task_added(result):
            self.title_entry.delete(0, END)
            self.ticker_entry.delete(0, END)
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
