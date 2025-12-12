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
from core.utils.chart_drawing_utils import build_lines_from_state
from components.analysis_service import fetch_analysis, delete_price_level
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
        # Support and resistance lists: list of tuples (level_id or None, price)
        self.support_levels = []
        self.resistance_levels = []
        # Horizontal-line storage handled by BaseChart.horizontal_lines

        self.create_widgets()
        self.load_chart("1 Year") # Default to 1 Year
        self.load_existing_data()
        self._update_ticker_name()

        # Bind keypress events to the key handler
        # We'll wire the key handler during widget creation (below)
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
        # Navigation arrows (prev/next) to cycle watchlist order
        self.prev_btn = ttk.Button(control_frame, text="◀ Prev", bootstyle="secondary", command=self._on_prev_ticker)
        self.prev_btn.pack(side=LEFT, padx=(6, 0))
        self.next_btn = ttk.Button(control_frame, text="Next ▶", bootstyle="secondary", command=self._on_next_ticker)
        self.next_btn.pack(side=LEFT, padx=(6, 0))
        
        # Upside label (pack BEFORE the long name so it doesn't get squeezed off-screen)
        self.upside_label = ttk.Label(control_frame, text="", font=("Helvetica", 12, "bold"), foreground="#4CAF50")
        self.upside_label.pack(side=LEFT, padx=(10, 0))

        # Ticker full name label
        # Use wraplength so long names don't hide other controls.
        self.ticker_name_label = ttk.Label(
            control_frame,
            text="",
            font=("Helvetica", 14, "bold"),
            foreground="#2196F3",
            wraplength=520,
            justify=LEFT,
        )
        self.ticker_name_label.pack(side=LEFT, padx=(10, 0))
        
        # Default navigation state is disabled until we can evaluate parent watchlist
        try:
            self.prev_btn.configure(state='disabled')
            self.next_btn.configure(state='disabled')
        except Exception:
            pass

        # Chart Area
        self.chart_frame = ttk.Frame(self, padding=10)
        self.chart_frame.pack(fill=BOTH, expand=True)

        self.chart = BaseChart(self.chart_frame, "Technical Chart")
        self.chart.pack(fill=BOTH, expand=True)

        # Bottom Control Panel
        self.analysis_panel = AnalysisControlPanel(
            self,
            self.save_analysis,
            on_delete_support_callback=self._on_delete_support,
            on_delete_resistance_callback=self._on_delete_resistance,
        )
        # Reduce the analysis panel height in the window so chart has more vertical room
        try:
            self.analysis_panel.configure(height=220)
            self.analysis_panel.pack_propagate(False)
        except Exception:
            pass
        # Status widget lets the user change the watchlist status for this ticker
        self.status_widget = StatusWidget(control_frame, lambda: self.ticker, self.async_run_bg, on_saved=self._on_status_saved)
        self.status_widget.pack(side=RIGHT, padx=(6,0))
        self.analysis_panel.pack(fill=X, side=BOTTOM)
        # Analysis drawer for redrawing the chart from state
        try:
            from components.analysis_drawer import AnalysisDrawer
            from components.analysis_keyhandler import AnalysisKeyHandler
            self.analysis_drawer = AnalysisDrawer(self.chart)
            self.key_handler = AnalysisKeyHandler(self, self.analysis_drawer)
        except Exception:
            self.analysis_drawer = None
            self.key_handler = None

        # BaseChart already tracks cursor position and manages mouse events
        try:
            self._update_navigation_state()
        except Exception:
            pass

    def on_period_change(self, event):
        period_label = self.period_var.get()
        self.load_chart(period_label)

    def update_ticker(self, ticker):
        """Update the window with a new ticker"""
        try:
            logging.getLogger(__name__).info("\n[TechAnalysis] Updating to ticker: %s", ticker)
            self.ticker = ticker
            self.title(f"{ticker} - Technical Analysis")
            self._update_ticker_name()
            # Update status widget if present
            try:
                if hasattr(self, "status_widget") and self.status_widget is not None:
                    # status_widget displays the current ticker via a lambda; no additional setup required
                    pass
            except Exception:
                pass
            # reload data & charts for new ticker
            try:
                self.load_chart(self.period_var.get())
            except Exception:
                pass
            try:
                self.load_existing_data()
            except Exception:
                logging.getLogger(__name__).exception('Failed reloading data after update_ticker')
        except Exception:
            logging.getLogger(__name__).exception('Failed updating ticker')
        # Update arrow enablement
        try:
            self._update_navigation_state()
        except Exception:
            pass
        # Update upside display for new ticker
        try:
            self._update_upside_display()
        except Exception:
            pass

    def _update_navigation_state(self):
        try:
            # Find a watchlist-like object with get_ordered_tickers
            parent = getattr(self, 'master', None)
            watchlist_obj = None
            if parent and hasattr(parent, 'get_ordered_tickers'):
                watchlist_obj = parent
            elif parent and hasattr(parent, 'watchlist'):
                watchlist_obj = getattr(parent, 'watchlist')
            else:
                # Walk up the master chain looking for a watchlist-like object
                cur = parent
                while cur is not None:
                    try:
                        if hasattr(cur, 'get_ordered_tickers'):
                            watchlist_obj = cur
                            break
                    except Exception:
                        pass
                    cur = getattr(cur, 'master', None)

            # If we found a watchlist, evaluate size and enable/disable accordingly
            if watchlist_obj is not None and callable(getattr(watchlist_obj, 'get_ordered_tickers', None)):
                try:
                    t = watchlist_obj.get_ordered_tickers() or []
                except Exception:
                    t = []
                if not t or len(t) <= 1:
                    try:
                        self.prev_btn.configure(state='disabled')
                        self.next_btn.configure(state='disabled')
                    except Exception:
                        pass
                    return
                else:
                    try:
                        self.prev_btn.configure(state='normal')
                        self.next_btn.configure(state='normal')
                    except Exception:
                        pass
            else:
                # No watchlist identified — keep navigation disabled
                try:
                    self.prev_btn.configure(state='disabled')
                    self.next_btn.configure(state='disabled')
                except Exception:
                    pass
        except Exception:
            pass

    def _find_watchlist_widget(self):
        """Try to find a WatchlistWidget instance in the parent chain or 'master'.

        Returns the widget if found, else None.
        """
        try:
            parent = getattr(self, 'master', None)
            # 1. If parent itself is a watchlist
            if parent and hasattr(parent, 'get_adjacent_ticker') and hasattr(parent, 'get_ordered_tickers'):
                return parent
            # 2. If parent is command center that has .watchlist attribute
            if parent and hasattr(parent, 'watchlist'):
                return getattr(parent, 'watchlist')
            # 3. Walk up the master chain looking for object with 'get_adjacent_ticker'
            cur = parent
            while cur is not None:
                try:
                    if hasattr(cur, 'get_adjacent_ticker') and hasattr(cur, 'get_ordered_tickers'):
                        return cur
                except Exception:
                    pass
                cur = getattr(cur, 'master', None)
        except Exception:
            pass
        return None

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
            # Ensure window stays on top after chart loads
            try:
                self.lift()
            except Exception:
                pass

        self.async_run_bg(get_historical_prices(self.ticker, days), callback=on_data_loaded)

    # cursor y is now retrieved from self.chart.get_cursor_y()

    def on_key_press(self, event):
        """Handle keypress events and delegate to the key handler (if present)."""
        try:
            if hasattr(self, 'key_handler') and self.key_handler:
                handled = self.key_handler.handle_key(event)
                if handled:
                    return
        except Exception:
            logging.getLogger(__name__).exception('Key handler failed')

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
        # Persist the support/res lists (in cents) - send None if empty
        support_cs = None
        resistance_cs = None
        if getattr(self, 'support_levels', None):
            support_cs = [int(p * 100) for (_id, p) in self.support_levels if p is not None]
        if getattr(self, 'resistance_levels', None):
            resistance_cs = [int(p * 100) for (_id, p) in self.resistance_levels if p is not None]

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
        for (_id, p) in getattr(self, 'support_levels', []) or []:
            if p is not None:
                self.chart.add_horizontal_line(p, 'green', f'Support: R{p:.2f}')
        for (_id, p) in getattr(self, 'resistance_levels', []) or []:
            if p is not None:
                self.chart.add_horizontal_line(p, 'red', f'Resistance: R{p:.2f}')

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
            await update_analysis_db(self.ticker, entry_c, stop_c, target_c, is_long, strategy, support_cs, resistance_cs)

        def _on_saved(_res=None):
            # reload to refresh persisted levels with their assigned IDs
            try:
                self.load_existing_data()
            except Exception:
                logging.getLogger(__name__).exception('Failed reloading data after save')

        try:
            # Disable the save button while DB update runs
            run_bg_with_button(self.analysis_panel.save_btn, self.async_run_bg, update_db_wrapper(), callback=_on_saved)
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
            cb = getattr(self, 'on_status_saved_callback', None)
            if callable(cb):
                try:
                    cb()
                except Exception:
                    logging.getLogger(__name__).exception('on_status_saved_callback failed')
        except Exception:
            pass
    

    def _on_delete_support(self, level_id, price):
        """Called by AnalysisControlPanel when the user requests deletion of a support level.

        If level_id is None the item is unsaved, and we remove it locally; otherwise delete from DB.
        """
        try:
            if level_id is None:
                # Remove the first unsaved entry matching the price
                for i, (lid, p) in enumerate(self.support_levels):
                    if lid is None and p == price:
                        self.support_levels.pop(i)
                        break
                # Update panel
                try:
                    self.analysis_panel.set_levels(support=self.support_levels, resistance=self.resistance_levels)
                except Exception:
                    pass
                try:
                    self._draw_all_levels()
                except Exception:
                    logging.getLogger(__name__).exception('Failed redrawing after support deletion')
                return

            # Delete persisted level from DB
            async def delete_task():
                await delete_price_level(level_id)
                # No-op: leave for context (ensures we still call delete).
            # Optimistically remove it from our in-memory list + UI so chart updates immediately
            try:
                for i, (lid, p) in enumerate(self.support_levels):
                    if lid == level_id:
                        self.support_levels.pop(i)
                        break
                try:
                    self.analysis_panel.set_levels(support=self.support_levels, resistance=self.resistance_levels)
                except Exception:
                    pass
                try:
                    self._draw_all_levels()
                except Exception:
                    logging.getLogger(__name__).exception('Failed optimistic redraw after support delete')
            except Exception:
                pass

            def on_deleted(_res=None):
                # refresh to reflect deleted row
                try:
                    self.load_existing_data()
                except Exception:
                    logging.getLogger(__name__).exception('Failed to refresh after deleting support level')

            self.async_run_bg(delete_task(), callback=on_deleted)
        except Exception:
            logging.getLogger(__name__).exception('Failed processing delete support request')

    def _on_delete_resistance(self, level_id, price):
        """Called by AnalysisControlPanel when the user requests deletion of a resistance level.

        If level_id is None the item is unsaved and we remove it locally; otherwise delete from DB.
        """
        try:
            if level_id is None:
                for i, (lid, p) in enumerate(self.resistance_levels):
                    if lid is None and p == price:
                        self.resistance_levels.pop(i)
                        break
                try:
                    self.analysis_panel.set_levels(support=self.support_levels, resistance=self.resistance_levels)
                except Exception:
                    pass
                try:
                    self._draw_all_levels()
                except Exception:
                    logging.getLogger(__name__).exception('Failed redrawing after resistance deletion')
                return

            async def delete_task():
                await delete_price_level(level_id)

            # Optimistically remove persisted level from our in-memory list + UI and redraw
            try:
                for i, (lid, p) in enumerate(self.resistance_levels):
                    if lid == level_id:
                        self.resistance_levels.pop(i)
                        break
                try:
                    self.analysis_panel.set_levels(support=self.support_levels, resistance=self.resistance_levels)
                except Exception:
                    pass
                try:
                    self._draw_all_levels()
                except Exception:
                    logging.getLogger(__name__).exception('Failed optimistic redraw after resistance delete')
            except Exception:
                pass

            def on_deleted(_res=None):
                try:
                    self.load_existing_data()
                except Exception:
                    logging.getLogger(__name__).exception('Failed to refresh after deleting resistance level')

            self.async_run_bg(delete_task(), callback=on_deleted)
        except Exception:
            logging.getLogger(__name__).exception('Failed processing delete resistance request')

    def _draw_all_levels(self):
        """Rebuild the chart horizontal lines from the in-memory levels and entry/target/stop."""
        try:
            lines = build_lines_from_state(
                getattr(self, 'entry_price', None),
                getattr(self, 'stop_loss', None),
                getattr(self, 'target_price', None),
                getattr(self, 'support_levels', None),
                getattr(self, 'resistance_levels', None),
            )
        except Exception:
            logging.getLogger(__name__).exception('Failed building levels to draw')
            lines = []
        setter = getattr(self.chart, 'set_horizontal_lines', None)
        if callable(setter) and lines:
            try:
                setter(lines)
            except Exception:
                logging.getLogger(__name__).exception('Failed calling set_horizontal_lines')


    def load_existing_data(self):
        """Fetch existing analysis data from DB."""
        async def fetch_data():
            # Fetch entry/target/stop from watchlist and strategy from stock_analysis.
            # Also fetch latest support/resistance price_level values from stock_price_levels.
            query = """
                SELECT 
                    w.entry_price, w.target_price, w.stop_loss, w.status,
                    sa.strategy,
                    (SELECT array_agg(spl.level_id ORDER BY spl.date_added DESC) FROM public.stock_price_levels spl WHERE spl.ticker = w.ticker AND spl.level_type = 'support') AS support_ids,
                    (SELECT array_agg(spl.price_level ORDER BY spl.date_added DESC) FROM public.stock_price_levels spl WHERE spl.ticker = w.ticker AND spl.level_type = 'support') AS support_prices,
                    (SELECT array_agg(spl.level_id ORDER BY spl.date_added DESC) FROM public.stock_price_levels spl WHERE spl.ticker = w.ticker AND spl.level_type = 'resistance') AS resistance_ids,
                    (SELECT array_agg(spl.price_level ORDER BY spl.date_added DESC) FROM public.stock_price_levels spl WHERE spl.ticker = w.ticker AND spl.level_type = 'resistance') AS resistance_prices
                FROM watchlist w
                LEFT JOIN stock_analysis sa ON w.ticker = sa.ticker
                WHERE w.ticker = $1
            """
            return await fetch_analysis(self.ticker)

        def on_loaded(data):
            if data:
                # Convert DB cents → rands (use helper to handle Decimal/None)
                raw_entry = data.get("entry_price")
                raw_target = data.get("target_price")
                raw_stop = data.get("stop_loss")
                raw_support_ids = data.get("support_ids") or []
                raw_support_prices = data.get("support_prices") or []
                raw_res_ids = data.get("resistance_ids") or []
                raw_res_prices = data.get("resistance_prices") or []

                self.entry_price = price_from_db(raw_entry)
                self.target_price = price_from_db(raw_target)
                self.stop_loss = price_from_db(raw_stop)
                # Build lists of persisted (id, price) tuples
                try:
                    self.support_levels = []
                    for _id, p in zip(raw_support_ids, raw_support_prices):
                        self.support_levels.append((int(_id) if _id is not None else None, price_from_db(p)))
                except Exception:
                    self.support_levels = []
                try:
                    self.resistance_levels = []
                    for _id, p in zip(raw_res_ids, raw_res_prices):
                        self.resistance_levels.append((int(_id) if _id is not None else None, price_from_db(p)))
                except Exception:
                    self.resistance_levels = []
                strategy = data.get("strategy")
                status = data.get("status")

                # Update Panel
                self.analysis_panel.set_values(
                    entry=self.entry_price,
                    target=self.target_price,
                    stop=self.stop_loss,
                    strategy=strategy
                )
                # Update support/res labels in the analysis panel if present
                try:
                    if getattr(self.analysis_panel, 'set_levels', None):
                        self.analysis_panel.set_levels(support=self.support_levels, resistance=self.resistance_levels)
                except Exception:
                    pass

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
                # We'll build a full final lines list below including support/resistance

                # Build the full set of lines from DB and in-memory levels
                try:
                    # to_store includes entry/target/stop from DB via build_saved_levels_from_row
                    if getattr(self, 'support_levels', None):
                        for (_id, p) in self.support_levels:
                            if p is not None:
                                to_store.append((p, 'green', f'Support: R{p:.2f}'))
                except Exception:
                    pass
                try:
                    if getattr(self, 'resistance_levels', None):
                        for (_id, p) in self.resistance_levels:
                            if p is not None:
                                to_store.append((p, 'red', f'Resistance: R{p:.2f}'))
                except Exception:
                    pass
                if to_store:
                    setter = getattr(self.chart, "set_horizontal_lines", None)
                    if callable(setter):
                        setter(to_store)
                # Update navigation state in case parent watchlist changed
                try:
                    self._update_navigation_state()
                except Exception:
                    pass
                # Update upside display
                try:
                    self._update_upside_display()
                except Exception:
                    pass
                # Ensure window stays on top after data loads
                try:
                    self.lift()
                except Exception:
                    pass

        self.async_run_bg(fetch_data(), callback=on_loaded)
    
    def _update_ticker_name(self):
        """Fetch and display the full name for the current ticker."""
        async def fetch_name():
            query = "SELECT full_name FROM stock_details WHERE ticker = $1"
            rows = await DBEngine.fetch(query, self.ticker)
            return rows[0]['full_name'] if rows and rows[0].get('full_name') else ""
        
        def on_name_loaded(full_name):
            if full_name:
                self.ticker_name_label.config(text=full_name)
            else:
                self.ticker_name_label.config(text="")
        
        self.async_run_bg(fetch_name(), callback=on_name_loaded)
    
    def _update_upside_display(self):
        """Calculate and display the upside potential based on current price, target, and position direction."""
        try:
            # Get current price from database
            async def get_current_price():
                query = "SELECT close_price FROM daily_stock_data WHERE ticker = $1 ORDER BY trade_date DESC LIMIT 1"
                rows = await DBEngine.fetch(query, self.ticker)
                return rows[0]['close_price'] if rows else None
            
            def on_price_loaded(current_price):
                try:
                    # Normalize price units.
                    # In this app, watchlist prices are stored in cents, while UI values are rands.
                    # Detect cents by comparing to the target (rand) and downscale when needed.
                    cp = None
                    try:
                        cp = float(current_price) if current_price is not None else None
                    except Exception:
                        cp = None

                    if cp is not None and self.target_price is not None:
                        try:
                            if cp > (float(self.target_price) * 10.0):
                                cp = cp / 100.0
                        except Exception:
                            pass

                    # Calculate upside if we have the required data
                    if (cp is not None and self.target_price is not None and cp > 0):
                        
                        # Determine if it's a long position (default assumption)
                        is_long = True
                        if hasattr(self, 'entry_price') and self.entry_price is not None:
                            is_long = self.target_price > self.entry_price
                        
                        # Calculate upside
                        if is_long:
                            gain = (self.target_price - cp) / cp * 100
                        else:
                            gain = (cp - self.target_price) / cp * 100
                        
                        upside_str = f"Upside: {abs(float(gain)):.1f}%"
                        self.upside_label.config(text=upside_str)
                    else:
                        self.upside_label.config(text="")
                        
                except Exception as e:
                    logging.getLogger(__name__).warning(f"Failed to calculate upside: {e}")
                    self.upside_label.config(text="")
            
            self.async_run_bg(get_current_price(), callback=on_price_loaded)
                
        except Exception as e:
            logging.getLogger(__name__).warning(f"Failed to start upside calculation: {e}")
            self.upside_label.config(text="")
    
    # -------------------------------------------------------------------------
    # Navigation helpers: cycle through watchlist order
    # -------------------------------------------------------------------------
    def _on_prev_ticker(self):
        try:
            w = self._find_watchlist_widget()
            if w and hasattr(w, 'get_adjacent_ticker'):
                prev_t = w.get_adjacent_ticker(self.ticker, direction=-1)
                if prev_t:
                    try:
                        if callable(getattr(w, 'on_select', None)):
                            w.on_select(prev_t)
                    except Exception:
                        pass
                    self.update_ticker(prev_t)
                    # Bring this window to the front after other windows reload
                    self.after(100, self.lift)
        except Exception:
            logging.getLogger(__name__).exception('Failed moving to previous ticker')

    def _on_next_ticker(self):
        try:
            w = self._find_watchlist_widget()
            if w and hasattr(w, 'get_adjacent_ticker'):
                nxt = w.get_adjacent_ticker(self.ticker, direction=1)
                if nxt:
                    try:
                        if callable(getattr(w, 'on_select', None)):
                            w.on_select(nxt)
                    except Exception:
                        pass
                    self.update_ticker(nxt)
                    # Bring this window to the front after other windows reload
                    self.after(100, self.lift)
        except Exception:
            logging.getLogger(__name__).exception('Failed moving to next ticker')
