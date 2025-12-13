from __future__ import annotations

import asyncio
import logging
import re
import urllib.parse
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

from standalone_scripts.results_scraper.env import Credentials
from standalone_scripts.results_scraper.navigation import TARGET_URL, attempt_login, fill_and_click_quote
from standalone_scripts.results_scraper.paths import ProjectPaths
from standalone_scripts.results_scraper.utils import dump_debug, find_frame, sanitize_ticker
from standalone_scripts.results_scraper.watchlist import DBENGINE_IMPORT_PATH, WATCHLIST_HELPER_PATH, resolve_tickers_to_process

from .navigation import click_news
from .db import DBENGINE_IMPORT_PATH as NEWS_DBENGINE_IMPORT_PATH
from .db import fetch_max_results_release_datetime


_NEWS_DATE_RE = re.compile(
    r"^(\d{1,2})\s*(?:-|\s)\s*([A-Za-z]{3,4})\s*(?:-|\s)\s*(\d{4})(?:\s+(\d{1,2}):(\d{2}))?$"
)
_SENS_PDF_RE = re.compile(r"\bSENS_\d{8}_[A-Za-z0-9]+\.pdf\b")
_HREF_PDF_RE = re.compile(r"href=\"([^\"]+?\.pdf[^\"]*)\"", flags=re.IGNORECASE)


def _extract_article_content(html_text: str) -> dict:
    """Extract the news body from a NewsArticle.aspx HTML response.

    OST renders the announcement inside a <td class="NC"> inside an ASP.NET form.
    We save the raw HTML already; this extracts a usable plain-text version.
    """

    try:
        from bs4 import BeautifulSoup  # type: ignore
    except Exception:
        return {"content_text": "", "sens_pdf_filename": None, "page_headline": ""}

    soup = BeautifulSoup(html_text or "", "html.parser")
    nh = soup.select_one("td.NH")
    nc = soup.select_one("td.NC")

    page_headline = nh.get_text(" ", strip=True) if nh else ""

    content_text = ""
    sens_pdf_filename: str | None = None
    if nc:
        # Convert <br> to newlines so get_text becomes readable.
        for br in nc.find_all("br"):
            br.replace_with("\n")

        raw = nc.get_text(separator="\n")
        # Normalize whitespace (keep newlines).
        lines = [ln.rstrip() for ln in (raw or "").splitlines()]
        content_text = "\n".join(lines).strip()

        m = _SENS_PDF_RE.search(content_text)
        if m:
            sens_pdf_filename = m.group(0)

    return {
        "page_headline": page_headline,
        "content_text": content_text,
        "sens_pdf_filename": sens_pdf_filename,
    }


async def _dump_frame_tree(page, debug_dir: Path, label: str) -> None:
    try:
        debug_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = debug_dir / f"{stamp}_{label}_frames.txt"
        lines = []
        for f in page.frames:
            try:
                lines.append(f"name={getattr(f, 'name', '')!r} url={getattr(f, 'url', '')!r}")
            except Exception:
                continue
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception:
        pass


async def _dump_frame_html(frame, debug_dir: Path, label: str) -> None:
    try:
        debug_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = debug_dir / f"{stamp}_{label}_frame.html"
        html = await frame.content()
        out.write_text(html, encoding="utf-8")
    except Exception:
        pass


def _parse_news_datetime(text: str) -> datetime | None:
    value = (text or "").strip()
    if not value:
        return None
    # Example: 09 Dec 2025 17:05
    # Also seen on some installs: 9-Dec-2025 7:05 or 09 Dec 2025
    # NOTE: datetime.strptime("%b") depends on OS locale; on Windows this can break.
    # Parse month abbreviations ourselves to keep it locale-independent.
    m = _NEWS_DATE_RE.match(value)
    if not m:
        return None

    try:
        day_s, mon_s, year_s, hh_s, mm_s = m.groups()
        mon_map = {
            "jan": 1,
            "feb": 2,
            "mar": 3,
            "apr": 4,
            "may": 5,
            "jun": 6,
            "jul": 7,
            "aug": 8,
            "sep": 9,
            "sept": 9,
            "oct": 10,
            "nov": 11,
            "dec": 12,
        }
        month = mon_map.get(mon_s.strip().lower())
        if not month:
            return None
        hh = int(hh_s) if hh_s is not None else 0
        mm = int(mm_s) if mm_s is not None else 0
        return datetime(int(year_s), int(month), int(day_s), hh, mm)
    except Exception:
        return None


