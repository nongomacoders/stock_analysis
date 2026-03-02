import ttkbootstrap as ttk
from ttkbootstrap.constants import TOP, X, BOTH, VERTICAL, Y, W, RIGHT
from modules.data.billing import get_monthly_ai_costs, get_total_monthly_cost, get_model_usage_stats

class BillingTab(ttk.Frame):
    """A tab that displays cumulative AI billing statistics from ai_cost_log."""

    def __init__(self, parent, async_run_bg):
        super().__init__(parent)
        self.async_run_bg = async_run_bg
        self.create_widgets()
        self.refresh_data()

    def create_widgets(self):
        """Creates the layout for the Billing statistics tab."""
        # --- HEADER (Total Cost Summary) ---
        header_frame = ttk.Frame(self, bootstyle="secondary")
        header_frame.pack(side=TOP, fill=X, padx=10, pady=10)

        self.total_cost_label = ttk.Label(
            header_frame, 
            text="Cumulative Cost (Current Month): $0.000000",
            font=("Segoe UI", 12, "bold"),
            bootstyle="inverse-secondary"
        )
        self.total_cost_label.pack(side=TOP, pady=5)

        # --- TABLES CONTAINER ---
        table_frame = ttk.Frame(self)
        table_frame.pack(fill=BOTH, expand=True, padx=10, pady=5)

        # --- MODEL SUMMARY (Small Top Table) ---
        ttk.Label(table_frame, text="Model Usage Summary", font=("Segoe UI", 10, "bold")).pack(anchor=W, pady=(10, 2))
        
        m_cols = ("Model", "Calls", "Cost")
        self.model_tree = ttk.Treeview(table_frame, columns=m_cols, show="headings", height=4)
        for col in m_cols:
            self.model_tree.heading(col, text=col)
            self.model_tree.column(col, width=150, anchor=W)
        self.model_tree.pack(fill=X, pady=(0, 10))

        # --- TICKER SUMMARY (Large Bottom Table) ---
        ttk.Label(table_frame, text="Cost by Ticker", font=("Segoe UI", 10, "bold")).pack(anchor=W, pady=(10, 2))

        t_cols = ("Ticker", "Calls", "Prompt Tokens", "Comp Tokens", "Total Cost")
        self.ticker_tree = ttk.Treeview(table_frame, columns=t_cols, show="headings")
        self.ticker_tree.heading("Ticker", text="Ticker")
        self.ticker_tree.heading("Calls", text="Calls")
        self.ticker_tree.heading("Prompt Tokens", text="Prompt Tokens")
        self.ticker_tree.heading("Comp Tokens", text="Comp Tokens")
        self.ticker_tree.heading("Total Cost", text="Total Cost")

        for col in t_cols:
            self.ticker_tree.column(col, anchor=W)
        
        self.ticker_tree.column("Ticker", width=100)
        self.ticker_tree.column("Total Cost", width=120)

        # Scrollbar for Ticker table
        scrolly = ttk.Scrollbar(table_frame, orient=VERTICAL, command=self.ticker_tree.yview)
        self.ticker_tree.configure(yscroll=scrolly.set)
        scrolly.pack(side=RIGHT, fill=Y)
        self.ticker_tree.pack(fill=BOTH, expand=True)

        # Refresh Button
        self.refresh_btn = ttk.Button(
            self, text="Refresh Billing Data", command=self.refresh_data, bootstyle="outline-info"
        )
        self.refresh_btn.pack(side=TOP, pady=10)

    def refresh_data(self):
        """Loads all billing stats asynchronously."""
        
        def on_total_loaded(total):
            cost_val = total if total is not None else 0.0
            self.total_cost_label.configure(text=f"Cumulative Cost (Current Month): ${cost_val:,.6f}")

        def on_models_loaded(data):
            self.model_tree.delete(*self.model_tree.get_children())
            if not data:
                return
            for row in data:
                self.model_tree.insert("", "end", values=(
                    row["model_name"],
                    row["call_count"],
                    f"${float(row['model_total_cost'] or 0):.6f}"
                ))

        def on_tickers_loaded(data):
            self.ticker_tree.delete(*self.ticker_tree.get_children())
            if not data:
                return
            for row in data:
                self.ticker_tree.insert("", "end", values=(
                    row["ticker"],
                    row["call_count"],
                    row["total_prompt_tokens"],
                    row["total_completion_tokens"],
                    f"${float(row['ticker_total_cost'] or 0):.6f}"
                ))

        self.async_run_bg(get_total_monthly_cost(), callback=on_total_loaded)
        self.async_run_bg(get_model_usage_stats(), callback=on_models_loaded)
        self.async_run_bg(get_monthly_ai_costs(), callback=on_tickers_loaded)
