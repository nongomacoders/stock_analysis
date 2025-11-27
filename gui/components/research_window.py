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
            font=("Consolas", 10)
        )
        text_widget.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.config(command=text_widget.yview)
        
        # Store reference to text widget
        frame.text_widget = text_widget
        
        return frame
    
    def load_research(self):
        """Load research data from database"""
        data = self.async_run(self.db.get_research_data(self.ticker))
        
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
