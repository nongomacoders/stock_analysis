from core.db.engine import DBEngine
import logging

logger = logging.getLogger(__name__)


async def get_latest_price(ticker: str):
    query = """
        SELECT trade_date, close_price 
        FROM daily_stock_data WHERE ticker = $1 
        ORDER BY trade_date DESC LIMIT 1
    """
    row = await DBEngine.fetch(query, ticker)
    return dict(row[0]) if row else None


async def get_historical_prices(ticker: str, days: int):
    query = """
        SELECT trade_date, open_price, high_price, low_price, close_price
        FROM daily_stock_data
        WHERE ticker = $1 AND trade_date >= CURRENT_DATE - INTERVAL '1 day' * $2
        ORDER BY trade_date ASC
    """
    rows = await DBEngine.fetch(query, ticker, days)
    return [dict(row) for row in rows]


async def insert_price_hit_log(ticker, level):
    query = """
        INSERT INTO price_hit_log (ticker, price_level) VALUES ($1, $2)
        ON CONFLICT (ticker, price_level, (hit_timestamp::date)) DO NOTHING
    """
    try:
        await DBEngine.execute(query, ticker, level)
        return True
    except Exception:
        logger.exception("DB ERROR: Failed to insert price hit log")
        return False
