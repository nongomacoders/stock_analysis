"""
Standalone Playwright script to navigate to the provided site and wait until
user manually closes the browser. Run with:

  python "standalone_scripts/results_scraper.py"

This script launches a visible browser (non-headless) by default so you can
interact with the page and watch the login flow.

Note: ensure Playwright is installed and browsers are installed, e.g.:
  pip install playwright
  playwright install

"""
import asyncio
import argparse
import logging
import os
from dotenv import load_dotenv
from pathlib import Path
import urllib.parse
from datetime import datetime
import time
import sys
# Make sure the repository root is available on sys.path so imports work
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))
# Import the watchlist helper if available
from playwright.async_api import async_playwright
try:
    # Prefer the package used by the GUI (core.db.engine)
    from core.db.engine import DBEngine
    DBEngine_IMPORT_PATH = 'core.db.engine'
except Exception as ex_core_import:
    try:
        from gui.core.db.engine import DBEngine
        DBEngine_IMPORT_PATH = 'gui.core.db.engine'
    except Exception as ex_gui_import:
        DBEngine = None
        DBEngine_IMPORT_PATH = None
        logger = logging.getLogger(__name__)
        logger.warning("Failed to import DBEngine from core.db.engine: %s", ex_core_import)
        logger.warning("Failed to import DBEngine from gui.core.db.engine: %s", ex_gui_import)
try:
    # Prefer the GUI-side helper path
    from gui.modules.data.scraper import get_watchlist_tickers_without_deepresearch
    WATCHLIST_HELPER_PATH = 'gui.modules.data.scraper'
except Exception as ex_gui_helper:
    try:
        from modules.data.scraper import get_watchlist_tickers_without_deepresearch
        WATCHLIST_HELPER_PATH = 'modules.data.scraper'
    except Exception as ex_modules_helper:
        get_watchlist_tickers_without_deepresearch = None
        WATCHLIST_HELPER_PATH = None
        logger = logging.getLogger(__name__)
        logger.warning("Failed to import get_watchlist_tickers_without_deepresearch from gui.modules.data.scraper: %s", ex_gui_helper)
        logger.warning("Failed to import get_watchlist_tickers_without_deepresearch from modules.data.scraper: %s", ex_modules_helper)

# Load .env file for credentials located next to the script
load_dotenv(dotenv_path=Path(__file__).parent / ".env")
OST_USERNAME = os.getenv("OST_USERNAME")
OST_PASSWORD = os.getenv("OST_PASSWORD")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TARGET_URL = "https://securities.standardbank.co.za/ost/"
DEBUG_DIR = Path(__file__).parent / "debug"


