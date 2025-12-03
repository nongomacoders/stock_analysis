import ttkbootstrap as ttk
from ttkbootstrap.constants import RIGHT, DISABLED, NORMAL, END, WORD
from ttkbootstrap.dialogs import Messagebox

from modules.data.research import save_research_data
from modules.analysis.engine import generate_master_research
from components.base_text_tab import BaseTextTab


class ResearchTab(BaseTextTab):
    """A tab for displaying and generating AI-driven research."""

    def __init__(self, parent, ticker, async_run, deep_research_tab_ref):
        super().__init__(parent, ticker, async_run)
        self.deep_research_tab = deep_research_tab_ref

        # Add the 'Generate' button to the toolbar created in the base class
        ttk.Button(
            self.toolbar,
            text="Generate New Research",
            bootstyle="info",
            command=self.generate_research
        ).pack(side=RIGHT, padx=5)

    def save_content(self):
        """Saves the content of the text widget to the database."""
        content = self.get_content()
        self.async_run(save_research_data(self.ticker, content))
        print(f"Research saved for {self.ticker}")

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
            print(f"Generating research for {self.ticker}...")
            # Show loading state
            self.text_widget.config(state=NORMAL)
            self.text_widget.delete("1.0", END)
            self.text_widget.insert("1.0", "Generating research... please wait...")
            self.text_widget.config(state=DISABLED)
            self.update()

            # Get content from the deep research tab and generate
            deep_research_content = self.deep_research_tab.get_content()
            new_research = self.async_run(generate_master_research(self.ticker, deep_research_content))
            
            # Update UI
            self.load_content(new_research)
            print("Research generation complete.")
        except Exception as e:
            print(f"Error generating research: {e}")
            self.load_content(f"Error: {str(e)}")