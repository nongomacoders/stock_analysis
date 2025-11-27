import asyncio
import os
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

# Import credentials
try:
    from env import USERNAME, PASSWORD
except ImportError:
    print("Error: env.py not found. Please create it with USERNAME and PASSWORD.")
    exit()

AUTH_FILE = os.path.join(os.path.dirname(__file__), "auth.json")
BASE_URL = "https://www.sharedata.co.za/v2/Scripts"

# Map IDs to readable names
TABLE_MAP = {
    "fin_I": "INCOME STATEMENT",
    "fin_B": "BALANCE SHEET",
    "fin_C": "CASH FLOW",
    "fin_S": "SHARE STATISTICS",
    "fin_R": "RATIOS"
}

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

async def ensure_logged_in(page, context):
    await page.goto(f"{BASE_URL}/Home.aspx", wait_until="domcontentloaded")
    await handle_concurrent_login_dialog(page)
    
    if await page.is_visible("text='Login'", timeout=2000):
        await page.click("text='Login'")
        await page.wait_for_selector("#LoginDialog", state="visible")
        await page.fill("#Branding_LblLoginEmail", USERNAME)
        await page.fill("#Branding_LblLoginPwd", PASSWORD)
        await page.click("#LoginDialog button:has-text('Login')")
        await page.wait_for_selector("#LoginDialog", state="hidden")
        await handle_concurrent_login_dialog(page)
        await context.storage_state(path=AUTH_FILE)

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
    except Exception as e:
        print(f"   [View] Error toggling highlights: {e}")

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
            context_options = {"storage_state": AUTH_FILE} if os.path.exists(AUTH_FILE) else {}
            context = await browser.new_context(**context_options)
            page = await context.new_page()
            
            await ensure_logged_in(page, context)
            
            target_url = f"{BASE_URL}/Results.aspx?c={clean_ticker}&x=JSE"
            await page.goto(target_url, wait_until="networkidle", timeout=30000)
            await handle_concurrent_login_dialog(page)
            
            if "Home.aspx" in page.url:
                await browser.close()
                return None
            
            # --- PHASE 1: SCRAPE FINALS (Default View) ---
            # Wait for data
            try:
                await page.wait_for_selector("table[id^='fin_']", state="visible", timeout=10000)
            except:
                print(f"Warning: Financial tables not found for {clean_ticker}")
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
            
    except Exception as e:
        print(f"Error scraping {ticker}: {e}")
        import traceback
        traceback.print_exc()
        return None

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context_options = {"storage_state": AUTH_FILE} if os.path.exists(AUTH_FILE) else {}
        context = await browser.new_context(**context_options)
        page = await context.new_page()
        
        await ensure_logged_in(page, context)
        
        tickers = ["NPN"] 
        
        for ticker in tickers:
            print(f"\n>>> Fetching {ticker}...")
            target_url = f"{BASE_URL}/Results.aspx?c={ticker}&x=JSE"
            
            await page.goto(target_url, wait_until="domcontentloaded")
            
            # Check for concurrent login dialog
            await handle_concurrent_login_dialog(page)
            
            if "Home.aspx" in page.url:
                print(f"❌ Failed. Redirected to Home.")
            else:
                await ensure_comprehensive_data(page)
                content = await page.content()
                await clean_and_print_data(content, ticker)
            
            await asyncio.sleep(1)

        print("\n✅ Scraping Complete.")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())