import asyncio
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.db.engine import DBEngine

async def apply_view():
    print("Applying view...")
    try:
        with open(r"c:\Users\Dion\Desktop\Projects\GITHUBPROJECTS\stock_analysis\gui\architecture\view.sql", "r") as f:
            sql = f.read()
            # Remove the OWNER TO postgres line if it causes issues, or keep it. 
            # Usually safer to execute the CREATE OR REPLACE VIEW part.
            # Splitting by statement might be safer if there are multiple.
            # The file has CREATE OR REPLACE VIEW ... ; and ALTER TABLE ... ;
            
            await DBEngine.execute(sql)
            print("View applied successfully.")
    except Exception as e:
        print(f"Error applying view: {e}")

if __name__ == "__main__":
    asyncio.run(apply_view())
