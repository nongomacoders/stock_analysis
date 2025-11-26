import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import asyncio
import threading


class AdminWindow(ttk.Toplevel):
    """Admin window for managing system operations like updating metrics"""
    
    def __init__(self, parent, db, event_loop):
        super().__init__(parent)
        self.db = db
        self.loop = event_loop
        self.title("Admin Panel")
        self.geometry("700x500")
        
        # Make it a utility window that stays on top
        self.transient(parent)
        
        print("Admin window created")
        self.create_layout()
        print("Admin layout created with Update Metrics button")
        
    def create_layout(self):
        """Create the admin panel layout"""
        # Header
        header_frame = ttk.Frame(self, bootstyle="primary")
        header_frame.pack(side=TOP, fill=X, padx=10, pady=10)
        
        ttk.Label(
            header_frame, 
            text="Admin Panel", 
            font=("Helvetica", 16, "bold"),
            bootstyle="inverse-primary"
        ).pack(pady=10)
        
        # Main content area
        content_frame = ttk.Frame(self)
        content_frame.pack(fill=BOTH, expand=True, padx=20, pady=10)
        
        # Metrics Update Section
        metrics_frame = ttk.Labelframe(
            content_frame, 
            text="Metrics Management", 
            bootstyle="info",
            padding=20
        )
        metrics_frame.pack(fill=X, pady=10)
        
        ttk.Label(
            metrics_frame,
            text="Update system metrics and recalculate data",
            font=("Helvetica", 10)
        ).pack(pady=(0, 15))
        
        # Update Metrics Button
        self.update_btn = ttk.Button(
            metrics_frame,
            text="Update Metrics",
            bootstyle="success",
            command=self.update_metrics,
            width=20
        )
        self.update_btn.pack(pady=5)
        
        # Status Label
        self.status_label = ttk.Label(
            metrics_frame,
            text="Ready",
            font=("Helvetica", 9),
            bootstyle="secondary"
        )
        self.status_label.pack(pady=(10, 0))
        
        # Log/Output Area
        log_frame = ttk.Labelframe(
            content_frame,
            text="Activity Log",
            bootstyle="secondary",
            padding=10
        )
        log_frame.pack(fill=BOTH, expand=True, pady=10)
        
        # Text widget for logs
        self.log_text = ttk.Text(
            log_frame,
            height=10,
            wrap=WORD,
            state=DISABLED
        )
        self.log_text.pack(fill=BOTH, expand=True, side=LEFT)
        
        # Scrollbar for logs
        scrollbar = ttk.Scrollbar(
            log_frame,
            orient=VERTICAL,
            command=self.log_text.yview
        )
        scrollbar.pack(side=RIGHT, fill=Y)
        self.log_text.config(yscrollcommand=scrollbar.set)
        
        # Close button at bottom
        close_btn = ttk.Button(
            self,
            text="Close",
            bootstyle="secondary",
            command=self.destroy,
            width=15
        )
        close_btn.pack(pady=10)
        
    def log_message(self, message):
        """Add a message to the log text area"""
        self.log_text.config(state=NORMAL)
        self.log_text.insert(END, f"{message}\n")
        self.log_text.see(END)
        self.log_text.config(state=DISABLED)
        
    def update_status(self, status):
        """Update the status label"""
        self.status_label.config(text=status)
        
    def update_metrics(self):
        """Handle the update metrics button click"""
        self.log_message("=" * 50)
        self.log_message("Starting metrics update...")
        self.update_status("Updating...")
        
        # Disable button during update
        self.update_btn.config(state=DISABLED)
        
        # Run the update in a separate thread to avoid blocking the UI
        thread = threading.Thread(target=self._perform_update)
        thread.daemon = True
        thread.start()
        
    def _perform_update(self):
        """Perform the actual metrics update (runs in separate thread)"""
        try:
            # Import valuation engine
            from valuation_engine import ValuationEngine
            
            # Create engine with logging callback
            engine = ValuationEngine(self.db, self.log_message)
            
            # Run async valuation update in the event loop
            future = asyncio.run_coroutine_threadsafe(
                engine.run_valuation_update(),
                self.loop
            )
            
            # Wait for completion with timeout (5 minutes)
            result = future.result(timeout=300)
            
            # Final status update
            self.after(0, lambda: self.update_status("Complete"))
            
        except asyncio.TimeoutError:
            self.after(0, lambda: self.log_message("Error: Valuation update timed out (5min limit)"))
            self.after(0, lambda: self.update_status("Timeout"))
        except Exception as e:
            self.after(0, lambda: self.log_message(f"Error: {type(e).__name__}: {str(e)}"))
            self.after(0, lambda: self.update_status("Error"))
        
        finally:
            # Re-enable button
            self.after(0, lambda: self.update_btn.config(state=NORMAL))
