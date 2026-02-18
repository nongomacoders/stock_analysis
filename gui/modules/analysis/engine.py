from core.db.engine import DBEngine
from modules.analysis.llm import query_ai
from modules.analysis.openrouter_llm import query_ai as openrouter_query_ai
from modules.analysis.prompts import (
    build_sens_prompt,
    build_price_prompt,
    build_research_prompt,
    build_spot_price_prompt,
)


async def analyze_new_sens(ticker: str, content: str):
    import logging
    logger = logging.getLogger(__name__)
    logger.info("AI: Analyzing SENS for %s...", ticker)

    # 1. Fetch Context
    row = await _fetch_context(ticker)
    if not row:
        return

    # 1.5 Fetch Current Price
    q_price = "SELECT close_price FROM daily_stock_data WHERE ticker = $1 ORDER BY trade_date DESC LIMIT 1"
    price_row = await DBEngine.fetch(q_price, ticker)
    current_price = price_row[0]["close_price"] if price_row else None

    # 2. Build Prompt & Query
    prompt = build_sens_prompt(row["research"], row["strategy"], content, current_price)
    analysis = await openrouter_query_ai(prompt)

    # 3. Extract significance from the response
    significance = None
    try:
        # Parse "Significance: <Low / Medium / High>" from the response
        import re
        match = re.search(r'Significance:\s*(Low|Medium|High)', analysis, re.IGNORECASE)
        if match:
            significance = match.group(1).capitalize()
    except Exception:
        logger.debug("Could not extract significance from SENS analysis for %s", ticker)

    # 4. Save Log
    headline = (content[:200] + "...") if len(content) > 200 else content
    await _save_log(ticker, "SENS", headline, analysis, significance=significance)
    logger.info("AI: SENS analysis saved for %s.", ticker)


async def analyze_price_change(ticker: str, new_price: float, level_hit: float):
    import logging
    logger = logging.getLogger(__name__)
    logger.info("AI: Analyzing Price Hit for %s (%sc)...", ticker, level_hit)

    row = await _fetch_context(ticker)
    if not row:
        return

    prompt = build_price_prompt(
        row["research"], row["strategy"], ticker, new_price, level_hit
    )
    analysis = await query_ai(prompt)

    trigger = f"Price crossed {level_hit}c, closing at {new_price}c."
    await _save_log(ticker, "Price Level", trigger, analysis)
    logger.info("AI: Price analysis saved for %s.", ticker)


async def generate_master_research(ticker: str, deep_research=None):
    import logging
    import time
    logger = logging.getLogger(__name__)
    logger.info("AI: Generating Research Summary for %s...", ticker)
    
    # 1. Generate
    start_time = time.time()
    prompt = build_research_prompt(deep_research)
    logger.info("AI: Research prompt length for %s: %d characters", ticker, len(prompt))
    
    result = await query_ai(prompt)
    
    duration = time.time() - start_time
    logger.info("AI: Research generation for %s took %.2f seconds", ticker, duration)
    
    return result


async def estimate_spot_price(ticker: str):
    """Estimate 'share price at spot' using DB averages and the last deep research.

    - Fetch deepresearch and deepresearch_date from stock_analysis.
    - Compute average commodity price and average FX rate since the deepresearch_date.
    - Build prompt and query AI.
    - Save an action_log entry of type 'Spot Price' containing the AI response.
    Returns the AI text (string) or an explanatory error message.
    """
    import logging
    logger = logging.getLogger(__name__)

    # 1) Fetch deep research and report date
    q = "SELECT deepresearch, deepresearch_date FROM stock_analysis WHERE ticker = $1"
    rows = await DBEngine.fetch(q, ticker)
    if not rows:
        logger.warning("Spot price: no stock_analysis row for %s", ticker)
        return "No deep research row found for this ticker."

    row = rows[0]
    deep = row.get("deepresearch")
    report_date = row.get("deepresearch_date")

    if not report_date:
        logger.warning("Spot price: no deepresearch_date for %s", ticker)
        return "Cannot compute spot price: report date (deepresearch_date) not set for this ticker."

    # 2) Compute per-commodity and per-FX averages since report_date (inclusive)
    commodity_avgs = []
    fx_avgs = []
    try:
        q1 = "SELECT commodity, AVG(price) AS avg_price, COUNT(*) AS cnt FROM commodity_prices WHERE collected_ts >= $1 GROUP BY commodity ORDER BY cnt DESC"
        rows1 = await DBEngine.fetch(q1, report_date)
        if rows1:
            for r in rows1:
                try:
                    commodity_avgs.append((r["commodity"], float(r["avg_price"]), int(r["cnt"])))
                except Exception:
                    continue

        q2 = "SELECT pair, AVG(rate) AS avg_rate, COUNT(*) AS cnt FROM fx_rates WHERE collected_ts >= $1 GROUP BY pair ORDER BY cnt DESC"
        rows2 = await DBEngine.fetch(q2, report_date)
        if rows2:
            for r in rows2:
                try:
                    fx_avgs.append((r["pair"], float(r["avg_rate"]), int(r["cnt"])))
                except Exception:
                    continue

        # Also compute an overall weighted average (fallback)
        total_comm = sum(avg * cnt for (_, avg, cnt) in commodity_avgs) if commodity_avgs else 0.0
        total_comm_cnt = sum(cnt for (_, _, cnt) in commodity_avgs) if commodity_avgs else 0
        avg_comm = (total_comm / total_comm_cnt) if total_comm_cnt else None

        total_fx = sum(avg * cnt for (_, avg, cnt) in fx_avgs) if fx_avgs else 0.0
        total_fx_cnt = sum(cnt for (_, _, cnt) in fx_avgs) if fx_avgs else 0
        avg_fx = (total_fx / total_fx_cnt) if total_fx_cnt else None

    except Exception:
        logger.exception("Failed to compute averages for %s", ticker)
        commodity_avgs = []
        fx_avgs = []
        avg_comm = None
        avg_fx = None

    # 3) Build prompt and query AI
    try:
        prompt = build_spot_price_prompt(deep, ticker, str(report_date), commodity_avgs, fx_avgs)
        logger.info("Spot price: querying AI for %s (report_date=%s)", ticker, report_date)
        analysis = await query_ai(prompt)
    except Exception:
        logger.exception("AI query failed for spot price %s", ticker)
        analysis = "Error generating AI response for spot price."

    # 4) Save to action_log for auditability
    try:
        await _save_log(ticker, "Spot Price", f"Spot price estimate requested (report_date={report_date})", analysis)
    except Exception:
        logger.exception("Failed to save spot price action log for %s", ticker)

    return analysis

async def _save_log(ticker, type_, content, analysis, significance=None):
    q = """
        INSERT INTO action_log (ticker, trigger_type, trigger_content, ai_analysis, significance)
        VALUES ($1, $2, $3, $4, $5)
    """
    await DBEngine.execute(q, ticker, type_, content, analysis, significance)


async def _fetch_context(ticker: str):
    q = "SELECT research, strategy FROM stock_analysis WHERE ticker = $1"
    rows = await DBEngine.fetch(q, ticker)
    if not rows:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning("AI: No context found for %s", ticker)
        return None
    return rows[0]
