from core.db.engine import DBEngine


async def get_action_logs(ticker: str, limit=50):
    """Get action logs for a ticker."""
    query = """
        SELECT log_id, log_timestamp, trigger_type, trigger_content, ai_analysis, is_read
        FROM action_log
        WHERE ticker = $1
        ORDER BY is_read ASC, log_timestamp DESC
        LIMIT $2
    """
    rows = await DBEngine.fetch(query, ticker, limit)
    return [dict(row) for row in rows]


async def mark_log_read(log_id: int):
    """Mark an action log as read."""
    query = "UPDATE action_log SET is_read = true WHERE log_id = $1"
    await DBEngine.execute(query, log_id)


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


async def save_strategy_data(ticker: str, content: str):
    """Update the strategy column for a ticker."""
    query = """
        UPDATE stock_analysis
        SET strategy = $2
        WHERE ticker = $1
    """
    await DBEngine.execute(query, ticker, content)


async def save_research_data(ticker: str, content: str):
    """Update the research column for a ticker."""
    query = """
        UPDATE stock_analysis
        SET research = $2
        WHERE ticker = $1
    """
    await DBEngine.execute(query, ticker, content)


async def save_deep_research_data(ticker: str, content: str):
    """Update the deepresearch column for a ticker."""
    query = """
        UPDATE stock_analysis
        SET deepresearch = $2
        WHERE ticker = $1
    """
    await DBEngine.execute(query, ticker, content)



