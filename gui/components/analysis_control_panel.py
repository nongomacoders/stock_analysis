import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import X, W, BOTH, E, END, LEFT, BOTTOM
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
    
    def __init__(self, parent, on_save_callback, on_delete_support_callback=None, on_delete_resistance_callback=None):
        # Default constrained height to reduce analysis panel vertical footprint
        super().__init__(parent, padding=6, height=250)
        # Prevent children from expanding the height beyond our configured value
        try:
            self.pack_propagate(False)
        except Exception:
            pass
        self.on_save_callback = on_save_callback
        self.on_delete_support_callback = on_delete_support_callback
        self.on_delete_resistance_callback = on_delete_resistance_callback
        
        # Variables
        self.entry_var = ttk.StringVar()
        self.target_var = ttk.StringVar()
        self.stop_var = ttk.StringVar()
        
        self.create_widgets()
        
    def create_widgets(self):
        # Save Button - pack first at bottom to ensure it's always visible
        self.save_btn = ttk.Button(
            self, 
            text="Save Analysis", 
            command=self._on_save, 
            bootstyle="success"
        )
        self.save_btn.pack(side=BOTTOM, anchor=E, pady=(6, 0))
        
        # We split the panel into 4 columns (entry/target/stop, support, resistance, strategy)
        panel_inner = ttk.Frame(self)
        panel_inner.pack(fill=BOTH, expand=True)

        # Column frames
        col0 = ttk.Frame(panel_inner)
        col0.pack(side=LEFT, fill=BOTH, expand=True, padx=(6, 4))
        col1 = ttk.Frame(panel_inner)
        col1.pack(side=LEFT, fill=BOTH, expand=True, padx=(4, 4))
        col2 = ttk.Frame(panel_inner)
        col2.pack(side=LEFT, fill=BOTH, expand=True, padx=(4, 4))
        col3 = ttk.Frame(panel_inner)
        col3.pack(side=LEFT, fill=BOTH, expand=True, padx=(4, 6))

        # Column 0: Entry / Target / Stop stacked vertically
        input_stack = ttk.Frame(col0)
        input_stack.pack(fill=BOTH, expand=True, pady=(0, 4))
        
        # Entry Price (stacked)
        entry_frame = ttk.Frame(input_stack)
        entry_frame.pack(fill=X, pady=(2, 2))
        ttk.Label(entry_frame, text="Entry Price (R):", font=("Helvetica", 9)).pack(anchor=W)
        entry_row = ttk.Frame(entry_frame)
        entry_row.pack(fill=X)
        self.entry_entry = ttk.Entry(entry_row, textvariable=self.entry_var, width=12)
        self.entry_entry.pack(side=LEFT)
        self.entry_value_label = ttk.Label(entry_row, text="", width=12, anchor=W, font=("Helvetica", 9, "bold"))
        self.entry_value_label.pack(side=LEFT, padx=(6, 0))
        
        # Target Price (stacked)
        target_frame = ttk.Frame(input_stack)
        target_frame.pack(fill=X, pady=(2, 2))
        ttk.Label(target_frame, text="Target Price (R):", font=("Helvetica", 9)).pack(anchor=W)
        target_row = ttk.Frame(target_frame)
        target_row.pack(fill=X)
        self.target_entry = ttk.Entry(target_row, textvariable=self.target_var, width=12)
        self.target_entry.pack(side=LEFT)
        self.target_value_label = ttk.Label(target_row, text="", width=12, anchor=W, font=("Helvetica", 9, "bold"))
        self.target_value_label.pack(side=LEFT, padx=(6, 0))
        
        # Stop Loss (stacked)
        stop_frame = ttk.Frame(input_stack)
        stop_frame.pack(fill=X, pady=(2, 2))
        ttk.Label(stop_frame, text="Stop Loss (R):", font=("Helvetica", 9)).pack(anchor=W)
        stop_row = ttk.Frame(stop_frame)
        stop_row.pack(fill=X)
        self.stop_entry = ttk.Entry(stop_row, textvariable=self.stop_var, width=12)
        self.stop_entry.pack(side=LEFT)
        self.stop_value_label = ttk.Label(stop_row, text="", width=12, anchor=W, font=("Helvetica", 9, "bold"))
        self.stop_value_label.pack(side=LEFT, padx=(6, 0))

        # Support / Resistance display (read-only labels)
        # Support / Resistance lists with delete buttons
        # Support / Resistance lists with delete buttons (columns 2 & 3)
        support_frame = ttk.Frame(col1)
        support_frame.pack(fill=BOTH, pady=(0, 4))

        # Support list
        ttk.Label(support_frame, text='Support Levels', font=(None, 9, 'bold')).pack(anchor=W)
        list_frame_sup = ttk.Frame(support_frame)
        list_frame_sup.pack(fill=BOTH, pady=(2, 4))
        self.support_listbox = tk.Listbox(list_frame_sup, height=4, exportselection=False)
        self.support_listbox.pack(side=LEFT, fill=BOTH, expand=True)
        self.support_scroll = ttk.Scrollbar(list_frame_sup, orient='vertical', command=self.support_listbox.yview)
        self.support_scroll.pack(side=LEFT, fill='y')
        self.support_listbox.config(yscrollcommand=self.support_scroll.set)
        self.support_ids = []  # aligned list of ids (None for unsaved)
        # Put delete below so support elements are vertically stacked
        self.delete_support_btn = ttk.Button(support_frame, text='Delete Support', command=self._on_delete_support_click, bootstyle='danger')
        self.delete_support_btn.pack(anchor=W, pady=(2, 0))

        # Resistance list
        ttk.Label(col2, text='Resistance Levels', font=(None, 9, 'bold')).pack(anchor=W)
        list_frame_res = ttk.Frame(col2)
        list_frame_res.pack(fill=BOTH, pady=(2, 4))
        self.resistance_listbox = tk.Listbox(list_frame_res, height=4, exportselection=False)
        self.resistance_listbox.pack(side=LEFT, fill=BOTH, expand=True)
        self.resistance_scroll = ttk.Scrollbar(list_frame_res, orient='vertical', command=self.resistance_listbox.yview)
        self.resistance_scroll.pack(side=LEFT, fill='y')
        self.resistance_listbox.config(yscrollcommand=self.resistance_scroll.set)
        self.resistance_ids = []
        self.delete_resistance_btn = ttk.Button(col2, text='Delete Resistance', command=self._on_delete_resistance_click, bootstyle='danger')
        self.delete_resistance_btn.pack(anchor=W, pady=(2, 0))
        
        # Strategy Text Area (column 4)
        ttk.Label(col3, text="Strategy / Notes:", font=("Helvetica", 9, "bold")).pack(anchor=W, pady=(0, 5))
        # Keep strategy compact to reduce panel height
        self.strategy_text = ScrolledText(col3, height=3, font=("Helvetica", 9))
        self.strategy_text.pack(fill=BOTH, expand=True, pady=(0, 4))

        # No persistent focus flag required; we'll determine focus on-demand
        # using the active widget so we accurately detect any input focus.

        # Ensure the value labels update whenever the entry boxes change
        try:
            self.entry_var.trace_add("write", lambda *a: self._update_value_label(self.entry_var, self.entry_value_label))
            self.target_var.trace_add("write", lambda *a: self._update_value_label(self.target_var, self.target_value_label))
            self.stop_var.trace_add("write", lambda *a: self._update_value_label(self.stop_var, self.stop_value_label))
        except Exception:
            pass

    def _update_value_label(self, var: ttk.StringVar, label_widget: ttk.Label) -> None:
        """Update the label next to a price entry when the underlying variable changes."""
        try:
            val = var.get()
            if val:
                # Accept either float or string; ensure numeric formatting if possible
                try:
                    v = float(val)
                    label_widget.config(text=f"R{v:.2f}")
                except Exception:
                    label_widget.config(text=val)
            else:
                label_widget.config(text="")
        except Exception:
            pass
        
    def set_values(self, entry=None, target=None, stop=None, strategy=None):
        """Update the UI fields with provided values."""
        if entry is not None:
            self.entry_var.set(f"{entry:.2f}")
            try:
                self.entry_value_label.config(text=f"R{entry:.2f}")
            except Exception:
                pass
        if target is not None:
            self.target_var.set(f"{target:.2f}")
            try:
                self.target_value_label.config(text=f"R{target:.2f}")
            except Exception:
                pass
        if stop is not None:
            self.stop_var.set(f"{stop:.2f}")
            try:
                self.stop_value_label.config(text=f"R{stop:.2f}")
            except Exception:
                pass
        if strategy is not None:
            self.strategy_text.delete("1.0", END)
            self.strategy_text.insert("1.0", strategy)

    def set_levels(self, support=None, resistance=None):
        """Populate support/resistance listboxes.

        Expect `support` and `resistance` to be lists of (id, price) tuples where id
        may be None for unsaved values.
        """
        # Support list
        try:
            self.support_listbox.delete(0, tk.END)
            self.support_ids = []
            if support:
                for item in support:
                    # item may be a scalar price (legacy) or tuple (id, price)
                    if isinstance(item, tuple):
                        _id, price = item
                    else:
                        _id, price = None, float(item)
                    self.support_listbox.insert(tk.END, f"R{price:.2f}")
                    self.support_ids.append(_id)
            else:
                # no data
                pass
        except Exception:
            pass

        # Resistance list
        try:
            self.resistance_listbox.delete(0, tk.END)
            self.resistance_ids = []
            if resistance:
                for item in resistance:
                    if isinstance(item, tuple):
                        _id, price = item
                    else:
                        _id, price = None, float(item)
                    self.resistance_listbox.insert(tk.END, f"R{price:.2f}")
                    self.resistance_ids.append(_id)
        except Exception:
            pass

    def get_selected_support(self):
        sel = self.support_listbox.curselection()
        if not sel:
            return None
        i = sel[0]
        return (self.support_ids[i], float(self.support_listbox.get(i).strip('R')))

    def get_selected_resistance(self):
        sel = self.resistance_listbox.curselection()
        if not sel:
            return None
        i = sel[0]
        return (self.resistance_ids[i], float(self.resistance_listbox.get(i).strip('R')))

    def _on_delete_support_click(self):
        sel = self.get_selected_support()
        if not sel:
            try:
                Messagebox.info('No Selection', 'Select a support level to delete')
            except Exception:
                pass
            return
        level_id, _price = sel
        # If caller wants to handle deletion, call it; otherwise do a UI-only remove
        if callable(self.on_delete_support_callback):
            try:
                # Pass both level_id and price so caller can decide if deletion should hit DB
                self.on_delete_support_callback(level_id, _price)
            except Exception:
                logging.getLogger(__name__).exception('on_delete_support_callback failed')
        else:
            # UI only: remove selected
            try:
                sel_idx = self.support_listbox.curselection()[0]
                self.support_listbox.delete(sel_idx)
                self.support_ids.pop(sel_idx)
            except Exception:
                pass

    def _on_delete_resistance_click(self):
        sel = self.get_selected_resistance()
        if not sel:
            try:
                Messagebox.info('No Selection', 'Select a resistance level to delete')
            except Exception:
                pass
            return
        level_id, _price = sel
        if callable(self.on_delete_resistance_callback):
            try:
                self.on_delete_resistance_callback(level_id, _price)
            except Exception:
                logging.getLogger(__name__).exception('on_delete_resistance_callback failed')
        else:
            try:
                sel_idx = self.resistance_listbox.curselection()[0]
                self.resistance_listbox.delete(sel_idx)
                self.resistance_ids.pop(sel_idx)
            except Exception:
                pass
            
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
            # Include listboxes in the input focus check so keyboard drawing is suppressed
            try:
                widgets.extend([self.support_listbox, self.resistance_listbox])
            except Exception:
                pass
            return focused is not None and any(focused == w or str(focused).startswith(str(w)) for w in widgets)
        except Exception:
            return False
