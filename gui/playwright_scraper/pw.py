import asyncio
import os
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import logging
from datetime import datetime

# Load credentials from .env file
load_dotenv()
USERNAME = os.getenv("STOCK_USERNAME")
PASSWORD = os.getenv("STOCK_PASSWORD")

if not USERNAME or not PASSWORD:
    logging.error("Error: STOCK_USERNAME and STOCK_PASSWORD must be set in .env file")
    exit()

AUTH_FILE = os.path.join(os.path.dirname(__file__), "auth.json")
BASE_URL = "https://www.sharedata.co.za/v2/Scripts"
DEBUG_DIR = os.path.join(os.path.dirname(__file__), "debug")
DEBUG_DUMPS_ENABLED = os.getenv("SHAREDATA_DEBUG_DUMPS", "0") == "1"

# Map IDs to readable names
TABLE_MAP = {
    "fin_I": "INCOME STATEMENT",
    "fin_B": "BALANCE SHEET",
    "fin_C": "CASH FLOW",
    "fin_S": "SHARE STATISTICS",
    "fin_R": "RATIOS"
}


def _infer_access_issue_from_html(html: str) -> str | None:
    if not html:
        return None
    lower = html.lower()

    if "you need a" in lower and "premium" in lower and "subscription" in lower:
        return "premium subscription required for Results.aspx"
    if "you have not accepted the terms of use" in lower and "conditions of subscription" in lower:
        return "terms not accepted (Terms of Use / Conditions of Subscription)"
    if "you need to be logged on as a" in lower and "free registered user" in lower:
        return "not logged in (or session not recognized for this link)"
    if "concurrent" in lower and "login" in lower:
        return "concurrent login detected (single-workstation restriction)"

    return None

async def handle_concurrent_login_dialog(page):
    """Dismiss concurrent login dialog if it appears."""
    try:
        concurrent_dialog = page.locator("text='Concurrent Logins Detected'")
        if await concurrent_dialog.is_visible(timeout=2000):
            close_button = page.locator("button.close, button:has-text('×')")
            if await close_button.is_visible(timeout=2000):
                await close_button.click()
                await asyncio.sleep(0.5)
    except Exception:
        pass


def _safe_filename(s: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in s)[:120]


