import os, requests, time, logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

API_KEY = os.getenv("GOOGLE_API_KEY")
BASE = "https://generativelanguage.googleapis.com/v1beta"

def total_reclamation():
    params = {'key': API_KEY}
    
    # 1. Get ALL stores
    res = requests.get(f"{BASE}/fileSearchStores", params=params)
    stores = res.json().get('fileSearchStores', [])
    
    logger.info(f"Found {len(stores)} stores. Initiating Force Purge...")

    for store in stores:
        s_name = store['name']
        logger.info(f"--- Processing: {s_name} ---")

        # 2. List Documents
        docs_res = requests.get(f"{BASE}/{s_name}/documents", params=params)
        docs = docs_res.json().get('documents', [])

        for doc in docs:
            d_name = doc['name']
            # FORCE DELETE: We add force=true to the URL parameters
            # This is the 'Secret Sauce' from the GitHub bug report
            force_params = {'key': API_KEY, 'force': 'true'}
            
            logger.info(f"  [FORCE] Deleting Document: {d_name}")
            del_res = requests.delete(f"{BASE}/{d_name}", params=force_params)
            
            if del_res.status_code not in [200, 204]:
                logger.warning(f"  Failed Document Force-Delete: {del_res.text}")

        # 3. Aggressive Wait
        # Even with force=true, the metadata counter takes a heartbeat to update
        time.sleep(3)
        
        # 4. Final Store Delete
        final = requests.delete(f"{BASE}/{s_name}", params=params)
        if final.status_code in [200, 204]:
            logger.info(f"  ✅ SUCCESS: {s_name} deleted.")
        else:
            # If it still fails, the API might need one more 'nudge'
            logger.warning(f"  ❌ STILL BUSY: {s_name}. (Will require 24h garbage collection)")

if __name__ == "__main__":
    total_reclamation()