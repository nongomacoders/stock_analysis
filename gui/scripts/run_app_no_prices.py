"""
Run the GUI application without starting the market agent (so no price/commodity/FX/fundamentals/SENS checks run on startup).

Usage:
    python gui/scripts/run_app_no_prices.py

This script sets the environment variable AUTO_START_AGENT=0 before importing the main GUI module
so the GUI will not auto-start the market agent subprocess.
"""

import os
import sys

# Ensure we set this BEFORE importing the GUI so the main module picks up the flag
os.environ["AUTO_START_AGENT"] = os.environ.get("AUTO_START_AGENT", "0")

# Append project root so imports work when run from repository root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.main import CommandCenter

if __name__ == "__main__":
    # Run the application normally; closing behavior is handled by CommandCenter
    app = CommandCenter()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
