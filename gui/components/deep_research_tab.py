from modules.data.research import save_deep_research_data
from components.base_text_tab import BaseTextTab


class DeepResearchTab(BaseTextTab):
    """A tab for displaying and editing deep research notes."""

    def __init__(self, parent, ticker, async_run):
        super().__init__(parent, ticker, async_run)

    def save_content(self):
        """Saves the content of the text widget to the database."""
        content = self.get_content()
        self.async_run(save_deep_research_data(self.ticker, content))
        print(f"Deep Research saved for {self.ticker}")