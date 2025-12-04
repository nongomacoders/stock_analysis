from typing import Any, Dict, List, Optional, Tuple
from core.db.engine import DBEngine


def price_from_db(raw_price: Any) -> Optional[float]:
    """Safely convert a numeric DB value (Decimal/int/float/None) to rands (float).

    Returns None for invalid/missing values, otherwise float(raw)/100.0
    """
    if raw_price is None:
        return None
    try:
        return float(raw_price) / 100.0
    except Exception:
        return None


def build_saved_levels_from_row(row: Dict[str, Any]) -> List[Tuple[float, str, str]]:
    """Given a DB row dict with entry_price/stop_loss/target_price (in cents),
    return a list of (price_rands, color, label) suitable for BaseChart.set_horizontal_lines.
    """
    out: List[Tuple[float, str, str]] = []
    if not row:
        return out

    entry = price_from_db(row.get("entry_price"))
    stop = price_from_db(row.get("stop_loss"))
    target = price_from_db(row.get("target_price"))

    if entry is not None:
        out.append((entry, "blue", f"Entry: R{entry:.2f}"))
    if stop is not None:
        out.append((stop, "red", f"Stop Loss: R{stop:.2f}"))
    if target is not None:
        out.append((target, "green", f"Target: R{target:.2f}"))

    return out


async def update_analysis_db(ticker: str, entry_c: Optional[int], stop_c: Optional[int], target_c: Optional[int], is_long: bool, strategy: str) -> None:
    """Persist analysis values to DB (watchlist + stock_analysis) in an async function.

    This mirrors logic previously embedded in TechnicalAnalysisWindow.save_analysis.
    """
    # Use upsert so a missing watchlist row is created when saving analysis
    # First try UPDATE; if it affected 0 rows, INSERT a new watchlist row.
    res = await DBEngine.execute(
        "UPDATE watchlist SET entry_price = $1, stop_loss = $2, target_price = $3, is_long = $4 WHERE ticker = $5",
        entry_c,
        stop_c,
        target_c,
        is_long,
        ticker,
    )
    # asyncpg returns a command tag like 'UPDATE 0' or 'UPDATE 1'
    updated = 0
    if isinstance(res, str) and res.split()[0].upper() == 'UPDATE':
        try:
            updated = int(res.split()[1]) if len(res.split()) > 1 else 0
        except Exception:
            updated = 0

    if updated > 0:
        return

    # nothing updated - insert row instead
    await DBEngine.execute(
        "INSERT INTO watchlist (ticker, entry_price, stop_loss, target_price, is_long) VALUES ($1, $2, $3, $4, $5)",
        ticker,
        entry_c,
        stop_c,
        target_c,
        is_long,
    )

    query_sa = """
        INSERT INTO stock_analysis (ticker, strategy)
        VALUES ($1, $2)
        ON CONFLICT (ticker)
        DO UPDATE SET strategy = EXCLUDED.strategy
    """
    await DBEngine.execute(query_sa, ticker, strategy)
