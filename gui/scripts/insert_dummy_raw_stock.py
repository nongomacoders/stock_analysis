import asyncio
import sys
import os
from datetime import date

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, ".."))
sys.path.append(project_root)

from core.db.engine import DBEngine

async def insert_dummy_data():
    print("Inserting dummy data for OPA.JO...")
    
    # Dummy data details
    # Period End: 30 June 2025
    # Release Date: 30 Sept 2025 (3 months later)
    # This will set next expected date to ~March 2026 (180 days later)
    
    query = """
        INSERT INTO raw_stock_valuations (
            ticker, 
            results_period_end, 
            results_period_label, 
            results_release_date,
            source,
            heps_12m_zarc,
            dividend_12m_zarc,
            cash_gen_ps_zarc,
            nav_ps_zarc
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9
        )
        ON CONFLICT (ticker, results_period_end) 
        DO UPDATE SET 
            results_release_date = EXCLUDED.results_release_date,
            source = EXCLUDED.source
    """
    
    try:
        await DBEngine.execute(
            query,
            "GCT.JO",
            date(2025, 6, 30),
            "Jun 2025 Interim (Dummy)",
            date(2025, 9, 30),
            "manual_dummy",
            0.0, 0.0, 0.0, 0.0 # Zero values for metrics
        )
        print("[SUCCESS] Dummy entry inserted for OPA.JO")
        
    except Exception as e:
        print(f"[ERROR] Failed to insert dummy data: {e}")
    finally:
        await DBEngine.close()

if __name__ == "__main__":
    asyncio.run(insert_dummy_data())
