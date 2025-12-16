"""
Zone Detection Settings Dialog

A dialog for configuring support/resistance zone detection parameters.
"""
import ttkbootstrap as ttk
from ttkbootstrap.constants import X, W, E, BOTH, LEFT, RIGHT
from ttkbootstrap.dialogs import Messagebox


class ZoneSettingsDialog(ttk.Toplevel):
    """A dialog for adjusting zone detection parameters."""
    
    # Default values
    DEFAULTS = {
        "lookback": 100,
        "peak_distance": 4,
        "peak_prominence": None,
        "atr_period": 14,
        "zone_atr_mult": 0.8,
        "min_touches": 2,
        "max_zones_each": 2,
        "recency_weight": 0.35,
        "rejection_weight": 0.75,
        "test_lookback": 120,
    }
    
    def __init__(self, parent, current_settings=None, on_save_callback=None):
        super().__init__(parent)
        self.title("Zone Detection Settings")
        self.geometry("380x500")
        self.resizable(False, False)
        
        self.on_save_callback = on_save_callback
        
        # Use current settings or defaults
        self.settings = dict(self.DEFAULTS)
        if current_settings:
            self.settings.update(current_settings)
        
        self.create_widgets()
        
        # Center on parent
        self.transient(parent)
        self.grab_set()
    
    def create_widgets(self):
        main_frame = ttk.Frame(self, padding=15)
        main_frame.pack(fill=BOTH, expand=True)
        
        # Title
        ttk.Label(main_frame, text="Zone Detection Parameters", font=("Helvetica", 12, "bold")).pack(anchor=W, pady=(0, 10))
        
        # Parameter input fields
        fields_frame = ttk.Frame(main_frame)
        fields_frame.pack(fill=X, expand=True)
        
        row = 0
        
        # Lookback
        ttk.Label(fields_frame, text="Lookback (bars):").grid(row=row, column=0, sticky=W, pady=3)
        self.lookback_var = ttk.StringVar(value=str(self.settings["lookback"]))
        ttk.Entry(fields_frame, textvariable=self.lookback_var, width=10).grid(row=row, column=1, sticky=E, pady=3)
        row += 1
        
        # Peak Distance
        ttk.Label(fields_frame, text="Peak Distance (bars):").grid(row=row, column=0, sticky=W, pady=3)
        self.peak_distance_var = ttk.StringVar(value=str(self.settings["peak_distance"]))
        ttk.Entry(fields_frame, textvariable=self.peak_distance_var, width=10).grid(row=row, column=1, sticky=E, pady=3)
        row += 1
        
        # Peak Prominence
        ttk.Label(fields_frame, text="Peak Prominence:").grid(row=row, column=0, sticky=W, pady=3)
        prom_val = "" if self.settings["peak_prominence"] is None else str(self.settings["peak_prominence"])
        self.peak_prominence_var = ttk.StringVar(value=prom_val)
        ttk.Entry(fields_frame, textvariable=self.peak_prominence_var, width=10).grid(row=row, column=1, sticky=E, pady=3)
        ttk.Label(fields_frame, text="(leave empty for auto)", font=("Helvetica", 8)).grid(row=row, column=2, sticky=W, padx=(5, 0))
        row += 1
        
        # ATR Period
        ttk.Label(fields_frame, text="ATR Period:").grid(row=row, column=0, sticky=W, pady=3)
        self.atr_period_var = ttk.StringVar(value=str(self.settings["atr_period"]))
        ttk.Entry(fields_frame, textvariable=self.atr_period_var, width=10).grid(row=row, column=1, sticky=E, pady=3)
        row += 1
        
        # Zone ATR Multiplier
        ttk.Label(fields_frame, text="Zone ATR Multiplier:").grid(row=row, column=0, sticky=W, pady=3)
        self.zone_atr_mult_var = ttk.StringVar(value=str(self.settings["zone_atr_mult"]))
        ttk.Entry(fields_frame, textvariable=self.zone_atr_mult_var, width=10).grid(row=row, column=1, sticky=E, pady=3)
        row += 1
        
        # Min Touches
        ttk.Label(fields_frame, text="Min Touches:").grid(row=row, column=0, sticky=W, pady=3)
        self.min_touches_var = ttk.StringVar(value=str(self.settings["min_touches"]))
        ttk.Entry(fields_frame, textvariable=self.min_touches_var, width=10).grid(row=row, column=1, sticky=E, pady=3)
        row += 1
        
        # Max Zones Each
        ttk.Label(fields_frame, text="Max Zones (each):").grid(row=row, column=0, sticky=W, pady=3)
        self.max_zones_each_var = ttk.StringVar(value=str(self.settings["max_zones_each"]))
        ttk.Entry(fields_frame, textvariable=self.max_zones_each_var, width=10).grid(row=row, column=1, sticky=E, pady=3)
        row += 1
        
        # Recency Weight
        ttk.Label(fields_frame, text="Recency Weight:").grid(row=row, column=0, sticky=W, pady=3)
        self.recency_weight_var = ttk.StringVar(value=str(self.settings["recency_weight"]))
        ttk.Entry(fields_frame, textvariable=self.recency_weight_var, width=10).grid(row=row, column=1, sticky=E, pady=3)
        row += 1
        
        # Rejection Weight
        ttk.Label(fields_frame, text="Rejection Weight:").grid(row=row, column=0, sticky=W, pady=3)
        self.rejection_weight_var = ttk.StringVar(value=str(self.settings["rejection_weight"]))
        ttk.Entry(fields_frame, textvariable=self.rejection_weight_var, width=10).grid(row=row, column=1, sticky=E, pady=3)
        row += 1
        
        # Test Lookback
        ttk.Label(fields_frame, text="Test Lookback (bars):").grid(row=row, column=0, sticky=W, pady=3)
        self.test_lookback_var = ttk.StringVar(value=str(self.settings["test_lookback"]))
        ttk.Entry(fields_frame, textvariable=self.test_lookback_var, width=10).grid(row=row, column=1, sticky=E, pady=3)
        row += 1
        
        fields_frame.columnconfigure(1, weight=1)
        
        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=X, pady=(15, 0))
        
        ttk.Button(btn_frame, text="Reset to Defaults", command=self._reset_defaults, bootstyle="secondary").pack(side=LEFT)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy, bootstyle="secondary").pack(side=RIGHT, padx=(5, 0))
        ttk.Button(btn_frame, text="Apply", command=self._on_apply, bootstyle="success").pack(side=RIGHT)
    
    def _reset_defaults(self):
        """Reset all fields to default values."""
        self.lookback_var.set(str(self.DEFAULTS["lookback"]))
        self.peak_distance_var.set(str(self.DEFAULTS["peak_distance"]))
        self.peak_prominence_var.set("")
        self.atr_period_var.set(str(self.DEFAULTS["atr_period"]))
        self.zone_atr_mult_var.set(str(self.DEFAULTS["zone_atr_mult"]))
        self.min_touches_var.set(str(self.DEFAULTS["min_touches"]))
        self.max_zones_each_var.set(str(self.DEFAULTS["max_zones_each"]))
        self.recency_weight_var.set(str(self.DEFAULTS["recency_weight"]))
        self.rejection_weight_var.set(str(self.DEFAULTS["rejection_weight"]))
        self.test_lookback_var.set(str(self.DEFAULTS["test_lookback"]))
    
    def _on_apply(self):
        """Validate and save settings."""
        try:
            settings = {
                "lookback": int(self.lookback_var.get()),
                "peak_distance": int(self.peak_distance_var.get()),
                "peak_prominence": float(self.peak_prominence_var.get()) if self.peak_prominence_var.get().strip() else None,
                "atr_period": int(self.atr_period_var.get()),
                "zone_atr_mult": float(self.zone_atr_mult_var.get()),
                "min_touches": int(self.min_touches_var.get()),
                "max_zones_each": int(self.max_zones_each_var.get()),
                "recency_weight": float(self.recency_weight_var.get()),
                "rejection_weight": float(self.rejection_weight_var.get()),
                "test_lookback": int(self.test_lookback_var.get()),
            }
            
            # Basic validation
            if settings["lookback"] < 10:
                raise ValueError("Lookback must be at least 10")
            if settings["peak_distance"] < 1:
                raise ValueError("Peak distance must be at least 1")
            if settings["min_touches"] < 1:
                raise ValueError("Min touches must be at least 1")
            if settings["max_zones_each"] < 1:
                raise ValueError("Max zones must be at least 1")
            
            if self.on_save_callback:
                self.on_save_callback(settings)
            
            self.destroy()
            
        except ValueError as e:
            Messagebox.show_error(f"Invalid value: {e}", "Validation Error", parent=self)
