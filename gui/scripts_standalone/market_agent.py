import asyncio
import sys
import os
import logging
from logging import FileHandler

# Configure logging for the market_agent subprocess separately. We prefer
# using the environment variable LOG_LEVEL to allow users to control verbosity
# just like the GUI process.
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(name)s %(levelname)s: %(message)s")

# Persistent per-subprocess log file: gui/logs/market_agent.log
LOG_DIR = os.environ.get("LOG_DIR", os.path.join(os.path.dirname(__file__), "..", "logs"))
LOG_DIR = os.path.abspath(LOG_DIR)
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "market_agent.log")

# Attach a file handler so logs persist across restarts
file_handler = FileHandler(LOG_FILE, mode="a", encoding="utf-8")
file_handler.setLevel(LOG_LEVEL)
file_handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s: %(message)s"))
logging.getLogger().addHandler(file_handler)

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from modules.market_agent.agent import run_market_agent

if __name__ == "__main__":
    asyncio.run(run_market_agent())
