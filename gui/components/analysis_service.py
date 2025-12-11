from typing import Any, Dict, List, Optional
from core.db.engine import DBEngine


async def fetch_analysis(ticker: str) -> Optional[Dict[str, Any]]:
    """Fetch analysis/watchlist + support/resistance for a ticker.

    Returns a single dict row or None if not found.
    """
    query = """
        SELECT 
            w.entry_price, w.target_price, w.stop_loss, w.status,
            sa.strategy,
            (SELECT array_agg(spl.level_id ORDER BY spl.date_added DESC) FROM public.stock_price_levels spl WHERE spl.ticker = w.ticker AND spl.level_type = 'support') AS support_ids,
            (SELECT array_agg(spl.price_level ORDER BY spl.date_added DESC) FROM public.stock_price_levels spl WHERE spl.ticker = w.ticker AND spl.level_type = 'support') AS support_prices,
            (SELECT array_agg(spl.level_id ORDER BY spl.date_added DESC) FROM public.stock_price_levels spl WHERE spl.ticker = w.ticker AND spl.level_type = 'resistance') AS resistance_ids,
            (SELECT array_agg(spl.price_level ORDER BY spl.date_added DESC) FROM public.stock_price_levels spl WHERE spl.ticker = w.ticker AND spl.level_type = 'resistance') AS resistance_prices
        FROM watchlist w
        LEFT JOIN stock_analysis sa ON w.ticker = sa.ticker
        WHERE w.ticker = $1
    """
    rows = await DBEngine.fetch(query, ticker)
    if rows:
        return dict(rows[0])
    # fallback: try stock_analysis + levels only
    fallback_query = """
        SELECT
            sa.strategy,
            (SELECT array_agg(spl.level_id ORDER BY spl.date_added DESC) FROM public.stock_price_levels spl WHERE spl.ticker = $1 AND spl.level_type = 'support') AS support_ids,
            (SELECT array_agg(spl.price_level ORDER BY spl.date_added DESC) FROM public.stock_price_levels spl WHERE spl.ticker = $1 AND spl.level_type = 'support') AS support_prices,
            (SELECT array_agg(spl.level_id ORDER BY spl.date_added DESC) FROM public.stock_price_levels spl WHERE spl.ticker = $1 AND spl.level_type = 'resistance') AS resistance_ids,
            (SELECT array_agg(spl.price_level ORDER BY spl.date_added DESC) FROM public.stock_price_levels spl WHERE spl.ticker = $1 AND spl.level_type = 'resistance') AS resistance_prices
        FROM stock_analysis sa
        WHERE sa.ticker = $1
    """
    rows2 = await DBEngine.fetch(fallback_query, ticker)
    if rows2:
        return dict(rows2[0])
    return None


async def delete_price_level(level_id: int) -> bool:
    """Delete a price level row by id. Returns True on success else False.
    """
    try:
        await DBEngine.execute("DELETE FROM public.stock_price_levels WHERE level_id = $1", level_id)
        return True
    except Exception:
        return False