def _safe_filename(value: str) -> str:
    v = (value or "").strip()
    v = v.replace("\\", "_").replace("/", "_").replace(":", "-")
    v = re.sub(r"\s+", "_", v)
    v = re.sub(r"[^A-Za-z0-9._-]", "_", v)
    v = re.sub(r"_+", "_", v)
    return v.strip("_") or "item"


async def _find_news_headlines_frame(page):
    # The OST site is heavily frame-based. The list typically renders in a nested
    # frame whose URL contains 'NewsHeadlines.aspx'. Prefer URL-based discovery.
    frame = await find_frame(page, url_contains="NewsHeadlines.aspx", timeout=15.0)
    if frame:
        return frame

    # Fallback: any /News/ frame.
    frame = await find_frame(page, url_contains="/News/", timeout=10.0)
    if frame:
        return frame

    # Last resort: any frame with the expected table class.
    return await find_frame(page, selector="table.CTbFW", timeout=10.0)


async def _extract_news_headlines(page, *, cutoff: datetime | None, debug_dir: Path) -> list[dict]:
    logger = logging.getLogger(__name__)

    frame = await _find_news_headlines_frame(page)
    if not frame:
        logger.warning("Could not locate News Headlines frame")
        try:
            await _dump_frame_tree(page, debug_dir, "news_headlines_frame_missing")
            await dump_debug(page, debug_dir, "news_headlines_frame_missing")
        except Exception:
            pass
        return []

    # Wait for the headlines tables to appear within this frame.
    table = None
    try:
        await frame.wait_for_selector("table.CTbFW", timeout=15000)
    except Exception:
        pass

    # There can be multiple tables with the same class (e.g. a hidden
    # JavaScript warning table). Choose the one that looks like headlines.
    try:
        candidate_tables = await frame.query_selector_all("table.CTbFW")
        best_table = None
        best_score = -1
        for t in candidate_tables:
            try:
                score = 0

                # Bonus if it contains the expected section header.
                try:
                    lh = await t.query_selector("td.LH")
                    if lh:
                        txt = (await lh.inner_text()).strip().lower()
                        if "news headlines" in txt:
                            score += 100
                except Exception:
                    pass

                # Count headline-like rows.
                try:
                    rows = await t.query_selector_all("tr")
                    for r in rows:
                        date_td = await r.query_selector("td.NWT")
                        link = await r.query_selector("td.ET a[href*='NewsArticle.aspx']")
                        if date_td and link:
                            score += 1
                except Exception:
                    pass

                if score > best_score:
                    best_score = score
                    best_table = t
            except Exception:
                continue

        table = best_table
    except Exception:
        table = None

    # If we still didn't find it, do a broader scan across all frames.
    if not table:
        deadline = asyncio.get_event_loop().time() + 10.0
        while asyncio.get_event_loop().time() < deadline and not table:
            for f in page.frames:
                try:
                    candidates = await f.query_selector_all("table.CTbFW")
                    for t in candidates:
                        # Same scoring logic as above, but keep it lightweight.
                        try:
                            r = await t.query_selector("td.NWT")
                            a = await t.query_selector("td.ET a[href*='NewsArticle.aspx']")
                            if r and a:
                                frame = f
                                table = t
                                break
                        except Exception:
                            continue
                    if table:
                        break
                except Exception:
                    continue
            if table:
                break
            await asyncio.sleep(0.25)

    if not table:
        logger.warning("News Headlines table not found")
        try:
            await _dump_frame_tree(page, debug_dir, "news_headlines_table_missing")
            await dump_debug(page, debug_dir, "news_headlines_table_missing")
        except Exception:
            pass
        return []

    rows = await table.query_selector_all("tr")
    items: list[dict] = []

    total_rows = 0
    rows_with_date_and_link = 0
    parsed_dates: list[datetime] = []
    failed_date_samples: list[str] = []

    for r in rows:
        total_rows += 1
        try:
            date_td = await r.query_selector("td.NWT")
            link = await r.query_selector("td.ET a[href*='NewsArticle.aspx']")
            if not date_td or not link:
                continue

            rows_with_date_and_link += 1

            date_text = (await date_td.inner_text()).strip()
            dt = _parse_news_datetime(date_text)
            if not dt:
                if len(failed_date_samples) < 8 and date_text:
                    failed_date_samples.append(date_text)
                continue

            parsed_dates.append(dt)

            if cutoff and dt <= cutoff:
                continue

            href = await link.get_attribute("href")
            headline = (await link.inner_text()).strip()

            source_td = await r.query_selector("td.T")
            source = (await source_td.inner_text()).strip() if source_td else ""

            items.append(
                {
                    "published": dt,
                    "published_text": date_text,
                    "href": href or "",
                    "headline": headline,
                    "source": source,
                }
            )
        except Exception:
            continue

    logger.info("Found %d news item(s) after cutoff", len(items))
    if cutoff:
        logger.info("Cutoff datetime: %s", cutoff)
    logger.info(
        "Headlines scan stats: total_rows=%d rows_with_date_and_link=%d parsed_dates=%d",
        total_rows,
        rows_with_date_and_link,
        len(parsed_dates),
    )
    if parsed_dates:
        logger.info("Parsed date range: %s .. %s", min(parsed_dates), max(parsed_dates))
    if failed_date_samples:
        logger.info("Unparsed date sample(s): %s", " | ".join(failed_date_samples))

    if cutoff and len(items) == 0:
        try:
            await _dump_frame_html(frame, debug_dir, "news_headlines_zero_after_cutoff")
        except Exception:
            pass
    return items


