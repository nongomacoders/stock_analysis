import ttkbootstrap as ttk
from ttkbootstrap.constants import HORIZONTAL, BOTH, VERTICAL, LEFT, RIGHT, Y, WORD, END, NORMAL, DISABLED


class SensTab(ttk.Frame):
    """A tab for displaying SENS announcements in a master-detail view."""

    def __init__(self, parent):
        super().__init__(parent)
        self.create_widgets()
        self.sens_map = {}

    def create_widgets(self):
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
        if not selection: return
        item_id = selection[0]
        content = self.sens_map.get(item_id, "Content not found.")

        self.text_widget.config(state=NORMAL)
        self.text_widget.delete("1.0", END)
        self.text_widget.insert("1.0", content)
        self.text_widget.config(state=DISABLED)