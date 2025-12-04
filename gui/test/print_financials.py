import asyncio
import os
import sys
import logging
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

# Add playwright directory to path to import env
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'playwright_scraper'))

logger = logging.getLogger(__name__)

# Import credentials
try:
    from env import USERNAME, PASSWORD
except ImportError:
    logger.error("Error: env.py not found in playwright_scraper directory. Please check your setup.")
    sys.exit(1)

AUTH_FILE = os.path.join(os.path.dirname(__file__), '..', 'playwright_scraper', 'auth.json')
BASE_URL = "https://www.sharedata.co.za/v2/Scripts"

# Map IDs to readable names
TABLE_MAP = {
    "fin_I": "INCOME STATEMENT",
    "fin_B": "BALANCE SHEET",
    "fin_C": "CASH FLOW",
    "fin_S": "SHARE STATISTICS",
    "fin_R": "RATIOS"
}

async def ensure_comprehensive_data(page):
    """
    Finds the 'Highlights' checkbox and unchecks it to ensure 
    all financial rows are visible.
    """
    try:
        checkbox = page.locator("#CheckHighlights")
        if await checkbox.is_visible():
            if await checkbox.is_checked():
                await checkbox.uncheck()
                await asyncio.sleep(1) 
        else:
            pass
    except Exception as e:
        logger.exception("Error toggling highlights in view")

async def clean_and_print_data(html_content, ticker):
    """
    Extracts multiple financial tables by ID, cleans columns, and prints them.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    logger.info("%s", '\n' + ('='*60))
    logger.info("FINANCIAL REPORT: %s", ticker)
    logger.info("%s", ('='*60))

    data_found = False

    for table_id, table_name in TABLE_MAP.items():
        table = soup.find("table", id=table_id)
        
        if not table:
            continue
            
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        data_found = True
        logger.info("\n--- %s ---", table_name)

        # --- HEADER PROCESSING ---
        header_row = rows[0]
        
        # Extract text from headers
        headers = [th.get_text(strip=True).replace('\n', ' ') for th in header_row.find_all(["th", "td"])]
        
        # Identify the 'Growth' column index
        growth_idx = -1
        for i, h in enumerate(headers):
            if "Avg." in h or "Growth" in h or "Observed" in h:
                growth_idx = i
                break
        
        if growth_idx == -1 and len(headers) > 2:
            growth_idx = 1

        # 1. Remove Growth Column
        if growth_idx != -1:
            headers.pop(growth_idx)
            
        # 2. Rename the NEW 2nd column (Latest Year) to 'OF'
        if len(headers) > 1:
            headers[1] = "OF"
            
        # Print headers with spacing
        logger.info("%s", ' | '.join(headers))
        logger.info("%s", '-' * 60)

        # --- ROW PROCESSING ---
        for row in rows[1:]:
            if 'display: none' in str(row) or 'display:none' in str(row):
                continue

            cols = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
            
            if not cols: continue
            
            # Clean the row
            if growth_idx != -1 and len(cols) > growth_idx:
                cols.pop(growth_idx)
                
                logger.info("%s", ' | '.join(cols))
            
    if not data_found:
        logger.warning("No standard financial tables (fin_I, fin_B, etc.) found.")

async def handle_concurrent_login_dialog(page):
    """
    Handles the concurrent login detection dialog by dismissing it.
    """
    try:
        concurrent_dialog = page.locator("text='Concurrent Logins Detected'")
        if await concurrent_dialog.is_visible(timeout=3000):
            logger.warning("Concurrent login detected dialog found - dismissing...")
            
            close_button = page.locator("button.close, button:has-text('×')")
            if await close_button.is_visible(timeout=2000):
                await close_button.click()
                await asyncio.sleep(1)
                logger.info("Dialog dismissed")
            
    except Exception as e:
        pass

async def ensure_logged_in(page, context):
    await page.goto(f"{BASE_URL}/Home.aspx", wait_until="domcontentloaded")
    
    await handle_concurrent_login_dialog(page)
    
    if await page.is_visible("text='Login'", timeout=2000):
        logger.info("Logging in...")
        await page.click("text='Login'")
        await page.wait_for_selector("#LoginDialog", state="visible")
        await page.fill("#Branding_LblLoginEmail", USERNAME)
        await page.fill("#Branding_LblLoginPwd", PASSWORD)
        await page.click("#LoginDialog button:has-text('Login')")
        await page.wait_for_selector("#LoginDialog", state="hidden")
        
        await handle_concurrent_login_dialog(page)
        
        await context.storage_state(path=AUTH_FILE)
        logger.info("Logged in successfully.")
    else:
        logger.info("Already logged in.")

async def main():
    async with async_playwright() as p:
        logger.info("Launching browser...")
        browser = await p.chromium.launch(headless=False)
        context_options = {"storage_state": AUTH_FILE} if os.path.exists(AUTH_FILE) else {}
        context = await browser.new_context(**context_options)
        page = await context.new_page()
        
        await ensure_logged_in(page, context)
        
        tickers = ["ART"] 
        
        for ticker in tickers:
            logger.info("\n>>> Fetching %s...", ticker)
            target_url = f"{BASE_URL}/Results.aspx?c={ticker}&x=JSE"
            
            await page.goto(target_url, wait_until="domcontentloaded")
            
            await handle_concurrent_login_dialog(page)
            
            if "Home.aspx" in page.url:
                logger.error("FAILED: Redirected to Home.")
            else:
                await ensure_comprehensive_data(page)
                # Wait a bit for the DOM to update after unchecking highlights
                await asyncio.sleep(2)
                content = await page.content()
                await clean_and_print_data(content, ticker)
            
            await asyncio.sleep(1)

        logger.info("\nScraping Complete.")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
