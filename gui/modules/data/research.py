from core.db.engine import DBEngine


async def get_research_data(ticker: str):
    """Get all research data for a ticker from stock_analysis table."""
    query = """
        SELECT 
            strategy,
            research,
            deepresearch,
            deepresearch_date
        FROM stock_analysis
        WHERE ticker = $1
    """
    rows = await DBEngine.fetch(query, ticker)
    return dict(rows[0]) if rows else None


async def get_sens_for_ticker(ticker: str, limit=50):
    """Get SENS announcements for a ticker."""
    query = """
        SELECT publication_datetime, content
        FROM SENS
        WHERE ticker = $1
        ORDER BY publication_datetime DESC
        LIMIT $2
    """
    rows = await DBEngine.fetch(query, ticker, limit)
    return [dict(row) for row in rows]
