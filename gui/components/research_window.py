import ttkbootstrap as ttk
from ttkbootstrap.constants import *

class ResearchWindow(ttk.Toplevel):
    def __init__(self, parent, ticker, db_layer, async_run):
        super().__init__(parent)
        self.title(f"{ticker} - Research")
        self.geometry("900x700")
        
        self.ticker = ticker
        self.db = db_layer
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
            font=("Helvetica", 16, "bold")
        ).pack()
        
        # Create notebook for tabs
        self.notebook = ttk.Notebook(self, bootstyle="primary")
        self.notebook.pack(fill=BOTH, expand=True, padx=10, pady=10)
        
        # Create tabs
        self.deep_research_tab = self.create_text_tab("Deep Research")
        self.master_strategy_tab = self.create_text_tab("Master Strategy")
        self.master_research_tab = self.create_text_tab("Master Research")
        
        self.notebook.add(self.deep_research_tab, text="Deep Research")
        self.notebook.add(self.master_strategy_tab, text="Strategy")
        self.notebook.add(self.master_research_tab, text="Research")
        
        self.sens_tab = self.create_sens_tab("SENS")
        self.notebook.add(self.sens_tab, text="SENS")
    
    def create_text_tab(self, title):
        """Create a tab with a scrollable text widget"""
        frame = ttk.Frame(self.notebook)
        
        # Text widget with scrollbar
        text_frame = ttk.Frame(frame)
        text_frame.pack(fill=BOTH, expand=True, padx=5, pady=5)
        
        scrollbar = ttk.Scrollbar(text_frame)
        scrollbar.pack(side=RIGHT, fill=Y)
        
        text_widget = ttk.Text(
            text_frame,
            wrap=WORD,
            yscrollcommand=scrollbar.set,
            font=("Consolas", 14)
        )
        text_widget.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.config(command=text_widget.yview)
        
        # Store reference to text widget
        frame.text_widget = text_widget
        
        return frame

    def create_sens_tab(self, title):
        """Create a tab with a PanedWindow: Treeview (left) and Text (right)"""
        frame = ttk.Frame(self.notebook)
        
        # PanedWindow
        paned = ttk.Panedwindow(frame, orient=HORIZONTAL)
        paned.pack(fill=BOTH, expand=True, padx=5, pady=5)
        
        # Left Frame: Treeview
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)
        
        columns = ("date", "content")
        tree = ttk.Treeview(left_frame, columns=columns, show="headings", bootstyle="primary")
        tree.heading("date", text="Date")
        tree.heading("content", text="Headline")
        tree.column("date", width=150, stretch=False)
        tree.column("content", stretch=True)
        
        scrollbar_tree = ttk.Scrollbar(left_frame, orient=VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar_tree.set)
        
        tree.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar_tree.pack(side=RIGHT, fill=Y)
        
        # Right Frame: Text Detail
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=2)
        
        scrollbar_text = ttk.Scrollbar(right_frame)
        scrollbar_text.pack(side=RIGHT, fill=Y)
        
        text_widget = ttk.Text(
            right_frame,
            wrap=WORD,
            yscrollcommand=scrollbar_text.set,
            font=("Consolas", 10)
        )
        text_widget.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar_text.config(command=text_widget.yview)
        
        # Bind selection event
        tree.bind("<<TreeviewSelect>>", self.on_sens_select)
        
        frame.tree = tree
        frame.text_widget = text_widget
        frame.sens_map = {} # To store full content
        
        return frame

    def on_sens_select(self, event):
        """Handle SENS item selection"""
        selection = self.sens_tab.tree.selection()
        if not selection:
            return
            
        item_id = selection[0]
        full_content = self.sens_tab.sens_map.get(item_id, "Content not found.")
        
        self.sens_tab.text_widget.config(state=NORMAL)
        self.sens_tab.text_widget.delete('1.0', END)
        self.sens_tab.text_widget.insert('1.0', full_content)
        self.sens_tab.text_widget.config(state=DISABLED)
    
    def load_research(self):
        """Load research data from database"""
        data = self.async_run(self.db.get_research_data(self.ticker))
        sens_data = self.async_run(self.db.get_sens_for_ticker(self.ticker))
        
        if data:
            # Deep Research
            deep_research = data.get('deepresearch') or 'No deep research available.'
            self.deep_research_tab.text_widget.delete('1.0', END)
            self.deep_research_tab.text_widget.insert('1.0', deep_research)
            self.deep_research_tab.text_widget.config(state=DISABLED)
            
            # Strategy
            strategy = data.get('strategy') or 'No strategy available.'
            self.master_strategy_tab.text_widget.delete('1.0', END)
            self.master_strategy_tab.text_widget.insert('1.0', strategy)
            self.master_strategy_tab.text_widget.config(state=DISABLED)
            
            # Research
            research = data.get('research') or 'No research available.'
            self.master_research_tab.text_widget.delete('1.0', END)
            self.master_research_tab.text_widget.insert('1.0', research)
            self.master_research_tab.text_widget.config(state=DISABLED)
        else:
            # No data available
            for tab in [self.deep_research_tab, self.master_strategy_tab, self.master_research_tab]:
                tab.text_widget.delete('1.0', END)
                tab.text_widget.insert('1.0', 'No data available for this ticker.')
                tab.text_widget.config(state=DISABLED)
        
        # Populate SENS tab
        # Populate SENS tab
        self.sens_tab.tree.delete(*self.sens_tab.tree.get_children())
        self.sens_tab.sens_map.clear()
        
        if sens_data:
            for item in sens_data:
                date_str = item['publication_datetime'].strftime("%Y-%m-%d %H:%M")
                content = item['content']
                # Get first non-empty line
                lines = [line.strip() for line in content.split('\n') if line.strip()]
                first_line = lines[0] if lines else "No content"
                
                item_id = self.sens_tab.tree.insert("", END, values=(date_str, first_line))
                self.sens_tab.sens_map[item_id] = content
        else:
             self.sens_tab.tree.insert("", END, values=("", "No SENS announcements found."))
