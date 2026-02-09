"""
Populate results_downloads table with existing PDF files in results/ directory.

Usage:
    python -m scripts_standalone.results_scraper.populate_results_downloads [--dry-run]
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

from .db import record_results_download
from .utils import extract_pdf_creation_date, sanitize_ticker


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _get_gui_index_for_relative_path(full_path: Path) -> Path:
    """Convert an absolute path to a path relative to gui/ directory.
    
    Example:
        /path/to/gui/results/NPN/20251201.pdf -> results/NPN/20251201.pdf
    """
    try:
        # Try to find the gui directory in the path
        parts = full_path.parts
        if "gui" in parts:
            gui_idx = parts.index("gui")
            return Path(*parts[gui_idx + 1 :])
    except Exception:
        pass
    return full_path


async def populate_results_downloads(results_root: Path, dry_run: bool = False) -> None:
    """Scan results directory and populate results_downloads table."""
    if not results_root.exists():
        logger.error("Results directory not found: %s", results_root)
        return

    logger.info("Scanning results directory: %s", results_root)

    processed = 0
    skipped = 0
    failed = 0

    # Scan ticker subdirectories
    for ticker_dir in sorted(results_root.iterdir()):
        if not ticker_dir.is_dir():
            continue

        ticker = ticker_dir.name
        logger.info("Processing ticker: %s", ticker)

        # Find all PDFs in this ticker directory
        pdf_files = sorted(ticker_dir.glob("*.pdf"))
        if not pdf_files:
            logger.debug("  No PDFs found in %s", ticker_dir)
            continue

        for pdf_path in pdf_files:
            try:
                # Read PDF bytes
                data = pdf_path.read_bytes()
                if not data.startswith(b"%PDF"):
                    logger.warning("  Skipping %s (not a valid PDF)", pdf_path.name)
                    skipped += 1
                    continue

                # Try to extract creation date from PDF metadata
                release_date = None
                try:
                    dt = extract_pdf_creation_date(data)
                    if dt:
                        release_date = dt.date()
                except Exception as ex:
                    logger.debug("  Could not extract date from %s: %s", pdf_path.name, ex)

                # Record in database (unless dry-run)
                relative_path = _get_gui_index_for_relative_path(pdf_path)
                
                if dry_run:
                    logger.info(
                        "  [DRY-RUN] Would record: ticker=%s, path=%s, release_date=%s",
                        ticker,
                        relative_path,
                        release_date,
                    )
                    processed += 1
                else:
                    success = await record_results_download(
                        ticker=ticker,
                        release_date=release_date,
                        pdf_path=relative_path,
                        pdf_url=None,
                        source="ost",
                        data=data,
                    )
                    if success:
                        logger.info(
                            "  Recorded: %s (%s)",
                            ticker,
                            relative_path.name,
                        )
                        processed += 1
                    else:
                        logger.error("  Failed to record: %s (%s)", ticker, relative_path.name)
                        failed += 1

            except Exception as ex:
                logger.exception("  Error processing %s: %s", pdf_path.name, ex)
                failed += 1

    logger.info(
        "Population complete. Processed: %d, Skipped: %d, Failed: %d",
        processed,
        skipped,
        failed,
    )


async def main():
    """Main entry point."""
    dry_run = "--dry-run" in sys.argv or "-n" in sys.argv

    if dry_run:
        logger.info("Running in DRY-RUN mode (no database changes)")

    # Find results directory - try multiple strategies
    cwd = Path.cwd()
    
    # Strategy 1: If cwd ends with 'gui/', use it directly
    if cwd.name == "gui":
        gui_dir = cwd
    # Strategy 2: If cwd is the gui folder or a subfolder, find gui in the path
    elif "gui" in cwd.parts:
        gui_idx = cwd.parts.index("gui")
        gui_dir = Path(*cwd.parts[:gui_idx + 1])
    else:
        # Strategy 3: Use relative path from script location
        script_dir = Path(__file__).parent  # results_scraper/
        gui_dir = script_dir.parent.parent.parent  # up to gui/
    
    results_root = gui_dir / "results"

    logger.info("Current directory: %s", cwd)
    logger.info("GUI directory: %s", gui_dir)
    logger.info("Results directory: %s", results_root)

    await populate_results_downloads(results_root, dry_run=dry_run)


if __name__ == "__main__":
    asyncio.run(main())
