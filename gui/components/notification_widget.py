import ttkbootstrap as ttk
from ttkbootstrap.constants import TOP, X, LEFT, RIGHT, BOTH, VERTICAL, Y, W, END
from tkinter import Menu
from datetime import datetime
import logging

# Import notification/alert functions
from modules.data.research import get_action_logs, mark_log_read, delete_action_log

logger = logging.getLogger(__name__)


class NotificationWidget(ttk.Frame):
    """A widget that displays recent notifications and alerts."""

    def __init__(self, parent, async_run, async_run_bg, notifier, on_select_callback=None):
        super().__init__(parent)
        self.async_run = async_run
        self.async_run_bg = async_run_bg
        self.notifier = notifier
        self.on_select = on_select_callback

        # Listen for action log notifications to auto-refresh the list (non-blocking)
        try:
            self.async_run_bg(self.notifier.add_listener("action_log_changes", self.on_notification_change))
            logger.debug("NotificationWidget: Registered listener for action_log_changes")
        except Exception as e:
            logger.exception("NotificationWidget: Failed to register notification listener: %s", e)
            # fallback to synchronous registration if background runner isn't available
            try:
                self.async_run(self.notifier.add_listener("action_log_changes", self.on_notification_change))
                logger.debug("NotificationWidget: Registered listener synchronously")
            except Exception as e2:
                logger.exception("NotificationWidget: Failed to register listener synchronously: %s", e2)

        self.create_widgets()
        self.refresh_notifications()

    def on_notification_change(self, payload: str):
        """Callback for DB notifications to reload the notification list."""
        logger.debug("NotificationWidget: Received action_log notification, refreshing...")
        self.after(0, self.refresh_notifications)

    def create_widgets(self):
        """Creates the content for the Notifications widget."""
        # --- TOOLBAR (Top) ---
        toolbar = ttk.Frame(self)
        toolbar.pack(side=TOP, fill=X, padx=5, pady=10)

        # Title
        ttk.Label(toolbar, text="Notifications & Alerts", font=("Segoe UI", 11, "bold")).pack(side=LEFT, padx=5)

        # Filter buttons
        ttk.Label(toolbar, text="Filter:").pack(side=LEFT, padx=(20, 5))
        
        self.filter_var = ttk.StringVar(value="unread")
        self.filter_combo = ttk.Combobox(
            toolbar, 
            textvariable=self.filter_var,
            values=["all", "unread", "read"], 
            state="readonly", 
            width=12
        )
        self.filter_combo.pack(side=LEFT, padx=2)
        self.filter_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_notifications())

        # Refresh button
        ttk.Button(
            toolbar, 
            text="Refresh", 
            command=self.refresh_notifications,
            bootstyle="info-outline",
            width=10
        ).pack(side=LEFT, padx=10)

        # Mark as Read button
        ttk.Button(
            toolbar, 
            text="Mark as Read", 
            command=self.mark_selected_read,
            bootstyle="success-outline",
            width=14
        ).pack(side=LEFT, padx=2)

        # Delete button
        ttk.Button(
            toolbar, 
            text="Delete", 
            command=self.delete_selected,
            bootstyle="danger-outline",
            width=10
        ).pack(side=LEFT, padx=2)

        # --- TREEVIEW (Main) ---
        cols = ("Timestamp", "Ticker", "Type", "Significance", "Alert", "Status")
        self.notif_tree = ttk.Treeview(self, columns=cols, show="headings")
        self.notif_tree.heading("Timestamp", text="Timestamp")
        self.notif_tree.heading("Ticker", text="Ticker")
        self.notif_tree.heading("Type", text="Type")
        self.notif_tree.heading("Significance", text="Significance")
        self.notif_tree.heading("Alert", text="Alert / Content")
        self.notif_tree.heading("Status", text="Status")

        self.notif_tree.column("Timestamp", width=150, anchor=W, stretch=False)
        self.notif_tree.column("Ticker", width=100, anchor=W, stretch=False)
        self.notif_tree.column("Type", width=100, anchor=W, stretch=False)
        self.notif_tree.column("Significance", width=100, anchor=W, stretch=False)
        self.notif_tree.column("Alert", width=400, anchor=W, stretch=True)
        self.notif_tree.column("Status", width=80, anchor=W, stretch=False)

        # Scrollbar
        scrolly = ttk.Scrollbar(self, orient=VERTICAL, command=self.notif_tree.yview)
        self.notif_tree.configure(yscroll=scrolly.set)

        scrolly.pack(side=RIGHT, fill=Y)
        self.notif_tree.pack(fill=BOTH, expand=True)

        # Data map
        self.notif_map = {}

        # --- STYLES & BINDINGS ---
        self.notif_tree.tag_configure("unread", foreground="#0066cc", font=("Segoe UI", 9, "bold"))
        self.notif_tree.tag_configure("read", foreground="grey", font=("Segoe UI", 9))
        self.notif_tree.tag_configure("warning", foreground="#d97706")
        self.notif_tree.tag_configure("critical", foreground="#dc2626", font=("Segoe UI", 9, "bold"))
        self.notif_tree.tag_configure("high", foreground="#dc2626", font=("Segoe UI", 9, "bold"))
        self.notif_tree.tag_configure("medium", foreground="#d97706")
        self.notif_tree.tag_configure("low", foreground="#10b981")

        # Bindings
        self.create_context_menu()
        self.notif_tree.bind("<Button-3>", self.show_context_menu)  # Right Click
        self.notif_tree.bind("<Double-1>", self.on_double_click)  # Double Click (Toggle Read Status)
        self.notif_tree.bind("<<TreeviewSelect>>", self.on_row_click)

    def create_context_menu(self):
        """Creates the right-click menu."""
        self.context_menu = Menu(self, tearoff=0)
        self.context_menu.add_command(
            label="Mark as Read", command=self.mark_selected_read
        )
        self.context_menu.add_command(
            label="Mark as Unread", command=self.mark_selected_unread
        )
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Delete", command=self.delete_selected)

    def show_context_menu(self, event):
        """Displays the context menu and selects the row under the mouse."""
        iid = self.notif_tree.identify_row(event.y)
        if iid:
            self.notif_tree.selection_set(iid)
            self.context_menu.post(event.x_root, event.y_root)

    def on_row_click(self, event):
        """Load ticker behavior on single click, mirroring the watchlist."""
        if not callable(self.on_select):
            return

        sel = self.notif_tree.selection()
        if not sel:
            return

        item = self.notif_tree.item(sel[0])
        values = item.get("values") or []
        if len(values) < 2:
            return

        ticker = values[1]
        if not ticker or ticker == "-":
            return

        self.on_select(ticker)

    def refresh_notifications(self):
        """Refresh the notifications list (non-blocking)."""

        def on_notifications_loaded(data):
            logger.debug("NotificationWidget: Loaded %s action logs", len(data) if data else 0)
            self.notif_tree.delete(*self.notif_tree.get_children())
            self.notif_map.clear()

            if not data:
                self.notif_tree.insert(
                    "", "end", values=("", "", "", "No notifications found!", "")
                )
                return

            # Apply filter
            filter_type = self.filter_var.get()
            filtered_data = data

            if filter_type == "unread":
                filtered_data = [row for row in data if not row.get("is_read")]
            elif filter_type == "read":
                filtered_data = [row for row in data if row.get("is_read")]

            # Exclude low significance items
            filtered_data = [
                row for row in filtered_data 
                if (row.get("significance") or "").lower() != "low"
            ]

            if not filtered_data:
                self.notif_tree.insert(
                    "", "end", values=("", "", "", "No notifications match filter.", "")
                )
                return

            for row in filtered_data:
                is_read = row.get("is_read", False)
                trigger_type = row.get("trigger_type", "alert")
                significance = row.get("significance", "") or "-"
                
                # Determine tags based on read status and type
                tags = ()
                if not is_read:
                    tags = ("unread",)
                else:
                    tags = ("read",)
                
                # Add significance tags
                sig_lower = significance.lower()
                if sig_lower == "high":
                    tags = tags + ("high",) if tags else ("high",)
                elif sig_lower == "medium":
                    tags = tags + ("medium",) if tags else ("medium",)
                elif sig_lower == "low":
                    tags = tags + ("low",) if tags else ("low",)
                
                # Add warning/critical tags based on trigger type
                if trigger_type == "price_hit":
                    tags = tags + ("warning",) if tags else ("warning",)
                elif trigger_type == "critical":
                    tags = ("critical",)

                # Format timestamp
                log_time = row.get("log_timestamp")
                time_str = ""
                if log_time:
                    if isinstance(log_time, str):
                        time_str = log_time[:16]  # ISO format, take first 16 chars
                    else:
                        try:
                            time_str = log_time.strftime("%Y-%m-%d %H:%M")
                        except Exception:
                            time_str = str(log_time)[:16]

                status = "Unread" if not is_read else "Read"

                iid = self.notif_tree.insert(
                    "",
                    "end",
                    values=(
                        time_str,
                        row.get("ticker", "-"),
                        trigger_type.title(),
                        significance,
                        row.get("trigger_content", "")[:100],  # Truncate long content
                        status,
                    ),
                    tags=tags,
                )
                self.notif_map[iid] = row

        # Fetch action logs (which serve as notifications)
        # Get all logs, not filtered by ticker - we want global notifications
        try:
            import asyncio
            # We need a global search for all tickers' logs
            # Use a special ticker string or modify the query to get all
            from core.db.engine import DBEngine
            
            async def get_all_alerts():
                query = """
                    SELECT 
                        log_id,
                        ticker,
                        log_timestamp,
                        trigger_type,
                        trigger_content,
                        is_read,
                        significance
                    FROM action_log
                    ORDER BY log_timestamp DESC
                    LIMIT 100
                """
                try:
                    results = await DBEngine.fetch(query)
                    logger.debug("NotificationWidget: Query returned %s results", len(results) if results else 0)
                    return results
                except Exception as e:
                    logger.exception("NotificationWidget: Failed to fetch action logs: %s", e)
                    return []
            
            self.async_run_bg(get_all_alerts(), callback=on_notifications_loaded)
        except Exception:
            # Fallback: try to get from a single ticker or return empty
            def on_fetch_failed(error):
                self.notif_tree.insert(
                    "", "end", values=("", "", "", "Error loading notifications", "")
                )
            self.async_run_bg(None, callback=on_fetch_failed)

    def on_double_click(self, event):
        """Toggle read status on double click."""
        selection = self.notif_tree.selection()
        if not selection:
            return

        item_id = selection[0]
        if item_id not in self.notif_map:
            return

        is_read = self.notif_map[item_id].get("is_read", False)
        
        if is_read:
            self.mark_selected_unread()
        else:
            self.mark_selected_read()

    def mark_selected_read(self):
        """Mark selected notification(s) as read."""
        selection = self.notif_tree.selection()
        if not selection:
            return

        def mark_all():
            for item_id in selection:
                if item_id in self.notif_map:
                    log_id = self.notif_map[item_id].get("log_id")
                    if log_id:
                        self.async_run_bg(mark_log_read(log_id))
            
            self.after(500, self.refresh_notifications)

        self.async_run_bg(mark_all() if not selection else None)
        # Mark synchronously for better UX
        for item_id in selection:
            if item_id in self.notif_map:
                log_id = self.notif_map[item_id].get("log_id")
                if log_id:
                    self.async_run_bg(mark_log_read(log_id))
        
        self.after(300, self.refresh_notifications)

    def mark_selected_unread(self):
        """Mark selected notification(s) as unread (note: may require DB modification)."""
        selection = self.notif_tree.selection()
        if not selection:
            return

        # For now, just refresh - marking unread may require a separate DB function
        # In a full implementation, you'd want an update function like mark_log_unread()
        self.refresh_notifications()

    def delete_selected(self):
        """Delete selected notification(s)."""
        selection = self.notif_tree.selection()
        if not selection:
            return

        import tkinter.messagebox as messagebox
        
        if messagebox.askyesno("Confirm Delete", f"Delete {len(selection)} notification(s)?"):
            for item_id in selection:
                if item_id in self.notif_map:
                    log_id = self.notif_map[item_id].get("log_id")
                    if log_id:
                        self.async_run_bg(delete_action_log(log_id))
            
            self.after(300, self.refresh_notifications)
