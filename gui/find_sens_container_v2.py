import requests
from bs4 import BeautifulSoup

url = 'https://www.moneyweb.co.za/sens/ned-nedbank-group-ltd-availability-of-the-2023-annual-reports-and-pillar-3-report-notice-of-annual-general-meeting-and-no-change-to-summarised-annual-financial-results/'
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

try:
    resp = requests.get(url, headers=headers, timeout=10)
    print(f"Status Code: {resp.status_code}")
    soup = BeautifulSoup(resp.content, "html.parser")
    
    # Print outer most structures
    print("Main containers:")
    for tag in soup.find_all(['main', 'article']):
        print(f"Container: {tag.name} | ID: {tag.get('id')} | Class: {tag.get('class')}")

    # Look for the text specifically
    # SENS usually has "SENS" or "REGULATORY" in it
    for tag in soup.find_all(['div', 'pre', 'p']):
        text = tag.get_text(strip=True)
        if len(text) > 1000: # Typical SENS size
            print(f"LARGE TAG: {tag.name} | ID: {tag.get('id')} | CLS: {tag.get('class')} | SIZE: {len(text)}")
            print(f"Snippet: {text[:200]}...")

except Exception as e:
    print(f"Error: {e}")
