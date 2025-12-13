from __future__ import annotations

import argparse
import asyncio
import logging

from .bootstrap import ensure_gui_root_on_syspath
from .env import load_credentials
from .paths import compute_paths
from .runner import run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Open a visible browser to the OST site and download Results Summaries PDFs.",
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
        "--debug-values",
        action="store_true",
        help="When combined with --list-only, show deepresearch values for each ticker",
    )
    parser.add_argument(
        "--manual-pdf-url",
        action="store_true",
        help="Do not download PDFs. Instead open the first PDF in a new tab and print its URL; close the tab to continue.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO)

    paths = compute_paths()
    ensure_gui_root_on_syspath()

    creds = load_credentials(paths.script_dir)

    args = build_parser().parse_args(argv)

    return asyncio.run(
        run(
            ticker=args.ticker,
            list_only=args.list_only,
            limit=args.limit,
            debug_values=args.debug_values,
            manual_pdf_url=args.manual_pdf_url,
            creds=creds,
            paths=paths,
        )
    )