async def _request_fetch_html(page, *, url: str, referer: str) -> str | None:
    logger = logging.getLogger(__name__)
    try:
        resp = await page.request.get(
            url,
            headers={
                "referer": referer,
                "accept": "text/html,application/xhtml+xml,*/*",
            },
        )
        status = getattr(resp, "status", None)
        if status != 200:
            logger.warning("Article %s returned status %s", url, status)
            return None
        body = await resp.body()
        try:
            return body.decode("utf-8", errors="ignore")
        except Exception:
            return None
    except Exception:
        logger.exception("Failed to download article HTML: %s", url)
        return None


async def _request_try_download_pdf(page, *, url: str, referer: str, out_path: Path) -> bool:
    logger = logging.getLogger(__name__)
    if out_path.exists():
        return True
    try:
        resp = await page.request.get(
            url,
            headers={
                "referer": referer,
                "accept": "application/pdf,*/*",
            },
        )
        status = getattr(resp, "status", None)
        if status != 200:
            return False
        data = await resp.body()
        if not data.startswith(b"%PDF"):
            return False
        out_path.write_bytes(data)
        logger.info("Saved PDF to %s", out_path)
        return True
    except Exception:
        return False


async def run(
    *,
    ticker: str | None,
    list_only: bool,
    limit: int | None,
    max_news: int | None,
    creds: Credentials,
    paths: ProjectPaths,
) -> int:
    logger = logging.getLogger(__name__)
    step_delay_seconds = 2

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context()
            page = await context.new_page()

            logger.info("Navigating to %s", TARGET_URL)
            await page.goto(TARGET_URL, wait_until="networkidle", timeout=30000)

            logger.info("Page loaded. Close the browser to exit.")

            if creds.username and creds.password:
                logger.info("Attempting to log in using credentials from .env")
                success = await attempt_login(page, username=creds.username, password=creds.password, debug_dir=paths.debug_dir)
                if success:
                    logger.info("Logged in successfully")
                else:
                    logger.warning("Login attempt failed; continuing without authentication")
            else:
                logger.info("Skipping login: username/password not provided or still using placeholders")

            logger.info(
                "DBEngine import path: %s (watchlist), %s (news); watchlist helper path: %s",
                DBENGINE_IMPORT_PATH,
                NEWS_DBENGINE_IMPORT_PATH,
                WATCHLIST_HELPER_PATH,
            )
            tickers_to_process = await resolve_tickers_to_process(ticker, limit)
            logger.info("Processing %d ticker(s)", len(tickers_to_process))

            if list_only:
                for t in tickers_to_process:
                    print(t)
                await browser.close()
                return 0

            for t in tickers_to_process:
                if not t:
                    continue
                canon = sanitize_ticker(t)
                logger.info("Processing ticker %s (sanitized %s)", t, canon)

                cutoff = None
                try:
                    cutoff = await fetch_max_results_release_datetime(t)
                except Exception:
                    logger.exception("Failed to query max results_release_date for %s", t)
                    cutoff = None

                await asyncio.sleep(step_delay_seconds)

                filled = await fill_and_click_quote(page, ticker=canon, debug_dir=paths.debug_dir)
                if not filled:
                    logger.warning("Unable to fill or click quote for %s", canon)
                    continue

                await asyncio.sleep(step_delay_seconds)

                clicked = await click_news(page, debug_dir=paths.debug_dir)
                if not clicked:
                    logger.warning("Failed to click News for %s", canon)
                    continue

                await asyncio.sleep(step_delay_seconds)

                # Extract news items newer than the latest results_release_date and download them.
                try:
                    news_items = await _extract_news_headlines(page, cutoff=cutoff, debug_dir=paths.debug_dir)
                except Exception:
                    logger.exception("Failed to parse news headlines for %s", canon)
                    news_items = []

                if not news_items:
                    logger.info("No new news items to download for %s", canon)
                else:
                    results_dir = paths.results_root / canon
                    results_dir.mkdir(parents=True, exist_ok=True)

                    downloaded = 0
                    for item in news_items:
                        if max_news is not None and downloaded >= max_news:
                            break
                        href = (item.get("href") or "").strip()
                        if not href:
                            continue

                        article_url = urllib.parse.urljoin(TARGET_URL, href)
                        published: datetime | None = item.get("published")
                        published_stamp = published.strftime("%Y-%m-%d_%H%M") if isinstance(published, datetime) else "unknown"

                        # Try to extract numeric id from querystring for stable naming.
                        article_id = ""
                        try:
                            parsed = urllib.parse.urlsplit(article_url)
                            qs = urllib.parse.parse_qs(parsed.query)
                            if "id" in qs and qs["id"]:
                                article_id = str(qs["id"][0])
                        except Exception:
                            article_id = ""

                        headline = _safe_filename(item.get("headline") or "news")
                        base_name = f"news_{published_stamp}_{article_id}_{headline}".strip("_")
                        base_name = base_name[:160]  # keep windows paths reasonable

                        txt_path = results_dir / (base_name + ".txt")

                        html_text = await _request_fetch_html(page, url=article_url, referer=page.url)
                        if not html_text:
                            continue

                        extracted = _extract_article_content(html_text)
                        content_text = (extracted.get("content_text") or "").strip()

                        if content_text:
                            txt_path.write_text(content_text + "\n", encoding="utf-8")
                            downloaded += 1
                        else:
                            logger.warning("No td.NC content extracted from %s", article_url)

                # Reset UI state for the next ticker
                try:
                    await page.goto(TARGET_URL, wait_until="networkidle", timeout=15000)
                except Exception:
                    try:
                        await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30000)
                    except Exception:
                        pass
                await asyncio.sleep(1)

            close_event = asyncio.Event()

            def _on_close(_=None):
                close_event.set()

            try:
                page.on("close", _on_close)
            except Exception:
                pass
            try:
                browser.on("disconnected", _on_close)
            except Exception:
                pass

            if not page.is_closed():
                await close_event.wait()

            logger.info("Detected browser/page close — exiting.")
            await browser.close()

        return 0
    except Exception:
        logger.exception("Fatal error in Playwright run")
        return 2
