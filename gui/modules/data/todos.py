from core.db.engine import DBEngine
import logging

logger = logging.getLogger(__name__)
from datetime import date


async def get_todos():
    """Fetch all TODOs, ordered by priority and status."""
    query = """
        SELECT id, task_date, title, description, ticker, priority, status, sort_order
        FROM daily_todos
        ORDER BY
            -- Active tasks first
            CASE status WHEN 'active' THEN 1 ELSE 2 END,
            -- High priority first
            CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
            -- Then by manual sort order (if used), then creation time
            sort_order ASC,
            created_at ASC
    """
    rows = await DBEngine.fetch(query)
    return [dict(row) for row in rows]


async def update_todo_status(todo_id: int, status: str):
    """
    Update the status of a TODO item.
    - If marked 'done', sets completed_at to NOW().
    - If marked 'active' or 'deferred', resets completed_at to NULL.
    """
    query = """
        UPDATE daily_todos
        SET 
            status = $2, 
            updated_at = NOW(), 
            completed_at = CASE 
                WHEN $2 = 'done' THEN NOW() 
                ELSE NULL 
            END
        WHERE id = $1
    """
    await DBEngine.execute(query, todo_id, status)
    return True


async def add_todo(
    task_date: date, title: str, description: str, ticker: str, priority: str
):
    """Add a new TODO item to the database."""
    query = """
        INSERT INTO daily_todos (task_date, title, description, ticker, priority, status)
        VALUES ($1, $2, $3, $4, $5, 'active')
        RETURNING id;
    """
    # Use a default for ticker if it's empty to respect VARCHAR constraints or logic
    ticker_val = ticker if ticker and ticker.strip() else None

    try:
        result = await DBEngine.fetch(
            query, task_date, title, description, ticker_val, priority
        )
        return result[0]["id"] if result else None
    except Exception:
        logger.exception("Error adding TODO")
        return None


async def delete_todo(todo_id: int):
    """Delete a TODO item from the database."""
    query = "DELETE FROM daily_todos WHERE id = $1"
    try:
        await DBEngine.execute(query, todo_id)
        return True
    except Exception:
        logger.exception("Error deleting TODO")
        return False
