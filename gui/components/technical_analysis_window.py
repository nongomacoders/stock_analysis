import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, X, LEFT, RIGHT, BOTTOM
import matplotlib.pyplot as plt
import pandas as pd
import mplfinance as mpf
from modules.data.market import get_historical_prices
from components.base_chart import BaseChart
from core.utils.chart_drawing_utils import add_axhline, add_legend_for_hlines
from core.db.engine import DBEngine
from components.analysis_control_panel import AnalysisControlPanel

class TechnicalAnalysisWindow(ttk.Toplevel):
    def __init__(self, parent, ticker, async_run_bg):
        super().__init__(parent)
        self.title(f"{ticker} - Technical Analysis")
        self.geometry("1000x700")

        self.ticker = ticker
        self.async_run_bg = async_run_bg

        # Configure matplotlib style
        plt.style.use("seaborn-v0_8-darkgrid")

        # Price levels for drawing
        self.entry_price = None
        self.stop_loss = None
        self.target_price = None
        # Horizontal-line storage handled by BaseChart.horizontal_lines

        self.create_widgets()
        self.load_chart("1 Year") # Default to 1 Year
        self.load_existing_data()

        # Bind keypress events
        self.bind_all("<KeyPress>", self.on_key_press)

    def create_widgets(self):
        # Top Control Panel
        control_frame = ttk.Frame(self, padding=10)
        control_frame.pack(fill=X)

        ttk.Label(control_frame, text="Period:", font=("Helvetica", 10, "bold")).pack(side=LEFT, padx=(0, 5))

        self.period_var = ttk.StringVar(value="1 Year")
        self.period_combo = ttk.Combobox(
            control_frame, 
            textvariable=self.period_var, 
            values=["3 Months", "6 Months", "9 Months", "1 Year", "2 Years", "5 Years"],
            state="readonly",
            width=15
        )
        self.period_combo.pack(side=LEFT)
        self.period_combo.bind("<<ComboboxSelected>>", self.on_period_change)

        # Chart Area
        self.chart_frame = ttk.Frame(self, padding=10)
        self.chart_frame.pack(fill=BOTH, expand=True)

        self.chart = BaseChart(self.chart_frame, "Technical Chart")
        self.chart.pack(fill=BOTH, expand=True)

        # Bottom Control Panel
        self.analysis_panel = AnalysisControlPanel(self, self.save_analysis)
        self.analysis_panel.pack(fill=X, side=BOTTOM)

        # BaseChart already tracks cursor position and manages mouse events

    def on_period_change(self, event):
        period_label = self.period_var.get()
        self.load_chart(period_label)

    def load_chart(self, period_label):
        # Map period labels to days
        period_map = {
            "3 Months": (90, "3M"),
            "6 Months": (180, "6M"),
            "9 Months": (270, "9M"),
            "1 Year": (365, "1Y"),
            "2 Years": (730, "2Y"),
            "5 Years": (1825, "5Y")
        }

        days, period_key = period_map.get(period_label, (365, "1Y"))

        print(f"[TechAnalysis] Fetching data for {period_label} ({days} days)...")

        def on_data_loaded(data):
            if not data:
                self.chart._show_no_data(f"No data for {period_label}")
                return

            print(f"[TechAnalysis] Plotting {len(data)} rows for {period_label}")
            print(f"[TechAnalysis] Period key: {period_key}")

            # Let BaseChart handle candles ONLY (no lines)
            # We do NOT add horizontal lines here because calling canvas.draw() after mpf.plot() clears the candles
            # Lines will only appear when user presses 'e', 'l', or 't' keys
            print(f"[TechAnalysis] Calling BaseChart.plot() with period_key={period_key}")
            self.chart.plot(data, period_key, lines=None)
            print(f"[TechAnalysis] BaseChart.plot() completed - candles rendered")

        self.async_run_bg(get_historical_prices(self.ticker, days), callback=on_data_loaded)

    # cursor y is now retrieved from self.chart.get_cursor_y()

    def on_key_press(self, event):
        """Handle keypress events to draw horizontal lines."""
        key = event.char.lower()

        if key not in ['e', 'l', 't']:
            return

        # Be defensive: older instances or mismatch could raise AttributeError
        cursor_y = None
        getter = getattr(self.chart, "get_cursor_y", None)
        if callable(getter):
            cursor_y = getter()
        if cursor_y is None or not isinstance(cursor_y, (int, float)):
            print(f"[TechAnalysis] No cursor position available")
            return

        # Set price and draw per-key in a single branch to avoid unbound var issues
        if key == 'e':
            price = round(cursor_y, 2)
            self.entry_price = price
            color = 'blue'
            label = f'Entry: R{price:.2f}'
            print(f"[TechAnalysis] Entry price set to R{price:.2f}")

            adder = getattr(self.chart, "add_horizontal_line", None)
            if callable(adder):
                adder(price, color, label)
            else:
                try:
                    line = add_axhline(self.chart.ax, price, color=color, label=label)
                    stored = getattr(self.chart, "horizontal_lines", None)
                    if isinstance(stored, list):
                        stored.append((price, color, label, line))
                    self.chart.canvas.draw()
                except Exception:
                    pass
            # Update UI panel
            self.analysis_panel.set_values(entry=price)

        elif key == 'l':
            price = round(cursor_y, 2)
            self.stop_loss = price
            color = 'red'
            label = f'Stop Loss: R{price:.2f}'
            print(f"[TechAnalysis] Stop loss set to R{price:.2f}")

            adder = getattr(self.chart, "add_horizontal_line", None)
            if callable(adder):
                adder(price, color, label)
            else:
                try:
                    line = add_axhline(self.chart.ax, price, color=color, label=label)
                    stored = getattr(self.chart, "horizontal_lines", None)
                    if isinstance(stored, list):
                        stored.append((price, color, label, line))
                    self.chart.canvas.draw()
                except Exception:
                    pass
            # Update UI panel
            self.analysis_panel.set_values(stop=price)

        elif key == 't':
            price = round(cursor_y, 2)
            self.target_price = price
            color = 'green'
            label = f'Target: R{price:.2f}'
            print(f"[TechAnalysis] Target price set to R{price:.2f}")

            adder = getattr(self.chart, "add_horizontal_line", None)
            if callable(adder):
                adder(price, color, label)
            else:
                try:
                    line = add_axhline(self.chart.ax, price, color=color, label=label)
                    stored = getattr(self.chart, "horizontal_lines", None)
                    if isinstance(stored, list):
                        stored.append((price, color, label, line))
                    self.chart.canvas.draw()
                except Exception:
                    pass
            # Update UI panel
            self.analysis_panel.set_values(target=price)

        # (UI updated in each branch)

    # horizontal-line drawing is delegated to BaseChart

    # redraw_horizontal_lines moved to BaseChart

    def save_analysis(self, values):
        """Save analysis data to database and redraw lines."""
        # --- 1) Sync internal state from panel values (these are in RANDS) ---
        self.entry_price  = values["entry_price"]
        self.target_price = values["target_price"]
        self.stop_loss    = values["stop_loss"]
        strategy          = values["strategy"]

        # --- 2) Convert GUI values (rand) back to cents for DB ---
        entry_c  = int(self.entry_price * 100)   if self.entry_price  is not None else None
        target_c = int(self.target_price * 100)  if self.target_price is not None else None
        stop_c   = int(self.stop_loss * 100)     if self.stop_loss    is not None else None

        # --- 3) Clear existing lines on the chart ---
        clearer = getattr(self.chart, "clear_horizontal_lines", None)
        if callable(clearer):
            clearer()
        else:
            # legacy fallback (shouldn't really be needed any more)
            try:
                stored = getattr(self.chart, "horizontal_lines", [])
                for _, _, _, lobj in list(stored):
                    try:
                        if lobj is not None:
                            lobj.remove()
                    except Exception:
                        pass
                if isinstance(stored, list):
                    stored.clear()
                self.chart.canvas.draw()
            except Exception:
                pass

        # --- 4) Draw new lines from the UPDATED prices ---
        if self.entry_price is not None:
            self.chart.add_horizontal_line(
                self.entry_price, 'blue', f'Entry: R{self.entry_price:.2f}'
            )
        if self.stop_loss is not None:
            self.chart.add_horizontal_line(
                self.stop_loss, 'red', f'Stop Loss: R{self.stop_loss:.2f}'
            )
        if self.target_price is not None:
            self.chart.add_horizontal_line(
                self.target_price, 'green', f'Target: R{self.target_price:.2f}'
            )

        # --- 5) Direction flag ---
        is_long = True
        if self.entry_price is not None and self.target_price is not None:
            is_long = self.target_price > self.entry_price

        print(
            f"[TechAnalysis] Saving analysis: "
            f"Entry={self.entry_price}, Target={self.target_price}, "
            f"Stop={self.stop_loss}, IsLong={is_long}"
        )

        # --- 6) Persist to DB in CENTS ---
        async def update_db():
            # Update watchlist
            query_wl = """
                UPDATE watchlist 
                SET entry_price = $1, stop_loss = $2, target_price = $3, is_long = $4
                WHERE ticker = $5
            """
            await DBEngine.execute(
                query_wl, entry_c, stop_c, target_c, is_long, self.ticker
            )

            # Update stock_analysis
            query_sa = """
                INSERT INTO stock_analysis (ticker, strategy)
                VALUES ($1, $2)
                ON CONFLICT (ticker) 
                DO UPDATE SET strategy = EXCLUDED.strategy
            """
            await DBEngine.execute(query_sa, self.ticker, strategy)

            print(f"[TechAnalysis] Database updated for {self.ticker}")

        self.async_run_bg(update_db())
    


    def load_existing_data(self):
        """Fetch existing analysis data from DB."""
        async def fetch_data():
            query = """
                SELECT 
                    w.entry_price, w.target_price, w.stop_loss,
                    sa.strategy
                FROM watchlist w
                LEFT JOIN stock_analysis sa ON w.ticker = sa.ticker
                WHERE w.ticker = $1
            """
            rows = await DBEngine.fetch(query, self.ticker)
            if rows:
                return dict(rows[0])
            return None

        def on_loaded(data):
            if data:
                # Convert DB cents → rands
                raw_entry = data.get("entry_price")
                raw_target = data.get("target_price")
                raw_stop = data.get("stop_loss")

                self.entry_price  = raw_entry  / 100 if raw_entry  else None
                self.target_price = raw_target / 100 if raw_target else None
                self.stop_loss    = raw_stop   / 100 if raw_stop   else None
                strategy = data.get("strategy")

                # Update Panel
                self.analysis_panel.set_values(
                    entry=self.entry_price,
                    target=self.target_price,
                    stop=self.stop_loss,
                    strategy=strategy
                )

                # Pass the prices to BaseChart so it can draw them after the plot
                to_store = []
                if self.entry_price:
                    to_store.append((self.entry_price, 'blue', f'Entry: R{self.entry_price:.2f}'))
                if self.stop_loss:
                    to_store.append((self.stop_loss, 'red', f'Stop Loss: R{self.stop_loss:.2f}'))
                if self.target_price:
                    to_store.append((self.target_price, 'green', f'Target: R{self.target_price:.2f}'))

                if to_store:
                    setter = getattr(self.chart, "set_horizontal_lines", None)
                    redrawer = getattr(self.chart, "redraw_horizontal_lines", None)
                    if callable(setter):
                        setter(to_store)
                    else:
                        # fallback: append entries to horizontal_lines storage
                        stored = getattr(self.chart, "horizontal_lines", None)
                        if isinstance(stored, list):
                            stored.extend([(p, c, l, None) for (p, c, l) in to_store])

                    if callable(redrawer):
                        redrawer()
                    else:
                        # fallback: attempt to draw directly
                        try:
                            for p, c, l in to_store:
                                add_axhline(self.chart.ax, price=p, color=c, label=l)
                            try:
                                add_legend_for_hlines(self.chart.ax, to_store)
                            except Exception:
                                pass
                            self.chart.canvas.draw()
                        except Exception:
                            pass

        self.async_run_bg(fetch_data(), callback=on_loaded)
