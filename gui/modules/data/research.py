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


async def delete_action_log(log_id: int):
    """Delete an action log entry by id."""
    query = "DELETE FROM action_log WHERE log_id = $1"
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
    import logging
    logger = logging.getLogger(__name__)

    rows = await DBEngine.fetch(query, ticker)
    if rows:
        logger.debug("get_research_data: found row for %s", ticker)
        return dict(rows[0])
    else:
        logger.debug("get_research_data: no stock_analysis row for %s", ticker)
        return None


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


async def get_stock_category(ticker: str):
    """Return the category name for a given ticker (or None)."""
    query = """
        SELECT sc.name as category
        FROM stock_details sd
        LEFT JOIN stock_categories sc ON sd.stock_category_id = sc.category_id
        WHERE sd.ticker = $1
        LIMIT 1
    """
    rows = await DBEngine.fetch(query, ticker)
    if rows:
        return rows[0].get('category')
    return None


async def save_strategy_data(ticker: str, content: str):
    """Upsert the strategy value for a ticker.

    If the stock_analysis row doesn't exist this will insert it.
    """
    query = """
        INSERT INTO stock_analysis (ticker, strategy)
        VALUES ($1, $2)
        ON CONFLICT (ticker) DO UPDATE SET strategy = EXCLUDED.strategy
    """
    await DBEngine.execute(query, ticker, content)


async def save_research_data(ticker: str, content: str):
    """Update the research column for a ticker."""
    import logging
    logger = logging.getLogger(__name__)

    query = """
        INSERT INTO stock_analysis (ticker, research)
        VALUES ($1, $2)
        ON CONFLICT (ticker) DO UPDATE SET research = EXCLUDED.research
    """
    try:
        logger.debug("Saving research for %s (content len=%d)", ticker, len(content) if content is not None else 0)
        await DBEngine.execute(query, ticker, content)
        logger.info("Saved research for %s", ticker)
    except Exception:
        logger.exception("Failed saving research for %s", ticker)
        raise


async def save_deep_research_data(ticker: str, content: str):
    """Upsert deepresearch for a ticker (insert or update).
    
    Raises ValueError if content is empty or just placeholder text.
    """
    # Prevent saving blank content or placeholder text
    if not content or content.strip() == "" or content == "No data available.":
        raise ValueError(f"Cannot save empty deep research content for {ticker}")
    
    query = """
        INSERT INTO stock_analysis (ticker, deepresearch)
        VALUES ($1, $2)
        ON CONFLICT (ticker) DO UPDATE SET deepresearch = EXCLUDED.deepresearch
    """
    await DBEngine.execute(query, ticker, content)



