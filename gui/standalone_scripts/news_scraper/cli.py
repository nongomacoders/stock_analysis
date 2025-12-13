from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from standalone_scripts.results_scraper.env import load_credentials
from standalone_scripts.results_scraper.paths import compute_paths

from .runner import run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Open a visible browser to the OST site and navigate to the News page for each ticker.",
    )
    parser.add_argument(
        "--ticker",
        default=None,
        help="Ticker to enter into the markIdTextBox (default: run on all watchlist tickers missing deepresearch)",
    )
    parser.add_argument("--list-only", action="store_true", help="Only list the tickers that would be processed and exit")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit the number of tickers to process (for testing) - pass an integer",
    )
    parser.add_argument(
        "--max-news",
        type=int,
        default=None,
        help="Maximum number of news articles to download per ticker (after filtering by results_release_date)",
    )
    return parser


def _ensure_gui_root_on_syspath() -> None:
    gui_root = Path(__file__).resolve().parents[2]
    if str(gui_root) not in sys.path:
        sys.path.insert(0, str(gui_root))


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO)
    _ensure_gui_root_on_syspath()

    paths = compute_paths()
    creds = load_credentials(paths.script_dir)

    args = build_parser().parse_args(argv)

    return asyncio.run(
        run(
            ticker=args.ticker,
            list_only=args.list_only,
            limit=args.limit,
            max_news=args.max_news,
            creds=creds,
            paths=paths,
        )
    )
