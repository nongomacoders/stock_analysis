import ttkbootstrap as ttk
from ttkbootstrap.constants import TOP, X, BOTH

# --- NEW IMPORT ---
from modules.data.research import get_research_data, get_sens_for_ticker, save_strategy_data, save_research_data, save_deep_research_data, get_action_logs, mark_log_read
from modules.analysis.engine import generate_master_research
from components.deep_research_tab import DeepResearchTab
from components.strategy_tab import StrategyTab
from components.research_tab import ResearchTab
from components.sens_tab import SensTab
from components.action_log_tab import ActionLogTab


class ResearchWindow(ttk.Toplevel):
    def __init__(self, parent, ticker, async_run, async_run_bg, notifier, on_data_change=None):
        # CHANGED: Removed db_layer argument, added async_run_bg for non-blocking operations
        super().__init__(parent)
        self.title(f"{ticker} - Research & Action Log")
        self.geometry("900x700")

        self.ticker = ticker
        self.async_run = async_run
        self.async_run_bg = async_run_bg
        self.on_data_change = on_data_change

        # Listen for DB notifications
        self.notifier = notifier
        self.async_run(self.notifier.add_listener('action_log_changes', self.on_action_log_notification))

        self.create_widgets()
        self.load_research()

    def on_action_log_notification(self, payload: str):
        """Callback for DB notifications to reload the action log."""
        self.after(0, self.action_log_tab.load_action_logs)

    def update_ticker(self, ticker):
        """Update the window with a new ticker"""
        self.ticker = ticker
        self.title(f"{ticker} - Research & Action Log")
        
        # Update title label
        for widget in self.winfo_children():
             if isinstance(widget, ttk.Frame) and str(widget).endswith("frame"): # Find title frame
                 for child in widget.winfo_children():
                     if isinstance(child, ttk.Label):
                         child.configure(text=f"{self.ticker} - Research & Analysis")
                         break
        
        # Update ticker on all child tabs
        self.deep_research_tab.ticker = ticker
        self.master_strategy_tab.ticker = ticker
        self.master_research_tab.ticker = ticker
        self.action_log_tab.ticker = ticker

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

        # Use the new component for the Deep Research tab
        self.deep_research_tab = DeepResearchTab(self.notebook, self.ticker, self.async_run, self.async_run_bg)

        # Use the new component for the Strategy tab
        self.master_strategy_tab = StrategyTab(self.notebook, self.ticker, self.async_run, self.async_run_bg)

        # Use the new component for the Research tab, passing a reference to the deep research tab
        self.master_research_tab = ResearchTab(
            self.notebook, self.ticker, self.async_run, self.deep_research_tab, self.async_run_bg
        )

        self.notebook.add(self.deep_research_tab, text="Deep Research")
        self.notebook.add(self.master_strategy_tab, text="Strategy")
        self.notebook.add(self.master_research_tab, text="Research")

        self.sens_tab = SensTab(self.notebook)
        self.notebook.add(self.sens_tab, text="SENS")

        self.action_log_tab = ActionLogTab(self.notebook, self.ticker, self.async_run, self.async_run_bg)
        self.notebook.add(self.action_log_tab, text="Action Log")

    def load_research(self):
        # CHANGED: Call module functions
        data = self.async_run(get_research_data(self.ticker))
        sens_data = self.async_run(get_sens_for_ticker(self.ticker))
        
        # Delegate loading to child tabs
        self.deep_research_tab.load_content(data.get("deepresearch") if data else None)
        self.master_strategy_tab.load_content(data.get("strategy") if data else None)
        self.master_research_tab.load_content(data.get("research") if data else None)
        self.sens_tab.load_content(sens_data)
        self.action_log_tab.load_action_logs()
