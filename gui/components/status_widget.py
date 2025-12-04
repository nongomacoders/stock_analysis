import ttkbootstrap as ttk
from ttkbootstrap.constants import LEFT, RIGHT, X
from tkinter import messagebox
from typing import Callable, Optional

from modules.data.watchlist import set_watchlist_status
import logging
from components.button_utils import run_bg_with_button


class StatusWidget(ttk.Frame):
    """A small widget to allow setting the watchlist status for a ticker.

    Usage: StatusWidget(parent, ticker_getter, async_run_bg, on_saved=None)
    - ticker_getter: callable that returns the current ticker string
    - async_run_bg: function to run coroutines in background
    - on_saved: optional callback called when status is successfully saved
    """

    VALID_STATUSES = ["Active-Trade", "Pre-Trade", "WL-Sleep", "WL-Active"]

    def __init__(self, parent, ticker_getter: Callable[[], str], async_run_bg: Callable, on_saved: Optional[Callable] = None):
        super().__init__(parent)
        self.ticker_getter = ticker_getter
        self.async_run_bg = async_run_bg
        self.on_saved = on_saved

        self.create_widgets()

    def create_widgets(self):
        ttk.Label(self, text="Watchlist Status:").pack(side=LEFT, padx=(0, 6))

        self.status_var = ttk.StringVar(value=self.VALID_STATUSES[0])
        self.status_combo = ttk.Combobox(self, values=self.VALID_STATUSES, textvariable=self.status_var, state="readonly", width=16)
        self.status_combo.pack(side=LEFT)

        self.save_btn = ttk.Button(self, text="Set Status", bootstyle="primary", command=self.on_save)
        self.save_btn.pack(side=RIGHT, padx=(8, 0))

    def on_save(self):
        logger = logging.getLogger(__name__)
        ticker = None
        try:
            ticker = self.ticker_getter()
        except Exception:
            ticker = None

        if not ticker:
            messagebox.showwarning("No ticker", "No ticker selected to set status for.")
            return
        status = self.status_var.get()

        logger.info("StatusWidget.on_save called for %s -> %s", ticker, status)

        # Use run_bg_with_button helper to disable the Save button while updating
        try:
            logger.debug("Calling set_watchlist_status for %s -> %s", ticker, status)
            run_bg_with_button(self.save_btn, self.async_run_bg, set_watchlist_status(ticker, status), callback=self._on_done)
        except Exception:
            # Fallback: call async_run_bg directly
            logger.exception("run_bg_with_button failed in StatusWidget.on_save - falling back to async_run_bg")
            self.async_run_bg(set_watchlist_status(ticker, status), callback=self._on_done)

    def _on_done(self, result):
        logger = logging.getLogger(__name__)
        logger.info("StatusWidget._on_done called for %s result=%s", self.ticker_getter(), result)

        if result:
            messagebox.showinfo("Success", f"Status for {self.ticker_getter()} set to {self.status_var.get()}")
            if callable(self.on_saved):
                try:
                    self.on_saved(self.ticker_getter(), self.status_var.get())
                except Exception:
                    pass
        else:
            messagebox.showerror("Error", "Failed to set status. See logs for details.")
