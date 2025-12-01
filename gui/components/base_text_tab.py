import ttkbootstrap as ttk
from ttkbootstrap.constants import *


class BaseTextTab(ttk.Frame):
    """A base class for tabs that primarily consist of an editable text widget."""

    def __init__(self, parent, ticker, async_run):
        super().__init__(parent)
        self.ticker = ticker
        self.async_run = async_run

        self.create_widgets()

    def create_widgets(self):
        """Creates the main UI components for the tab."""
        # Toolbar
        self.toolbar = ttk.Frame(self)
        self.toolbar.pack(side=TOP, fill=X, padx=5, pady=5)

        # Save button is common to all, added to the right
        ttk.Button(
            self.toolbar,
            text="Save Changes",
            bootstyle="success",
            command=self.save_content
        ).pack(side=RIGHT, padx=5)

        # Text widget with scrollbar
        text_frame = ttk.Frame(self)
        text_frame.pack(fill=BOTH, expand=True, padx=5, pady=5)

        scrollbar = ttk.Scrollbar(text_frame)
        scrollbar.pack(side=RIGHT, fill=Y)

        self.text_widget = ttk.Text(
            text_frame, wrap=WORD, yscrollcommand=scrollbar.set, font=("Consolas", 14)
        )
        self.text_widget.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.config(command=self.text_widget.yview)

    def load_content(self, content):
        """Fills the text widget with content."""
        self.text_widget.config(state=NORMAL)
        self.text_widget.delete("1.0", END)
        self.text_widget.insert("1.0", content if content else "No data available.")

    def get_content(self):
        """Returns the current content of the text widget."""
        return self.text_widget.get("1.0", END).strip()

    def save_content(self):
        """Placeholder for the save method. Must be implemented by subclasses."""
        raise NotImplementedError("Each text tab must implement its own save_content method.")