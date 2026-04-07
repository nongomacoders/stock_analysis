import requests
from bs4 import BeautifulSoup

url = 'https://www.moneyweb.co.za/sens/ned-nedbank-group-ltd-availability-of-the-2023-annual-reports-and-pillar-3-report-notice-of-annual-general-meeting-and-no-change-to-summarised-annual-financial-results/'
headers = {"User-Agent": "Mozilla/5.0"}

try:
    resp = requests.get(url, headers=headers, timeout=10)
    soup = BeautifulSoup(resp.content, "html.parser")
    
    print("Checking for potential SENS containers:")
    
    # Check for monospaced blocks often used for SENS
    pre_tags = soup.find_all("pre")
    for i, pre in enumerate(pre_tags):
        print(f"PRE {i} size: {len(pre.get_text())}")
        if len(pre.get_text()) > 100:
            print(f"PRE {i} snippet: {pre.get_text()[:100]}...")

    # Check for divs with "sens" in class or ID
    for tag in soup.find_all(["div", "article"]):
        tid = tag.get("id", "")
        tcls = tag.get("class", [])
        if "sens" in str(tid).lower() or any("sens" in str(c).lower() for c in tcls):
            print(f"TAG: {tag.name} | ID: {tid} | CLASS: {tcls} | TEXT SIZE: {len(tag.get_text())}")
            
    # Check for specific Moneyweb classes
    content_divs = soup.find_all("div", class_="moneyweb-sens-content") # Guessing
    for div in content_divs:
        print(f"Found moneyweb-sens-content div, size: {len(div.get_text())}")

except Exception as e:
    print(f"Error: {e}")
