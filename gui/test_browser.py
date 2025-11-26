"""
Quick debug script to test the browser/scraping issue
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
sys.path.append(os.path.join(os.path.dirname(__file__), 'playwright'))

async def test_import():
    print("Testing imports...")
    
    # Test 1: Can we import pw module?
    try:
        from pw import scrape_ticker_fundamentals
        print("[OK] Successfully imported scrape_ticker_fundamentals from pw module")
    except ImportError as e:
        print(f"[FAIL] Failed to import pw module: {e}")
        return False
    
    # Test 2: Can we call the function?
    try:
        print("\nTesting scrape for NPN...")
        result = await scrape_ticker_fundamentals('NPN')
        
        if result:
            print(f"[OK] Scraping succeeded! Found tables: {list(result.keys())}")
            return True
        else:
            print("[FAIL] Scraping returned None")
            return False
            
    except Exception as e:
        print(f"[FAIL] Error during scraping: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_import())
    
    if success:
        print("\n[SUCCESS] Test passed - browser and scraping are working")
    else:
        print("\n[WARNING] Test failed - there's an issue with the browser or imports")
