import os, requests, logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_KEY = os.getenv("GOOGLE_API_KEY")
BASE = "https://generativelanguage.googleapis.com/v1beta"

def check_real_quota():
    params = {'key': API_KEY}
    # We fetch a store to see its sizeBytes
    res = requests.get(f"{BASE}/fileSearchStores", params=params)
    stores = res.json().get('fileSearchStores', [])
    
    total_bytes = 0
    for s in stores:
        size = int(s.get('sizeBytes', 0))
        total_bytes += size
        logger.info(f"Store: {s['name']} | Size: {size / 1024 / 1024:.2f} MB")
    
    logger.info("-" * 30)
    logger.info(f"TOTAL STORAGE USED: {total_bytes / 1024 / 1024:.2f} MB / 1000 MB")

if __name__ == "__main__":
    check_real_quota()