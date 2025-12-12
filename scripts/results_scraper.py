"""
Standalone Playwright script to navigate to the provided site and wait until
user manually closes the browser. Run with:

  python scripts/results_scraper.py

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
from datetime import datetime
import time
from playwright.async_api import async_playwright

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


async def attempt_login(page, username: str, password: str) -> bool:
    """Attempt to log in using the page, returns True on success."""
    logger = logging.getLogger(__name__)
    def _frames():
        # Return an iterable of frames including the main frame (page.main_frame)
        return [page.main_frame] + page.frames

    found_frame = None
    try:
        # Find a frame that contains both the visible username and password inputs
        for f in _frames():
            try:
                if await f.query_selector("#normalUsername") and await f.query_selector("#j_password"):
                    found_frame = f
                    break
            except Exception:
                continue
    except Exception:
        logger.debug("login fields did not appear in time or frames unavailable")

    try:
        # Default to page main frame if we didn't find a specific frame
        frame = found_frame or page.main_frame

        # Normal visible username field - use typing and update hiddenUsername if present
        try:
            if await frame.query_selector("#normalUsername"):
                logger.debug("Typing username into #normalUsername in frame %s", getattr(frame, "name", "main"))
                await frame.focus("#normalUsername")
                await frame.type("#normalUsername", username, delay=50)
                # Also set hiddenUsername if it's present (some forms copy from hidden fields)
                try:
                    await frame.evaluate("(val) => { const el = document.getElementById('hiddenUsername'); if (el) el.value = val; }", username)
                except Exception:
                    pass
            else:
                # If there is a hiddenUsername input we can set it directly via evaluate in the frame
                try:
                    await frame.evaluate("(val) => { const el = document.getElementById('hiddenUsername'); if (el) el.value = val }", username)
                except Exception:
                    pass
        except Exception:
            logger.debug("Failed to set username in any frame")

        # Fill password using typing so JS handlers trigger
        try:
            if await frame.query_selector("#j_password"):
                logger.debug("Typing password into #j_password in frame %s", getattr(frame, "name", "main"))
                await frame.focus("#j_password")
                await frame.type("#j_password", password, delay=50)
            else:
                # Try by name attribute
                try:
                    await frame.focus("input[name='j_password']")
                    await frame.type("input[name='j_password']", password, delay=50)
                except Exception:
                    pass
        except Exception:
            logger.debug("Failed to set password in any frame")

        # Pre-submit stabilization pause: sometimes the UI requires a brief delay after filling inputs
        try:
            await asyncio.sleep(1)
        except Exception:
            pass

        # Click the login control (an anchor in the page snippet). Try frame-specific click.
        clicked = False
        try:
            if await frame.query_selector("#submitButton"):
                await frame.click("#submitButton")
                clicked = True
            else:
                try:
                    # Try several alternatives scoped to the frame
                    await frame.click("a:has-text('Login')")
                    clicked = True
                except Exception:
                    try:
                        await frame.click("button:has-text('Login')")
                        clicked = True
                    except Exception:
                        logger.debug("Failed to find a visible login submit control to click in any frame")
        except Exception:
            logger.debug("Failed to click login submit control in frame")

        # After submit attempt, allow the site a moment to respond
        if clicked:
            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                await asyncio.sleep(1)
        else:
            try:
                # try pressing Enter to submit
                if await frame.query_selector('#j_password'):
                    await frame.press('#j_password', 'Enter')
                else:
                    await page.keyboard.press('Enter')
            except Exception:
                pass

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

    # Try several selectors for the quote button in nav_top
    selectors = ['#quoteButton','input[name="quoteButton"]','input[type="button"][value="Quote"]','button:has-text("Quote")','input[onclick*="doQuickFind"]']
    button = None
    for sel in selectors:
        try:
            b = await nav_frame.query_selector(sel)
            if b:
                button = b
                logger.info('Found quote button selector in nav_top: %s', sel)
                break
        except Exception:
            continue

    if button:
        try:
            await button.click()
            try:
                await page.wait_for_load_state('networkidle', timeout=5000)
            except Exception:
                await asyncio.sleep(1)
            return True
        except Exception:
            logger.debug('Failed to click quote button in nav_top')

    # Fallback: call doQuickFind() in nav_top only
    try:
        found = await nav_frame.evaluate("() => typeof doQuickFind !== 'undefined'")
        if found:
            logger.info('Calling doQuickFind in nav_top frame')
            try:
                await nav_frame.evaluate("() => doQuickFind(1, 'Delayed')")
                try:
                    await page.wait_for_load_state('networkidle', timeout=5000)
                except Exception:
                    await asyncio.sleep(1)
                return True
            except Exception:
                logger.debug('nav_top doQuickFind invocation failed')
    except Exception:
        pass

    logger.warning('Could not find markIdTextBox/quoteButton in nav_top frame')
    try:
        await dump_debug(page, f"quote_missing_nav_top_{ticker}")
    except Exception:
        logger.debug('dump_debug failed')

    return False



async def run(ticker: str = "NPN") -> int:
    try:
        async with async_playwright() as p:
            # Always run with a visible (non-headless) browser so the user can interact and "see" the page.
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context()
            page = await context.new_page()

            logger.info("Navigating to %s", TARGET_URL)
            await page.goto(TARGET_URL, wait_until="networkidle")

            logger.info("Page loaded. Keep the browser open to continue. Close the browser to exit.")

            # Optional login using credentials from .env
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
            try:
                if ticker:
                    logger.info("Attempting to fill and click quote for %s", ticker)
                    filled = await fill_and_click_quote(page, ticker=ticker)
                    if not filled:
                        logger.warning("Unable to fill or click quote for %s", ticker)
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
    parser.add_argument("--ticker", default="NPN", help="Ticker to enter into the markIdTextBox (default: NPN)")
    args = parser.parse_args()

    loop = asyncio.get_event_loop()
    exit_code = loop.run_until_complete(run(ticker=args.ticker))
    raise SystemExit(exit_code)
