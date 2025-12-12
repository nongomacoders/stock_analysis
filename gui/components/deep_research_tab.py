from modules.data.research import save_deep_research_data
from components.base_text_tab import BaseTextTab
import logging
from ttkbootstrap.dialogs import Messagebox

logger = logging.getLogger(__name__)


from components.button_utils import run_bg_with_button


class DeepResearchTab(BaseTextTab):
    """A tab for displaying and editing deep research notes."""

    def __init__(self, parent, ticker, async_run, async_run_bg=None):
        super().__init__(parent, ticker, async_run)
        self.async_run_bg = async_run_bg
        self._loading = False  # Flag to prevent saves during content load

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