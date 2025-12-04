import ttkbootstrap as ttk
from ttkbootstrap.constants import RIGHT, DISABLED, NORMAL, END, WORD
from ttkbootstrap.dialogs import Messagebox

from modules.data.research import save_research_data
from modules.analysis.engine import generate_master_research
from components.base_text_tab import BaseTextTab
from components.button_utils import run_bg_with_button
import logging

logger = logging.getLogger(__name__)


class ResearchTab(BaseTextTab):
    """A tab for displaying and generating AI-driven research."""

    def __init__(self, parent, ticker, async_run, deep_research_tab_ref, async_run_bg=None):
        super().__init__(parent, ticker, async_run)
        self.deep_research_tab = deep_research_tab_ref
        self.async_run_bg = async_run_bg

        # Add the 'Generate' button to the toolbar created in the base class
        # Prefer store a reference so we can disable while generating
        self.generate_btn = ttk.Button(
            self.toolbar,
            text="Generate New Research",
            bootstyle="info",
            command=self.generate_research
        )
        self.generate_btn.pack(side=RIGHT, padx=5)

    def save_content(self):
        """Saves the content of the text widget to the database."""
        content = self.get_content()
        import logging
        logger = logging.getLogger(__name__)
        logger.debug("ResearchTab.save_content called for %s (len=%d)", self.ticker, len(content) if content is not None else 0)
        # For compatibility, implement save_async factory used by BaseTextTab
        # so the base will run the save in background when available.
        # This method remains a synchronous helper for direct calls.
        if hasattr(self, "async_run_bg") and self.async_run_bg:
            # Prefer the background helper (BaseTextTab._safe_save will call save_async())
            try:
                run_bg_with_button(self.save_btn, self.async_run_bg, save_research_data(self.ticker, content))
                logger.info("Research save started (background) for %s", self.ticker)
                return
            except Exception:
                logger.exception("run_bg_with_button failed for save; falling back to blocking save")

        try:
            self.async_run(save_research_data(self.ticker, content))
            logger.info("Research saved for %s", self.ticker)
        except Exception:
            logger.exception("Research save failed for %s", self.ticker)
            raise

    def save_async(self):
        """Create the coroutine used to save current research content."""
        content = self.get_content()
        import logging
        logging.getLogger(__name__).debug("ResearchTab.save_async for %s (len=%d)", self.ticker, len(content) if content is not None else 0)
        return save_research_data(self.ticker, content)

        self.async_run(save_research_data(self.ticker, content))
        logger.info("Research saved for %s", self.ticker)

    def generate_research(self):
        """Trigger AI research generation."""
        confirm = Messagebox.yesno(
            "This will overwrite existing research. Continue?",
            "Generate Research",
            parent=self
        )
        if confirm != "Yes":
            return

        try:
            logger.info("Generating research for %s...", self.ticker)
            # Show loading state
            self.text_widget.config(state=NORMAL)
            self.text_widget.delete("1.0", END)
            self.text_widget.insert("1.0", "Generating research... please wait...")
            self.text_widget.config(state=DISABLED)
            self.update()

            # Get content from the deep research tab and generate
            deep_research_content = self.deep_research_tab.get_content()

            # If an async_run_bg helper is available, use it and disable the Generate button
            if hasattr(self, "async_run_bg") and self.async_run_bg:
                def on_generated(result):
                    try:
                        self.load_content(result)
                    except Exception:
                        logger.exception("Failed applying generated research result to UI")

                try:
                    run_bg_with_button(self.generate_btn, self.async_run_bg, generate_master_research(self.ticker, deep_research_content), callback=on_generated)
                    return
                except Exception:
                    # fallback to sync run
                    logger.exception("run_bg_with_button failed; falling back to blocking async_run")

            new_research = self.async_run(generate_master_research(self.ticker, deep_research_content))
            # Update UI
            self.load_content(new_research)
            logger.info("Research generation complete.")
        except Exception as e:
            logger.exception("Error generating research")
            self.load_content(f"Error: {str(e)}")