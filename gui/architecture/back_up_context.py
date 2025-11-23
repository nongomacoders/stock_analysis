📋 Context Restoration: JSE Command Center
1. Our Roles & Workflow

Me (User): Project Lead.

You (Gemini): The Architect/Staff Engineer. You design the architecture and generate "Mission Prompts".

Google Antigravity: The IDE/Agent. I paste your Mission Prompts into Antigravity, and it writes the actual code.

2. Project Overview

App Name: JSE Command Center (Financial Analysis Dashboard).

Tech Stack: Python, ttkbootstrap (Tkinter), PostgreSQL (psycopg2), yfinance.

Database: Existing PostgreSQL DB (jse_stock_data) with tables: watchlist, stock_details, daily_stock_data, stock_analysis, action_log, portfolio_holdings.

Current Directory: gui/ (Building a modular UI structure).

3. Current Architecture We are building a modular application to keep files under 300 lines.

gui/main.py: Entry point.

gui/db_layer.py: Data Access Object (using DictCursor).

gui/utils.py: Helpers for date calculation (calculate_days_to_event) and status logic.

gui/components/watchlist.py: The main grid widget.

4. Current Design Decisions (The "Monitoring" Context)

Theme: Light Mode (cosmo).

Visual Logic:

Row Colors (Backgrounds):

Portfolio: #d1e7dd (Mint)

WL-Active: #fff3cd (Wheat)

Pre-Trade: #f8f9fa (Light Grey)

Text: Black text for readability.

Ticker Truncation: Ticker names limited to 10 chars.

Data Filtering: Watchlist excludes Closed, Pending, and WL-Sleep.