import asyncio
from datetime import datetime, time as dt_time
from core.db.engine import DBEngine

# Import the workers we created in the previous step
from modules.market_agent.sens import run_sens_check
from modules.market_agent.prices import run_price_update
from modules.market_agent.fundamentals import run_fundamentals_check

# --- Scheduler Configuration ---
RUN_START = dt_time(7, 0)  # 7:00 AM
RUN_END = dt_time(17, 30)  # 5:30 PM
CLOSE_TIME = dt_time(17, 30)  # Markets Close
MIDNIGHT = dt_time(0, 5)  # Reset flags


async def run_market_agent():
    """
    The main scheduler loop.
    It runs indefinitely and coordinates the SENS and Price workers.
    """
    print("--- Market Agent Scheduler Started ---")

    # Ensure DB pool is ready
    await DBEngine.get_pool()
    
    # Track last fundamentals run to avoid duplicates
    fundamentals_last_run_date = None

    try:
        while True:
            now = datetime.now()
            is_weekday = 0 <= now.weekday() <= 4  # Mon-Fri
            is_work_hours = RUN_START <= now.time() <= RUN_END
            
            print(f"DEBUG: Now={now}, Weekday={is_weekday}, WorkHours={is_work_hours}")

            # 1. SENS & Price Check (Runs periodically during work hours)
            if is_weekday and is_work_hours:
                print("DEBUG: Inside work hours block. Running checks...")
                # We await this, so it finishes before sleeping
                await run_sens_check()
                await run_price_update()
                
                # Run fundamentals check once per day
                today = now.date()
                if fundamentals_last_run_date != today:
                    await run_fundamentals_check()
                    fundamentals_last_run_date = today
            else:
                print("DEBUG: Outside work hours. Skipping checks.")

            # 2. Smart Sleep Strategy
            # If it's work hours, check every 15 mins (900s).
            # If it's night/weekend, check every 10 mins (600s) just to keep heartbeat.
            sleep_seconds = 900 if (is_weekday and is_work_hours) else 600

            print(f"Scheduler sleeping for {sleep_seconds/60:.0f} minutes...")
            await asyncio.sleep(sleep_seconds)

    except asyncio.CancelledError:
        print("Market Agent stopping...")
    except Exception as e:
        print(f"CRITICAL AGENT ERROR: {e}")
        # In production, you might want to log this to a file
    finally:
        await DBEngine.close()


if __name__ == "__main__":
    # Allow running this file directly for testing
    asyncio.run(run_market_agent())
