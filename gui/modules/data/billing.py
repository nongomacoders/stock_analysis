from core.db.engine import DBEngine
from datetime import datetime

async def get_monthly_ai_costs():
    """Retrieve billing statistics grouped by ticker for the current month."""
    now = datetime.now()
    first_day = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    q = """
        SELECT 
            ticker,
            COUNT(*) as call_count,
            SUM(prompt_tokens) as total_prompt_tokens,
            SUM(completion_tokens) as total_completion_tokens,
            SUM(total_cost_usd) as ticker_total_cost
        FROM ai_cost_log
        WHERE call_timestamp >= $1
        GROUP BY ticker
        ORDER BY ticker_total_cost DESC
    """
    return await DBEngine.fetch(q, first_day)

async def get_total_monthly_cost():
    """Retrieve the total cumulative cost for the current month."""
    now = datetime.now()
    first_day = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    q = """
        SELECT SUM(total_cost_usd) as total
        FROM ai_cost_log
        WHERE call_timestamp >= $1
    """
    rows = await DBEngine.fetch(q, first_day)
    if rows and rows[0]["total"]:
        return float(rows[0]["total"])
    return 0.0

async def get_model_usage_stats():
    """Retrieve usage stats grouped by model name for the current month."""
    now = datetime.now()
    first_day = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    q = """
        SELECT 
            model_name,
            COUNT(*) as call_count,
            SUM(total_cost_usd) as model_total_cost
        FROM ai_cost_log
        WHERE call_timestamp >= $1
        GROUP BY model_name
        ORDER BY call_count DESC
    """
    return await DBEngine.fetch(q, first_day)
