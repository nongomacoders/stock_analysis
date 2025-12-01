from core.db.engine import DBEngine

async def get_stock_metrics(ticker: str):
    """
    Get current stock metrics from the v_live_valuations view.
    Returns a dictionary with keys:
    - current_price
    - pe_ratio
    - div_yield_perc
    - peg_ratio_historical
    - graham_fair_value
    - valuation_premium_perc
    - financials_date
    """
    query = """
        SELECT 
            current_price,
            pe_ratio,
            div_yield_perc,
            peg_ratio_historical,
            graham_fair_value,
            valuation_premium_perc,
            historical_growth_cagr,
            financials_date
        FROM v_live_valuations
        WHERE ticker = $1
    """
    row = await DBEngine.fetch(query, ticker)
    if row:
        return dict(row[0])
    return None
