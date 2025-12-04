import ttkbootstrap as ttk
from ttkbootstrap.constants import TOP, X, RIGHT, Y, LEFT, BOTH, WORD, END, NORMAL
import logging
from ttkbootstrap.dialogs import Messagebox
from components.button_utils import run_bg_with_button, wrap_sync_button


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

        # Save button is common to all, added to the right. Keep a reference so
        # other code can disable while saves are running.
        self.save_btn = ttk.Button(
            self.toolbar,
            text="Save Changes",
            bootstyle="success",
            command=self._safe_save
        )
        self.save_btn.pack(side=RIGHT, padx=5)

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

    def _safe_save(self):
        """Wrapper around save_content that logs any exceptions and informs the user.

        This prevents quiet failures when save handlers raise and provides
        centralized logging for saves triggered through the common Save button.
        """
        # Log the invocation so button presses are visible in gui.log
        try:
            caller = self.__class__.__name__
            ticker_val = getattr(self, 'ticker', None)
            logging.getLogger(__name__).info("_safe_save called on %s ticker=%s", caller, ticker_val)
        except Exception:
            # non-fatal if logging introspection fails
            pass

        # If the subclass provides an async-saving coroutine factory `save_async`
        # and the UI has a background runner (`async_run_bg`) then prefer to
        # run the coroutine in the background while disabling the save button.
        try:
            if hasattr(self, "async_run_bg") and getattr(self, "async_run_bg") and hasattr(self, "save_async") and callable(getattr(self, "save_async")):
                try:
                    run_bg_with_button(self.save_btn, self.async_run_bg, self.save_async())
                    return
                except Exception:
                    logging.getLogger(__name__).exception("Failed to start background save via run_bg_with_button; falling back to sync save")

            # Otherwise, call save_content synchronously while keeping the
            # save button disabled so the user can't re-press it.
            try:
                wrap_sync_button(self.save_btn, self.save_content)
            except Exception:
                logging.getLogger(__name__).exception("Error saving content in %s", self.__class__.__name__)
                try:
                    Messagebox.error("Save failed", f"An error occurred while saving ({self.__class__.__name__}). See logs for details.")
                except Exception:
                    pass
        except Exception:
            # Catch any unexpected error to avoid crashing the UI
            logging.getLogger(__name__).exception("Unexpected error in _safe_save for %s", self.__class__.__name__)