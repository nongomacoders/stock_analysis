import asyncio
from db_layer import DBLayer
from datetime import date

async def main():
    db = DBLayer()
    await db.init_pool()
    
    print("Testing upsert_raw_fundamentals...")
    
    # Dummy data
    periods_data = [{
        'results_period_end': date(2025, 3, 31),
        'results_period_label': 'Test Period',
        'heps_12m_zarc': 100.0,
        'dividend_12m_zarc': 50.0,
        'cash_gen_ps_zarc': 200.0,
        'nav_ps_zarc': 1000.0,
        'quick_ratio': 1.5
    }]
    
    try:
        success = await db.upsert_raw_fundamentals('TEST.JO', periods_data)
        if success:
            print("Success!")
        else:
            print("Failed (check logs above)")
    except Exception as e:
        print(f"Exception: {e}")
        
    await db.close_pool()

if __name__ == "__main__":
    asyncio.run(main())
