import ttkbootstrap as ttk
from ttkbootstrap.constants import TOP, X, BOTH

# --- NEW IMPORT ---
from modules.data.research import (
    get_research_data,
    get_sens_for_ticker,
    save_strategy_data,
    save_research_data,
    save_deep_research_data,
    get_action_logs,
    mark_log_read,
    get_stock_category,
)
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
        # Register listener in background to avoid blocking the GUI
        try:
            self.async_run_bg(self.notifier.add_listener('action_log_changes', self.on_action_log_notification))
        except Exception:
            # Fallback: try synchronously if background registration fails
            try:
                self.async_run(self.notifier.add_listener('action_log_changes', self.on_action_log_notification))
            except Exception:
                pass

        self.create_widgets()
        self.load_research()

    def on_action_log_notification(self, payload: str):
        """Callback for DB notifications to reload the action log."""
        self.after(0, self.action_log_tab.load_action_logs)

    def update_ticker(self, ticker):
        """Update the window with a new ticker"""
        self.ticker = ticker
        self.title(f"{ticker} - Research & Action Log")
        
        # Update title label if present (do this asynchronously to avoid blocking)
        if hasattr(self, 'title_label'):
            def _on_category_loaded(category):
                if category:
                    self.title_label.configure(text=f"{ticker} — {category} — Research & Analysis")
                else:
                    self.title_label.configure(text=f"{ticker} - Research & Analysis")

            try:
                self.async_run_bg(get_stock_category(ticker), callback=_on_category_loaded)
            except Exception:
                # fallback to synchronous fetch if background runner fails
                try:
                    category = self.async_run(get_stock_category(ticker))
                except Exception:
                    category = None
                if category:
                    self.title_label.configure(text=f"{ticker} — {category} — Research & Analysis")
                else:
                    self.title_label.configure(text=f"{ticker} - Research & Analysis")
        else:
            # fallback: search existing label
            for widget in self.winfo_children():
                if isinstance(widget, ttk.Frame) and str(widget).endswith("frame"):
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
        # store a reference to the label so we can update the category later
        self.title_label = ttk.Label(
            title_frame,
            text=f"{self.ticker} - Research & Analysis",
            font=("Helvetica", 16, "bold"),
        )
        self.title_label.pack()

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
        """Load research data without blocking the GUI by using background tasks."""
        def _on_research_loaded(data):
            # Update title/category asynchronously
            try:
                self.async_run_bg(
                    get_stock_category(self.ticker),
                    callback=lambda category: self.title_label.configure(text=f"{self.ticker} — {category} — Research & Analysis") if category else self.title_label.configure(text=f"{self.ticker} - Research & Analysis"),
                )
            except Exception:
                # fallback: sync fetch
                try:
                    category = self.async_run(get_stock_category(self.ticker))
                except Exception:
                    category = None
                if category:
                    self.title_label.configure(text=f"{self.ticker} — {category} — Research & Analysis")
                else:
                    self.title_label.configure(text=f"{self.ticker} - Research & Analysis")

            # Delegate loading to child tabs (immediate update from fetched data)
            self.deep_research_tab.load_content(data.get("deepresearch") if data else None)
            self.master_strategy_tab.load_content(data.get("strategy") if data else None)
            self.master_research_tab.load_content(data.get("research") if data else None)

            # Load SENS data asynchronously
            try:
                self.async_run_bg(get_sens_for_ticker(self.ticker), callback=lambda s: self.sens_tab.load_content(s))
            except Exception:
                try:
                    s = self.async_run(get_sens_for_ticker(self.ticker))
                except Exception:
                    s = None
                self.sens_tab.load_content(s)

            # Refresh action log (non-blocking)
            self.action_log_tab.load_action_logs()

        # Kick off the background fetch for the main research payload
        try:
            self.async_run_bg(get_research_data(self.ticker), callback=_on_research_loaded)
        except Exception:
            # fallback: synchronous fetch if background runner fails
            try:
                data = self.async_run(get_research_data(self.ticker))
            except Exception:
                data = None
            _on_research_loaded(data)
