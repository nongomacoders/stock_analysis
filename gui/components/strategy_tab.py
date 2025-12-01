from modules.data.research import save_strategy_data
from components.base_text_tab import BaseTextTab


class StrategyTab(BaseTextTab):
    """A tab for displaying and editing the investment strategy."""

    def __init__(self, parent, ticker, async_run):
        super().__init__(parent, ticker, async_run)

    def save_content(self):
        """Saves the content of the text widget to the database."""
        content = self.get_content()
        self.async_run(save_strategy_data(self.ticker, content))
        print(f"Strategy saved for {self.ticker}")