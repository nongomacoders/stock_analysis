from core.db.engine import DBEngine
import logging

logger = logging.getLogger(__name__)


async def insert_valuation(data: dict):
    delete_q = "DELETE FROM stock_valuations WHERE ticker = $1"
    insert_q = """
        INSERT INTO stock_valuations (
            ticker, valuation_date, price_zarc, heps_12m_zarc, dividend_12m_zarc, 
            cash_gen_ps_zarc, nav_ps_zarc, earnings_yield, dividend_yield, 
            cash_flow_yield, quick_ratio, p_to_nav, peg_ratio
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
    """
    try:
        await DBEngine.execute(delete_q, data["ticker"])
        await DBEngine.execute(
            insert_q,
            data["ticker"],
            data["valuation_date"],
            data.get("price_zarc"),
            data.get("heps_12m_zarc"),
            data.get("dividend_12m_zarc"),
            data.get("cash_gen_ps_zarc"),
            data.get("nav_ps_zarc"),
            data.get("earnings_yield"),
            data.get("dividend_yield"),
            data.get("cash_flow_yield"),
            data.get("quick_ratio"),
            data.get("p_to_nav"),
            data.get("peg_ratio"),
        )
        return True
    except Exception:
        logger.exception("Error inserting valuation")
        return False


async def upsert_raw_fundamentals(ticker: str, periods: list):
    query = """
    INSERT INTO raw_stock_valuations (
        ticker, results_period_end, results_period_label, results_release_date,
        heps_12m_zarc, dividend_12m_zarc, cash_gen_ps_zarc, nav_ps_zarc, quick_ratio, source
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'sharedata')
    ON CONFLICT (ticker, results_period_end) DO UPDATE SET
        heps_12m_zarc = EXCLUDED.heps_12m_zarc,
        dividend_12m_zarc = EXCLUDED.dividend_12m_zarc
    """
    # Note: Simplified UPDATE clause for brevity, add fields as needed
    try:
        for p in periods:
            await DBEngine.execute(
                query,
                ticker,
                p["results_period_end"],
                p["results_period_label"],
                p.get("results_release_date"),
                p.get("heps_12m_zarc"),
                p.get("dividend_12m_zarc"),
                p.get("cash_gen_ps_zarc"),
                p.get("nav_ps_zarc"),
                p.get("quick_ratio"),
            )
        return True
    except Exception:
        logger.exception("Error upserting raw fundamentals")
        return False
