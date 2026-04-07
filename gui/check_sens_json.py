import requests
from bs4 import BeautifulSoup
import json

url = "https://www.moneyweb.co.za/mny_sens/nedbank-group-limited-dealings-in-securities-by-executive-directors-prescribed-officers-and-company-secretary/"
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

try:
    resp = requests.get(url, headers=headers, timeout=10)
    soup = BeautifulSoup(resp.content, "html.parser")
    
    print("Checking JSON-LD:")
    scripts = soup.find_all("script", type="application/ld+json")
    for i, script in enumerate(scripts):
        try:
            data = json.loads(script.string)
            print(f"JSON-LD {i} type: {data.get('@type') or data.get('@graph', [{}])[0].get('@type')}")
            # If it's an article, print description or body
            if isinstance(data, dict):
                print(f"Description: {data.get('description') or 'None'}")
                print(f"ArticleBody: {data.get('articleBody') or 'None'}")
        except:
            pass

    # Generic search for strings that look like SENS content
    print("\nSearching for large text blocks in any tag:")
    for tag in soup.find_all(True):
        if tag.string and len(tag.string) > 500:
             print(f"Tag: {tag.name} | Size: {len(tag.string)} | Text: {tag.string[:100]}...")

except Exception as e:
    print(f"Error: {e}")
