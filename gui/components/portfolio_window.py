import ttkbootstrap as ttk
from ttkbootstrap.constants import LEFT, RIGHT, BOTH, X, Y, END
import tkinter as tk
from tkinter import simpledialog, messagebox
from typing import Optional
import asyncio
import logging

from core.db.engine import DBEngine
from modules.data.market import get_latest_price
from modules.market_agent.prices import run_price_update

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
        self.geometry("1200x700")
        self.async_run = async_run
        self.async_run_bg = async_run_bg

        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.create_widgets()
        # initial load
        self.load_portfolios()

    def create_widgets(self):
        container = ttk.Frame(self, padding=8)
        container.pack(fill=BOTH, expand=True)

        # Left: Portfolio list + actions
        left = ttk.Frame(container)
        left.pack(side=LEFT, fill=Y, padx=6, pady=6)

        ttk.Label(left, text="Portfolios", font=(None, 12, "bold")).pack(anchor="w")
        self.portfolio_list = tk.Listbox(left, height=24, width=36)
        self.portfolio_list.pack(fill=Y, expand=False)
        self.portfolio_list.bind("<<ListboxSelect>>", self.on_portfolio_select)

        btn_frame = ttk.Frame(left)
        btn_frame.pack(fill=X, pady=(6, 0))
        ttk.Button(btn_frame, text="New", bootstyle="success", command=self.create_portfolio).pack(side=LEFT, padx=4)
        ttk.Button(btn_frame, text="Rename", command=self.rename_portfolio).pack(side=LEFT, padx=4)
        ttk.Button(btn_frame, text="Delete", bootstyle="danger", command=self.delete_portfolio).pack(side=LEFT, padx=4)

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
        self.holdings_list = ttk.Treeview(
            right,
            columns=("ticker", "qty", "avg", "cost", "latest", "pl", "pct"),
            show="headings",
            height=20,
        )
        self.holdings_list.heading("ticker", text="Ticker")
        self.holdings_list.heading("qty", text="Quantity")
        self.holdings_list.heading("avg", text="Avg Price (c)")
        # portfolio cost value (avg price * qty) shown in rands
        self.holdings_list.heading("cost", text="Portfolio Cost Value (R)")
        self.holdings_list.heading("latest", text="Latest")
        self.holdings_list.heading("pl", text="P/L (R)")
        self.holdings_list.heading("pct", text="P/L (%)")
        self.holdings_list.pack(fill=BOTH, expand=True, pady=(6, 8))

        # tags to color-code P/L: positive -> green, negative -> red, zero/none -> default
        try:
            self.holdings_list.tag_configure("pl_pos", foreground="#1a7f1a")
            self.holdings_list.tag_configure("pl_neg", foreground="#c02020")
            self.holdings_list.tag_configure("pl_zero", foreground="#000000")
        except Exception:
            # Some ttk/treeview variants might not support tag_configure; ignore if unavailable
            pass

        # when a holding row is selected, populate the entry fields
        self.holdings_list.bind("<<TreeviewSelect>>", self.on_holding_select)

        # sensible default column widths (pixels)
        self.holdings_list.column("ticker", width=160, anchor="w")
        self.holdings_list.column("qty", width=80, anchor="e")
        self.holdings_list.column("avg", width=120, anchor="e")
        self.holdings_list.column("cost", width=150, anchor="e")
        self.holdings_list.column("latest", width=120, anchor="e")
        self.holdings_list.column("pl", width=120, anchor="e")
        self.holdings_list.column("pct", width=100, anchor="e")
        form = ttk.Frame(right, padding=6)
        form.pack(fill=X)

        ttk.Label(form, text="Ticker").grid(row=0, column=0, sticky="w")
        # use StringVars so we can trace content and enable/disable the Add/Update button
        self.ticker_var = tk.StringVar()
        self.qty_var = tk.StringVar()
        self.avg_var = tk.StringVar()

        self.ticker_entry = ttk.Entry(form, textvariable=self.ticker_var)
        self.ticker_entry.grid(row=0, column=1, padx=6, pady=2, sticky="ew")

        ttk.Label(form, text="Quantity").grid(row=1, column=0, sticky="w")
        self.qty_entry = ttk.Entry(form, textvariable=self.qty_var)
        self.qty_entry.grid(row=1, column=1, padx=6, pady=2, sticky="ew")

        ttk.Label(form, text="Avg Price").grid(row=2, column=0, sticky="w")
        # clarify units next to the price field (in red)
        # use tk.Label so we can quickly set a red foreground color without creating a new ttk style
        tk.Label(form, text="(in cents)", fg="red", font=("Arial", 9)).grid(row=2, column=2, sticky="w", padx=(6, 0))
        self.avg_entry = ttk.Entry(form, textvariable=self.avg_var)
        self.avg_entry.grid(row=2, column=1, padx=6, pady=2, sticky="ew")

        form.columnconfigure(1, weight=1)

        actions = ttk.Frame(right)
        actions.pack(fill=X, pady=(6, 0))
        # keep a reference to the Add/Update button so we can enable/disable it
        self.add_update_btn = ttk.Button(actions, text="Add/Update Holding", bootstyle="primary", command=self.add_or_update_holding)
        self.add_update_btn.pack(side=LEFT, padx=4)
        self.add_update_btn.configure(state="disabled")
        ttk.Button(actions, text="Delete Holding", bootstyle="danger", command=self.delete_holding).pack(side=LEFT, padx=4)
        # quick download latest prices from yfinance for all tickers
        self.get_prices_btn = ttk.Button(actions, text="Get latest prices", bootstyle="info", command=self.fetch_latest_prices)
        self.get_prices_btn.pack(side=LEFT, padx=6)

        # trace input changes to validate form
        self.ticker_var.trace_add("write", lambda *a: self._validate_form())
        self.qty_var.trace_add("write", lambda *a: self._validate_form())
        self.avg_var.trace_add("write", lambda *a: self._validate_form())

        status = ttk.Frame(self)
        status.pack(fill=X, side=tk.BOTTOM)
        self.status_label = ttk.Label(status, text="Ready")
        self.status_label.pack(side=LEFT, padx=8, pady=6)

        # Totals display (right side of status bar)
        # Total P/L (R) and Total P/L (%) across all portfolios
        self.total_pl_label = ttk.Label(status, text="Total P/L: R0.00")
        self.total_pl_label.pack(side=tk.RIGHT, padx=8, pady=6)
        self.total_pl_pct_label = ttk.Label(status, text="(0.00%)")
        self.total_pl_pct_label.pack(side=tk.RIGHT, padx=0, pady=6)

    # ---- Persistence helpers (async) ----
    def load_portfolios(self):
        self.async_run_bg(self._fetch_portfolios(), callback=self._on_portfolios_loaded)

    async def _fetch_portfolios(self):
        try:
            rows = await DBEngine.fetch("SELECT id, name FROM portfolios ORDER BY id")
            return [dict(r) for r in rows]
        except Exception:
            logger.exception("Failed to fetch portfolios")
            return []

    def _on_portfolios_loaded(self, result):
        self.portfolio_list.delete(0, END)
        self._current_portfolio_id = None
        for p in result:
            self.portfolio_list.insert(END, f"{p['id']} - {p['name']}")
        # auto-select the first portfolio (if any) so holdings load immediately
        if result:
            self.portfolio_list.selection_clear(0, END)
            self.portfolio_list.selection_set(0)
            # trigger load
            self.on_portfolio_select()
        # refresh totals across portfolios when portfolios are loaded
        try:
            self.async_run_bg(self._fetch_totals(), callback=self._on_totals_loaded)
        except Exception:
            pass

    def _selected_portfolio(self) -> Optional[int]:
        sel = self.portfolio_list.curselection()
        if not sel:
            return None
        text = self.portfolio_list.get(sel[0])
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
        self.async_run_bg(self._fetch_holdings(pid), callback=self._on_holdings_loaded)

    async def _fetch_holdings(self, portfolio_id):
        try:
            rows = await DBEngine.fetch(
                "SELECT id, ticker, quantity, average_buy_price FROM portfolio_holdings WHERE portfolio_id = $1 ORDER BY id",
                portfolio_id,
            )
            holdings = [dict(r) for r in rows]

            # fetch latest prices concurrently for each ticker (if available)
            # get_latest_price returns a dict with 'close_price' or None
            tasks = [get_latest_price(h["ticker"]) for h in holdings]
            latests = []
            if tasks:
                latests = await asyncio.gather(*tasks, return_exceptions=True)

            # merge latest price and compute P/L per holding
            enriched = []
            for h, l in zip(holdings, latests if latests else [{}] * len(holdings)):
                try:
                    latest_price = None
                    if isinstance(l, dict) and l:
                        # DB stores close_price in cents — convert to rands for display and calculations
                        raw = l.get("close_price")
                        try:
                            latest_price = float(raw) / 100.0 if raw is not None else None
                        except Exception:
                            latest_price = None
                    elif isinstance(l, Exception):
                        latest_price = None

                    # compute values in rands
                    avg = h.get("average_buy_price")  # stored in cents
                    qty = h.get("quantity")
                    pl = None
                    cost_value = None
                    if avg is not None and qty is not None:
                        try:
                            # avg is stored in cents -> convert to rands
                            avg_rands = float(avg) / 100.0
                            cost_value = avg_rands * float(qty)
                        except Exception:
                            cost_value = None

                    pct_pl = None
                    if latest_price is not None and avg is not None and qty is not None:
                        try:
                            avg_rands = float(avg) / 100.0
                            pl = (float(latest_price) - avg_rands) * float(qty)
                            # percent change relative to average buy price (in rands)
                            if avg_rands and avg_rands != 0:
                                pct_pl = (float(latest_price) - avg_rands) / avg_rands * 100.0
                            else:
                                pct_pl = None
                        except Exception:
                            pl = None
                            pct_pl = None

                    h["latest_price"] = latest_price
                    h["pl"] = pl
                    h["pct_pl"] = pct_pl
                    h["cost_value"] = cost_value
                except Exception:
                    logger.exception("Error enriching holding with latest price")
                    h["latest_price"] = None
                    h["pl"] = None
                enriched.append(h)

            return enriched
        except Exception:
            logger.exception("Failed to fetch holdings")
            return []

    # ---- Totals across all portfolios ----
    def load_totals(self):
        try:
            self.async_run_bg(self._fetch_totals(), callback=self._on_totals_loaded)
        except Exception:
            pass

    async def _fetch_totals(self):
        """Fetch all holdings and compute total cost and total P/L in rands (and percent)."""
        try:
            rows = await DBEngine.fetch("SELECT id, ticker, quantity, average_buy_price FROM portfolio_holdings")
            holdings = [dict(r) for r in rows]

            if not holdings:
                return {"total_cost": 0.0, "total_pl": 0.0, "total_pct": 0.0}

            # fetch latest prices for unique tickers
            tasks = [get_latest_price(h["ticker"]) for h in holdings]
            latests = await asyncio.gather(*tasks, return_exceptions=True) if tasks else []

            total_cost = 0.0
            total_pl = 0.0
            for h, l in zip(holdings, latests if latests else [{}] * len(holdings)):
                latest_price = None
                if isinstance(l, dict) and l:
                    raw = l.get("close_price")
                    try:
                        latest_price = float(raw) / 100.0 if raw is not None else None
                    except Exception:
                        latest_price = None

                avg = h.get("average_buy_price")
                qty = h.get("quantity")
                if avg is None or qty is None:
                    continue
                try:
                    avg_rands = float(avg) / 100.0
                    cost_value = avg_rands * float(qty)
                    total_cost += cost_value
                    if latest_price is not None:
                        pl = (float(latest_price) - avg_rands) * float(qty)
                        total_pl += pl
                except Exception:
                    # skip if values malformed
                    continue

            total_pct = (total_pl / total_cost * 100.0) if total_cost != 0 else 0.0
            return {"total_cost": total_cost, "total_pl": total_pl, "total_pct": total_pct}
        except Exception:
            logger.exception("Failed to compute totals")
            return {"total_cost": 0.0, "total_pl": 0.0, "total_pct": 0.0}

    def _on_totals_loaded(self, result):
        try:
            total_pl = result.get("total_pl", 0.0)
            total_pct = result.get("total_pct", 0.0)
            # update labels
            self.total_pl_label.configure(text=f"Total P/L: R{total_pl:,.2f}")
            # color the P/L value label
            try:
                if total_pl > 0:
                    self.total_pl_label.configure(foreground="#1a7f1a")
                elif total_pl < 0:
                    self.total_pl_label.configure(foreground="#c02020")
                else:
                    self.total_pl_label.configure(foreground="#000000")
            except Exception:
                pass

            self.total_pl_pct_label.configure(text=f"({total_pct:+.2f}%)")
        except Exception:
            logger.exception("Failed updating totals UI")

    # ---- Download latest prices (yfinance) ----
    def fetch_latest_prices(self):
        """Kick off a background task that downloads latest prices for all tickers using yfinance.

        Uses the existing modules.market_agent.prices.run_price_update implementation.
        """
        try:
            # disable the button while running
            self.get_prices_btn.configure(state="disabled")
            self.status_label.configure(text="Downloading latest prices...")
            self.async_run_bg(run_price_update(), callback=self._on_prices_fetched)
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
        for item in self.holdings_list.get_children():
            self.holdings_list.delete(item)
        for r in rows:
            # use explicit index='end' literal to satisfy static type checkers
            latest = r.get("latest_price")
            pl = r.get("pl")
            cost_value = r.get("cost_value")

            latest_display = "" if latest is None else f"R{float(latest):,.2f}"
            pl_display = "" if pl is None else f"R{float(pl):,.2f}"
            pct = r.get("pct_pl")
            pct_display = "" if pct is None else f"{float(pct):+.2f}%"
            cost_display = "" if cost_value is None else f"R{float(cost_value):,.2f}"

            # determine tag for P/L color-coding
            tag = ()
            try:
                if pl is None:
                    tag = ("pl_zero",)
                else:
                    val = float(pl)
                    if val > 0:
                        tag = ("pl_pos",)
                    elif val < 0:
                        tag = ("pl_neg",)
                    else:
                        tag = ("pl_zero",)
            except Exception:
                tag = ("pl_zero",)

            self.holdings_list.insert(
                "",
                index='end',
                iid=str(r["id"]),
                values=(r["ticker"], r["quantity"], r["average_buy_price"], cost_display, latest_display, pl_display, pct_display),
                tags=tag,
            )
        # reset any previously selected holding when repopulating
        self.selected_holding_id = None
        # ensure the Add/Update button state reflects current contents / selection
        try:
            self._validate_form()
        except Exception:
            # ignore in GUI thread if validation not yet wired
            pass

        # also refresh totals across all portfolios (async)
        try:
            self.async_run_bg(self._fetch_totals(), callback=self._on_totals_loaded)
        except Exception:
            pass

    # ---- Portfolio actions ----
    def create_portfolio(self):
        name = simpledialog.askstring("Create Portfolio", "Portfolio name:", parent=self)
        if not name:
            return
        self.async_run_bg(self._create_portfolio(name), callback=lambda _: self.load_portfolios())

    async def _create_portfolio(self, name):
        try:
            await DBEngine.execute("INSERT INTO portfolios (name) VALUES ($1)", name)
            logger.info("Created portfolio %s", name)
        except Exception:
            logger.exception("Create portfolio failed")

    def rename_portfolio(self):
        pid = self._selected_portfolio()
        if pid is None:
            return
        current = self.portfolio_list.get(self.portfolio_list.curselection()[0])
        _, name = current.split(" - ", 1)
        new_name = simpledialog.askstring("Rename Portfolio", "New name:", initialvalue=name, parent=self)
        if not new_name:
            return
        self.async_run_bg(self._rename_portfolio(pid, new_name), callback=lambda _: self.load_portfolios())

    async def _rename_portfolio(self, pid, new_name):
        try:
            await DBEngine.execute("UPDATE portfolios SET name = $1 WHERE id = $2", new_name, pid)
            logger.info("Renamed portfolio %s -> %s", pid, new_name)
        except Exception:
            logger.exception("Rename portfolio failed")

    def delete_portfolio(self):
        pid = self._selected_portfolio()
        if pid is None:
            return
        if not messagebox.askyesno("Confirm", "Delete portfolio and all holdings?", parent=self):
            return
        self.async_run_bg(self._delete_portfolio(pid), callback=lambda _: self.load_portfolios())

    async def _delete_portfolio(self, pid):
        try:
            await DBEngine.execute("DELETE FROM portfolio_holdings WHERE portfolio_id = $1", pid)
            await DBEngine.execute("DELETE FROM portfolios WHERE id = $1", pid)
            logger.info("Deleted portfolio %s", pid)
        except Exception:
            logger.exception("Delete portfolio failed")

    # ---- Holding actions ----
    def add_or_update_holding(self):
        pid = self._current_portfolio_id if hasattr(self, '_current_portfolio_id') else None
        if not pid:
            messagebox.showwarning("No portfolio selected", "Please select a portfolio first.", parent=self)
            return

        ticker = self.ticker_entry.get().strip().upper()
        try:
            qty = float(self.qty_entry.get())
        except Exception:
            messagebox.showerror("Invalid quantity", "Please enter a numeric quantity.", parent=self)
            return
        try:
            avg = float(self.avg_entry.get())
        except Exception:
            messagebox.showerror("Invalid price", "Please enter a numeric average price.", parent=self)
            return

        # If the user clicked a holding and its id is tracked, update that specific holding by id
        if hasattr(self, "selected_holding_id") and self.selected_holding_id:
            hid = self.selected_holding_id
            self.async_run_bg(self._update_holding(hid, ticker, qty, avg), callback=lambda _: self.on_portfolio_select())
        else:
            # no selection -> upsert by ticker for this portfolio (create or update)
            self.async_run_bg(self._upsert_holding(pid, ticker, qty, avg), callback=lambda _: self.on_portfolio_select())

    async def _upsert_holding(self, portfolio_id, ticker, qty, avg_price):
        try:
            # Check if exists by ticker+portfolio
            exists = await DBEngine.fetch("SELECT id FROM portfolio_holdings WHERE portfolio_id = $1 AND ticker = $2", portfolio_id, ticker)
            if exists:
                # DBEngine.fetch often returns a list of records; coerce id safely
                ex_id = exists[0].get("id") if isinstance(exists[0], dict) else exists[0]["id"]
                await DBEngine.execute("UPDATE portfolio_holdings SET quantity = $1, average_buy_price = $2 WHERE id = $3", qty, avg_price, ex_id)
                logger.info("Updated holding %s in portfolio %s", ticker, portfolio_id)
            else:
                await DBEngine.execute("INSERT INTO portfolio_holdings (portfolio_id, ticker, quantity, average_buy_price) VALUES ($1, $2, $3, $4)", portfolio_id, ticker, qty, avg_price)
                logger.info("Added holding %s in portfolio %s", ticker, portfolio_id)
        except Exception:
            logger.exception("Upsert holding failed")

    async def _update_holding(self, hid, ticker, qty, avg_price):
        try:
            # Update by the holding id the user selected in the UI.
            await DBEngine.execute(
                "UPDATE portfolio_holdings SET ticker = $1, quantity = $2, average_buy_price = $3 WHERE id = $4",
                ticker,
                qty,
                avg_price,
                int(hid),
            )
            logger.info("Updated holding id=%s -> %s qty=%s avg=%s", hid, ticker, qty, avg_price)
        except Exception:
            logger.exception("Update holding failed")

    def delete_holding(self):
        sel = self.holdings_list.selection()
        if not sel:
            return
        hid = sel[0]
        if not messagebox.askyesno("Confirm", "Delete selected holding?", parent=self):
            return
        self.async_run_bg(self._delete_holding(hid), callback=lambda _: self.on_portfolio_select())

    async def _delete_holding(self, hid):
        try:
            await DBEngine.execute("DELETE FROM portfolio_holdings WHERE id = $1", int(hid))
            logger.info("Deleted holding %s", hid)
        except Exception:
            logger.exception("Delete holding failed")

    # When a holding is selected in the Treeview, populate the entry boxes
    def on_holding_select(self, event=None):
        sel = self.holdings_list.selection()
        if not sel:
            # clear entry boxes and selection state
            self.selected_holding_id = None
            self.ticker_entry.delete(0, END)
            self.qty_entry.delete(0, END)
            self.avg_entry.delete(0, END)
            # ensure button reflects the cleared entries
            try:
                self._validate_form()
            except Exception:
                pass
            return

        hid = sel[0]
        try:
            # values are (ticker, quantity, avg_price)
            vals = self.holdings_list.item(hid, "values") or ()
            ticker = vals[0] if len(vals) > 0 else ""
            qty = vals[1] if len(vals) > 1 else ""
            avg = vals[2] if len(vals) > 2 else ""

            self.selected_holding_id = int(hid)
            # populate entries
            self.ticker_entry.delete(0, END)
            self.ticker_entry.insert(0, ticker)
            self.qty_entry.delete(0, END)
            self.qty_entry.insert(0, str(qty))
            self.avg_entry.delete(0, END)
            self.avg_entry.insert(0, str(avg))
            # focus qty for quick edits
            self.qty_entry.focus_set()
            # re-evaluate form validity
            try:
                self._validate_form()
            except Exception:
                pass
        except Exception:
            logger.exception("Failed populating holding selection")

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
            ticker = (self.ticker_var.get() if hasattr(self, "ticker_var") else "").strip()
            if not ticker:
                self.add_update_btn.configure(state="disabled")
                return False

            # quantity and avg price must be numeric
            qty_text = (self.qty_var.get() if hasattr(self, "qty_var") else "").strip()
            avg_text = (self.avg_var.get() if hasattr(self, "avg_var") else "").strip()
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
