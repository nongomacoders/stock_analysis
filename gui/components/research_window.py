import ttkbootstrap as ttk
from ttkbootstrap.constants import *

# --- NEW IMPORT ---
from modules.data.research import get_research_data, get_sens_for_ticker, save_strategy_data, save_research_data, save_deep_research_data
from modules.analysis.engine import generate_master_research


class ResearchWindow(ttk.Toplevel):
    def __init__(self, parent, ticker, async_run):
        # CHANGED: Removed db_layer argument
        super().__init__(parent)
        self.title(f"{ticker} - Research")
        self.geometry("900x700")

        self.ticker = ticker
        self.async_run = async_run

        self.create_widgets()
        self.load_research()

    def create_widgets(self):
        # Title
        title_frame = ttk.Frame(self, bootstyle="secondary")
        title_frame.pack(side=TOP, fill=X, padx=10, pady=10)
        ttk.Label(
            title_frame,
            text=f"{self.ticker} - Research & Analysis",
            font=("Helvetica", 16, "bold"),
        ).pack()

        # Notebook
        self.notebook = ttk.Notebook(self, bootstyle="primary")
        self.notebook.pack(fill=BOTH, expand=True, padx=10, pady=10)

        self.deep_research_tab = self.create_text_tab(editable=True)
        self.master_strategy_tab = self.create_text_tab(editable=True)
        self.master_research_tab = self.create_text_tab(
            editable=True,
            extra_buttons=[
                {
                    "text": "Generate New Research",
                    "command": self.generate_research,
                    "bootstyle": "info",
                }
            ],
        )

        self.notebook.add(self.deep_research_tab, text="Deep Research")
        self.notebook.add(self.master_strategy_tab, text="Strategy")
        self.notebook.add(self.master_research_tab, text="Research")

        self.sens_tab = self.create_sens_tab()
        self.notebook.add(self.sens_tab, text="SENS")

    def create_text_tab(self, editable=False, extra_buttons=None):
        frame = ttk.Frame(self.notebook)
        
        # Toolbar for editable tabs
        if editable:
            toolbar = ttk.Frame(frame)
            toolbar.pack(side=TOP, fill=X, padx=5, pady=5)
            
            # Save Button
            ttk.Button(
                toolbar, 
                text="Save Changes", 
                bootstyle="success", 
                command=lambda: self.save_tab_content(frame)
            ).pack(side=RIGHT, padx=5)

            # Extra Buttons
            if extra_buttons:
                for btn_config in extra_buttons:
                    ttk.Button(
                        toolbar,
                        text=btn_config["text"],
                        bootstyle=btn_config.get("bootstyle", "primary"),
                        command=btn_config["command"],
                    ).pack(side=RIGHT, padx=5)

        text_frame = ttk.Frame(frame)
        text_frame.pack(fill=BOTH, expand=True, padx=5, pady=5)

        scrollbar = ttk.Scrollbar(text_frame)
        scrollbar.pack(side=RIGHT, fill=Y)

        text_widget = ttk.Text(
            text_frame, wrap=WORD, yscrollcommand=scrollbar.set, font=("Consolas", 14)
        )
        text_widget.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.config(command=text_widget.yview)

        frame.text_widget = text_widget
        frame.editable = editable
        return frame

    def create_sens_tab(self):
        frame = ttk.Frame(self.notebook)
        paned = ttk.Panedwindow(frame, orient=HORIZONTAL)
        paned.pack(fill=BOTH, expand=True, padx=5, pady=5)

        # Left: Treeview
        left = ttk.Frame(paned)
        paned.add(left, weight=1)

        tree = ttk.Treeview(
            left, columns=("date", "content"), show="headings", bootstyle="primary"
        )
        tree.heading("date", text="Date")
        tree.heading("content", text="Headline")
        tree.column("date", width=150, stretch=False)
        tree.column("content", stretch=True)

        sb_tree = ttk.Scrollbar(left, orient=VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=sb_tree.set)
        tree.pack(side=LEFT, fill=BOTH, expand=True)
        sb_tree.pack(side=RIGHT, fill=Y)

        # Right: Text
        right = ttk.Frame(paned)
        paned.add(right, weight=2)

        sb_text = ttk.Scrollbar(right)
        sb_text.pack(side=RIGHT, fill=Y)

        text_widget = ttk.Text(
            right, wrap=WORD, yscrollcommand=sb_text.set, font=("Consolas", 10)
        )
        text_widget.pack(side=LEFT, fill=BOTH, expand=True)
        sb_text.config(command=text_widget.yview)

        tree.bind("<<TreeviewSelect>>", self.on_sens_select)

        frame.tree = tree
        frame.text_widget = text_widget
        frame.sens_map = {}
        return frame

    def on_sens_select(self, event):
        selection = self.sens_tab.tree.selection()
        if not selection:
            return
        item_id = selection[0]
        content = self.sens_tab.sens_map.get(item_id, "Content not found.")

        self.sens_tab.text_widget.config(state=NORMAL)
        self.sens_tab.text_widget.delete("1.0", END)
        self.sens_tab.text_widget.insert("1.0", content)
        self.sens_tab.text_widget.config(state=DISABLED)

    def load_research(self):
        # CHANGED: Call module functions
        data = self.async_run(get_research_data(self.ticker))
        sens_data = self.async_run(get_sens_for_ticker(self.ticker))

        self._fill_tab(
            self.deep_research_tab, data.get("deepresearch") if data else None
        )
        self._fill_tab(self.master_strategy_tab, data.get("strategy") if data else None)
        self._fill_tab(self.master_research_tab, data.get("research") if data else None)

        self.sens_tab.tree.delete(*self.sens_tab.tree.get_children())
        self.sens_tab.sens_map.clear()

        if sens_data:
            for item in sens_data:
                d_str = item["publication_datetime"].strftime("%Y-%m-%d %H:%M")
                content = item["content"]
                first_line = content.strip().split("\n")[0] if content else "No content"

                iid = self.sens_tab.tree.insert("", END, values=(d_str, first_line))
                self.sens_tab.sens_map[iid] = content
        else:
            self.sens_tab.tree.insert(
                "", END, values=("", "No SENS announcements found.")
            )

    def _fill_tab(self, tab, content):
        tab.text_widget.config(state=NORMAL)
        tab.text_widget.delete("1.0", END)
        tab.text_widget.insert("1.0", content if content else "No data available.")
        
        # Only disable if not editable
        if not getattr(tab, "editable", False):
            tab.text_widget.config(state=DISABLED)

    def save_tab_content(self, tab_frame):
        """Save content based on which tab triggered the save."""
        content = tab_frame.text_widget.get("1.0", END).strip()
        
        if tab_frame == self.master_strategy_tab:
            self.async_run(save_strategy_data(self.ticker, content))
            print(f"Strategy saved for {self.ticker}")
        elif tab_frame == self.master_research_tab:
            self.async_run(save_research_data(self.ticker, content))
            print(f"Research saved for {self.ticker}")
        elif tab_frame == self.deep_research_tab:
            self.async_run(save_deep_research_data(self.ticker, content))
            print(f"Deep Research saved for {self.ticker}")

    def generate_research(self):
        """Trigger AI research generation."""
        from ttkbootstrap.dialogs import Messagebox
        
        confirm = Messagebox.yesno(
            "This will overwrite existing research. Continue?",
            "Generate Research",
            parent=self
        )
        if confirm != "Yes":
            return

        try:
            print(f"Generating research for {self.ticker}...")
            # Show loading state
            self.master_research_tab.text_widget.config(state=NORMAL)
            self.master_research_tab.text_widget.delete("1.0", END)
            self.master_research_tab.text_widget.insert("1.0", "Generating research... please wait...")
            self.master_research_tab.text_widget.config(state=DISABLED)
            self.update()

            # Generate
            deep_research=self.deep_research_tab.text_widget.get("1.0", END).strip()
            new_research = self.async_run(generate_master_research(self.ticker,deep_research))
            
            # Update UI
            self._fill_tab(self.master_research_tab, new_research)
            print("Research generation complete.")
            
        except Exception as e:
            print(f"Error generating research: {e}")
            self._fill_tab(self.master_research_tab, f"Error: {str(e)}")
