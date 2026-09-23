from core.db.engine import DBEngine


async def get_action_logs(ticker: str, limit=50):
    """Get action logs for a ticker."""
    query = """
        SELECT log_id, log_timestamp, trigger_type, trigger_content, ai_analysis, is_read
        FROM action_log
        WHERE ticker = $1 AND dismissed_at IS NULL
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
    """Hide a log and remember a SENS dismissal without removing source evidence."""
    from hashlib import sha256
    pool = await DBEngine.get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow("""SELECT ticker,trigger_type,trigger_content,sens_content_hash
                FROM action_log WHERE log_id=$1 FOR UPDATE""", log_id)
            if row is None:
                return
            digest = row["sens_content_hash"]
            if row["trigger_type"] == "SENS" and not digest:
                # Legacy logs lack a source link. Resolve only an unambiguous body.
                matches = await conn.fetch("""SELECT DISTINCT content FROM sens WHERE ticker=$1 AND
                    (left(content,203)=$2 OR left(content,200)||'...'=$2 OR content=$2)
                    LIMIT 2""", row["ticker"], row["trigger_content"])
                if len(matches) == 1:
                    digest = sha256(matches[0]["content"].encode("utf-8")).hexdigest()
            if row["trigger_type"] == "SENS" and digest:
                await conn.execute("""INSERT INTO sens_action_dismissals
                    (ticker,content_hash,source_log_id) VALUES($1,$2,$3)
                    ON CONFLICT(ticker,content_hash) DO NOTHING""", row["ticker"], digest, log_id)
            await conn.execute("UPDATE action_log SET dismissed_at=now() WHERE log_id=$1", log_id)


async def get_research_data(ticker: str):
    """Get all research data for a ticker from stock_analysis table."""
    query = """
        SELECT 
            strategy,
            research,
            deepresearch,
            deepresearch_date,
            current_report_id
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
        SELECT sens_id, publication_datetime, content, source_document_id
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
    
    from modules.data.report_versions import save_manual_report
    return await save_manual_report(ticker, content)



async def get_latest_deepresearch_with_upside(limit=50):
    """Fetch the latest deep research entries along with full names and target price for upside calculation."""
    query = """
        SELECT 
            sa.ticker, 
            sd.full_name,
            sa.deepresearch_date,
            w.target_price,
            (SELECT close_price FROM daily_stock_data dsd WHERE dsd.ticker = sa.ticker ORDER BY trade_date DESC LIMIT 1) as current_price
        FROM stock_analysis sa
        LEFT JOIN stock_details sd ON sa.ticker = sd.ticker
        LEFT JOIN watchlist w ON sa.ticker = w.ticker
        WHERE sa.deepresearch IS NOT NULL AND sa.deepresearch != ''
        ORDER BY sa.deepresearch_date DESC NULLS LAST, sa.ticker ASC
        LIMIT $1
    """
    rows = await DBEngine.fetch(query, limit)
    
    results = []
    for row in rows:
        d = dict(row)
        target = d.get("target_price")
        current = d.get("current_price")
        
        upside = None
        if target and current:
            # target is in cents, current is in cents
            upside = ((float(target) - float(current)) / float(current)) * 100
            
        d["calculated_upside"] = upside
        results.append(d)
        
    return results


async def save_watchlist_notes(ticker: str, notes: str):
    """Update the notes for a given ticker in the watchlist."""
    query = """
        UPDATE watchlist 
        SET notes = $1 
        WHERE ticker = $2
    """
    await DBEngine.execute(query, notes, ticker)



