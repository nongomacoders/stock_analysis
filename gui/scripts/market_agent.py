import asyncio
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from modules.market_agent.agent import run_market_agent

if __name__ == "__main__":
    asyncio.run(run_market_agent())
