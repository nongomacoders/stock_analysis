import requests
from bs4 import BeautifulSoup

url = "https://www.moneyweb.co.za/mny_sens/nedbank-group-limited-dealings-in-securities-by-executive-directors-prescribed-officers-and-company-secretary/"
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

try:
    resp = requests.get(url, headers=headers, timeout=10)
    soup = BeautifulSoup(resp.content, "html.parser")
    
    print("Checking Meta Tags:")
    for meta in soup.find_all("meta"):
        print(f"Name: {meta.get('name')} | Property: {meta.get('property')} | Content snippet: {str(meta.get('content'))[:100]}...")

    print("\nChecking Social Share Links:")
    for a in soup.find_all("a", href=True):
        if "linkedin" in a['href'].lower():
            print(f"LinkedIn Link: {a['href'][:200]}...")
            
    # Check for script tags that might contain data
    print("\nChecking Script tags for SENS data:")
    for script in soup.find_all("script"):
        if script.string and "SENS" in script.string:
            print(f"Script (match) size: {len(script.string)}")
            print(f"Snippet: {script.string[:200]}...")

except Exception as e:
    print(f"Error: {e}")
