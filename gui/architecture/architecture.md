# GUI Application Architecture
**Last Updated:** 2025-11-30

## Overview
This document describes the architecture of the JSE Stock Analysis GUI application, a desktop application built with Python and ttkbootstrap that provides real-time stock monitoring, analysis, and portfolio management capabilities.

## System Architecture

### High-Level Components

```
┌─────────────────────────────────────────────────────────────┐
│                    CommandCenter (Main Window)               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  Watchlist   │  │ Chart Window │  │Research Window│      │
│  │   Widget     │  │              │  │              │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────────┐
        │         Core Services Layer           │
        │  ┌──────────┐  ┌──────────────────┐  │
        │  │ DBEngine │  │   DBNotifier     │  │
        │  │  (Pool)  │  │ (LISTEN/NOTIFY)  │  │
        │  └──────────┘  └──────────────────┘  │
        └───────────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────────┐
        │      PostgreSQL Database              │
        │  ┌────────────┐  ┌─────────────────┐ │
        │  │ action_log │  │  Trigger/NOTIFY │ │
        │  │   Table    │  │    Function     │ │
        │  └────────────┘  └─────────────────┘ │
        └───────────────────────────────────────┘
                            ▲
                            │
        ┌───────────────────────────────────────┐
        │      Background Services              │
        │  ┌──────────────────────────────────┐ │
        │  │   market_agent.py (Daemon)       │ │
        │  │   - Monitors market events       │ │
        │  │   - Writes to action_log         │ │
        │  └──────────────────────────────────┘ │
        └───────────────────────────────────────┘
```

## Directory Structure

```
gui/
├── scripts/                    # Entry points and background services
│   ├── main.py                # Main application entry point
│   ├── market_agent.py        # Background market monitoring daemon
│   └── apply_migration.py     # Database migration utility
│
├── core/                      # Core infrastructure
│   ├── db/                    # Database layer
│   │   ├── engine.py         # Connection pool manager (DBEngine)
│   │   ├── notifier.py       # PostgreSQL LISTEN/NOTIFY handler
│   │   └── migrations/       # SQL migration scripts
│   ├── utils/                # Shared utilities
│   └── config.py             # Configuration settings
│
├── components/               # UI components
│   ├── watchlist.py         # Main watchlist grid widget
│   ├── chart_window.py      # Stock chart window
│   └── research_window.py   # Research and analysis window
│
├── modules/                 # Business logic modules
│   ├── data/               # Data access layer
│   │   ├── watchlist.py   # Watchlist data queries
│   │   └── research.py    # Research data queries
│   ├── analysis/          # Analysis engines
│   └── market_agent/      # Market monitoring logic
│
└── architecture/           # Documentation
    └── architecture.md    # This file
```

## Key Design Patterns

### 1. Singleton Pattern - Database Connection Pool
The `DBEngine` class implements a singleton pattern for the PostgreSQL connection pool:
- Single shared pool across the application
- Lazy initialization on first access
- Thread-safe async operations

### 2. Observer Pattern - Real-Time Notifications
PostgreSQL LISTEN/NOTIFY implements the observer pattern:
- Database triggers act as publishers
- `DBNotifier` acts as subscriber
- GUI components react to notifications

### 3. Callback Pattern - UI Updates
Components use callbacks for decoupled communication:
- `WatchlistWidget` → `CommandCenter` (ticker selection)
- `ResearchWindow` → `CommandCenter` (data changes)
- `DBNotifier` → `CommandCenter` (database notifications)

## Async Architecture

### Event Loop Management
- Main thread runs tkinter event loop
- Separate thread runs asyncio event loop
- `async_run()` helper bridges sync/async code

```python
# Async loop in background thread
self.loop = asyncio.new_event_loop()
self.loop_thread = threading.Thread(target=self._run_event_loop, daemon=True)

# Bridge from sync to async
def async_run(self, coro):
    future = asyncio.run_coroutine_threadsafe(coro, self.loop)
    return future.result()
```

## Real-Time Notification System

### PostgreSQL LISTEN/NOTIFY Flow

1. **Trigger Setup** (Database)
   ```sql
   CREATE TRIGGER action_log_notify_trigger
       AFTER INSERT OR UPDATE ON action_log
       FOR EACH ROW
       EXECUTE FUNCTION notify_action_log_change();
   ```

2. **Notification Listener** (Application)
   - `DBNotifier` maintains dedicated connection
   - Listens on `action_log_changes` channel
   - Invokes callback on notification

3. **UI Update** (Main Thread)
   - Callback uses `after()` to schedule on main thread
   - Watchlist refreshes to show updated data
   - Red highlighting applied for unread logs

### Benefits
- **Instant Updates**: 1-2 second latency vs 30-second polling
- **Reduced Load**: No periodic database queries
- **Scalable**: Push-based architecture

## Window Management

### Window Positioning
- **Watchlist**: Left half of screen
- **Chart Window**: Right upper quadrant
- **Research Window**: Right lower quadrant

### Window Reuse
Windows are reused rather than recreated:
```python
if self.research_window and self.research_window.winfo_exists():
    self.research_window.update_ticker(ticker)
    self.research_window.lift()
else:
    self.research_window = ResearchWindow(...)
```

## Data Flow

### Watchlist Refresh Flow
```
User Action / Notification
        ↓
CommandCenter.watchlist.refresh()
        ↓
fetch_watchlist_data() (async)
        ↓
PostgreSQL Query (with unread_log_count)
        ↓
WatchlistWidget.refresh()
        ↓
Apply row tags (unread/holding/pretrade)
        ↓
UI Update (red background for unread)
```

### Action Log Update Flow
```
market_agent.py writes to action_log
        ↓
PostgreSQL Trigger fires
        ↓
NOTIFY sent on action_log_changes channel
        ↓
DBNotifier receives notification
        ↓
Callback invokes watchlist.refresh()
        ↓
UI updates immediately
```

## Database Schema (Relevant Tables)

### action_log
- `log_id` (PK)
- `ticker` (FK to stock_details)
- `log_timestamp`
- `trigger_type`
- `trigger_content`
- `ai_analysis`
- `is_read` (boolean)

### Indexes & Triggers
- Trigger: `action_log_notify_trigger` (AFTER INSERT OR UPDATE)
- Function: `notify_action_log_change()` (sends NOTIFY)

## Configuration

### Database Connection
Configured in `core/config.py`:
```python
DB_CONFIG = {
    "host": "100.92.22.55",
    "dbname": "jse_stock_data",
    "user": "postgres",
    "password": "..."
}
```

### Connection Pool Settings
- Min connections: 2
- Max connections: 10
- Managed by `DBEngine` singleton

## Background Services

### market_agent.py
- Runs as separate daemon process
- Monitors market events and SENS announcements
- Writes to `action_log` table
- Triggers real-time UI updates via NOTIFY

## UI Theming
- Framework: ttkbootstrap
- Theme: "cosmo"
- Custom row tags for visual states:
  - `unread`: Red background (#ffcccc)
  - `holding`: Green background (#d1e7dd)
  - `pretrade`: Purple background (#E6E6FA)

## Future Enhancements
- Multiple notification channels for different event types
- Notification batching for high-frequency updates
- Reconnection logic for network failures
- Metrics/monitoring for notification latency