async def _dump_debug(page, label: str):
    """Dump useful artifacts for debugging redirect/login issues."""
    if not DEBUG_DUMPS_ENABLED:
        return
    try:
        os.makedirs(DEBUG_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = os.path.join(DEBUG_DIR, f"{ts}_{_safe_filename(label)}")

        # Best-effort title + URL logging
        try:
            title = await page.title()
        except Exception:
            title = "(title unavailable)"
        logging.getLogger(__name__).warning("[PW DEBUG] %s url=%s title=%s", label, page.url, title)

        try:
            await page.screenshot(path=base + ".png", full_page=True)
        except Exception:
            pass
        try:
            html = await page.content()
            with open(base + ".html", "w", encoding="utf-8") as f:
                f.write(html)
        except Exception:
            pass
    except Exception:
        logging.getLogger(__name__).exception("[PW DEBUG] Failed to dump debug artifacts")


async def _goto_with_debug(page, url: str, label: str, wait_until: str = "domcontentloaded", timeout: int = 30000):
    """Navigate and log response status/final URL (helps diagnose redirects)."""
    logger = logging.getLogger(__name__)
    logger.info("[PW] GOTO(%s): %s", label, url)
    response = None
    try:
        response = await page.goto(url, wait_until=wait_until, timeout=timeout)
    except Exception:
        logger.exception("[PW] GOTO failed (%s): %s", label, url)
        await _dump_debug(page, f"goto_failed_{label}")
        raise

    try:
        status = response.status if response is not None else None
        resp_url = response.url if response is not None else None
        logger.info("[PW] GOTO(%s) status=%s response_url=%s final_url=%s", label, status, resp_url, page.url)
    except Exception:
        pass

    return response

async def ensure_logged_in(page, context):
    await _goto_with_debug(page, f"{BASE_URL}/Home.aspx", label="home")
    await handle_concurrent_login_dialog(page)
    
    # ShareData UI sometimes changes wording; try a couple of selectors.
    login_visible = False
    for sel in ("text='Login'", "text='Log in'", "#BtnLogin", "a:has-text('Login')"):
        try:
            if await page.is_visible(sel, timeout=1000):
                login_visible = True
                await page.click(sel)
                break
        except Exception:
            continue

    if login_visible:
        await page.wait_for_selector("#LoginDialog", state="visible")
        await page.fill("#Branding_LblLoginEmail", USERNAME)
        await page.fill("#Branding_LblLoginPwd", PASSWORD)
        await page.click("#LoginDialog button:has-text('Login')")
        await page.wait_for_selector("#LoginDialog", state="hidden")
        await handle_concurrent_login_dialog(page)
        await context.storage_state(path=AUTH_FILE)
        logging.getLogger(__name__).info("[PW] Logged in as %s and saved storage_state.", USERNAME)
    else:
        # Already logged in (or UI changed). Record state for debugging.
        logging.getLogger(__name__).info("[PW] Login button not visible; assuming already logged in.")


async def logout_sharedata(headless: bool = True) -> bool:
    """Best-effort logout to avoid concurrent-login lockouts on subsequent runs."""
    logger = logging.getLogger(__name__)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            if os.path.exists(AUTH_FILE):
                context = await browser.new_context(storage_state=AUTH_FILE)
            else:
                context = await browser.new_context()
            page = await context.new_page()

            await _goto_with_debug(page, f"{BASE_URL}/Home.aspx", label="logout_home", wait_until="domcontentloaded")
            await handle_concurrent_login_dialog(page)

            # If we can find a logout control, click it.
            logout_clicked = False
            for sel in (
                "text=Logout",
                "td:has-text('Logout')",
                "a:has-text('Logout')",
            ):
                try:
                    loc = page.locator(sel).first
                    if await loc.is_visible(timeout=1500):
                        await loc.click()
                        logout_clicked = True
                        break
                except Exception:
                    continue

            if logout_clicked:
                try:
                    await page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass

                # Persist the logged-out state (keep auth.json, but remove the active session).
                try:
                    await context.storage_state(path=AUTH_FILE)
                except Exception:
                    pass

                logger.info("[PW] Logged out of ShareData.")
                await browser.close()
                return True

            logger.info("[PW] Logout control not found; skipping logout.")
            await browser.close()
            return False
    except Exception:
        logger.exception("[PW] Logout failed")
        return False

async def ensure_comprehensive_data(page):
    """
    Finds the 'Highlights' checkbox and unchecks it.
    This must be called every time the data view changes (Final vs Interim).
    """
    try:
        checkbox = page.locator("#CheckHighlights")
        if await checkbox.is_visible():
            if await checkbox.is_checked():
                await checkbox.uncheck()
                # Brief pause to allow table rows to expand
                await asyncio.sleep(1) 
    except Exception:
        logging.exception("Error toggling highlights in view")

async def extract_current_tables(page):
    """Extracts the HTML of the financial tables currently visible on the page."""
    html_content = await page.content()
    soup = BeautifulSoup(html_content, 'html.parser')
    tables = {}
    
    for table_id in TABLE_MAP.keys():
        table = soup.find("table", id=table_id)
        if table:
            tables[table_id] = str(table)
    return tables

async def scrape_ticker_fundamentals(ticker: str):
    """
    Scrape ShareData for ticker fundamentals (BOTH Final and Interim).
    
    Returns a LIST of dictionaries containing table HTML:
    [
        { "fin_S": "<table>...Finals...</table>", ... },
        { "fin_S": "<table>...Interims...</table>", ... }
    ]
    """
    clean_ticker = ticker.replace('.JO', '').replace('.jo', '')
    results_sets = []

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            if os.path.exists(AUTH_FILE):
                context = await browser.new_context(storage_state=AUTH_FILE)
            else:
                context = await browser.new_context()
            page = await context.new_page()

            # Log key navigation events (helps diagnose silent redirects)
            try:
                page.on("framenavigated", lambda frame: logging.getLogger(__name__).debug("[PW] NAV frame=%s url=%s", getattr(frame, "name", "?"), frame.url))
            except Exception:
                pass
            
            await ensure_logged_in(page, context)
            
            target_url = f"{BASE_URL}/Results.aspx?c={clean_ticker}&x=JSE"
            await _goto_with_debug(page, target_url, label=f"results_{clean_ticker}", wait_until="networkidle", timeout=30000)
            await handle_concurrent_login_dialog(page)
            
            if "Home.aspx" in page.url:
                reason = None
                try:
                    reason = _infer_access_issue_from_html(await page.content())
                except Exception:
                    reason = None

                if reason:
                    logging.getLogger(__name__).warning(
                        "[PW] Redirected to Home.aspx after navigating to Results for %s (%s).",
                        clean_ticker,
                        reason,
                    )
                else:
                    logging.getLogger(__name__).warning(
                        "[PW] Redirected to Home.aspx after navigating to Results for %s. Likely not authenticated/subscribed or site changed.",
                        clean_ticker,
                    )
                await _dump_debug(page, f"redirected_home_{clean_ticker}")
                await browser.close()
                return None

            # Some failures land on a login page without the Home.aspx URL.
            try:
                if await page.is_visible("#LoginDialog", timeout=1000) or await page.is_visible("text='Login'", timeout=1000):
                    logging.getLogger(__name__).warning("[PW] Appears to be logged out after Results navigation for %s.", clean_ticker)
                    await _dump_debug(page, f"redirected_login_{clean_ticker}")
            except Exception:
                pass
            
            # --- PHASE 1: SCRAPE FINALS (Default View) ---
            # Wait for data
            try:
                await page.wait_for_selector("table[id^='fin_']", state="visible", timeout=10000)
            except:
                logging.warning("Financial tables not found for %s", clean_ticker)
                await _dump_debug(page, f"tables_missing_{clean_ticker}")
                await browser.close()
                return None

            # Ensure Highlights off for Finals
            await ensure_comprehensive_data(page)
            await asyncio.sleep(1) # Extra buffer for rendering
            
            final_tables = await extract_current_tables(page)
            if final_tables:
                results_sets.append(final_tables)
                
            # --- PHASE 2: SCRAPE INTERIMS ---
            # Uncheck Final, Check Interim
            # Triggers LoadFinancials() JS
            
            # 1. Uncheck Final
            if await page.is_checked("#CheckFinal"):
                await page.uncheck("#CheckFinal")
            
            # 2. Check Interim
            await page.check("#CheckInterim")
            
            # 3. Wait for data reload. 
            # We wait for network idle or a specific element state change.
            # Since the DOM updates, a simple sleep is often safest after a network idle.
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2) 
            
            # 4. Ensure Highlights off for Interims (Preferences might reset on reload)
            await ensure_comprehensive_data(page)
            
            interim_tables = await extract_current_tables(page)
            if interim_tables:
                results_sets.append(interim_tables)

            await browser.close()
            
            return results_sets if results_sets else None
            
    except Exception:
        logging.exception("Error scraping %s", ticker)
        return None
