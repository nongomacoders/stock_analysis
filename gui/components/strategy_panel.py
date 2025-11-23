import ttkbootstrap as ttk
from ttkbootstrap.constants import *

class StrategyPanel(ttk.Labelframe):
    def __init__(self, parent, db_layer):
        super().__init__(parent, text="Strategy Preview", padding=10)
        self.db = db_layer
        
        self.text_area = ttk.Text(self, height=6, wrap="word", state="disabled", font=("Consolas", 10))
        self.text_area.pack(fill=BOTH, expand=True)

    def load_strategy(self, ticker):
        self.config(text=f"Strategy Preview: {ticker}")
        strategy = self.db.fetch_strategy(ticker)
        
        self.text_area.config(state="normal")
        self.text_area.delete("1.0", "end")
        self.text_area.insert("1.0", strategy)
        self.text_area.config(state="disabled")