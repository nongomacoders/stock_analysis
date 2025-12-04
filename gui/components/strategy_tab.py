from modules.data.research import save_strategy_data
from components.base_text_tab import BaseTextTab
from components.button_utils import run_bg_with_button
import logging

logger = logging.getLogger(__name__)


class StrategyTab(BaseTextTab):
    """A tab for displaying and editing the investment strategy."""

    def __init__(self, parent, ticker, async_run, async_run_bg=None):
        super().__init__(parent, ticker, async_run)
        self.async_run_bg = async_run_bg

    def save_content(self):
        """Saves the content of the text widget to the database."""
        content = self.get_content()
        # Provide save_async factory for BaseTextTab to run in background
        if hasattr(self, "async_run_bg") and self.async_run_bg:
            try:
                run_bg_with_button(self.save_btn, self.async_run_bg, save_strategy_data(self.ticker, content))
                return
            except Exception:
                pass

        self.async_run(save_strategy_data(self.ticker, content))

    def save_async(self):
        content = self.get_content()
        return save_strategy_data(self.ticker, content)
        logger.info("Strategy saved for %s", self.ticker)