from core.db.engine import DBEngine
from modules.analysis.llm import query_ai
from modules.analysis.prompts import (
    build_sens_prompt,
    build_price_prompt,
    build_research_prompt,
)


async def analyze_new_sens(ticker: str, content: str):
    import logging
    logger = logging.getLogger(__name__)
    logger.info("AI: Analyzing SENS for %s...", ticker)

    # 1. Fetch Context
    row = await _fetch_context(ticker)
    if not row:
        return

    # 2. Build Prompt & Query
    prompt = build_sens_prompt(row["research"], row["strategy"], content)
    analysis = await query_ai(prompt)

    # 3. Save Log
    headline = (content[:200] + "...") if len(content) > 200 else content
    await _save_log(ticker, "SENS", headline, analysis)
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
    logger = logging.getLogger(__name__)
    logger.info("AI: Generating Research Summary for %s...", ticker)
    # 1. Generate
    prompt = build_research_prompt(deep_research)
    return await query_ai(prompt)


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

    # 2) Compute averages since report_date (inclusive)
    try:
        q1 = "SELECT AVG(price) AS avg_price, COUNT(*) AS cnt FROM commodity_prices WHERE collected_ts >= $1"
        rows1 = await DBEngine.fetch(q1, report_date)
        avg_comm = rows1[0]["avg_price"] if rows1 and rows1[0]["avg_price"] is not None else None

        q2 = "SELECT AVG(rate) AS avg_rate, COUNT(*) AS cnt FROM fx_rates WHERE collected_ts >= $1"
        rows2 = await DBEngine.fetch(q2, report_date)
        avg_fx = rows2[0]["avg_rate"] if rows2 and rows2[0]["avg_rate"] is not None else None
    except Exception:
        logger.exception("Failed to compute averages for %s", ticker)
        avg_comm = None
        avg_fx = None

    # 3) Build prompt and query AI
    try:
        prompt = build_spot_price_prompt(deep, ticker, str(report_date), avg_comm, avg_fx)
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

async def _save_log(ticker, type_, content, analysis):
    q = """
        INSERT INTO action_log (ticker, trigger_type, trigger_content, ai_analysis)
        VALUES ($1, $2, $3, $4)
    """
    await DBEngine.execute(q, ticker, type_, content, analysis)


async def _fetch_context(ticker: str):
    q = "SELECT research, strategy FROM stock_analysis WHERE ticker = $1"
    rows = await DBEngine.fetch(q, ticker)
    if not rows:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning("AI: No context found for %s", ticker)
        return None
    return rows[0]
