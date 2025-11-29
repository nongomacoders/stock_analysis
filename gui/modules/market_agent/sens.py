import requests
from bs4 import BeautifulSoup
from datetime import datetime
import threading
from core.db.engine import DBEngine
from core.config import DB_CONFIG


BASE_URL = "https://www.moneyweb.co.za"
LIST_URL = f"{BASE_URL}/tools-and-data/moneyweb-sens/"
HEADERS = {"User-Agent": "Mozilla/5.0"}


async def run_sens_check():
    """Main SENS scraping logic."""
    print(f"\n[{datetime.now().strftime('%H:%M')}] --- Running SENS Check ---")

    # 1. Fetch Tickers
    q_tickers = "SELECT ticker FROM stock_details"
    rows = await DBEngine.fetch(q_tickers)
    db_tickers = {r["ticker"].replace(".JO", "") for r in rows}

    if not db_tickers:
        return

    # 2. Scrape List
    try:
        resp = requests.get(LIST_URL, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.content, "html.parser")
        sens_rows = soup.find_all("div", class_="sens-row")
    except Exception as e:
        print(f"SENS HTTP Error: {e}")
        return

    new_items = []

    for row in sens_rows:
        try:
            ticker = row.find(
                "a", title="Visit Click a company for this listing"
            ).get_text(strip=True)
            if ticker not in db_tickers:
                continue

            time_str = row.find("time").get_text(strip=True)
            pub_date = _parse_date(time_str)
            if not pub_date:
                continue

            # Check DB
            exists_q = (
                "SELECT 1 FROM SENS WHERE ticker = $1 AND publication_datetime = $2"
            )
            exists = await DBEngine.fetch(exists_q, f"{ticker}.JO", pub_date)
            if exists:
                continue

            # Fetch Content
            link = row.find("a", title="Go to SENS announcement")["href"]
            if link.startswith("/"):
                link = BASE_URL + link

            content = _fetch_content(link)

            # Insert
            ins_q = "INSERT INTO SENS (ticker, publication_datetime, content) VALUES ($1, $2, $3)"
            await DBEngine.execute(ins_q, f"{ticker}.JO", pub_date, content)

            print(f"  -> NEW SENS: {ticker} @ {time_str}")
            new_items.append((f"{ticker}.JO", content))

        except Exception as e:
            print(f"Error processing row: {e}")

    # Trigger AI
    import modules.analysis.engine as ai_engine

    # Inside run_sens_check loop:
    for t_full, content in new_items:
        # We await it directly. Since this is an async function,
        # it runs cooperatively within the event loop.
        await ai_engine.analyze_new_sens(t_full, content)


def _parse_date(s):
    try:
        return datetime.strptime(s, "%d.%m.%y %H:%M")
    except:
        return None


def _fetch_content(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.content, "html.parser")
        div = soup.find("div", id="sens-content")
        return div.get_text(separator="\n", strip=True) if div else "No content"
    except Exception as e:
        return str(e)
