import os
import logging
from pathlib import Path
from dotenv import load_dotenv, set_key
from google import genai

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def initialize_master_store():
    # 1. Load existing .env
    env_path = Path(".env")
    load_dotenv(env_path)
    
    api_key = os.getenv("GOOGLE_API_KEY")
    current_store_id = os.getenv("GEMINI_MASTER_STORE_ID")
    
    if not api_key:
        logger.error("GOOGLE_API_KEY not found in .env. Please add it first.")
        return

    client = genai.Client(api_key=api_key)

    # 2. Verify if the existing ID is still valid
    if current_store_id:
        try:
            client.file_search_stores.get(name=current_store_id)
            logger.info(f"✅ Found existing valid Master Store: {current_store_id}")
            return current_store_id
        except Exception:
            logger.warning(f"⚠️ Store ID in .env ({current_store_id}) is no longer valid or was deleted.")

    # 3. Create a brand new Master Store
    logger.info("🚀 Creating a new Permanent Master Store...")
    try:
        new_store = client.file_search_stores.create(
            config={"display_name": "Stock-Analysis-Master-Library"}
        )
        new_id = new_store.name
        
        # 4. Automatically update the .env file
        set_key(str(env_path), "GEMINI_MASTER_STORE_ID", new_id)
        
        logger.info("-" * 50)
        logger.info(f"✨ SUCCESS! New Master Store Created: {new_id}")
        logger.info(f"📝 Updated .env file at: {env_path.absolute()}")
        logger.info("-" * 50)
        return new_id
        
    except Exception as e:
        logger.error(f"❌ Failed to create Master Store: {e}")
        return None

if __name__ == "__main__":
    initialize_master_store()