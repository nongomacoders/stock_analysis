from modules.data.research import save_deep_research_data
from components.base_text_tab import BaseTextTab
from scripts.generate_deepresearch_from_results import run as run_deepresearch
import logging
import ttkbootstrap as ttk
from ttkbootstrap.constants import RIGHT, LEFT, X, BOTH, Y
from ttkbootstrap.dialogs import Messagebox

logger = logging.getLogger(__name__)


from components.button_utils import run_bg_with_button
from modules.analysis.engine import estimate_spot_price


class DeepResearchTab(BaseTextTab):
    """A tab for displaying and editing deep research notes."""

    def __init__(self, parent, ticker, async_run, async_run_bg=None):
        super().__init__(parent, ticker, async_run)
        self.async_run_bg = async_run_bg
        self._loading = False  # Flag to prevent saves during content load

        # Add 'Share price at spot' button to the toolbar (right side, near Save)
        try:
            self.spot_btn = ttk.Button(
                self.toolbar,
                text="Share price at spot",
                bootstyle="info",
                command=self._on_spot_price_clicked,
            )
            self.spot_btn.pack(side=RIGHT, padx=5)
        except Exception:
            logger.exception("Failed to create spot price button")

        # Add 'Rerun DeepResearch' button to the toolbar
        try:
            self.rerun_btn = ttk.Button(
                self.toolbar,
                text="Rerun AI DeepResearch",
                bootstyle="success",
                command=self._on_rerun_clicked,
            )
            self.rerun_btn.pack(side=RIGHT, padx=5)
        except Exception:
            logger.exception("Failed to create rerun deepresearch button")

    def save_content(self):
        """Saves the content of the text widget to the database."""
        # Prevent saves during ticker transition/loading
        if self._loading:
            logger.warning(f"[DeepResearch] Blocked save during load for {self.ticker}")
            return
            
        content = self.get_content()
        
        # Log what we're attempting to save
        logger.info(f"[DeepResearch] save_content called for {self.ticker}, content length: {len(content) if content else 0}")
        
        # Prevent saving blank content or placeholder text
        if not content or content == "No data available.":
            logger.warning(f"[DeepResearch] Blocked blank save for {self.ticker}")
            try:
                Messagebox.show_warning(
                    "Cannot Save Empty Content",
                    "Deep research content is empty or contains only placeholder text. Add content before saving.",
                    parent=self
                )
            except Exception:
                pass
            return
        
        # Provide save_async so the base class can run in background
        if hasattr(self, "async_run_bg") and self.async_run_bg:
            try:
                run_bg_with_button(self.save_btn, self.async_run_bg, save_deep_research_data(self.ticker, content))
                return
            except Exception:
                pass

        self.async_run(save_deep_research_data(self.ticker, content))

    def save_async(self):
        # Prevent saves during ticker transition/loading
        if self._loading:
            logger.warning(f"[DeepResearch] Blocked save_async during load for {self.ticker}")
            raise ValueError("Cannot save during content loading")
            
        content = self.get_content()
        
        # Log what we're attempting to save
        logger.info(f"[DeepResearch] save_async called for {self.ticker}, content length: {len(content) if content else 0}")
        
        # Prevent saving blank content or placeholder text
        if not content or content == "No data available.":
            logger.warning(f"[DeepResearch] Blocked blank save_async for {self.ticker}")
            raise ValueError("Cannot save empty deep research content")
        
        logger.info(f"[DeepResearch] Proceeding with save for {self.ticker}")
        return save_deep_research_data(self.ticker, content)
    
    def load_content(self, content):
        """Override to set loading flag during content load."""
        self._loading = True
        logger.info(f"[DeepResearch] load_content called for {self.ticker}, setting loading=True")
        try:
            super().load_content(content)
        finally:
            self._loading = False
            logger.info(f"[DeepResearch] load_content complete for {self.ticker}, setting loading=False")

    def _on_spot_price_clicked(self):
        """Handler for the 'Share price at spot' button.

        Runs the AI estimation in the background and displays the result in a dialog.
        """
        try:
            # Prefer background runner if available
            if hasattr(self, "async_run_bg") and self.async_run_bg:
                def _show(result):
                    try:
                        Messagebox.show_info("Share Price at Spot", result or "(no result)", parent=self)
                    except Exception:
                        logger.exception("Failed to show spot price result dialog")

                run_bg_with_button(self.spot_btn, self.async_run_bg, estimate_spot_price(self.ticker), callback=_show)
                return
        except Exception:
            logger.exception("Failed to start background spot price job; falling back to sync")

        # Fallback: run synchronously on event loop and show result
        try:
            res = self.async_run(estimate_spot_price(self.ticker))
            Messagebox.show_info("Share Price at Spot", res or "(no result)", parent=self)
        except Exception:
            logger.exception("Failed to compute or show spot price")

    def _confirm_source_inventory(self, inventory):
        """Show a readable, scrollable review of folder-based report inputs."""
        dialog = ttk.Toplevel(self)
        dialog.title("Review Deep Research Sources")
        dialog.geometry("760x540")
        dialog.minsize(640, 430)
        dialog.transient(self.winfo_toplevel())
        result = {"run": False}

        header = ttk.Frame(dialog, padding=(20, 16, 20, 10))
        header.pack(fill=X)
        ttk.Label(header, text="Review Deep Research Sources",
                  font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(header,
                  text="Confirm the evidence that will be sent to Gemini for this rerun.",
                  bootstyle="secondary").pack(anchor="w", pady=(3, 0))

        location = ttk.Labelframe(dialog, text="Source folder", padding=10)
        location.pack(fill=X, padx=20, pady=(0, 10))
        folder_value = ttk.StringVar(value=str(inventory["folder"]))
        ttk.Entry(location, textvariable=folder_value, state="readonly").pack(fill=X)

        roles = inventory.get("document_roles", {})
        has_afs = "annual_financial_statements" in set(roles.values())
        counts = ttk.Frame(dialog)
        counts.pack(fill=X, padx=20, pady=(0, 10))
        ttk.Label(counts, text=f"Text files: {len(inventory['text_files'])}",
                  bootstyle="info", font=("Segoe UI", 10, "bold")).pack(side=LEFT, padx=(0, 20))
        ttk.Label(counts, text=f"PDF files: {len(inventory['pdf_files'])}",
                  bootstyle="success" if inventory["pdf_files"] else "danger",
                  font=("Segoe UI", 10, "bold")).pack(side=LEFT, padx=(0, 20))
        ttk.Label(counts, text=f"Evidence depth: {inventory.get('evidence_depth','HEADLINE_RESULTS_ONLY')}",
                  bootstyle="primary", font=("Segoe UI", 10, "bold")).pack(side=LEFT)
        if inventory["ignored_files"]:
            ttk.Label(counts, text=f"Ignored: {len(inventory['ignored_files'])}",
                      bootstyle="secondary").pack(side=LEFT)

        table_frame = ttk.Labelframe(dialog, text="Files in folder", padding=8)
        table_frame.pack(fill=BOTH, expand=True, padx=20, pady=(0, 10))
        table = ttk.Treeview(table_frame, columns=("status", "filename"),
                             show="headings", height=10)
        table.heading("status", text="Used as")
        table.heading("filename", text="Filename")
        table.column("status", width=110, stretch=False, anchor="w")
        table.column("filename", width=560, stretch=True, anchor="w")
        yscroll = ttk.Scrollbar(table_frame, orient="vertical", command=table.yview)
        xscroll = ttk.Scrollbar(table_frame, orient="horizontal", command=table.xview)
        table.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        table.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        for file in inventory["pdf_files"]:
            table.insert("", "end", values=({"annual_financial_statements":"Annual financial statements"}.get(roles.get(file),"PDF evidence"), file.name))
        for file in inventory["text_files"]:
            table.insert("", "end", values=({"results_sens":"Results SENS"}.get(roles.get(file),"Text evidence"), file.name))
        for file in inventory["ignored_files"]:
            table.insert("", "end", values=("Ignored", file.name))

        if not has_afs:
            warning = ttk.Frame(dialog, padding=10, bootstyle="danger")
            warning.pack(fill=X, padx=20, pady=(0, 10))
            ttk.Label(warning, text="Annual financial statements PDF not detected",
                      bootstyle="inverse-danger", font=("Segoe UI", 10, "bold")).pack(anchor="w")
            ttk.Label(warning,
                      text="The detailed financial presentation will not be supplied to Gemini. "
                           "The report may lack notes, segment detail and complete financial statements.",
                      bootstyle="inverse-danger", wraplength=690, justify="left").pack(anchor="w", pady=(2, 0))

        ttk.Label(dialog,
                  text="The previous report is archived after successful replacement and is not supplied to Gemini.",
                  bootstyle="secondary").pack(anchor="w", padx=20, pady=(0, 10))

        buttons = ttk.Frame(dialog, padding=(20, 0, 20, 18))
        buttons.pack(fill=X)
        def close(run=False):
            result["run"] = run
            dialog.destroy()
        ttk.Button(buttons, text="Cancel", bootstyle="secondary",
                   command=lambda: close(False)).pack(side=RIGHT, padx=(8, 0))
        run_button = ttk.Button(buttons, text="Run Deep Research", bootstyle="success",
                                command=lambda: close(True))
        run_button.pack(side=RIGHT)
        dialog.protocol("WM_DELETE_WINDOW", lambda: close(False))
        dialog.bind("<Escape>", lambda event: close(False))
        dialog.bind("<Return>", lambda event: close(True))
        dialog.update_idletasks()
        parent = self.winfo_toplevel()
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - dialog.winfo_width()) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - dialog.winfo_height()) // 2)
        dialog.geometry(f"+{x}+{y}")
        dialog.grab_set()
        run_button.focus_set()
        dialog.wait_window()
        return result["run"]

    def _on_rerun_clicked(self):
        """Handler for the 'Rerun AI DeepResearch' button.

        Triggers the generate_deepresearch_from_results script for the current ticker.
        """
        if not self.ticker:
            return

        from scripts.generate_deepresearch_from_results import get_results_source_inventory
        inventory = get_results_source_inventory(self.ticker)
        if not inventory["text_files"] and not inventory["pdf_files"]:
            Messagebox.show_warning(
                "No Deep Research Sources",
                f"No .txt or .pdf files were found in:\n{inventory['folder']}\n\n"
                "Add a detailed financial PDF or export selected SENS announcements first.",
                parent=self,
            )
            return
        if not self._confirm_source_inventory(inventory):
            return

        if hasattr(self, "async_run_bg") and self.async_run_bg:
            def _on_generated(result):
                """Refresh the UI after the AI generation finishes."""
                try:
                    from modules.data.research import get_research_data
                    
                    async def _reload():
                        data = await get_research_data(self.ticker)
                        if data and data.get("deepresearch"):
                            self.load_content(data["deepresearch"])
                        else:
                            logger.warning(f"No deepresearch data found for {self.ticker} after rerun")

                    self.async_run_bg(_reload())
                    logger.info(f"AI DeepResearch complete for {self.ticker}; refresh triggered")
                except Exception:
                    logger.exception("Failed to refresh DeepResearchTab after AI generation")

            run_bg_with_button(
                self.rerun_btn,
                self.async_run_bg,
                run_deepresearch(ticker=self.ticker, limit=None, dry_run=False, max_chars=200_000,
                                 post_compare=True),
                callback=_on_generated
            )
        else:
            self.async_run(run_deepresearch(ticker=self.ticker, limit=None, dry_run=False,
                                             max_chars=200_000, post_compare=True))


