import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.moneyweb.co.za"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

def _fetch_content(url):
    try:
        print(f"Fetching: {url}")
        resp = requests.get(url, headers=HEADERS, timeout=10)
        print(f"Status: {resp.status_code}")
        soup = BeautifulSoup(resp.content, "html.parser")
        div = soup.find("div", id="sens-content")
        if div:
            return div.get_text(separator="\n", strip=True)
        else:
            # Fallback check: look for ANY element with id='sens-content'
            any_div = soup.find(id="sens-content")
            if any_div:
                return any_div.get_text(separator="\n", strip=True)
            return "No content"
    except Exception as e:
        return str(e)

# URL from user's browser state
test_url = "https://www.moneyweb.co.za/mny_sens/nedbank-group-limited-dealings-in-securities-by-executive-directors-prescribed-officers-and-company-secretary/"

content = _fetch_content(test_url)
print("\n--- CONTENT ---")
print(content[:500] + "...")
print(f"\nSize: {len(content)}")
