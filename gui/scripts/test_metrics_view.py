import asyncio
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from modules.data.metrics import get_stock_metrics

async def test_metrics():
    ticker = "ABG.JO"
    print(f"Testing metrics for {ticker}...")
    metrics = await get_stock_metrics(ticker)
    if metrics:
        print("Metrics found:")
        for key, value in metrics.items():
            print(f"  {key}: {value}")
    else:
        print("No metrics found.")

if __name__ == "__main__":
    asyncio.run(test_metrics())
