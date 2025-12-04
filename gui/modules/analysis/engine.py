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
