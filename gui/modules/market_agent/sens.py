import requests
from bs4 import BeautifulSoup
from datetime import datetime
import threading
from core.db.engine import DBEngine
from core.config import DB_CONFIG
import logging

logger = logging.getLogger(__name__)


BASE_URL = "https://www.moneyweb.co.za"
LIST_URL = f"{BASE_URL}/tools-and-data/moneyweb-sens/"
HEADERS = {"User-Agent": "Mozilla/5.0"}


async def run_sens_check() -> None:
    """Main SENS scraping logic."""
    logger.info("\n[%s] --- Running SENS Check ---", datetime.now().strftime('%H:%M'))

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
    except Exception:
        logger.exception("SENS HTTP Error")
        return

    new_items = []

    for row in sens_rows:
        try:
            ticker_link = row.find(
                "a", title="Visit Click a company for this listing"
            )
            if not ticker_link:
                continue
                
            ticker = ticker_link.get_text(strip=True)
            if ticker not in db_tickers:
                continue

            time_elem = row.find("time")
            if not time_elem:
                continue

            pub_date = _parse_date(time_elem)
            if not pub_date:
                continue

            # Link exists and not in DB?
            link_elem = row.find("a", title="Go to SENS announcement")
            if not link_elem:
                continue
                
            link = link_elem["href"]
            if link.startswith("/"):
                link = BASE_URL + link

            content = _fetch_content(link)
            if not content:
                logger.info("  -> NO CONTENT for %s @ %s (skipping)", ticker, pub_date)
                continue

            # Check if this specific SENS already exists in DB (to avoid double AI calls)
            check_q = "SELECT 1 FROM SENS WHERE ticker = $1 AND publication_datetime = $2 AND md5(content) = md5($3)"
            exists = await DBEngine.fetch(check_q, f"{ticker}.JO", pub_date, content)
            if exists:
                logger.info("  -> SENS ALREADY EXISTS: %s @ %s (skipping)", ticker, pub_date)
                continue

            # Trigger AI FIRST
            import modules.analysis.engine as ai_engine
            try:
                # We await AI analysis. If this fails (raises exception), 
                # we don't proceed to insert into SENS table.
                await ai_engine.analyze_new_sens(f"{ticker}.JO", content)
                
                # If AI was successful, NOW insert into SENS
                # Use ON CONFLICT DO NOTHING as a final safety check
                ins_q = """
                    INSERT INTO SENS (ticker, publication_datetime, content) 
                    VALUES ($1, $2, $3)
                    ON CONFLICT DO NOTHING
                """
                await DBEngine.execute(ins_q, f"{ticker}.JO", pub_date, content)

                logger.info("  -> NEW SENS PROCESSED: %s @ %s", ticker, pub_date)
            except Exception as e:
                logger.error("  -> AI FAILED for %s, skipping DB entry: %s", ticker, e)
                continue

        except Exception:
            logger.exception("Error processing row")

    if not new_items:
        logger.info("No new SENS announcements found.")


def _parse_date(elem) -> datetime | None:
    # Try datetime attribute first (ISO 8601)
    if elem.has_attr("datetime"):
        try:
            dt = datetime.fromisoformat(elem["datetime"])
            # Return naive datetime to match previous behavior/DB expectation
            return dt.replace(tzinfo=None)
        except ValueError:
            pass

    # Fallback to text parsing
    try:
        # Use separator=" " to ensure "Date Time" not "DateTime"
        text = elem.get_text(separator=" ", strip=True)
        return datetime.strptime(text, "%d.%m.%y %H:%M")
    except Exception:
        return None


def _fetch_content(url: str) -> str | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.content, "html.parser")
        div = soup.find("div", id="sens-content")
        if not div:
            return None
        content = div.get_text(separator="\n", strip=True)
        return content if content else None
    except Exception as e:
        logger.error("Error fetching SENS content from %s: %s", url, e)
        return None