async def dump_debug(page, label: str):
    logger = logging.getLogger(__name__)
    try:
        os.makedirs(DEBUG_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = DEBUG_DIR / f"{ts}_{label}"
        try:
            await page.screenshot(path=str(base) + ".png", full_page=True)
        except Exception:
            logger.debug("screenshot failed")
        try:
            html = await page.content()
            with open(str(base) + ".html", "w", encoding="utf-8") as fh:
                fh.write(html)
        except Exception:
            logger.debug("saving HTML failed")
        logger.info("Debug dumped to %s.*", base)
    except Exception:
        logger.exception("Failed to write debug artifacts")




async def find_frame(page, name: str | None = None, url_contains: str | None = None, selector: str | None = None, timeout: float = 10.0):
    """Find a frame on the page matching a name, a url substring, or a selector.
    Returns the frame object or None if not found within timeout.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        for f in page.frames:
            try:
                if name and getattr(f, 'name', None) == name:
                    return f
                if url_contains and getattr(f, 'url', None) and url_contains in f.url:
                    return f
                if selector:
                    try:
                        el = await f.query_selector(selector)
                        if el:
                            return f
                    except Exception:
                        pass
            except Exception:
                continue
        await asyncio.sleep(0.25)
    return None


def sanitize_ticker(ticker: str | None) -> str:
    if not ticker:
        return ''
    t = str(ticker).strip()
    if t.upper().endswith('.JO'):
        return t[:-3]
    return t

async def get_watchlist_tickers_from_db(limit: int | None = None):
    """Fallback server-side SQL defined inline if the helper module import fails."""
    logger = logging.getLogger(__name__)
    if not DBEngine:
        logger.warning("DBEngine not available; cannot query watchlist directly")
        return []
    query = """
        SELECT w.ticker
        FROM watchlist w
        JOIN stock_details sd ON w.ticker = sd.ticker
        LEFT JOIN stock_analysis sa ON (sa.ticker = w.ticker OR sa.ticker = REPLACE(w.ticker, '.JO', ''))
        WHERE w.status NOT IN ('WL-Sleep')
          AND (sa.deepresearch IS NULL OR TRIM(sa.deepresearch) = '')
        ORDER BY
            CASE WHEN sd.priority = 'A' THEN 1
                 WHEN sd.priority = 'B' THEN 2
                 ELSE 3 END,
            w.ticker
    """
    if limit:
        query += f" LIMIT {limit}"
    rows = await DBEngine.fetch(query)
    tickers = [r['ticker'] for r in rows]
    logger.info("DB fallback: found %d tickers without deepresearch", len(tickers))
    return tickers


async def debug_get_watchlist_rows(limit: int | None = None):
    """Return watchlist rows joined with stock_analysis.deepresearch for debugging."""
    logger = logging.getLogger(__name__)
    if not DBEngine:
        logger.warning("DBEngine not available; cannot query watchlist directly")
        return []
    query = """
        SELECT w.ticker, sa.deepresearch
        FROM watchlist w
        LEFT JOIN stock_analysis sa ON (sa.ticker = w.ticker OR sa.ticker = REPLACE(w.ticker, '.JO', ''))
        WHERE w.status NOT IN ('WL-Sleep')
        ORDER BY w.ticker
    """
    if limit:
        query += f" LIMIT {limit}"
    rows = await DBEngine.fetch(query)
    return rows


async def attempt_login(page, username: str, password: str) -> bool:
    """Attempt to log in using the page, returns True on success."""
    logger = logging.getLogger(__name__)
    def _frames():
        # Return an iterable of frames including the main frame (page.main_frame)
        return [page.main_frame] + page.frames

    # Find the exact frame that contains the username input
    found_frame = None
    try:
        found_frame = await find_frame(page, selector="#normalUsername")
        if not found_frame:
            # If the username input is not present, try the password selector
            found_frame = await find_frame(page, selector="#j_password")
    except Exception:
        logger.debug("login frame search failed")

    try:
        # If frame not found, abort login (we expect exact selectors in a known frame)
        if not found_frame:
            logger.warning("Login frame with #normalUsername/#j_password not found; aborting login")
            return False
        frame = found_frame

        # Normal visible username field - use typing
        try:
            if await frame.query_selector("#normalUsername"):
                logger.debug("Typing username into #normalUsername in frame %s", getattr(frame, "name", "main"))
                await frame.focus("#normalUsername")
                await frame.type("#normalUsername", username, delay=50)
            else:
                logger.warning("#normalUsername not found in selected login frame; aborting login")
                return False
            # No fallback; we expect normalUsername to exist
        except Exception:
            logger.debug("Failed to set username in any frame")

        # Fill password using typing so JS handlers trigger
        try:
            if await frame.query_selector("#j_password"):
                logger.debug("Typing password into #j_password in frame %s", getattr(frame, "name", "main"))
                await frame.focus("#j_password")
                await frame.type("#j_password", password, delay=50)
            else:
                logger.warning("#j_password not found in selected login frame; aborting login")
                return False
        except Exception:
            logger.debug("Failed to set password in any frame")

        # Pre-submit stabilization pause: sometimes the UI requires a brief delay after filling inputs
        try:
            await asyncio.sleep(1)
        except Exception:
            pass

        # Click the login control (exact id expected)
        clicked = False
        try:
            await frame.click("#submitButton")
            clicked = True
        except Exception:
            logger.debug("Failed to click #submitButton in login frame")

        # After submit attempt, allow the site a moment to respond
        if clicked:
            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                await asyncio.sleep(1)
        else:
            # If click didn't happen, abort login (no fallbacks)
            logger.warning("Login submit not performed; aborting login")
            return False

        # Quickly check that fields were set (do not log sensitive values)
        frame_for_check = found_frame or page.main_frame
        try:
            usr_len = await frame_for_check.evaluate("() => (document.getElementById('normalUsername')?.value || '').length")
        except Exception:
            usr_len = 0
        try:
            pwd_len = await frame_for_check.evaluate("() => (document.getElementById('j_password')?.value || '').length")
        except Exception:
            pwd_len = 0

        logger.debug("username length=%d password length=%d", usr_len, pwd_len)
        if usr_len == 0:
            logger.warning("Username field wasn't populated; login may fail")
        if pwd_len == 0:
            logger.warning("Password field wasn't populated; login may fail")

        # Wait for login to complete: either the login form disappears, or a Logout control appears
        try:
            await page.wait_for_selector("#loginForm", state="hidden", timeout=6000)
            return True
        except Exception:
            try:
                if await page.is_visible("text=Logout", timeout=3000):
                    return True
            except Exception:
                pass

        # As a last check: consider navigation change as success
        if 'Home.aspx' not in page.url and page.url != TARGET_URL:
            return True
        # Fallback: Try submitting the login form directly (in the frame), then wait briefly
        try:
            try:
                await frame.evaluate("() => { const f = document.getElementById('loginForm'); if (f) f.submit(); }")
            except Exception:
                try:
                    await page.evaluate("() => { const f = document.getElementById('loginForm'); if (f) f.submit(); }")
                except Exception:
                    pass
            try:
                await page.wait_for_load_state('networkidle', timeout=4000)
            except Exception:
                await asyncio.sleep(1)
            # check logout or selector again
            try:
                if await page.is_visible("text=Logout", timeout=3000):
                    return True
            except Exception:
                pass
        except Exception:
            pass
    except Exception:
        logger.exception("Error performing login flow")
    return False


async def fill_and_click_quote(page, ticker: str = "NPN") -> bool:
    """Finds the `markIdTextBox` input and `quoteButton` in any frame, waits for them to appear, types ticker, and clicks the button."""
    logger = logging.getLogger(__name__)

    def _frames():
        return [page.main_frame] + page.frames

    # Give the UI a little time after login to render dynamic content
    try:
        await page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        await asyncio.sleep(1)

    # Use nav_top only for the quote action
    # Try to find a nested frame named 'nav_top' (or with a TopMenu URL)
    async def find_frame_by_name_or_url(name: str = "nav_top", url_contains: str | None = "TopMenu", timeout: float = 10.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            for f in page.frames:
                try:
                    if name and getattr(f, 'name', None) == name:
                        return f
                    if url_contains and getattr(f, 'url', None) and url_contains in f.url:
                        return f
                except Exception:
                    continue
            await asyncio.sleep(0.25)
        return None

    nav_frame = await find_frame_by_name_or_url(name="nav_top", url_contains="TopMenu", timeout=10.0)

    if not nav_frame:
        logger.warning('nav_top frame not found; aborting quote action')
        try:
            await dump_debug(page, f"nav_top_missing_{ticker}")
        except Exception:
            pass
        return False

    # Wait for nav_frame to render controls
    try:
        await nav_frame.wait_for_selector('#markIdTextBox', timeout=5000)
    except Exception:
        await asyncio.sleep(1)

    try:
        box = await nav_frame.query_selector('#markIdTextBox')
    except Exception:
        box = None

    if not box:
        logger.warning('markIdTextBox not found in nav_top frame')
        try:
            await dump_debug(page, f"quote_missing_box_nav_top_{ticker}")
        except Exception:
            pass
        return False

    # Fill the box and try to submit by clicking the button or invoking doQuickFind
    try:
        await nav_frame.focus('#markIdTextBox')
        await nav_frame.type('#markIdTextBox', ticker, delay=50)
    except Exception:
        try:
            await nav_frame.evaluate("(val) => { const el = document.getElementById('markIdTextBox'); if (el) el.value = val; }", ticker)
        except Exception:
            logger.debug('Failed to set markIdTextBox value in nav_top frame')

    # Find the quote button by id and click it
    try:
        button = await nav_frame.query_selector('#quoteButton')
    except Exception:
        button = None

    if button:
        try:
            await button.click()
            try:
                await page.wait_for_load_state('networkidle', timeout=5000)
            except Exception:
                await asyncio.sleep(1)
            return True
        except Exception:
            logger.debug('Failed to click #quoteButton in nav_top')

    # No fallback; if #quoteButton not found/clicked, abort and dump debug
    logger.warning('Could not find or click #quoteButton in nav_top frame')
    try:
        await dump_debug(page, f"quote_missing_nav_top_{ticker}")
    except Exception:
        logger.debug('dump_debug failed')

    return False


async def click_results_summaries(page) -> bool:
    """Click the 'Results Summaries' link inside the nav_content frame.
    Returns True on click (and after navigation), False otherwise.
    """
    logger = logging.getLogger(__name__)
    # Find nav_content frame by name
    nav_content = await find_frame(page, name='nav_content', timeout=10.0)
    if not nav_content:
        logger.warning("nav_content frame not found; cannot click Results Summaries")
        try:
            await dump_debug(page, "nav_content_missing")
        except Exception:
            pass
        return False

    # Wait for the Results Summaries anchor in nav_content
    try:
        await nav_content.wait_for_selector("a[title='Results Summaries']", timeout=5000)
    except Exception:
        # Let the following query_selector attempt handle it
        pass

    try:
        link = await nav_content.query_selector("a[title='Results Summaries']")
        if not link:
            link = await nav_content.query_selector("a[href*='ResultsSummaries.htm']")
        if not link:
            link = await nav_content.query_selector("a:has-text('Results Summaries')")
    except Exception:
        link = None

    if not link:
        logger.warning("Results Summaries link not found in nav_content")
        try:
            await dump_debug(page, "results_summaries_missing")
        except Exception:
            pass
        return False

    try:
        await link.click()
        try:
            await page.wait_for_load_state('networkidle', timeout=5000)
        except Exception:
            await asyncio.sleep(1)
        return True
    except Exception:
        logger.exception("Failed to click Results Summaries link")
        try:
            await dump_debug(page, "results_summaries_click_failed")
        except Exception:
            pass
        return False
    """Click the 'Full glossy financials in PDF format' link inside the nav_content frame."""
    logger = logging.getLogger(__name__)
    # Find nav_content frame by name
    nav_content = await find_frame(page, name='nav_content', timeout=10.0)
    if not nav_content:
        logger.warning("nav_content frame not found; cannot click PDF link")
        try:
            await dump_debug(page, "nav_content_missing_pdf")
        except Exception:
            pass
        return False

    # Wait for the PDF link to appear
    try:
        await nav_content.wait_for_selector("a[href*='PDF.htm']", timeout=5000)
    except Exception:
        await asyncio.sleep(1)

    try:
        link = await nav_content.query_selector("a[href*='PDF.htm']")
        if not link:
            link = await nav_content.query_selector("a:has-text('Full glossy financials in PDF format')")
        if not link:
            logger.warning("Full glossy PDF link not found in nav_content")
            try:
                await dump_debug(page, "pdf_link_missing")
            except Exception:
                pass
            return False
    except Exception:
        link = None

    try:
        if not link:
            return False
        await link.click()
        try:
            await page.wait_for_load_state('networkidle', timeout=5000)
        except Exception:
            await asyncio.sleep(1)
        return True
    except Exception:
        logger.exception("Failed to click Full glossy PDF link")
        try:
            await dump_debug(page, "pdf_click_failed")
        except Exception:
            pass
        return False


async def click_first_pdf_in_list(page, ticker: str | None = None) -> bool:
    """Click the first PDF link in the list and download it (save to results/<ticker>)."""
    logger = logging.getLogger(__name__)
    nav_content = await find_frame(page, name='nav_content', timeout=10.0)
    if not nav_content:
        logger.warning("nav_content frame not found; cannot find PDF list")
        return False

    # Look for anchors in the table; prefer anchors whose href ends with .pdf
    anchors = await nav_content.query_selector_all("table a[href$='.pdf'], a[href$='.pdf']")
    if not anchors:
        logger.warning("No PDF links found in nav_content")
        return False
    first = anchors[0]
    try:
        href = await first.get_attribute('href')
        href = href.replace('\\', '/') if href else href
        abs_url = href if href and href.startswith('http') else urllib.parse.urljoin(page.url, href or '')
    except Exception:
        abs_url = None
    # Try to click and capture a download event
    try:
        async with page.expect_download(timeout=5000) as download_info:
            await first.click()
        download = await download_info.value
        # Save to results/<sanitized_ticker>
        repo_root = Path(__file__).resolve().parent.parent
        safe_ticker = (sanitize_ticker(ticker) if ticker else 'unknown')
        results_dir = repo_root / 'results' / safe_ticker
        results_dir.mkdir(parents=True, exist_ok=True)
        target = results_dir / (download.suggested_filename or Path(abs_url or '').name or 'download.pdf')
        await download.save_as(str(target))
        logger.info("Saved download to %s", target)
        return True
    except Exception:
        # Fallback: fetch via request.get
        try:
            if abs_url:
                resp = await page.request.get(abs_url)
                if resp and resp.status == 200:
                    data = await resp.body()
                    repo_root = Path(__file__).resolve().parent.parent
                    safe_ticker = (sanitize_ticker(ticker) if ticker else 'unknown')
                    results_dir = repo_root / 'results' / safe_ticker
                    results_dir.mkdir(parents=True, exist_ok=True)
                    filename = Path(abs_url).name or 'download.pdf'
                    out_path = results_dir / filename
                    with open(out_path, 'wb') as fh:
                        fh.write(data)
                    logger.info("Saved PDF via request to %s", out_path)
                    return True
        except Exception:
            logger.exception("Failed to download PDF via request.get")
        logger.exception("Failed to click or download first PDF in list")
        return False

async def click_full_glossy_pdf(page) -> bool:
    """Click the 'Full glossy financials in PDF format' link found in nav_content frame."""
    logger = logging.getLogger(__name__)
    nav_content = await find_frame(page, name='nav_content', timeout=10.0)
    if not nav_content:
        logger.warning("nav_content frame not found; cannot click full glossy PDF list")
        return False
    try:
        await nav_content.wait_for_selector("a[href*='PDF.htm']", timeout=5000)
    except Exception:
        await asyncio.sleep(1)
    try:
        link = await nav_content.query_selector("a[href*='PDF.htm']")
        if not link:
            link = await nav_content.query_selector("a:has-text('Full glossy financials in PDF format')")
        if not link:
            logger.warning("Full glossy list link not found in nav_content")
            return False
        await link.click()
        try:
            await page.wait_for_load_state('networkidle', timeout=5000)
        except Exception:
            await asyncio.sleep(1)
        return True
    except Exception:
        logger.exception("Failed clicking full glossy link in nav_content")
        return False
    return True
    # Try to click and capture a download event
    try:
        async with page.expect_download(timeout=5000) as download_info:
            await first.click()
        download = await download_info.value
        # Save to results/<sanitized_ticker>
        repo_root = Path(__file__).resolve().parent.parent
        safe_ticker = (sanitize_ticker(ticker) if ticker else 'unknown')
        results_dir = repo_root / 'results' / safe_ticker
        results_dir.mkdir(parents=True, exist_ok=True)
        target = results_dir / (download.suggested_filename or Path(abs_url or '').name or 'download.pdf')
        await download.save_as(str(target))
        logger.info("Saved download to %s", target)
        return True
    except Exception:
        # Fallback: fetch via request.get
        try:
            if abs_url:
                resp = await page.request.get(abs_url)
                if resp and resp.status == 200:
                    data = await resp.body()
                    repo_root = Path(__file__).resolve().parent.parent
                    safe_ticker = (sanitize_ticker(ticker) if ticker else 'unknown')
                    results_dir = repo_root / 'results' / safe_ticker
                    results_dir.mkdir(parents=True, exist_ok=True)
                    filename = Path(abs_url).name or 'download.pdf'
                    out_path = results_dir / filename
                    with open(out_path, 'wb') as fh:
                        fh.write(data)
                    logger.info("Saved PDF via request to %s", out_path)
                    return True
        except Exception:
            logger.exception("Failed to download PDF via request.get")
        logger.exception("Failed to click or download first PDF in list")
        return False



async def run(ticker: str | None = None, list_only: bool = False, limit: int | None = None, debug_values: bool = False) -> int:
    try:
        async with async_playwright() as p:
            # Always run with a visible (non-headless) browser so the user can interact and "see" the page.
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context()
            page = await context.new_page()

            logger.info("Navigating to %s", TARGET_URL)
            try:
                await page.goto(TARGET_URL, wait_until="networkidle", timeout=30000)
            except Exception:
                logger.warning("Initial goto timed out; retrying with domcontentloaded and longer timeout")
                try:
                    await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
                except Exception:
                    logger.exception("Page.goto failed on retry; dumping debug and aborting")
                    try:
                        await dump_debug(page, "goto_failed")
                    except Exception:
                        pass
                    raise

            logger.info("Page loaded. Keep the browser open to continue. Close the browser to exit.")

            # Always attempt login using credentials from .env
            if OST_USERNAME and OST_PASSWORD and not OST_USERNAME.startswith("your_") and not OST_PASSWORD.startswith("your_"):
                logger.info("Attempting to log in using credentials from .env")
                success = await attempt_login(page, OST_USERNAME, OST_PASSWORD)
                if success:
                    logger.info("Logged in successfully")
                else:
                    logger.warning("Login attempt failed; continuing without authentication")
                    try:
                        await dump_debug(page, "login_failed")
                    except Exception:
                        pass
            else:
                logger.info("Skipping login: username/password not provided or still using placeholders")

            # After login (or skip), enter the `ticker` into the markIdTextBox and press the quote button
            logger.info("DBEngine import path: %s; watchlist helper path: %s", DBEngine_IMPORT_PATH, WATCHLIST_HELPER_PATH)
            try:
                # If no ticker provided, process all watchlist tickers without deepresearch
                if not ticker:
                    if get_watchlist_tickers_without_deepresearch:
                        tickers_to_process = await get_watchlist_tickers_without_deepresearch(limit=limit)
                    else:
                        # Fallback: Query DB directly if DBEngine is available
                        if DBEngine:
                            try:
                                tickers_to_process = await get_watchlist_tickers_from_db(limit=limit)
                            except Exception:
                                logger.warning("DB fallback query failed; no tickers to process")
                                tickers_to_process = []
                        else:
                            logger.warning("No watchlist helper and no DB engine; cannot determine tickers to process")
                            tickers_to_process = []
                else:
                    tickers_to_process = [ticker]

                logger.info("Processing %d ticker(s)", len(tickers_to_process))
                # If list-only, print and exit
                if list_only:
                    for t in tickers_to_process:
                        print(t)
                    if debug_values and DBEngine:
                        rows = await debug_get_watchlist_rows(limit=limit)
                        for r in rows:
                            print(r)
                    await browser.close()
                    return 0
                for t in tickers_to_process:
                    if not t:
                        continue
                    canon = t.strip()
                    if canon.upper().endswith('.JO'):
                        canon = canon[:-3]
                    logger.info("Processing ticker %s (sanitized %s)", t, canon)
                    filled = await fill_and_click_quote(page, ticker=canon)
                    if not filled:
                        logger.warning("Unable to fill or click quote for %s", canon)
                        continue
                    clicked_rs = await click_results_summaries(page)
                    if not clicked_rs:
                        logger.warning("Failed to click Results Summaries for %s", canon)
                        continue
                    clicked_pdf = await click_full_glossy_pdf(page)
                    if not clicked_pdf:
                        logger.warning("Failed to click Full glossy PDF link for %s", canon)
                        continue
                    downloaded = await click_first_pdf_in_list(page, ticker=canon)
                    if downloaded:
                        logger.info("Downloaded first PDF for %s", canon)
                    else:
                        logger.warning("Failed to download first PDF for %s", canon)
                    # Reset UI state by navigating back to main page for the next ticker
                    try:
                        await page.goto(TARGET_URL, wait_until='networkidle', timeout=15000)
                    except Exception:
                        try:
                            await page.goto(TARGET_URL, wait_until='domcontentloaded', timeout=30000)
                        except Exception:
                            pass
                    await asyncio.sleep(1)
            except Exception:
                logger.exception("Error performing fill+click quote flow")

            # Wait until the page is closed by the user.
            close_event = asyncio.Event()

            def _on_close(_=None):
                close_event.set()

            # Prefer a page "close" event so we can detect a single tab being closed in headful runs
            try:
                page.on("close", _on_close)
            except Exception:
                pass

            # Also watch the browser / context disconnect to be resilient across Playwright versions
            try:
                browser.on("disconnected", _on_close)
            except Exception:
                try:
                    context.on("close", _on_close)
                except Exception:
                    pass

            # If any of these fire, the event will be set.
            # As a final fallback for extremely old versions, poll page.is_closed().
            if page.is_closed():
                # already closed
                pass
            else:
                # await event with a small timeout so we can break if loop is cancelled
                await close_event.wait()

            logger.info("Detected browser/page close — exiting.")
            await browser.close()
        return 0
    except Exception:
        logger.exception("Fatal error in Playwright run")
        return 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Open a visible browser to TARGET_URL and wait until manually closed.")
    parser.add_argument("--ticker", default=None, help="Ticker to enter into the markIdTextBox (default: run on all watchlist tickers missing deepresearch)")
    parser.add_argument("--list-only", action="store_true", help="Only list the tickers that would be processed and exit")
    parser.add_argument("--limit", type=int, default=None, help="Limit the number of tickers to process (for testing) - pass an integer")
    parser.add_argument("--debug-values", action="store_true", help="When combined with --list-only, show deepresearch values for each ticker")
    args = parser.parse_args()

    loop = asyncio.get_event_loop()
    exit_code = loop.run_until_complete(run(ticker=args.ticker, list_only=args.list_only, limit=args.limit, debug_values=args.debug_values))
    raise SystemExit(exit_code)
