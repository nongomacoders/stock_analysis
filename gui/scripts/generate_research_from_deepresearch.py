"""Generate 'research' from existing 'deepresearch' rows.

Workflow:
- Find tickers in stock_analysis that have deepresearch but do not yet have research.
- For each ticker:
  - Build a research extraction prompt using modules.analysis.prompts.build_research_prompt(deepresearch).
  - Send to the LLM via modules.analysis.llm.query_ai.
  - Save into stock_analysis.research via modules.data.research.save_research_data.

Examples (repo root):
  python gui/scripts/generate_research_from_deepresearch.py --dry-run --limit 5
  python gui/scripts/generate_research_from_deepresearch.py --ticker ACL.JO --dry-run
  python gui/scripts/generate_research_from_deepresearch.py --limit 10

Notes:
- Requires DB access (core.db.engine.DBEngine) and GOOGLE_API_KEY for Gemini.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file (now in project root)
load_dotenv()

def _ensure_repo_root_on_syspath() -> Path:
    """Allow running from either repo root or gui/ directory."""
    this_file = Path(__file__).resolve()
    gui_root = this_file.parents[1]
    repo_root = gui_root.parent

    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    if str(gui_root) not in sys.path:
        sys.path.insert(0, str(gui_root))

    return gui_root


GUI_ROOT = _ensure_repo_root_on_syspath()


async def _fetch_tickers_to_process(*, ticker: str | None, limit: int | None) -> list[dict]:
    """Return rows: {ticker, deepresearch}."""

    from core.db.engine import DBEngine

    if ticker:
        q = """
            SELECT ticker, deepresearch
            FROM stock_analysis
            WHERE ticker = $1
              AND deepresearch IS NOT NULL
              AND BTRIM(deepresearch) <> ''
              AND deepresearch <> 'No data available.'
              AND (research IS NULL OR BTRIM(research) = '')
            LIMIT 1
        """
        rows = await DBEngine.fetch(q, ticker)
        return [dict(r) for r in rows]

    q = """
        SELECT ticker, deepresearch
        FROM stock_analysis
        WHERE deepresearch IS NOT NULL
          AND BTRIM(deepresearch) <> ''
          AND deepresearch <> 'No data available.'
          AND (research IS NULL OR BTRIM(research) = '')
        ORDER BY ticker
    """
    if limit is not None:
        q += "\nLIMIT $1"
        rows = await DBEngine.fetch(q, limit)
    else:
        rows = await DBEngine.fetch(q)

    return [dict(r) for r in rows]


async def run(*, ticker: str | None, limit: int | None, dry_run: bool) -> int:
    from modules.analysis.selector import managed_query_ai
    from modules.analysis.prompts import build_research_prompt
    from modules.data.research import save_research_data

    logger = logging.getLogger(__name__)

    rows = await _fetch_tickers_to_process(ticker=ticker, limit=limit)
    if not rows:
        logger.info("No tickers found needing research")
        return 0

    logger.info("Processing %d ticker(s)", len(rows))

    for row in rows:
        t = (row.get("ticker") or "").strip()
        deep = row.get("deepresearch") or ""
        if not t or not deep.strip():
            continue

        logger.info("\n=== %s ===", t)

        prompt = build_research_prompt(deep)

        if dry_run:
            logger.info("Dry-run: would send %d chars to LLM", len(prompt))
            continue

        response = await managed_query_ai("research_extraction", prompt)
        if not response or response.strip().lower().startswith("error generating ai response"):
            logger.warning("LLM returned an error-like response for %s", t)
            continue

        try:
            await save_research_data(t, response)
            logger.info("Saved research for %s (len=%d)", t, len(response))
        except Exception:
            logger.exception("Failed to save research for %s", t)

        await asyncio.sleep(1)

    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(
        description="Generate stock_analysis.research for tickers that have deepresearch but no research",
    )
    parser.add_argument("--ticker", default=None, help="Process a single ticker (must exist in stock_analysis)")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of tickers (when --ticker not provided)")
    parser.add_argument("--dry-run", action="store_true", help="Build prompts but do not call the LLM or save to DB")

    args = parser.parse_args(argv)
    return asyncio.run(run(ticker=args.ticker, limit=args.limit, dry_run=args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
