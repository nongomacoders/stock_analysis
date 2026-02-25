import ttkbootstrap as ttk
from ttkbootstrap.constants import TOP, X, HORIZONTAL, BOTH, VERTICAL, LEFT, RIGHT, Y, WORD, END, NORMAL, DISABLED
from modules.analysis.engine import analyze_new_sens
from components.button_utils import run_bg_with_button


class SensTab(ttk.Frame):
    """A tab for displaying SENS announcements in a master-detail view."""

    def __init__(self, parent, ticker, async_run, async_run_bg):
        super().__init__(parent)
        self.ticker = ticker
        self.async_run = async_run
        self.async_run_bg = async_run_bg
        self.create_widgets()
        self.sens_map = {}
        self.current_selection_content = None

    def create_widgets(self):
        # Toolbar
        toolbar = ttk.Frame(self)
        toolbar.pack(side=TOP, fill=X, padx=5, pady=5)

        self.analyze_btn = ttk.Button(
            toolbar,
            text="Run AI Analysis",
            bootstyle="success",
            command=self.on_analyze_sens_clicked,
            state=DISABLED
        )
        self.analyze_btn.pack(side=LEFT, padx=5)

        paned = ttk.Panedwindow(self, orient=HORIZONTAL)
        paned.pack(fill=BOTH, expand=True, padx=5, pady=5)

        # Left: Treeview for SENS headlines
        left = ttk.Frame(paned)
        paned.add(left, weight=1)

        self.tree = ttk.Treeview(
            left, columns=("date", "content"), show="headings", bootstyle="primary"
        )
        self.tree.heading("date", text="Date")
        self.tree.heading("content", text="Headline")
        self.tree.column("date", width=150, stretch=False)
        self.tree.column("content", stretch=True)

        sb_tree = ttk.Scrollbar(left, orient=VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb_tree.set)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        sb_tree.pack(side=RIGHT, fill=Y)

        # Right: Text widget for SENS content
        right = ttk.Frame(paned)
        paned.add(right, weight=2)

        sb_text = ttk.Scrollbar(right)
        sb_text.pack(side=RIGHT, fill=Y)

        self.text_widget = ttk.Text(
            right, wrap=WORD, yscrollcommand=sb_text.set, font=("Consolas", 10)
        )
        self.text_widget.pack(side=LEFT, fill=BOTH, expand=True)
        sb_text.config(command=self.text_widget.yview)

        self.tree.bind("<<TreeviewSelect>>", self.on_sens_select)

    def load_content(self, sens_data):
        """Fills the treeview with SENS data."""
        self.tree.delete(*self.tree.get_children())
        self.sens_map.clear()
        self.current_selection_content = None
        self.analyze_btn.config(state=DISABLED)

        self.text_widget.config(state=NORMAL)
        self.text_widget.delete("1.0", END)
        self.text_widget.config(state=DISABLED)

        if sens_data:
            for item in sens_data:
                d_str = item["publication_datetime"].strftime("%Y-%m-%d %H:%M")
                content = item["content"]
                first_line = content.strip().split("\n")[0] if content else "No content"

                iid = self.tree.insert("", END, values=(d_str, first_line))
                self.sens_map[iid] = content
        else:
            self.tree.insert("", END, values=("", "No SENS announcements found."))

    def on_sens_select(self, event):
        """Displays the full SENS content when an item is selected."""
        selection = self.tree.selection()
        if not selection:
            self.current_selection_content = None
            self.analyze_btn.config(state=DISABLED)
            return

        item_id = selection[0]
        content = self.sens_map.get(item_id)
        
        if not content:
            self.current_selection_content = None
            self.analyze_btn.config(state=DISABLED)
            return

        self.current_selection_content = content
        self.analyze_btn.config(state=NORMAL)

        self.text_widget.config(state=NORMAL)
        self.text_widget.delete("1.0", END)
        self.text_widget.insert("1.0", content)
        self.text_widget.config(state=DISABLED)

    def on_analyze_sens_clicked(self):
        """Triggers the AI analysis for the currently selected SENS."""
        if not self.current_selection_content or not self.ticker:
            return

        # Use helper to run in background and disable button
        run_bg_with_button(
            self.analyze_btn,
            self.async_run_bg,
            analyze_new_sens(self.ticker, self.current_selection_content)
        )