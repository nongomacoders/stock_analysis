JSE Stock Analyzer: Updated Application Architecture
1. Overall Purpose
This is a multi-faceted system for analyzing JSE-listed stocks, consisting of a GUI workstation, a central database, and an autonomous 24/7 monitoring agent.

The system is designed to:

Provide a multi-tabbed Tkinter GUI for manual analysis, charting, and trade planning.

Connect to a central PostgreSQL database to store and manage all user data and market data.

Automate 24/7 Monitoring: A standalone 'agent' runs to scrape SENS news and EOD prices.

Provide AI-Driven Insights: The agent feeds new data (SENS, price hits) to an AI analysis engine, which generates actionable plans based on the user's saved research.

2. System Components
The system is broken into four distinct components:

The GUI (stock_analyzer_gui.py + tab_*.py files):

This is the user-facing workstation.

It's used for manual data entry (earnings, strategy), charting, and reviewing AI-generated action plans.

It is not responsible for any automated data scraping.

The Agent (market_agent.py):

This is a standalone Python script designed to run 24/7 on a server or in a terminal.

It is not part of the GUI.

It manages its own schedule, running SENS checks during market hours and EOD price downloads after market close.

The AI Brain (analysis_engine.py):

This is a new, non-GUI Python module.

It contains functions that are called by the Agent.

Its job is to:

Receive a trigger (e.g., "New SENS for KAP.JO").

Fetch the user's master research from the stock_analysis table.

Build a detailed prompt for the Google AI.

Get the AI's recommendation and save it to the action_log table.

The PostgreSQL Database (jse_stock_data):

The central "memory" for all components.

It's used by the GUI to read and write user data.

It's used by the Agent to get its ticker list and save new SENS/price data.

It's used by the AI Brain to read research and write action plans.

3. Database Tables (9 Total)
Market & Scraper Tables
daily_stock_data: Stores all EOD OHLCV price data (in Cents), downloaded by the Agent.

price_update_log: Log table used by the Agent to manage data freshness and EOD downloads.

SENS (New): Stores the full text content of SENS announcements, scraped and saved by the Agent.

User-Entered Data Tables
stock_details: The master list of all stocks (e.g., KAP.JO, "KAP Industrial Holdings").

historical_earnings: Stores historical HEPS data, managed by the Earnings Tab.

stock_analysis (New): Stores the user's master research, strategy, and research price levels (as a decimal array). This table is managed exclusively by the Strategy Tab.

watchlist: Manages the status of all stocks (e.g., "Pending", "Active-Trade").

stock_price_levels: Stores the single active trade entry price for a stock. This table is managed exclusively by the Analysis Tab ("Add to Watchlist" button).

AI & Logging Tables
action_log (New): The "to-do list" of AI-generated insights. The AI Brain writes new recommendations here, and the GUI (in a future tab) will read from it.

4. GUI Module Interaction (stock_analyzer_gui.py)
This describes the flow within the Tkinter application itself.

stock_analyzer_gui.py (Main):

Builds the ttk.Notebook and imports all tab_*.py modules.

Passes DB_CONFIG to all tabs for their database connections.

Contains the load_ticker_on_analysis_tab "bridge function."

tab_scan.py (Scan Tab):

Scans daily_stock_data and stock_details for proximity hits on "Pending" stocks.

Note: This tab's download logic has been removed and is now handled by the market_agent.py. This tab is now read-only.

tab_details.py (Details Tab):

Full CRUD (Create, Read, Update, Delete) for the stock_details table.

tab_earnings.py (Earnings Tab):

Full CRUD for the historical_earnings table.

tab_strategy.py (Strategy Tab) (New):

Full CRUD for the stock_analysis table, allowing you to edit your master research, strategy, and research price level array.

tab_analysis.py (Analysis & Watchlist Hub):

Reads daily_stock_data for charts.

Reads stock_price_levels to draw the single purple trade entry line.

Reads historical_earnings to calculate P/E and PEG.

"Add to Watchlist" Button:

Updates a stock's row in the watchlist table (sets status to "WL-Active", saves trade data).

Deletes/Creates a row in the stock_price_levels table (to set the new single entry price).

"Remove" Button:

Updates the watchlist row, setting status to "Pending" and trade data to NULL.

5. Agent Module Interaction (market_agent.py)
This describes the logic of the standalone 24/7 script.

SENS Check (Runs 7:00 - 17:30, Mon-Fri):

Fetches the SENS page.

Fetches its clean ticker list from stock_details (e.g., {'KAP', 'CCC'}).

Loops through SENS. If a match is found (e.g., KAP):

Adds .JO suffix back (KAP.JO).

Checks if this SENS already exists in the SENS table.

If NO, it saves the full content to the SENS table.

After saving, it triggers the AI Brain: analysis_engine.analyze_new_sens('KAP.JO', sens_content).

EOD Price Check (Runs once after 17:30, Mon-Fri):

Fetches all tickers with suffixes from stock_details (e.g., KAP.JO).

Downloads all EOD price data from yfinance.

Saves/updates all data in the daily_stock_data table.

Logs the update in the price_update_log table.

(Future AI Trigger): It will then loop through the new prices, check them against the stock_analysis.price_levels array, and call analysis_engine.analyze_price_change() if any research level is hit.

AI Brain (analysis_engine.py):

When triggered by the agent, it reads the user's research from stock_analysis, builds a prompt, gets an AI insight, and saves that insight as a new row in the action_log table.