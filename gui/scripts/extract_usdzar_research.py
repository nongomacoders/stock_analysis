#!/usr/bin/env python3
"""Extract context lines around 'USDZAR' / 'USD ZAR' occurrences in
the stock_analysis.epp_research column and write results to a text file.

Usage:
  python scripts/extract_usdzar_research.py [--out OUTPUT] [--context N]

By default writes to 'out_usdzar_excerpts.txt' in the current directory
and extracts 3 lines above/below each match.
"""
import argparse
import asyncio
import os
import re
import sys
from datetime import datetime

# Make the repo's gui package importable when run from project root
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.db.engine import DBEngine


PATTERN = re.compile(r"usd", flags=re.IGNORECASE)


async def fetch_rows():
    q = """
    SELECT ticker, deepresearch
    FROM stock_analysis
    WHERE deepresearch ILIKE '%usd%'
    """
    rows = await DBEngine.fetch(q)
    return rows


def extract_context(text: str, context: int = 3):
    """Return a list of excerpts. Each excerpt is a (match_line_idx, start, end, lines)
    where lines is the list of lines extracted (start <= idx < end).
    """
    if not text:
        return []

    lines = text.splitlines()
    results = []

    for i, line in enumerate(lines):
        if PATTERN.search(line):
            start = max(0, i - context)
            end = min(len(lines), i + context + 1)
            excerpt = lines[start:end]
            results.append((i, start, end, excerpt))

    return results


async def run(output_path: str, context: int):
    rows = await fetch_rows()

    if not rows:
        print("No matches found in stock_analysis.epp_research")
        return 0

    with open(output_path, 'w', encoding='utf-8') as fh:
        fh.write(f"Extract run: {datetime.utcnow().isoformat()}Z\n")
        fh.write("Search pattern: USD (substring match)\n\n")

        total = 0
        for r in rows:
            # asyncpg returns Record objects - behave like dict
            ticker = r.get('ticker') if isinstance(r, dict) else r['ticker']
            # asyncpg Record supports dict-like access; column name is `deepresearch` in DB
            try:
                text = r.get('deepresearch') if isinstance(r, dict) else r['deepresearch']
            except Exception:
                # Fallback to checking alternative keys
                text = r.get('deep_research') if isinstance(r, dict) else r.get('deep_research', None)
            if not text:
                continue
            excerpts = extract_context(str(text), context=context)
            if not excerpts:
                continue

            fh.write(f"--- Ticker: {ticker}  (excerpts: {len(excerpts)})\n")
            for match_idx, start, end, chunk in excerpts:
                fh.write(f"[lines {start+1}-{end}] matched at line {match_idx+1}\n")
                for li, ln in enumerate(chunk, start=start+1):
                    fh.write(f"{li:5d}: {ln}\n")
                fh.write("\n")
                total += 1

        fh.write(f"\nTotal excerpts: {total}\n")

    print(f"Wrote {output_path} with {total} excerpts from {len(rows)} rows checked.")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Extract USD excerpts from stock_analysis.deepresearch")
    parser.add_argument('--out', '-o', default='out_usd_excerpts.txt', help='Output file')
    parser.add_argument('--context', '-c', default=3, type=int, help='Lines of context above/below match')

    args = parser.parse_args(argv)

    try:
        asyncio.run(run(args.out, args.context))
    except Exception as e:
        print('Fatal error:', e)
        return 2

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
