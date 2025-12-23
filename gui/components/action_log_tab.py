import ttkbootstrap as ttk
from ttkbootstrap.constants import TOP, X, RIGHT, HORIZONTAL, BOTH, LEFT, VERTICAL, Y, WORD, END, DISABLED,NORMAL


from modules.data.research import get_action_logs, mark_log_read
from components.button_utils import run_bg_with_button


class ActionLogTab(ttk.Frame):
    """A tab for displaying action logs in a master-detail view."""

    def __init__(self, parent, ticker, async_run, async_run_bg):
        super().__init__(parent)
        self.ticker = ticker
        self.async_run = async_run
        self.async_run_bg = async_run_bg
        self.logs_map = {}

        self.create_widgets()

    def create_widgets(self):
        # Toolbar
        toolbar = ttk.Frame(self)
        toolbar.pack(side=TOP, fill=X, padx=5, pady=5)

        self.mark_read_btn = ttk.Button(
            toolbar,
            text="Mark as Read",
            bootstyle="success",
            command=self.mark_as_read,
            state=DISABLED
        )
        self.mark_read_btn.pack(side=RIGHT, padx=5)

        # Delete button to remove an action log entry
        try:
            import tkinter.messagebox as messagebox
            from modules.data.research import delete_action_log

            self.delete_btn = ttk.Button(
                toolbar,
                text="Delete",
                bootstyle="danger",
                command=self._on_delete_clicked,
                state=DISABLED,
            )
            self.delete_btn.pack(side=RIGHT, padx=5)
        except Exception:
            # If imports fail, we'll proceed without the delete button
            self.delete_btn = None
            try:
                logger = __import__('logging').getLogger(__name__)
                logger.exception('Failed to create delete button for ActionLogTab')
            except Exception:
                pass

        # Master-Detail View
        paned = ttk.Panedwindow(self, orient=HORIZONTAL)
        paned.pack(fill=BOTH, expand=True, padx=5, pady=5)

        # Left: Treeview
        left = ttk.Frame(paned)
        paned.add(left, weight=1)

        self.tree = ttk.Treeview(
            left, columns=("date", "type", "content", "status"), show="headings", bootstyle="info"
        )
        self.tree.heading("date", text="Date")
        self.tree.heading("type", text="Type")
        self.tree.heading("content", text="Trigger")
        self.tree.heading("status", text="Status")

        self.tree.column("date", width=150, stretch=False)
        self.tree.column("type", width=100, stretch=False)
        self.tree.column("content", stretch=True)
        self.tree.column("status", width=80, stretch=False)

        sb_tree = ttk.Scrollbar(left, orient=VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb_tree.set)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        sb_tree.pack(side=RIGHT, fill=Y)

        # Right: Text widget for details
        right = ttk.Frame(paned)
        paned.add(right, weight=2)

        sb_text = ttk.Scrollbar(right)
        sb_text.pack(side=RIGHT, fill=Y)

        self.text_widget = ttk.Text(
            right, wrap=WORD, yscrollcommand=sb_text.set, font=("Consolas", 10)
        )
        self.text_widget.pack(side=LEFT, fill=BOTH, expand=True)
        sb_text.config(command=self.text_widget.yview)

        self.tree.bind("<<TreeviewSelect>>", self.on_action_log_select)

    def load_action_logs(self):
        """Fetch and display action logs for the current ticker."""
        def on_logs_loaded(action_logs):
            self.tree.delete(*self.tree.get_children())
            self.logs_map.clear()
            self.mark_read_btn.config(state=DISABLED)
            self.text_widget.config(state=NORMAL)
            self.text_widget.delete("1.0", END)
            self.text_widget.config(state=DISABLED)

            if action_logs:
                for item in action_logs:
                    d_str = item["log_timestamp"].strftime("%Y-%m-%d %H:%M")
                    status = "Read" if item.get("is_read") else "Unread"
                    first_line = item["trigger_content"].strip().split("\n")[0] if item["trigger_content"] else "No content"

                    iid = self.tree.insert("", END, values=(d_str, item["trigger_type"], first_line, status))
                    self.logs_map[iid] = item
            else:
                self.tree.insert("", END, values=("", "", "No Action Logs found.", ""))

        self.async_run_bg(get_action_logs(self.ticker), callback=on_logs_loaded)

    def on_action_log_select(self, event):
        selection = self.tree.selection()
        if not selection: return
        item_id = selection[0]
        data = self.logs_map.get(item_id)
        if not data: return

        display_text = f"Trigger Type: {data['trigger_type']}\nDate: {data['log_timestamp']}\n{'-'*40}\n\n"
        display_text += f"TRIGGER CONTENT:\n{data['trigger_content']}\n\n{'='*40}\n\nAI ANALYSIS:\n{data['ai_analysis']}"

        self.text_widget.config(state=NORMAL)
        self.text_widget.delete("1.0", END)
        self.text_widget.insert("1.0", display_text)
        self.text_widget.config(state=DISABLED)

        self.mark_read_btn.config(state=NORMAL if not data.get("is_read", False) else DISABLED)
        # Enable delete button if present
        try:
            if getattr(self, 'delete_btn', None):
                self.delete_btn.config(state=NORMAL)
        except Exception:
            pass

    def mark_as_read(self):
        selection = self.tree.selection()
        if not selection: return
        item_id = selection[0]
        data = self.logs_map.get(item_id)

        if data and not data.get("is_read", False):
            # Use helper to disable the button while the mark-as-read background job runs
            try:
                run_bg_with_button(self.mark_read_btn, self.async_run_bg, mark_log_read(data["log_id"]), callback=lambda _ : self.load_action_logs())
            except Exception:
                # fallback to original behavior
                self.mark_read_btn.config(state=DISABLED)
                self.async_run_bg(mark_log_read(data["log_id"]))

    def _on_delete_clicked(self):
        """Handler for the Delete button. Confirms then deletes the selected log."""
        try:
            import tkinter.messagebox as messagebox
            from modules.data.research import delete_action_log
        except Exception:
            # If imports fail, log and abort
            try:
                __import__('logging').getLogger(__name__).exception('Delete handler imports failed')
            except Exception:
                pass
            return

        selection = self.tree.selection()
        if not selection:
            return
        item_id = selection[0]
        data = self.logs_map.get(item_id)
        if not data:
            return

        # Confirm with the user
        try:
            ok = messagebox.askyesno("Confirm Delete", "Delete this action log entry?", parent=self)
        except Exception:
            ok = False

        if not ok:
            return

        # Disable delete button while running
        if getattr(self, 'delete_btn', None):
            try:
                self.delete_btn.config(state=DISABLED)
            except Exception:
                pass

        # Run delete in background and reload logs when done
        try:
            run_bg_with_button(self.delete_btn or self.mark_read_btn, self.async_run_bg, delete_action_log(data["log_id"]), callback=lambda _ : self.load_action_logs())
        except Exception:
            try:
                # fallback: call background function directly
                self.async_run_bg(delete_action_log(data["log_id"]))
                self.load_action_logs()
            except Exception:
                __import__('logging').getLogger(__name__).exception('Failed to delete action log')
