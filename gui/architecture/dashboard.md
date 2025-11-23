# Monitoring Dashboard Architecture

## 1. The Watchlist Grid (Central Widget)
* **Ticker:** Color-coded by Event Proximity (Red < 7 days, Green < 30, Yellow < 60).
* **Name:** Truncated.
* **Proximity:** Always visible text (e.g., "Hitting Stop" or "Entry in 15%").
* **SENS Icon:** Indicates unread news.
* **Interaction:**
    * **Single Click:** Updates the **Strategy Preview Panel** at the bottom.
    * **Double Click:** Opens the full **Execution Window**.

## 2. The SENS Feed (Side Panel)
* **Source:** `action_log` filtered for SENS.
* **Logic:** Shows unread items. "High Impact" items flagged by AI turn Red.
* **Interaction:** Double-click opens the Execution Window.

## 3. The Portfolio Scorecard (Top HUD)
A persistent ribbon showing real-time financial health.
* **Metrics:** Total Investment Value | Total Open P&L (R and %) | Day P&L | Cash Available | Top Mover.

## 4. The Strategy Preview Panel (Bottom Dock)
A read-only pane fixed to the bottom of the dashboard.

### A. Functionality
* **Trigger:** Updates instantly when a row in the Watchlist Grid is selected (single-click or arrow keys).
* **Content:** Displays the `strategy` text from the `public.stock_analysis` table.
* **Visuals:**
    * **Header:** "Strategy for [TICKER]: [Full Name]"
    * **Body:** Scrollable text area. If the strategy is empty, it displays a placeholder like "No strategy defined."
    * **Quick Action:** A small "Edit" button in the corner that launches the full Execution Window (same action as double-clicking the grid row).