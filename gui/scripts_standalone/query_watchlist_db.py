"""Standalone DB diagnostic for why a ticker is missing from the GUI watchlist.

Usage:
  python gui/scripts_standalone/query_watchlist_db.py --ticker CSB.JO

This script connects using `core.config.DB_CONFIG` (same config as the GUI) and
checks:
- whether a matching row exists in `watchlist`
- whether it is excluded by the GUI filter (status = 'WL-Sleep')
- what ticker variants exist (with/without .JO)
- whether `stock_details` contains the ticker

Notes:
- Does NOT print DB credentials.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import os
import sys

import asyncpg

# Ensure imports work when running from repo root.
GUI_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if GUI_ROOT not in sys.path:
    sys.path.insert(0, GUI_ROOT)

from core.config import DB_CONFIG


@dataclass(frozen=True)
class TickerCheck:
    label: str
    ticker: str


def _normalize_input_ticker(raw: str) -> str:
    return (raw or "").strip()


def _candidate_tickers(ticker: str) -> list[TickerCheck]:
    t = _normalize_input_ticker(ticker)
    if not t:
        return []

    t_upper = t.upper()
    base = t_upper[:-3] if t_upper.endswith(".JO") else t_upper
    with_suffix = t_upper if t_upper.endswith(".JO") else f"{t_upper}.JO"

    # Keep order deterministic and deduplicate.
    candidates: list[TickerCheck] = [
        TickerCheck("as_entered", t),
        TickerCheck("upper", t_upper),
        TickerCheck("base_no_suffix", base),
        TickerCheck("with_.JO", with_suffix),
    ]

    seen: set[str] = set()
    out: list[TickerCheck] = []
    for c in candidates:
        key = c.ticker.strip().upper()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(TickerCheck(c.label, c.ticker.strip()))
    return out


async def _fetch_one(conn: asyncpg.Connection, query: str, *args):
    return await conn.fetchrow(query, *args)


async def _fetch_all(conn: asyncpg.Connection, query: str, *args):
    return await conn.fetch(query, *args)


def _print_rows(title: str, rows) -> None:
    print("\n" + title)
    print("-" * len(title))
    if not rows:
        print("(none)")
        return
    for r in rows:
        # asyncpg Record prints ok, but format explicitly for readability.
        print(dict(r))


async def run(ticker: str) -> int:
    candidates = _candidate_tickers(ticker)
    if not candidates:
        print("ERROR: --ticker is required")
        return 2

    conn: asyncpg.Connection | None = None
    try:
        conn = await asyncpg.connect(
            host=DB_CONFIG["host"],
            database=DB_CONFIG["dbname"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
        )

        # 1) Exact matches in watchlist and stock_details
        for c in candidates:
            row_w = await _fetch_one(
                conn,
                """
                SELECT ticker, status, date_added, entry_price, stop_loss, target_price
                FROM watchlist
                WHERE UPPER(ticker) = UPPER($1)
                """,
                c.ticker,
            )
            row_sd = await _fetch_one(
                conn,
                """
                SELECT ticker, full_name, priority
                FROM stock_details
                WHERE UPPER(ticker) = UPPER($1)
                """,
                c.ticker,
            )

            print(f"\n== Candidate: {c.label}: {c.ticker} ==")
            print("watchlist:", dict(row_w) if row_w else None)
            print("stock_details:", dict(row_sd) if row_sd else None)
            if row_w and str(row_w.get("status") or "").strip() == "WL-Sleep":
                print("NOTE: This row is filtered out by the GUI (status 'WL-Sleep').")

        # 2) Partial matches (helps spot whether DB stores base ticker without .JO)
        base = candidates[0].ticker.upper()
        base = base[:-3] if base.endswith(".JO") else base
        like = f"%{base}%"

        rows_like = await _fetch_all(
            conn,
            """
            SELECT ticker, status, date_added
            FROM watchlist
            WHERE ticker ILIKE $1
            ORDER BY ticker
            """,
            like,
        )
        _print_rows(f"watchlist partial matches (ticker ILIKE '{like}')", rows_like)

        rows_sd_like = await _fetch_all(
            conn,
            """
            SELECT ticker, full_name, priority
            FROM stock_details
            WHERE ticker ILIKE $1
            ORDER BY ticker
            """,
            like,
        )
        _print_rows(f"stock_details partial matches (ticker ILIKE '{like}')", rows_sd_like)

        # 3) Replicate the GUI inclusion filter for the best candidate.
        # The GUI query effectively includes tickers where status NOT IN ('WL-Sleep')
        # and where an inner join to stock_details exists.
        best = candidates[-1].ticker  # 'with_.JO' tends to be most expected
        gui_row = await _fetch_one(
            conn,
            """
            SELECT w.ticker, w.status, sd.full_name
            FROM watchlist w
            JOIN stock_details sd ON w.ticker = sd.ticker
            WHERE UPPER(w.ticker) = UPPER($1)
              AND w.status NOT IN ('WL-Sleep')
            """,
            best,
        )
        print(f"\nGUI-inclusion check for {best}:")
        print(dict(gui_row) if gui_row else None)

        print("\nDone.")
        return 0

    except Exception as e:
        print("ERROR:", e)
        return 1
    finally:
        if conn is not None:
            try:
                await conn.close()
            except Exception:
                pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True, help="Ticker to check (e.g. CSB.JO or CSB)")
    args = parser.parse_args()
    return asyncio.run(run(args.ticker))


if __name__ == "__main__":
    raise SystemExit(main())
