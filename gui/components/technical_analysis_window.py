import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, X, LEFT, RIGHT, BOTTOM
import matplotlib.pyplot as plt
import logging
import pandas as pd
import mplfinance as mpf
from modules.data.market import get_historical_prices
from components.base_chart import BaseChart
from core.db.engine import DBEngine
from core.utils.technical_utils import (
    build_saved_levels_from_row,
    price_from_db,
    update_analysis_db,
)
from components.analysis_control_panel import AnalysisControlPanel
from components.status_widget import StatusWidget
from components.button_utils import run_bg_with_button

class TechnicalAnalysisWindow(ttk.Toplevel):
    def __init__(self, parent, ticker, async_run_bg, on_status_saved_callback=None):
        super().__init__(parent)
        self.title(f"{ticker} - Technical Analysis")
        self.geometry("1000x700")

        self.ticker = ticker
        self.async_run_bg = async_run_bg

        # Optional callback invoked after watchlist status changes.
        self.on_status_saved_callback = on_status_saved_callback

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
        # Status widget lets the user change the watchlist status for this ticker
        self.status_widget = StatusWidget(control_frame, lambda: self.ticker, self.async_run_bg, on_saved=self._on_status_saved)
        self.status_widget.pack(side=RIGHT, padx=(6,0))
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

        logging.getLogger(__name__).debug(
            "[TechAnalysis] Fetching data for %s (%d days)...", period_label, days
        )

        def on_data_loaded(data):
            if not data:
                self.chart._show_no_data(f"No data for {period_label}")
                return

            logging.getLogger(__name__).debug(
                "[TechAnalysis] Plotting %d rows for %s", len(data), period_label
            )
            logging.getLogger(__name__).debug("[TechAnalysis] Period key: %s", period_key)

            # Let BaseChart handle candles ONLY (no lines)
            # We do NOT add horizontal lines here because calling canvas.draw() after mpf.plot() clears the candles
            # Lines will only appear when user presses 'e', 'l', or 't' keys
            logging.getLogger(__name__).debug(
                "[TechAnalysis] Calling BaseChart.plot() with period_key=%s", period_key
            )
            self.chart.plot(data, period_key, lines=None)
            logging.getLogger(__name__).debug(
                "[TechAnalysis] BaseChart.plot() completed - candles rendered"
            )

        self.async_run_bg(get_historical_prices(self.ticker, days), callback=on_data_loaded)

    # cursor y is now retrieved from self.chart.get_cursor_y()

    def on_key_press(self, event):
        """Handle keypress events to draw horizontal lines."""
        # Only accept keypresses for drawing lines if the chart has focus (i.e. was clicked)
        # and no input field has focus. This avoids accidental price changes while typing.
        try:
            # if analysis panel reports any input focused -> ignore keypresses
            if hasattr(self, "analysis_panel") and callable(getattr(self.analysis_panel, "has_any_input_focus", None)) and self.analysis_panel.has_any_input_focus():
                return
        except Exception:
            pass

        # Chart must be clicked/focused for keypress actions to be handled
        try:
            if not hasattr(self, "chart") or not callable(getattr(self.chart, "has_focus", None)) or not self.chart.has_focus():
                return
        except Exception:
            # Be defensive: if chart focus check fails, skip handling
            return

        key = event.char.lower()

        if key not in ['e', 'l', 't']:
            return

        # Be defensive: older instances or mismatch could raise AttributeError
        cursor_y = None
        getter = getattr(self.chart, "get_cursor_y", None)
        if callable(getter):
            cursor_y = getter()
        if cursor_y is None or not isinstance(cursor_y, (int, float)):
            logging.getLogger(__name__).warning(
                "[TechAnalysis] No cursor position available"
            )
            return

        # Map keys to attributes / colors / panel updates so we can handle in one place
        key_map = {
            'e': ('entry_price', 'blue', 'entry'),
            'l': ('stop_loss', 'red', 'stop'),
            't': ('target_price', 'green', 'target'),
        }

        attr_name, color, panel_field = key_map[key]
        price = round(cursor_y, 2)
        setattr(self, attr_name, price)
        label = f"{panel_field.capitalize()}: R{price:.2f}" if panel_field != 'entry' else f"Entry: R{price:.2f}"
        logging.getLogger(__name__).info(
            "[TechAnalysis] %s price set to R%.2f", panel_field.capitalize(), price
        )

        # Use BaseChart API to add a horizontal line — we expect this to exist
        # and prefer centralized behavior (no direct ax manipulation here).
        self.chart.add_horizontal_line(price, color, label)

        # Update UI panel
        kwargs = {panel_field: price}
        self.analysis_panel.set_values(**kwargs)

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
            # If BaseChart doesn't provide clear_horizontal_lines (very old instances),
            # skip explicit clearing and rely on the chart API to manage state.
            logging.getLogger(__name__).warning(
                "[TechAnalysis] clear_horizontal_lines not available — skipping explicit clear"
            )

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

        logging.getLogger(__name__).info(
            "[TechAnalysis] Saving analysis: Entry=%s, Target=%s, Stop=%s, IsLong=%s",
            str(self.entry_price),
            str(self.target_price),
            str(self.stop_loss),
            str(is_long),
        )

        # --- 6) Persist to DB in CENTS ---
        # offload DB updates to helper that performs the same async operations
        async def update_db_wrapper():
            await update_analysis_db(self.ticker, entry_c, stop_c, target_c, is_long, strategy)

        try:
            # Disable the save button while DB update runs
            run_bg_with_button(self.analysis_panel.save_btn, self.async_run_bg, update_db_wrapper())
        except Exception:
            # fallback
            self.async_run_bg(update_db_wrapper())

    def _on_status_saved(self, ticker: str, status: str):
        """Callback invoked when StatusWidget confirms a saved status."""
        logging.getLogger(__name__).info("Status for %s set to %s", ticker, status)
        # reload existing data so UI is kept consistent
        try:
            self.load_existing_data()
        except Exception:
            logging.getLogger(__name__).exception("Failed to refresh existing analysis data after status change")
        # Notify parent that status changed so external UI (eg. watchlist) can refresh
        try:
            if callable(getattr(self, 'on_status_saved_callback', None)):
                try:
                    self.on_status_saved_callback()
                except Exception:
                    logging.getLogger(__name__).exception('on_status_saved_callback failed')
        except Exception:
            pass
    


    def load_existing_data(self):
        """Fetch existing analysis data from DB."""
        async def fetch_data():
            query = """
                SELECT 
                    w.entry_price, w.target_price, w.stop_loss, w.status,
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
                # Convert DB cents → rands (use helper to handle Decimal/None)
                raw_entry = data.get("entry_price")
                raw_target = data.get("target_price")
                raw_stop = data.get("stop_loss")

                self.entry_price = price_from_db(raw_entry)
                self.target_price = price_from_db(raw_target)
                self.stop_loss = price_from_db(raw_stop)
                strategy = data.get("strategy")
                status = data.get("status")

                # Update Panel
                self.analysis_panel.set_values(
                    entry=self.entry_price,
                    target=self.target_price,
                    stop=self.stop_loss,
                    strategy=strategy
                )

                # Update status widget if available
                try:
                    if hasattr(self, "status_widget") and status is not None:
                        # If the status is not one of VALID_STATUSES, ignore
                        if status in getattr(self.status_widget, "VALID_STATUSES", []):
                            self.status_widget.status_var.set(status)
                except Exception:
                    logging.getLogger(__name__).exception("Failed updating status widget")

                # Pass the prices to BaseChart so it can draw them after the plot
                to_store = build_saved_levels_from_row(data)

                if to_store:
                    setter = getattr(self.chart, "set_horizontal_lines", None)
                    redrawer = getattr(self.chart, "redraw_horizontal_lines", None)
                    # use BaseChart API where supported
                    if callable(setter):
                        setter(to_store)
                    if callable(redrawer):
                        redrawer()

        self.async_run_bg(fetch_data(), callback=on_loaded)
