from __future__ import annotations
import os
import asyncio
from pathlib import Path
from datetime import datetime
from scripts_standalone.results_scraper.utils import sanitize_ticker
from scripts.generate_deepresearch_from_results import run as run_deepresearch

async def process_sens_for_deepresearch(ticker: str, content: str) -> bool:
    """
    Saves the SENS content to the results folder for the ticker and 
    triggers the deep research generation script.
    """
    if not ticker or not content:
        return False

    # 1. Determine the results directory
    # Based on generate_deepresearch_from_results.py's GUI_ROOT / "results"
    repo_root = Path(__file__).resolve().parents[2]
    results_root = repo_root / "results"
    
    canon_ticker = sanitize_ticker(ticker)
    ticker_dir = results_root / canon_ticker
    ticker_dir.mkdir(parents=True, exist_ok=True)

    # 2. Save the content to a .txt file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Take the first line of content as a filename hint if possible, but keep it safe
    first_line = content.strip().split("\n")[0]
    safe_name = "".join(c for c in first_line[:50] if c.isalnum() or c in (" ", "_")).strip().replace(" ", "_")
    filename = f"{timestamp}_{safe_name}.txt"
    file_path = ticker_dir / filename

    try:
        file_path.write_text(content, encoding="utf-8")
    except Exception as e:
        print(f"Failed to write SENS content to {file_path}: {e}")
        return False

    # 3. Trigger deep research generation for this ticker
    # We call the run function from generate_deepresearch_from_results.py
    try:
        # ticker: str | None, limit: int | None, dry_run: bool, max_chars: int | None
        await run_deepresearch(ticker=ticker, limit=None, dry_run=False, max_chars=200_000)
    except Exception as e:
        print(f"Failed to trigger deep research for {ticker}: {e}")
        return False

    return True
