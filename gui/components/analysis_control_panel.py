import ttkbootstrap as ttk
from ttkbootstrap.constants import X, W, BOTH, E, END
from ttkbootstrap.scrolled import ScrolledText
import logging
from ttkbootstrap.dialogs import Messagebox

class AnalysisControlPanel(ttk.Frame):
    """
    A control panel for editing technical analysis parameters:
    - Entry Price
    - Target Price
    - Stop Loss
    - Strategy Description
    """
    
    def __init__(self, parent, on_save_callback):
        super().__init__(parent, padding=10)
        self.on_save_callback = on_save_callback
        
        # Variables
        self.entry_var = ttk.StringVar()
        self.target_var = ttk.StringVar()
        self.stop_var = ttk.StringVar()
        
        self.create_widgets()
        
    def create_widgets(self):
        # Grid layout for inputs
        input_frame = ttk.Frame(self)
        input_frame.pack(fill=X, expand=True, pady=(0, 10))
        
        # Entry Price
        ttk.Label(input_frame, text="Entry Price (R):", font=("Helvetica", 9)).grid(row=0, column=0, padx=5, sticky=W)
        self.entry_entry = ttk.Entry(input_frame, textvariable=self.entry_var, width=15)
        self.entry_entry.grid(row=0, column=1, padx=5, sticky=W)
        
        # Target Price
        ttk.Label(input_frame, text="Target Price (R):", font=("Helvetica", 9)).grid(row=0, column=2, padx=5, sticky=W)
        self.target_entry = ttk.Entry(input_frame, textvariable=self.target_var, width=15)
        self.target_entry.grid(row=0, column=3, padx=5, sticky=W)
        
        # Stop Loss
        ttk.Label(input_frame, text="Stop Loss (R):", font=("Helvetica", 9)).grid(row=0, column=4, padx=5, sticky=W)
        self.stop_entry = ttk.Entry(input_frame, textvariable=self.stop_var, width=15)
        self.stop_entry.grid(row=0, column=5, padx=5, sticky=W)
        
        # Strategy Text Area
        ttk.Label(self, text="Strategy / Notes:", font=("Helvetica", 9, "bold")).pack(anchor=W, pady=(0, 5))
        self.strategy_text = ScrolledText(self, height=5, font=("Helvetica", 9))
        self.strategy_text.pack(fill=BOTH, expand=True, pady=(0, 10))

        # No persistent focus flag required; we'll determine focus on-demand
        # using the active widget so we accurately detect any input focus.
        
        # Save Button
        self.save_btn = ttk.Button(
            self, 
            text="Save Analysis", 
            command=self._on_save, 
            bootstyle="success"
        )
        self.save_btn.pack(anchor=E)
        
    def set_values(self, entry=None, target=None, stop=None, strategy=None):
        """Update the UI fields with provided values."""
        if entry is not None:
            self.entry_var.set(f"{entry:.2f}")
        if target is not None:
            self.target_var.set(f"{target:.2f}")
        if stop is not None:
            self.stop_var.set(f"{stop:.2f}")
        if strategy is not None:
            self.strategy_text.delete("1.0", END)
            self.strategy_text.insert("1.0", strategy)
            
    def get_values(self):
        """Return a dictionary of current values from the UI."""
        try:
            entry = float(self.entry_var.get()) if self.entry_var.get() else None
        except ValueError:
            entry = None
            
        try:
            target = float(self.target_var.get()) if self.target_var.get() else None
        except ValueError:
            target = None
            
        try:
            stop = float(self.stop_var.get()) if self.stop_var.get() else None
        except ValueError:
            stop = None
            
        strategy = self.strategy_text.get("1.0", END).strip()
        
        return {
            "entry_price": entry,
            "target_price": target,
            "stop_loss": stop,
            "strategy": strategy
        }
        
    def _on_save(self):
        """Trigger the save callback with current values."""
        values = self.get_values()
        if self.on_save_callback:
            try:
                self.on_save_callback(values)
            except Exception:
                logging.getLogger(__name__).exception("Error in AnalysisControlPanel save callback")
                try:
                    Messagebox.error("Save failed", "An error occurred saving analysis. See logs for details.")
                except Exception:
                    pass

        def has_strategy_focus(self) -> bool:
            """Return True if the strategy text area currently has input focus."""
            try:
                focused = self.focus_get()
                return focused is not None and (focused == self.strategy_text or str(focused).startswith(str(self.strategy_text)))
            except Exception:
                return False

        def has_any_input_focus(self) -> bool:
            """Return True if any of the form inputs (entry/target/stop/strategy) currently has focus."""
            try:
                focused = self.focus_get()
                widgets = [self.entry_entry, self.target_entry, self.stop_entry, self.strategy_text]
                return focused is not None and any(focused == w or str(focused).startswith(str(w)) for w in widgets)
            except Exception:
                return False
