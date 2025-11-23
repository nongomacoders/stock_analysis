import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from db_layer import DBLayer
from components.watchlist import WatchlistWidget
# We will add Scorecard and SensFeed later to keep it simple for now

class CommandCenter(ttk.Window):
    def __init__(self):
        super().__init__(themename="cosmo")
        self.title("JSE Command Center")
        self.geometry("1280x800")
        
        self.db = DBLayer()
        self.create_layout()

    def create_layout(self):
        # 1. Top HUD (Placeholder for now)
        hud_frame = ttk.Frame(self, height=50, bootstyle="secondary")
        hud_frame.pack(side=TOP, fill=X, padx=5, pady=5)
        ttk.Label(hud_frame, text="[Portfolio Scorecard Placeholder]").pack(anchor=CENTER)

        # 2. Main Watchlist Grid (Takes up all remaining space)
        self.watchlist = WatchlistWidget(self, self.db, self.on_ticker_select)
        self.watchlist.pack(fill=BOTH, expand=True, padx=5, pady=5)

        # Initial Load
        self.watchlist.refresh()

    def on_ticker_select(self, ticker):
        """Callback when watchlist row is clicked"""
        # Currently no action needed as Strategy Panel is removed
        print(f"Selected: {ticker}")

if __name__ == "__main__":
    app = CommandCenter()
    app.mainloop()