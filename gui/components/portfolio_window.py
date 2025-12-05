import ttkbootstrap as ttk
from ttkbootstrap.constants import LEFT, RIGHT, BOTH, X, Y, END
import tkinter as tk
from tkinter import simpledialog, messagebox
from typing import Optional
import logging

from modules.market_agent.prices import run_price_update
from components.portfolio_service import PortfolioService
from components.portfolio_list_widget import PortfolioListWidget
from components.holdings_widget import HoldingsWidget
from components.holding_form_widget import HoldingFormWidget
from components.totals_status_widget import TotalsStatusWidget
from components.button_utils import run_bg_with_button

logger = logging.getLogger(__name__)


class PortfolioWindow(ttk.Toplevel):
    """A simple modal window to manage portfolios and holdings (CRUD).

    Usage: PortfolioWindow(parent, async_run, async_run_bg)
    async_run: function to run coroutine and wait for result (sync wrapper)
    async_run_bg: function to run coroutine in background and call callback when done
    """

    def __init__(self, parent, async_run, async_run_bg):
        super().__init__(parent)
        self.title("Portfolio Manager")
        # Larger default size - more space for holdings
        self.geometry("1600x700")
        self.async_run = async_run
        self.async_run_bg = async_run_bg

        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.service = PortfolioService()
        self.create_widgets()
        # initial load
        self.load_portfolios()

    def create_widgets(self):
        container = ttk.Frame(self, padding=8)
        container.pack(fill=BOTH, expand=True)

        # Left: Portfolio list + actions
        left = ttk.Frame(container)
        left.pack(side=LEFT, fill=Y, padx=6, pady=6)
        self.portfolio_list_widget = PortfolioListWidget(left, select_callback=self.on_portfolio_select)
        self.portfolio_list_widget.pack(fill=Y, expand=False)

        btn_frame = ttk.Frame(left)
        btn_frame.pack(fill=X, pady=(6, 0))
        self.create_btn = ttk.Button(btn_frame, text="New", bootstyle="success", command=self.create_portfolio)
        self.create_btn.pack(side=LEFT, padx=4)
        self.rename_btn = ttk.Button(btn_frame, text="Rename", command=self.rename_portfolio)
        self.rename_btn.pack(side=LEFT, padx=4)
        self.delete_portfolio_btn = ttk.Button(btn_frame, text="Delete", bootstyle="danger", command=self.delete_portfolio)
        self.delete_portfolio_btn.pack(side=LEFT, padx=4)

        # Right: Holdings + form
        right = ttk.Frame(container)
        right.pack(side=RIGHT, fill=BOTH, expand=True, padx=6, pady=6)

        top = ttk.Frame(right)
        top.pack(fill=X)
        ttk.Label(top, text="Holdings", font=(None, 12, "bold")).pack(anchor="w")

        columns_frame = ttk.Frame(right)
        columns_frame.pack(fill=BOTH, expand=True)

        # attach Treeview to the `right` frame so layout behaves correctly
        # columns: ticker, qty, avg (stored in cents), cost_value (R), latest (R), pl (R), pct (P/L %)
        self.holdings_widget = HoldingsWidget(right, select_callback=self.on_holding_select)
        self.holdings_widget.pack(fill=BOTH, expand=True, pady=(6, 8))

        # tags to color-code P/L: positive -> green, negative -> red, zero/none -> default
        # tag configuration for P/L is handled by HoldingsWidget

        # when a holding row is selected, populate the entry fields
        # selection binding handled inside HoldingsWidget

        # sensible default column widths (pixels)
        # column layout handled inside HoldingsWidget
        form = ttk.Frame(right, padding=6)
        form.pack(fill=X)

        # use StringVars so we can trace content and enable/disable the Add/Update button
        # form widget created and will expose variables
        self.form_widget = HoldingFormWidget(form, change_callback=self._validate_form)
        self.form_widget.pack(fill=X)
        # entries and trace binding handled inside HoldingFormWidget

        # entries created inside HoldingFormWidget

        # clarify units next to the price field (in red)
        # use tk.Label so we can quickly set a red foreground color without creating a new ttk style
        # units handled in form (simplified)

        # form layout delegated to HoldingFormWidget

        actions = ttk.Frame(right)
        actions.pack(fill=X, pady=(6, 0))
        # keep a reference to the Add/Update button so we can enable/disable it
        self.add_update_btn = ttk.Button(actions, text="Add/Update Holding", bootstyle="primary", command=self.add_or_update_holding)
        self.add_update_btn.pack(side=LEFT, padx=4)
        self.add_update_btn.configure(state="disabled")
        self.delete_holding_btn = ttk.Button(actions, text="Delete Holding", bootstyle="danger", command=self.delete_holding)
        self.delete_holding_btn.pack(side=LEFT, padx=4)
        # quick download latest prices from yfinance for all tickers
        self.get_prices_btn = ttk.Button(actions, text="Get latest prices", bootstyle="info", command=self.fetch_latest_prices)
        self.get_prices_btn.pack(side=LEFT, padx=6)

        # trace input changes to validate form
        # form trace handled in HoldingFormWidget; wire add/update validation on construct

        status = ttk.Frame(self)
        status.pack(fill=X, side=tk.BOTTOM)
        self.status_label = ttk.Label(status, text="Ready")
        self.status_label.pack(side=LEFT, padx=8, pady=6)

        # Totals display (right side of status bar)
        # Total Value (R), Total P/L (R) and Total P/L (%) across all portfolios
        self.totals_widget = TotalsStatusWidget(status)
        self.totals_widget.pack(side=RIGHT)

    # ---- Persistence helpers (async) ----
    def load_portfolios(self):
        self.async_run_bg(self.service.fetch_portfolios(), callback=self._on_portfolios_loaded)

    # PortfolioService handles fetch_portfolios

    def _on_portfolios_loaded(self, result):
        # update the list widget
        self.portfolio_list_widget.set_items(result)
        self._current_portfolio_id = None
        # auto-select the first portfolio (if any) so holdings load immediately
        if result:
            self.portfolio_list_widget.auto_select_first()
            # trigger load
            self.on_portfolio_select()
        # refresh totals across portfolios when portfolios are loaded
        try:
            self.async_run_bg(self.service.fetch_totals(), callback=self._on_totals_loaded)
        except Exception:
            pass

    def _selected_portfolio(self) -> Optional[int]:
        selected_text = self.portfolio_list_widget.get_selected()
        if not selected_text:
            return None
        text = selected_text
        try:
            pid = int(text.split(" - ")[0])
            return pid
        except Exception:
            return None

    def on_portfolio_select(self, event=None):
        pid = self._selected_portfolio()
        if pid is None:
            return
        self._current_portfolio_id = pid
        # portfolio selection may change whether Add/Update is valid
        try:
            self._validate_form()
        except Exception:
            pass
        # load holdings
        self.async_run_bg(self.service.fetch_holdings(pid), callback=self._on_holdings_loaded)

    # PortfolioService handles fetch_holdings

    # ---- Totals across all portfolios ----
    def load_totals(self):
        try:
            self.async_run_bg(self.service.fetch_totals(), callback=self._on_totals_loaded)
        except Exception:
            pass

    # PortfolioService handles computing totals

    def _on_totals_loaded(self, result):
        try:
            total_pl = result.get("total_pl", 0.0)
            total_pct = result.get("total_pct", 0.0)
            total_value = result.get("total_value", 0.0)
            # update totals widget
            try:
                self.totals_widget.update_totals(total_value=total_value, total_pl=total_pl, total_pct=total_pct)
            except Exception:
                logger.exception("Failed updating totals widget")
            # color and pct handled by totals widget
        except Exception:
            logger.exception("Failed updating totals UI")

    # ---- Download latest prices (yfinance) ----
    def fetch_latest_prices(self):
        """Kick off a background task that downloads latest prices for all tickers using yfinance.

        Uses the existing modules.market_agent.prices.run_price_update implementation.
        """
        try:
            # update status and use helper to disable the button while running
            self.status_label.configure(text="Downloading latest prices...")
            run_bg_with_button(self.get_prices_btn, self.async_run_bg, run_price_update(), callback=self._on_prices_fetched)
        except Exception:
            logger.exception("Failed starting price download")
            try:
                self.get_prices_btn.configure(state="normal")
            except Exception:
                pass

    def _on_prices_fetched(self, result):
        try:
            # result is typically None; refresh data
            self.status_label.configure(text="Latest prices downloaded")
            # reload portfolios + holdings (they will refresh totals via the existing hooks)
            try:
                self.load_portfolios()
            except Exception:
                pass
            try:
                self.load_totals()
            except Exception:
                pass
        except Exception:
            logger.exception("Error in prices fetched callback")
        finally:
            try:
                self.get_prices_btn.configure(state="normal")
            except Exception:
                pass

    def _on_holdings_loaded(self, rows):
        # delegate to holdings widget
        self.holdings_widget.set_holdings(rows)
        # reset any previously selected holding when repopulating and clear form
        # so that consecutive additions do not treat the previous entry as selected
        try:
            self.clear_form()
        except Exception:
            self.selected_holding_id = None

        # also refresh totals across all portfolios (async)
        try:
            self.async_run_bg(self.service.fetch_totals(), callback=self._on_totals_loaded)
        except Exception:
            pass

    # ---- Portfolio actions ----
    def create_portfolio(self):
        name = simpledialog.askstring("Create Portfolio", "Portfolio name:", parent=self)
        if not name:
            return
        try:
            run_bg_with_button(self.create_btn, self.async_run_bg, self.service.create_portfolio(name), callback=lambda _: self.load_portfolios())
        except Exception:
            # fallback
            self.async_run_bg(self.service.create_portfolio(name), callback=lambda _: self.load_portfolios())

    # PortfolioService handles create_portfolio

    def rename_portfolio(self):
        pid = self._selected_portfolio()
        if pid is None:
            return
        current = self.portfolio_list_widget.get_selected()
        if not current:
            return
        _, name = current.split(" - ", 1)
        new_name = simpledialog.askstring("Rename Portfolio", "New name:", initialvalue=name, parent=self)
        if not new_name:
            return
        try:
            run_bg_with_button(self.rename_btn, self.async_run_bg, self.service.rename_portfolio(pid, new_name), callback=lambda _: self.load_portfolios())
        except Exception:
            self.async_run_bg(self.service.rename_portfolio(pid, new_name), callback=lambda _: self.load_portfolios())

    # PortfolioService handles rename_portfolio

    def delete_portfolio(self):
        pid = self._selected_portfolio()
        if pid is None:
            return
        if not messagebox.askyesno("Confirm", "Delete portfolio and all holdings?", parent=self):
            return
        try:
            run_bg_with_button(self.delete_portfolio_btn, self.async_run_bg, self.service.delete_portfolio(pid), callback=lambda _: self.load_portfolios())
        except Exception:
            self.async_run_bg(self.service.delete_portfolio(pid), callback=lambda _: self.load_portfolios())

    # PortfolioService handles delete_portfolio

    # ---- Holding actions ----
    def add_or_update_holding(self):
        pid = self._current_portfolio_id if hasattr(self, '_current_portfolio_id') else None
        if not pid:
            messagebox.showwarning("No portfolio selected", "Please select a portfolio first.", parent=self)
            return
        ticker, qty_text, avg_text = self.form_widget.get_values()
        ticker = ticker.strip().upper()
        try:
            qty = float(qty_text)
        except Exception:
            messagebox.showerror("Invalid quantity", "Please enter a numeric quantity.", parent=self)
            return
        try:
            avg = float(avg_text)
        except Exception:
            messagebox.showerror("Invalid price", "Please enter a numeric average price.", parent=self)
            return

        # If the user clicked a holding and its id is tracked, update that specific holding by id
        if hasattr(self, "selected_holding_id") and self.selected_holding_id:
            hid = self.selected_holding_id
            try:
                run_bg_with_button(self.add_update_btn, self.async_run_bg, self.service.update_holding(hid, ticker, qty, avg), callback=lambda _ : self._post_mutation_refresh())
            except Exception:
                self.async_run_bg(self.service.update_holding(hid, ticker, qty, avg), callback=lambda _ : self._post_mutation_refresh())
        else:
            # no selection -> upsert by ticker for this portfolio (create or update)
            try:
                run_bg_with_button(self.add_update_btn, self.async_run_bg, self.service.upsert_holding(pid, ticker, qty, avg), callback=lambda _ : self._post_mutation_refresh())
            except Exception:
                self.async_run_bg(self.service.upsert_holding(pid, ticker, qty, avg), callback=lambda _ : self._post_mutation_refresh())

    # PortfolioService handles upsert_holding

    # PortfolioService handles update_holding

    def delete_holding(self):
        hid = self.holdings_widget.get_selection_iid()
        if not hid:
            return
        if not messagebox.askyesno("Confirm", "Delete selected holding?", parent=self):
            return
        try:
            hid_int = int(hid)
        except Exception:
            logger.exception("Invalid selected holding id for deletion: %s", hid)
            return
        try:
            # Delete the holding and mark its watchlist status as WL-Active in the same background operation
            run_bg_with_button(
                self.delete_holding_btn,
                self.async_run_bg,
                self.service.delete_holding_and_mark_wl_active(hid_int),
                callback=lambda _ : self.on_portfolio_select(),
            )
        except Exception:
            self.async_run_bg(self.service.delete_holding_and_mark_wl_active(hid_int), callback=lambda _: self.on_portfolio_select())

    # PortfolioService handles delete_holding

    # When a holding is selected in the Treeview, populate the entry boxes
    def on_holding_select(self, event=None):
        hid = self.holdings_widget.get_selection_iid()
        if not hid:
            # clear entry boxes and selection state
            self.selected_holding_id = None
            self.form_widget.clear()
            # ensure button reflects the cleared entries
            try:
                self._validate_form()
            except Exception:
                pass
            return

        hid = hid
        try:
            # values are (ticker, quantity, avg_price)
            vals = self.holdings_widget.get_item_values(hid) or ()
            ticker = vals[0] if len(vals) > 0 else ""
            qty = vals[1] if len(vals) > 1 else ""
            avg = vals[2] if len(vals) > 2 else ""

            self.selected_holding_id = int(hid)
            # populate entries
            self.form_widget.set_values(ticker, qty, avg)
            # focus qty for quick edits
            try:
                self.form_widget.qty_entry.focus_set()
            except Exception:
                pass
            # re-evaluate form validity
            try:
                self._validate_form()
            except Exception:
                pass
        except Exception:
            logger.exception("Failed populating holding selection")

    def clear_form(self):
        """Clear the ticker/qty/avg form and reset selection state."""
        try:
            self.selected_holding_id = None
        except Exception:
            self.selected_holding_id = None
        try:
            # reset via form widget
            if hasattr(self, "form_widget"):
                self.form_widget.clear()
        except Exception:
            pass
        try:
            # clear any treeview selection
            if hasattr(self, "holdings_widget"):
                self.holdings_widget.clear_selection()
        except Exception:
            pass
        # make sure the Add/Update button state reflects emptied fields
        try:
            self._validate_form()
        except Exception:
            pass

    def _post_mutation_refresh(self):
        """Helper called after add/update/delete to refresh UI and clear form."""
        try:
            self.clear_form()
        except Exception:
            pass
        try:
            self.on_portfolio_select()
        except Exception:
            pass

    def on_close(self):
        self.destroy()

    # ---- form validation ----
    def _validate_form(self) -> bool:
        """Enable the Add/Update button only when we have a portfolio selected and
        all form fields can be interpreted as valid values (non-empty + numeric where required).

        Returns True when form is valid.
        """
        try:
            # must have a portfolio selected
            if not hasattr(self, "_current_portfolio_id") or not self._current_portfolio_id:
                self.add_update_btn.configure(state="disabled")
                return False

            # ticker required
            ticker, qty_text, avg_text = self.form_widget.get_values() if hasattr(self, "form_widget") else ("", "", "")
            ticker = (ticker or "").strip()
            if not ticker:
                self.add_update_btn.configure(state="disabled")
                return False

            # quantity and avg price must be numeric
            qty_text = (qty_text or "").strip()
            avg_text = (avg_text or "").strip()
            if qty_text == "" or avg_text == "":
                self.add_update_btn.configure(state="disabled")
                return False

            # try parse
            float(qty_text)
            float(avg_text)

            # everything looked ok -> enable
            self.add_update_btn.configure(state="normal")
            return True
        except Exception:
            # on any parse/validation error, disable
            try:
                self.add_update_btn.configure(state="disabled")
            except Exception:
                pass
            return False
