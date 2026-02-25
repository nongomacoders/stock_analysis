import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, VERTICAL, Y, RIGHT, LEFT, TOP, BOTTOM, X, W, END, NORMAL, WORD, DISABLED
from modules.data.research import get_latest_deepresearch_with_notes, save_watchlist_notes
import logging

logger = logging.getLogger(__name__)

class LatestDeepResearchWidget(ttk.Frame):
    """A widget that displays the latest deep research entries with notes."""

    def __init__(self, parent, async_run, async_run_bg, on_select_callback=None):
        super().__init__(parent)
        self.async_run = async_run
        self.async_run_bg = async_run_bg
        self.on_select = on_select_callback

        self.create_widgets()
        self.refresh_data()

    def create_widgets(self):
        # Toolbar
        toolbar = ttk.Frame(self)
        toolbar.pack(side=TOP, fill=X, padx=5, pady=5)

        ttk.Label(toolbar, text="Latest Deep Research", font=("Segoe UI", 11, "bold")).pack(side=LEFT, padx=5)

        self.refresh_btn = ttk.Button(
            toolbar,
            text="Refresh",
            command=self.refresh_data,
            bootstyle="info-outline",
            width=10
        )
        self.refresh_btn.pack(side=RIGHT, padx=5)

        self.notes_btn = ttk.Button(
            toolbar,
            text="Edit Notes",
            command=self.on_notes_clicked,
            bootstyle="success-outline",
            width=12,
            state=DISABLED
        )
        self.notes_btn.pack(side=RIGHT, padx=5)

        # Treeview
        cols = ("Ticker", "Name", "Date", "Notes")
        self.tree = ttk.Treeview(self, columns=cols, show="headings")
        self.tree.heading("Ticker", text="Ticker")
        self.tree.heading("Name", text="Name")
        self.tree.heading("Date", text="Date")
        self.tree.heading("Notes", text="Notes")

        self.tree.column("Ticker", width=100, anchor=W, stretch=False)
        self.tree.column("Name", width=200, anchor=W, stretch=False)
        self.tree.column("Date", width=150, anchor=W, stretch=False)
        self.tree.column("Notes", width=400, anchor=W, stretch=True)

        scrollbar = ttk.Scrollbar(self, orient=VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)

        scrollbar.pack(side=RIGHT, fill=Y)
        self.tree.pack(fill=BOTH, expand=True)

        self.tree.bind("<<TreeviewSelect>>", self.on_row_click)
        self.tree.bind("<Double-1>", self.on_row_click)

    def refresh_data(self):
        """Fetch and display the latest deep research data."""
        def on_loaded(data):
            self.tree.delete(*self.tree.get_children())
            if not data:
                self.tree.insert("", "end", values=("", "", "No research found", ""))
                return

            for row in data:
                dr_date = row.get("deepresearch_date")
                date_str = str(dr_date) if dr_date else "-"
                
                self.tree.insert(
                    "",
                    "end",
                    values=(
                        row.get("ticker", ""),
                        row.get("full_name", "") or "-",
                        date_str,
                        row.get("notes", "") or "-"
                    )
                )

        try:
            self.async_run_bg(get_latest_deepresearch_with_notes(), callback=on_loaded)
        except Exception:
            logger.exception("Failed to refresh LatestDeepResearchWidget data")

    def on_row_click(self, event):
        """Handle selection to open research and charts for the selected ticker."""
        sel = self.tree.selection()
        if not sel:
            self.notes_btn.config(state=DISABLED)
            return
            
        self.notes_btn.config(state=NORMAL)
        
        if not self.on_select:
            return
            
        item = self.tree.item(sel[0])
        values = item.get("values")
        if values and len(values) > 0:
            ticker = values[0]
            if ticker and ticker != "-":
                self.on_select(ticker)

    def on_notes_clicked(self):
        """Open a dialog to edit notes for the selected ticker."""
        sel = self.tree.selection()
        if not sel:
            return
            
        item = self.tree.item(sel[0])
        values = item.get("values")
        ticker = values[0]
        current_notes = values[3] if values[3] != "-" else ""
        
        # Create dialog
        dialog = ttk.Toplevel(self)
        dialog.title(f"Notes for {ticker}")
        dialog.geometry("600x600")
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()
        
        # Main container with padding
        main_container = ttk.Frame(dialog, padding=15)
        main_container.pack(fill=BOTH, expand=True)

        # Buttons (pinned to bottom)
        btn_frame = ttk.Frame(main_container, padding=(0, 10, 0, 0))
        btn_frame.pack(side=BOTTOM, fill=X)
        
        # Textbox (takes remaining space)
        text_frame = ttk.Frame(main_container)
        text_frame.pack(side=TOP, fill=BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(text_frame)
        scrollbar.pack(side=RIGHT, fill=Y)
        
        text_box = ttk.Text(text_frame, wrap=WORD, yscrollcommand=scrollbar.set, font=("Consolas", 12))
        text_box.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.config(command=text_box.yview)
        
        text_box.insert("1.0", current_notes)
        text_box.focus_set()  # Ensure user can type immediately
        
        def save():
            new_notes = text_box.get("1.0", END).strip()
            
            async def do_save():
                await save_watchlist_notes(ticker, new_notes)
                
            def on_saved(res):
                self.refresh_data()
                dialog.destroy()
                
            self.async_run_bg(do_save(), callback=on_saved)
            
        ttk.Button(btn_frame, text="Save", command=save, bootstyle="success", width=12).pack(side=RIGHT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy, bootstyle="secondary-outline", width=12).pack(side=RIGHT, padx=5)
