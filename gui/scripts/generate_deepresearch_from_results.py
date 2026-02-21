"""Generate deep research for tickers missing deepresearch.

Workflow:
- Resolve watchlist tickers that have no deepresearch.
- For each ticker:
  - Load all extracted announcement text files from gui/results/<TICKER>/.
  - Fetch latest close price from daily_stock_data.
  - Choose an "appropriate" prompt from gui/prompts based on the stock category.
  - Submit to the LLM (modules.analysis.llm.query_ai).
  - Save response into stock_analysis.deepresearch (and deepresearch_date).

Run examples (from repo root):
  python gui/scripts/generate_deepresearch_from_results.py --dry-run --limit 3
  python gui/scripts/generate_deepresearch_from_results.py --ticker ***.JO
  python gui/scripts/generate_deepresearch_from_results.py --limit 10

Notes:
- Requires DB access (core.db.engine.DBEngine) and GOOGLE_API_KEY for Gemini.
- Expects per-ticker folders under gui/results/ like gui/results/NPN/.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import sys
import time
import os
from datetime import date
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file (now in project root)
load_dotenv()

def _ensure_repo_root_on_syspath() -> Path:
    """Allow running from either repo root or gui/ directory."""
    this_file = Path(__file__).resolve()
    gui_root = this_file.parents[1]
    repo_root = gui_root.parent

    # Ensure both repo root and gui root are importable.
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    if str(gui_root) not in sys.path:
        sys.path.insert(0, str(gui_root))

    return gui_root


# Ensure imports work even when running from repo root.
GUI_ROOT = _ensure_repo_root_on_syspath()


def _normalize_category(value: str) -> str:
    v = (value or "").strip().lower()
    v = v.replace("&", "and")
    for ch in "()[]{}.,;:/\\|\"'`":
        v = v.replace(ch, " ")
    v = "_".join([p for p in v.split() if p])
    v = v.replace("__", "_")
    return v.strip("_")


def _select_prompt_file(prompts_dir: Path, category: str | None) -> Path:
    """Pick a prompt file from prompts_dir.

    Heuristic:
    - Normalize category, compare to prompt stems (minus _prompt).
    - Prefer exact match, then substring match.
    - Fallback to sa_inc_mid_small_prompt.txt.
    """

    prompt_files = sorted([p for p in prompts_dir.iterdir() if p.is_file() and p.suffix.lower() == ".txt"])
    if not prompt_files:
        raise FileNotFoundError(f"No prompt .txt files found in {prompts_dir}")

    fallback = prompts_dir / "sa_inc_mid_small_prompt.txt"
    if not category:
        return fallback if fallback.exists() else prompt_files[0]

    cat_norm = _normalize_category(category)

    def _variants(s: str) -> set[str]:
        out = {s}
        if s.endswith("y") and len(s) > 1:
            out.add(s[:-1] + "ies")
        if s.endswith("ies") and len(s) > 3:
            out.add(s[:-3] + "y")
        if s.endswith("s") and len(s) > 1:
            out.add(s[:-1])
        return {v for v in out if v}

    def stem_norm(p: Path) -> str:
        s = p.stem
        if s.lower().endswith("_prompt"):
            s = s[: -len("_prompt")]
        return _normalize_category(s)

    norms = {p: stem_norm(p) for p in prompt_files}

    # Exact
    for p, n in norms.items():
        if n == cat_norm:
            return p

    # Substring (either direction), with basic singular/plural variants.
    cat_vars = _variants(cat_norm)
    for p, n in norms.items():
        n_vars = _variants(n)
        for cv in cat_vars:
            for nv in n_vars:
                if cv and nv and (cv in nv or nv in cv):
                    return p

    return fallback if fallback.exists() else prompt_files[0]


async def _fetch_latest_close_price(ticker: str) -> float | None:
    from core.db.engine import DBEngine

    q = """
        SELECT close_price
        FROM daily_stock_data
        WHERE ticker = $1
          AND trade_date = (SELECT max(trade_date) FROM daily_stock_data WHERE ticker = $1)
        LIMIT 1
    """
    rows = await DBEngine.fetch(q, ticker)
    if not rows:
        return None
    r0 = rows[0]
    try:
        v = r0.get("close_price") if hasattr(r0, "get") else r0["close_price"]
    except Exception:
        v = None
    try:
        return float(v) if v is not None else None
    except Exception:
        return None


async def _fetch_category_name(ticker: str) -> str | None:
    # Reuse the app's helper.
    try:
        from modules.data.research import get_stock_category

        return await get_stock_category(ticker)
    except Exception:
        return None


async def _fetch_existing_deepresearch(ticker: str) -> str | None:
    """Return the current deepresearch text for *ticker*, or None."""
    from core.db.engine import DBEngine

    q = """
        SELECT deepresearch
        FROM stock_analysis
        WHERE ticker = $1
          AND deepresearch IS NOT NULL
          AND BTRIM(deepresearch) <> ''
        LIMIT 1
    """
    rows = await DBEngine.fetch(q, ticker)
    if not rows:
        return None
    val = rows[0].get("deepresearch") if hasattr(rows[0], "get") else rows[0]["deepresearch"]
    return val if val and str(val).strip() else None


async def _fetch_last_results_date(ticker: str):
    """Return the most recent results_release_date for *ticker*, or None."""
    from core.db.engine import DBEngine

    q = """
        SELECT results_release_date
        FROM raw_stock_valuations
        WHERE ticker = $1
        ORDER BY results_release_date DESC
        LIMIT 1
    """
    rows = await DBEngine.fetch(q, ticker)
    if not rows:
        return None
    return rows[0].get("results_release_date") if hasattr(rows[0], "get") else rows[0]["results_release_date"]


async def _fetch_commodity_fx_averages(
    since_date,
) -> tuple[list[tuple[str, float, int]], list[tuple[str, float, int]]]:
    """Fetch per-commodity and per-FX averages since *since_date*.

    Returns (commodity_avgs, fx_avgs) where each is a list of (name, avg, count).
    Mirrors the logic in engine.estimate_spot_price.
    """
    from core.db.engine import DBEngine

    commodity_avgs: list[tuple[str, float, int]] = []
    fx_avgs: list[tuple[str, float, int]] = []

    q1 = """
        SELECT commodity, AVG(price) AS avg_price, COUNT(*) AS cnt
        FROM commodity_prices
        WHERE collected_ts >= $1
        GROUP BY commodity
        ORDER BY cnt DESC
    """
    rows1 = await DBEngine.fetch(q1, since_date)
    for r in (rows1 or []):
        try:
            commodity_avgs.append((r["commodity"], float(r["avg_price"]), int(r["cnt"])))
        except Exception:
            continue

    q2 = """
        SELECT pair, AVG(rate) AS avg_rate, COUNT(*) AS cnt
        FROM fx_rates
        WHERE collected_ts >= $1
        GROUP BY pair
        ORDER BY cnt DESC
    """
    rows2 = await DBEngine.fetch(q2, since_date)
    for r in (rows2 or []):
        try:
            fx_avgs.append((r["pair"], float(r["avg_rate"]), int(r["cnt"])))
        except Exception:
            continue

    return commodity_avgs, fx_avgs


def _load_results_text(results_root: Path, canon_ticker: str, *, max_chars: int | None) -> tuple[str, list[Path]]:
    ticker_dir = results_root / canon_ticker
    if not ticker_dir.exists():
        return "", []

    files = sorted([p for p in ticker_dir.glob("*.txt") if p.is_file()])
    if not files:
        return "", []

    parts: list[str] = []
    used: list[Path] = []
    total = 0

    for p in files:
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        chunk = f"\n\n===== FILE: {p.name} =====\n\n{txt.strip()}\n"
        if max_chars is not None and (total + len(chunk)) > max_chars:
            break

        parts.append(chunk)
        used.append(p)
        total += len(chunk)

    return "".join(parts).strip() + "\n", used


def _find_result_pdfs(results_root: Path, canon_ticker: str) -> list[Path]:
    ticker_dir = results_root / canon_ticker
    if not ticker_dir.exists():
        return []
    return sorted([p for p in ticker_dir.glob("*.pdf") if p.is_file()])


def _gemini_file_name_slug(value: str) -> str:
    """Create a Gemini file resource name slug.

    Constraint from API error:
    - lowercase alphanumeric or dashes
    - cannot begin or end with a dash
    """

    raw = (value or "").strip().lower()
    out: list[str] = []
    prev_dash = False
    for ch in raw:
        if ch.isalnum():
            out.append(ch)
            prev_dash = False
        else:
            if not prev_dash:
                out.append("-")
                prev_dash = True
    slug = "".join(out).strip("-")
    return slug or "file"


def _gemini_resource_name(raw: str, *, max_len: int = 40, fallback_prefix: str = "file") -> str:
    """Return a Gemini Files API resource name (File ID) within the API constraints.

    Constraint (from API error): file name (ID, excluding 'files/') must be <= 40 chars.
    Also must be lowercase alphanumeric or dashes, and cannot start/end with a dash.
    """

    slug = _gemini_file_name_slug(raw)
    if len(slug) <= max_len:
        return slug

    # Keep stable uniqueness while staying short.
    digest = hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:12]
    prefix = _gemini_file_name_slug(fallback_prefix)[: max(1, max_len - (1 + len(digest)))]
    out = f"{prefix}-{digest}".strip("-")
    return out[:max_len].strip("-") or digest


def _build_llm_prompt(
    prompt_template: str,
    *,
    ticker: str,
    price: float | None,
    payload: str,
    previous_report: str | None = None,
    commodity_avgs: list[tuple[str, float, int]] | None = None,
    fx_avgs: list[tuple[str, float, int]] | None = None,
    results_date: str | None = None,
) -> str:
    today = date.today().isoformat()
    # DB stores close_price in ZAR cents (ZARc). Convert to ZAR for the model.
    price_zar = None if price is None else (float(price) / 100.0)
    price_str = "UNKNOWN" if price_zar is None else f"{price_zar:.2f}"

    # Some prompts include placeholders like [Insert Price]; best-effort fill.
    txt = prompt_template
    txt = txt.replace("<today's date>", today)
    txt = txt.replace("[Insert Price]", price_str)

    # Optional: include previous deep research report for change comparison.
    prev_block = ""
    if previous_report:
        prev_block = (
            "\n\n[PREVIOUS DEEP RESEARCH REPORT]\n"
            + previous_report.strip()
            + "\n[END PREVIOUS REPORT]\n\n"
            + "IMPORTANT: Your response MUST include a section titled \"## Summary of Changes\"\n"
            + "at the end that summarises the key differences between this new report and the\n"
            + "previous report above. Highlight changes in financials, outlook, risks, and any\n"
            + "new developments.\n"
        )

    # Optional: inject commodity and FX average prices.
    commodity_block = ""
    if commodity_avgs or fx_avgs:
        parts: list[str] = ["\n[CURRENT COMMODITY PRICES]"]
        if results_date:
            parts.append(f"Average prices since last reporting period ({results_date}):")
        else:
            parts.append("Recent average commodity prices:")
        if commodity_avgs:
            for c, avg, cnt in commodity_avgs[:10]:
                parts.append(f"  {c}: {avg:.2f} (samples={cnt})")
        if fx_avgs:
            parts.append("FX rates (averages):")
            for p, avg, cnt in fx_avgs[:10]:
                parts.append(f"  {p}: {avg:.4f} (samples={cnt})")
        parts.append("[END COMMODITY PRICES]")
        parts.append("")
        parts.append(
            "IMPORTANT: Use the commodity prices and FX rates above for your HEPS equation "
            "and valuation calculations. Do NOT use hypothetical or web-searched prices."
        )
        commodity_block = "\n".join(parts)

    # Provide a consistent preamble, then include payload.
    return (
        txt.rstrip()
        + prev_block
        + commodity_block
        + "\n\n"
        + f"TICKER: {ticker}\n"
        + f"LATEST CLOSE PRICE (ZAR): {price_str}\n"
        + ("" if price is None else f"LATEST CLOSE PRICE (ZARc): {int(price)}\n")
        + "\n"
        + "[PASTE RESULTS / SENS ANNOUNCEMENTS BELOW THIS LINE]\n"
        + payload.strip()
        + "\n"
    )


def _query_ai_with_pdfs(*, prompt: str, pdf_paths: list[Path], display_name_prefix: str) -> str:
    """Generate content using Gemini's file_search tool over uploaded PDFs.

    Uses google-genai (google.genai) because it supports FileSearchStore + citations.
    """

    from google import genai
    from google.genai import types

    client = genai.Client()

    store = client.file_search_stores.create(
        config={"display_name": f"{display_name_prefix}-pdf-store"}
    )

    store_name = getattr(store, "name", None)
    if not store_name:
        raise RuntimeError("Failed to create file search store (missing name)")

    operations = []
    uploaded_file_names: list[str] = []

    for pdf_path in pdf_paths:
        # Resource name must be a slug; display_name can be the real filename for citations.
        resource_name = _gemini_resource_name(
            f"{display_name_prefix}-{pdf_path.stem}",
            max_len=40,
            fallback_prefix=display_name_prefix,
        )
        uploaded = client.files.upload(
            file=str(pdf_path),
            config={
                "name": resource_name,
                "display_name": pdf_path.name,
            },
        )
        uploaded_name = getattr(uploaded, "name", None)
        if not uploaded_name:
            raise RuntimeError(f"Failed to upload {pdf_path.name} (missing uploaded file name)")

        uploaded_file_names.append(uploaded_name)

        op = client.file_search_stores.import_file(
            file_search_store_name=store_name,
            file_name=uploaded_name,
        )
        operations.append(op)

    # Wait for all imports to finish (bounded).
    deadline = time.time() + 10 * 60
    for op in operations:
        while not op.done:
            if time.time() > deadline:
                raise TimeoutError("Timed out waiting for PDF import into file search store")
            time.sleep(5)
            op = client.operations.get(op)

    response = client.models.generate_content(
        model="gemini-3-flash-preview",#this is free and comparable to gemini 2.5 pro
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[
                types.Tool(
                    file_search=types.FileSearch(
                        file_search_store_names=[store_name]
                    )
                )
            ]
        ),
    )

    # Best-effort: do not hard-fail if deletion APIs differ across versions.
    # Keeping artifacts is acceptable; they are referenced by name for citations.
    try:
        for n in uploaded_file_names:
            try:
                client.files.delete(name=n)
            except Exception:
                pass
        try:
            client.file_search_stores.delete(name=store_name)
        except Exception:
            pass
    except Exception:
        pass

    return getattr(response, "text", "") or ""


_MIN_RESPONSE_CHARS = 500

_ERROR_PREFIXES = (
    "error",
    "i cannot",
    "i'm unable",
    "i am unable",
    "sorry",
    "unfortunately",
    "as an ai",
    "i don't have",
    "i do not have",
    "quota exceeded",
    "rate limit",
)


def _validate_response(response: str, ticker: str, logger: logging.Logger) -> bool:
    """Return True if *response* looks like a valid deep-research report."""
    if not response or not response.strip():
        logger.warning("SKIP %s — empty response from LLM", ticker)
        return False

    stripped = response.strip()

    # Too short to be real research.
    if len(stripped) < _MIN_RESPONSE_CHARS:
        logger.warning(
            "SKIP %s — response too short (%d chars, min %d)",
            ticker, len(stripped), _MIN_RESPONSE_CHARS,
        )
        return False

    # Starts with a known error pattern.
    lower = stripped.lower()
    for prefix in _ERROR_PREFIXES:
        if lower.startswith(prefix):
            logger.warning(
                "SKIP %s — response looks like an error: %.120s...",
                ticker, stripped[:120],
            )
            return False

    # A valid report typically contains markdown headings.
    if "#" not in stripped and len(stripped) < 2000:
        logger.warning(
            "SKIP %s — response has no headings and is only %d chars; likely not a real report",
            ticker, len(stripped),
        )
        return False

    return True


async def _save_deepresearch(ticker: str, content: str) -> None:
    from core.db.engine import DBEngine

    # Prefer upsert with deepresearch_date when column exists.
    q = """
        INSERT INTO stock_analysis (ticker, deepresearch, deepresearch_date)
        VALUES ($1, $2, NOW())
        ON CONFLICT (ticker) DO UPDATE
        SET deepresearch = EXCLUDED.deepresearch,
            deepresearch_date = EXCLUDED.deepresearch_date
    """
    try:
        await DBEngine.execute(q, ticker, content)
        return
    except Exception:
        # Fallback if deepresearch_date doesn't exist.
        from modules.data.research import save_deep_research_data

        await save_deep_research_data(ticker, content)


async def run(*, ticker: str | None, limit: int | None, dry_run: bool, max_chars: int | None) -> int:
    from scripts_standalone.results_scraper.watchlist import resolve_tickers_to_process
    from scripts_standalone.results_scraper.utils import sanitize_ticker
    from modules.analysis.selector import managed_query_ai

    logger = logging.getLogger(__name__)

    results_root = GUI_ROOT / "results"
    prompts_dir = GUI_ROOT / "prompts"

    tickers = await resolve_tickers_to_process(ticker, limit)
    if not tickers:
        logger.info("No tickers to process")
        return 0

    logger.info("Processing %d ticker(s)", len(tickers))

    for t in tickers:
        if not t:
            continue

        canon = sanitize_ticker(t)
        logger.info("\n=== %s (canon=%s) ===", t, canon)

        pdfs = _find_result_pdfs(results_root, canon)

        # Load all results text (optional if PDFs exist).
        payload, used_files = _load_results_text(results_root, canon, max_chars=max_chars)

        if (not payload.strip()) and (not pdfs):
            logger.warning("No .txt or .pdf files found for %s under %s", canon, results_root / canon)
            continue

        if not payload.strip():
            payload = "[NO TEXT FILES FOUND FOR THIS TICKER]\n"

        price = None
        try:
            # Prefer ticker with .JO for prices.
            price_ticker = t if t.upper().endswith(".JO") else (t + ".JO")
            price = await _fetch_latest_close_price(price_ticker)
        except Exception:
            logger.exception("Failed to fetch latest close_price for %s", t)

        category = None
        try:
            # Category helper expects ticker in DB format (often with .JO).
            category_ticker = t if t.upper().endswith(".JO") else (t + ".JO")
            category = await _fetch_category_name(category_ticker)
        except Exception:
            category = None

        prompt_file = _select_prompt_file(prompts_dir, category)
        prompt_template = prompt_file.read_text(encoding="utf-8", errors="ignore")

        # Fetch any existing deep research so the LLM can produce a change summary.
        existing_dr = None
        try:
            existing_dr = await _fetch_existing_deepresearch(t)
        except Exception:
            logger.debug("Could not fetch existing deepresearch for %s", t)

        # For commodity-type tickers, fetch average commodity/FX prices since last reporting period.
        commodity_avgs = None
        fx_avgs = None
        results_date_str = None
        is_commodity = prompt_file.name.lower().startswith("commodity")
        if is_commodity:
            try:
                rd = await _fetch_last_results_date(t)
                if rd is not None:
                    results_date_str = str(rd)
                    commodity_avgs, fx_avgs = await _fetch_commodity_fx_averages(rd)
                    logger.info(
                        "Commodity data: %d commodity avg(s), %d FX avg(s) since %s",
                        len(commodity_avgs), len(fx_avgs), results_date_str,
                    )
                else:
                    logger.info("No results_release_date found for %s; skipping commodity data", t)
            except Exception:
                logger.exception("Failed to fetch commodity/FX averages for %s", t)

        logger.info(
            "Category: %s | Prompt: %s | Txt files: %d | Pdf files: %d | Has previous DR: %s",
            category or "(none)",
            prompt_file.name,
            len(used_files),
            len(pdfs),
            bool(existing_dr),
        )

        llm_prompt = _build_llm_prompt(
            prompt_template,
            ticker=t,
            price=price,
            payload=payload,
            previous_report=existing_dr,
            commodity_avgs=commodity_avgs,
            fx_avgs=fx_avgs,
            results_date=results_date_str,
        )

        if pdfs:
            llm_prompt = (
                llm_prompt.rstrip()
                + "\n\n"
                + "[PDF ATTACHMENTS]\n"
                + "There are PDF attachments available via file search. Use them as primary sources when relevant and cite them.\n"
                + "Prefer facts found in the PDFs over speculation.\n"
            )

        if dry_run:
            if pdfs:
                logger.info(
                    "Dry-run: would send %d chars to LLM + upload %d PDF(s) for file search",
                    len(llm_prompt),
                    len(pdfs),
                )
            else:
                logger.info("Dry-run: would send %d chars to LLM", len(llm_prompt))
            continue

        if pdfs:
            # Use Gemini file_search for PDFs; run in a thread to avoid blocking the event loop.
            response = await asyncio.to_thread(
                _query_ai_with_pdfs,
                prompt=llm_prompt,
                pdf_paths=pdfs,
                display_name_prefix=f"{canon}-{int(time.time())}",
            )
        else:
            response = await managed_query_ai("deep_research", llm_prompt)
        if not _validate_response(response, t, logger):
            continue

        try:
            await _save_deepresearch(t, response)
            logger.info("Saved deepresearch for %s (len=%d)", t, len(response))
        except Exception:
            logger.exception("Failed to save deepresearch for %s", t)
            continue

        # Clean up results folder now that deep research is saved.
        ticker_dir = results_root / canon
        if ticker_dir.exists() and ticker_dir.is_dir():
            removed = 0
            for f in list(ticker_dir.iterdir()):
                try:
                    f.unlink()
                    removed += 1
                except Exception:
                    logger.warning("Could not delete %s", f)
            try:
                ticker_dir.rmdir()  # only succeeds if empty
            except Exception:
                pass
            logger.info("Cleaned up %d file(s) from %s", removed, ticker_dir)

        # Gentle pacing.
        await asyncio.sleep(1)

    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(
        description="Generate deepresearch for tickers without deepresearch, using gui/results/*.txt and sector prompts",
    )
    parser.add_argument("--ticker", default=None, help="Process a single ticker (e.g., NPN.JO)")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of tickers (when --ticker not provided)")
    parser.add_argument("--dry-run", action="store_true", help="Build prompts but do not call the LLM or save to DB")
    parser.add_argument(
        "--max-chars",
        type=int,
        default=200_000,
        help="Maximum characters of results text to include per ticker (default: 200000)",
    )

    args = parser.parse_args(argv)

    return asyncio.run(run(ticker=args.ticker, limit=args.limit, dry_run=args.dry_run, max_chars=args.max_chars))


if __name__ == "__main__":
    raise SystemExit(main())
