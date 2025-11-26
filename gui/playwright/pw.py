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

AUTH_FILE = "auth.json"
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
        print(f"   [View] Error toggling highlights: {e}")

async def clean_and_print_data(html_content, ticker):
    """
    Extracts multiple financial tables by ID, cleans columns, and prints them.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    print(f"\n{'='*60}")
    print(f"📊 FINANCIAL REPORT: {ticker}")
    print(f"{'='*60}")

    data_found = False

    for table_id, table_name in TABLE_MAP.items():
        table = soup.find("table", id=table_id)
        
        if not table:
            continue
            
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        data_found = True
        print(f"\n--- {table_name} ---")

        # --- HEADER PROCESSING ---
        # We need to handle the "Avg. Growth" / "Observed" column dynamically
        header_row = rows[0] # Usually row 0 or 1 contains the main headers
        
        # Extract text from headers
        headers = [th.get_text(strip=True).replace('\n', ' ') for th in header_row.find_all(["th", "td"])]
        
        # Identify the 'Growth' column index (usually index 1)
        growth_idx = -1
        for i, h in enumerate(headers):
            if "Avg." in h or "Growth" in h or "Observed" in h:
                growth_idx = i
                break
        
        # If no explicit name match, assume index 1 if it's a % column (heuristic)
        if growth_idx == -1 and len(headers) > 2:
            growth_idx = 1

        # 1. Remove Growth Column
        if growth_idx != -1:
            headers.pop(growth_idx)
            
        # 2. Rename the NEW 2nd column (Latest Year) to 'OF'
        if len(headers) > 1:
            headers[1] = "OF"
            
        print(headers)

        # --- ROW PROCESSING ---
        # Start from the row after headers. 
        # In your HTML, row 0 is headers. Data starts at row 1.
        for row in rows[1:]:
            # Skip rows that are hidden (display: none) if BeautifulSoup picked them up
            if 'display: none' in str(row) or 'display:none' in str(row):
                continue

            cols = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
            
            if not cols: continue
            
            # Clean the row: Remove the same index we removed from headers
            if growth_idx != -1 and len(cols) > growth_idx:
                cols.pop(growth_idx)
                
            print(cols)
            
    if not data_found:
        print("⚠️  No standard financial tables (fin_I, fin_B, etc.) found.")

async def handle_concurrent_login_dialog(page):
    """
    Handles the concurrent login detection dialog by dismissing it.
    
    The dialog shows when ShareData detects a login from another computer.
    This function clicks the X button to close the dialog and continue.
    """
    try:
        # Wait for the concurrent login dialog (with short timeout)
        concurrent_dialog = page.locator("text='Concurrent Logins Detected'")
        if await concurrent_dialog.is_visible(timeout=3000):
            print("⚠️  Concurrent login detected dialog found - dismissing...")
            
            # Try to close the dialog by clicking the X button
            close_button = page.locator("button.close, button:has-text('×')")
            if await close_button.is_visible(timeout=2000):
                await close_button.click()
                await asyncio.sleep(1)
                print("✓ Dialog dismissed")
            
            # Alternative: If there's a specific close/OK button
            # await page.click("button:has-text('OK')")
            
    except Exception as e:
        # No dialog found or already closed - this is fine
        pass

async def ensure_logged_in(page, context):
    await page.goto(f"{BASE_URL}/Home.aspx", wait_until="domcontentloaded")
    
    # Check for concurrent login dialog first
    await handle_concurrent_login_dialog(page)
    
    if await page.is_visible("text='Login'", timeout=2000):
        await page.click("text='Login'")
        await page.wait_for_selector("#LoginDialog", state="visible")
        await page.fill("#Branding_LblLoginEmail", USERNAME)
        await page.fill("#Branding_LblLoginPwd", PASSWORD)
        await page.click("#LoginDialog button:has-text('Login')")
        await page.wait_for_selector("#LoginDialog", state="hidden")
        
        # Check again after login in case dialog appears
        await handle_concurrent_login_dialog(page)
        
        await context.storage_state(path=AUTH_FILE)

async def scrape_ticker_fundamentals(ticker: str):
    """
    Scrape ShareData for ticker fundamentals.
    
    Returns dict with table HTML:
    {
        "fin_S": "<table>...</table>",
        "fin_R": "<table>...</table>",
        ...
    }
    
    or None on failure.
    
    Handles login, navigation, and full data view automatically.
    """
    try:
        # Strip .JO suffix if present (ShareData expects just the ticker code)
        clean_ticker = ticker.replace('.JO', '').replace('.jo', '')
        
        async with async_playwright() as p:
            # Use headless=False to avoid anti-bot detection
            browser = await p.chromium.launch(headless=False)
            context_options = {"storage_state": AUTH_FILE} if os.path.exists(AUTH_FILE) else {}
            context = await browser.new_context(**context_options)
            page = await context.new_page()
            
            await ensure_logged_in(page, context)
            
            target_url = f"{BASE_URL}/Results.aspx?c={clean_ticker}&x=JSE"
            
            # Navigate and wait for network to be idle (all resources loaded)
            await page.goto(target_url, wait_until="networkidle", timeout=30000)
            
            # Check for concurrent login dialog after navigation
            await handle_concurrent_login_dialog(page)
            
            if "Home.aspx" in page.url:
                await browser.close()
                return None
            
            # Wait for at least one financial table to be visible
            try:
                await page.wait_for_selector("table[id^='fin_']", state="visible", timeout=10000)
            except:
                print(f"Warning: Financial tables not found for {clean_ticker}")
                await browser.close()
                return None
            
            await ensure_comprehensive_data(page)
            
            # Give extra time for data to render after unchecking highlights
            await asyncio.sleep(2)
            
            html_content = await page.content()
            
            # Parse HTML and extract tables
            soup = BeautifulSoup(html_content, 'html.parser')
            tables = {}
            
            for table_id in TABLE_MAP.keys():
                table = soup.find("table", id=table_id)
                if table:
                    tables[table_id] = str(table)
            
            await browser.close()
            
            return tables if tables else None
            
    except Exception as e:
        print(f"Error scraping {ticker}: {e}")
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