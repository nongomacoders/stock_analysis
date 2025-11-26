"""
Test script for Raw Fundamentals Loader

This script:
1. Creates the raw_stock_valuations table (if not exists)
2. Runs the Raw Fundamentals Loader for NPN and ABG
3. Verifies the data was inserted correctly
4. Runs the Valuation Engine to test integration

Usage:
    python test_raw_fundamentals.py
"""

import asyncio
import sys
import os

# Ensure we can import local modules
sys.path.insert(0, os.path.dirname(__file__))

from db_layer import DBLayer
from raw_fundamentals_loader import RawFundamentalsLoader
from valuation_engine import ValuationEngine


async def create_table():
    """Create the raw_stock_valuations table"""
    print("Step 1: Creating raw_stock_valuations table...")
    
    db = DBLayer()
    await db.init_pool()
    
    # Read and execute SQL file
    sql_path = os.path.join(os.path.dirname(__file__), 'sql', 'raw_stock_valuations.sql')
    
    if not os.path.exists(sql_path):
        print(f"❌ SQL file not found: {sql_path}")
        return False
    
    with open(sql_path, 'r') as f:
        sql = f.read()
    
    try:
        async with db.pool.acquire() as conn:
            await conn.execute(sql)
        print("✓ Table created successfully")
        return True
    except Exception as e:
        print(f"❌ Error creating table: {e}")
        return False
    finally:
        await db.close_pool()


async def test_raw_fundamentals_loader():
    """Test the Raw Fundamentals Loader"""
    print("\nStep 2: Running Raw Fundamentals Loader...")
    print("=" * 60)
    
    db = DBLayer()
    await db.init_pool()
    
    loader = RawFundamentalsLoader(db, log_callback=print)
    
    # Test with NPN and ABG
    test_tickers = ['NPN', 'ABG']
    
    result = await loader.run_fundamentals_update(tickers=test_tickers)
    
    print("\n" + "=" * 60)
    print(f"Loader Results: {result}")
    
    await db.close_pool()
    
    return result['succeeded'] > 0


async def verify_data():
    """Verify the data was inserted correctly"""
    print("\nStep 3: Verifying data in raw_stock_valuations...")
    print("=" * 60)
    
    db = DBLayer()
    await db.init_pool()
    
    query = """
        SELECT 
            ticker,
            results_period_end,
            results_period_label,
            heps_12m_zarc,
            dividend_12m_zarc,
            quick_ratio
        FROM raw_stock_valuations
        WHERE ticker IN ('NPN', 'ABG')
        ORDER BY ticker, results_period_end DESC
    """
    
    try:
        async with db.pool.acquire() as conn:
            rows = await conn.fetch(query)
        
        if not rows:
            print("⚠ No data found in raw_stock_valuations")
            return False
        
        print(f"\nFound {len(rows)} period records:")
        print()
        
        current_ticker = None
        for row in rows:
            if row['ticker'] != current_ticker:
                current_ticker = row['ticker']
                print(f"\n{current_ticker}:")
                print("-" * 60)
            
            print(f"  Period: {row['results_period_label']}")
            print(f"  End Date: {row['results_period_end']}")
            print(f"  HEPS: {row['heps_12m_zarc']} ZARc")
            print(f"  Dividend: {row['dividend_12m_zarc']} ZARc")
            print(f"  Quick Ratio: {row['quick_ratio']}")
            print()
        
        print("✓ Data verification complete")
        return True
        
    except Exception as e:
        print(f"❌ Error verifying data: {e}")
        return False
    finally:
        await db.close_pool()


async def test_valuation_engine_integration():
    """Test that ValuationEngine can use the raw fundamentals"""
    print("\nStep 4: Testing Valuation Engine Integration...")
    print("=" * 60)
    
    db = DBLayer()
    await db.init_pool()
    
    engine = ValuationEngine(db, log_callback=print)
    
    # Test with a single ticker
    result = await engine.run_valuation_update()
    
    print("\n" + "=" * 60)
    print(f"Valuation Engine Results: {result}")
    
    await db.close_pool()
    
    return result['succeeded'] > 0


async def main():
    """Main test orchestration"""
    print("Testing Raw Fundamentals Loader Implementation")
    print("=" * 60)
    
    # Step 1: Create table
    table_created = await create_table()
    if not table_created:
        print("\n❌ Failed to create table. Aborting tests.")
        return
    
    # Step 2: Run loader
    loader_success = await test_raw_fundamentals_loader()
    if not loader_success:
        print("\n❌ Loader failed. Aborting remaining tests.")
        return
    
    # Step 3: Verify data
    data_verified = await verify_data()
    if not data_verified:
        print("\n⚠ Data verification failed, but continuing...")
    
    # Step 4: Test integration
    integration_success = await test_valuation_engine_integration()
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Table Creation: {'✓' if table_created else '❌'}")
    print(f"Loader Execution: {'✓' if loader_success else '❌'}")
    print(f"Data Verification: {'✓' if data_verified else '❌'}")
    print(f"Valuation Engine Integration: {'✓' if integration_success else '❌'}")
    print()
    
    if all([table_created, loader_success, data_verified, integration_success]):
        print("✅ ALL TESTS PASSED!")
    else:
        print("⚠ SOME TESTS FAILED")


if __name__ == "__main__":
    asyncio.run(main())
