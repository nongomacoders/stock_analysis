from core.db.engine import DBEngine
from components.analysis_service import fetch_analysis, delete_price_level
from core.utils.technical_utils import build_saved_levels_from_row, price_from_db, update_analysis_db

class AnalysisDataManager:
    """Data access helpers for TechnicalAnalysisWindow. Methods are async and meant to be run with the window's async_run_bg."""

    def __init__(self):
        pass

    # ---------- Read helpers ----------
    async def fetch_analysis_row(self, ticker):
        return await fetch_analysis(ticker)

    async def fetch_full_name(self, ticker):
        query = "SELECT full_name FROM stock_details WHERE ticker = $1"
        rows = await DBEngine.fetch(query, ticker)
        return rows[0]['full_name'] if rows and rows[0].get('full_name') else ""

    async def fetch_current_price(self, ticker):
        query = "SELECT close_price FROM daily_stock_data WHERE ticker = $1 ORDER BY trade_date DESC LIMIT 1"
        rows = await DBEngine.fetch(query, ticker)
        return rows[0]['close_price'] if rows else None

    # ---------- Mutations ----------
    async def update_analysis(self, ticker, entry_c, stop_c, target_c, is_long, strategy, support_cs, resistance_cs):
        await update_analysis_db(ticker, entry_c, stop_c, target_c, is_long, strategy, support_cs, resistance_cs)

    async def delete_price_level(self, level_id):
        await delete_price_level(level_id)

    # ---------- Small helpers reused by UI ----------
    def saved_levels_from_row(self, row):
        # wrapper to keep tests simple
        return build_saved_levels_from_row(row)

    def price_from_db(self, val):
        return price_from_db(val)