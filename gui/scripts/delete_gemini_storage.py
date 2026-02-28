import os, requests, time, logging

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

API_KEY = os.getenv("GOOGLE_API_KEY")
BASE = "https://generativelanguage.googleapis.com/v1beta"
PARAMS = {"key": API_KEY}


def total_annihilation():
    while True:
        # 1. Fetch current batch of stores
        res = requests.get(f"{BASE}/fileSearchStores", params=PARAMS)
        stores = res.json().get("fileSearchStores", [])

        if not stores:
            logger.info("✨ PROJECT IS CLEAN: No more stores found.")
            break

        logger.info(f"Found {len(stores)} stores in this batch. Purging...")

        for store in stores:
            s_name = store["name"]
            logger.info(f"--- Purging: {s_name} ---")

            # 2. List and Force Purge Documents
            docs_res = requests.get(f"{BASE}/{s_name}/documents", params=PARAMS)
            for doc in docs_res.json().get("documents", []):
                requests.delete(
                    f"{BASE}/{doc['name']}", params={"key": API_KEY, "force": "true"}
                )

            # 3. Delete the Store container
            requests.delete(f"{BASE}/{s_name}", params=PARAMS)
            time.sleep(1)  # Small delay to let the backend catch up

        logger.info("Batch complete. Checking for next page...")
        time.sleep(2)


if __name__ == "__main__":
    total_annihilation()
