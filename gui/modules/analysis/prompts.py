def build_sens_prompt(
    research, strategy, sens_content, current_price: float | None = None
):
    price_info = f"Current Share Price: {current_price}c\n" if current_price else ""

    return f"""
You are a professional JSE financial analyst.

--- MARKET CONTEXT ---
{price_info}
--- END CONTEXT ---

--- MY RESEARCH ---
{research}
--- END RESEARCH ---

--- MY STRATEGY ---
{strategy}
--- END STRATEGY ---

--- NEW SENS ANNOUNCEMENT ---
{sens_content}
--- END SENS ---

INSTRUCTIONS:

1. Significance Classification:
Classify the SENS announcement into ONE of the following levels ONLY:

- Low:
Administrative or procedural announcements unlikely to influence valuation or investor behaviour.
Examples include director dealings, shareholder notifications, share scheme adjustments, or meeting notices.

- Medium:
Operational or corporate updates that may influence sentiment but are unlikely to materially change valuation.
Examples include trading updates without large earnings deviations, minor acquisitions/disposals, operational updates, or strategy commentary.

- High:
Material valuation-impacting announcements likely to influence share price meaningfully.
Examples include:
• Results releases (interim or annual)
• Trading statements with large HEPS deviations
• Dividends or capital returns
• M&A transactions
• Capital raises or debt refinancing
• Major operational disruptions or production guidance changes
• Regulatory rulings with earnings impact

2. Significance Explanation:
Explain WHY the announcement falls into that classification.
Relate your reasoning to:
- Key metrics in my research
- Earnings impact
- Balance sheet impact
- Valuation impact
- Current share price attractiveness or risk

3. Market Impact:
State whether the news is:
Positive, Negative, or Neutral

Also explain:
- Whether the news is likely already priced in
- Whether current valuation now appears attractive or expensive

4. Action Plan:
Provide ONE of the following:
Buy, Sell, Hold, Watchlist

Explicitly reference:
- Current share price
- My strategy
- Whether this SENS changes the investment thesis

5. Research Update Requirement:
If the announcement contains NEW hard financial data (HEPS, EPS, dividends, guidance, production metrics, balance sheet metrics) respond:
"Required"

Otherwise respond:
"Not required"

OUTPUT FORMAT (STRICT):

Significance: <Low / Medium / High>
Explanation: <text>

Impact: <Positive / Negative / Neutral>
Impact Explanation: <text>

Action Plan: <Buy / Sell / Hold / Watchlist>
Action Rationale: <text>

Research Update: <Required / Not required>

"""


def build_price_prompt(research, strategy, ticker, new_price, price_level):
    return f"""
    You are a professional JSE financial analyst. 
    
    --- MY RESEARCH ---
    {research}
    --- END RESEARCH ---

    --- MY STRATEGY ---
    {strategy}
    --- END STRATEGY ---

    --- PRICE TRIGGER ---
    CRITICAL EVENT: {ticker} crossed {price_level}c (Current: {new_price}c).
    --- END TRIGGER ---

    INSTRUCTIONS:
    1. Significance: What does this price cross mean relative to the strategy?
    2. Action Plan: What does the Master Strategy specifically say to do at this level?
    """


def build_research_prompt(deep_research_str=None):
    base_context = ""
    if deep_research_str:
        base_context = (
            "--- BASELINE TRUTH (DEEP RESEARCH) ---\n"
            f"{deep_research_str}\n"
            "--- END BASELINE ---\n"
        )

    template = """
PRICE LEVELS & TARGETS
Report Date Share Price: [Insert]
Report 12-Month Target: [Insert]
Consensus Target: [Insert]
Valuation Floor (NAV): [Insert]

CATALYSTS & RISKS
Positive:
- [List positives here]

Negative:
- [List negatives here]

KEY DATES
Debt / Facilities Maturing:
- [List key debt due dates here]

Project Timelines / Milestones:
- [List key project dates here]
"""

    return f"""
You are a data extractor and synthesizer. Extract the relevant data from the Deep Research Report.

SOURCES:
1. Deep Research Report (Baseline Truth).

{base_context}

INSTRUCTIONS:
- Answer in plain text only. Do NOT use markdown, bullets with asterisks, hashes (#), or bold/italic tags.
- Use exactly the template below and replace the [Insert] and [List] placeholders with concrete values.
- Do not add any extra sections or formatting.

--- TEMPLATE ---
{template}
"""


def build_spot_price_prompt(
    deep_research: str | None,
    ticker: str,
    report_date: str | None,
    commodity_avgs: list[tuple[str, float, int]] | None,
    fx_avgs: list[tuple[str, float, int]] | None,
):
    """Build a prompt to ask the AI for a "share price at spot" estimate.

    - commodity_avgs: list of (commodity, avg_price, count)
    - fx_avgs: list of (pair, avg_rate, count)

    The AI should return a concise numeric estimate and 2-3 brief reasons supporting the update.
    Return must be plain text (no markdown).
    """
    parts: list[str] = [
        "You are a professional JSE financial analyst.",
        "\n--- CONTEXT ---",
        f"Ticker: {ticker}",
    ]

    if report_date:
        parts.append(f"Report date: {report_date}")

    # Add per-commodity averages (limit output to top 10 by count)
    if commodity_avgs:
        parts.append("Per-commodity averages since report date:")
        for c, avg, cnt in (commodity_avgs[:10]):
            parts.append(f"- {c}: {avg:.6f} (n={cnt})")
    else:
        parts.append("Per-commodity averages: unavailable")

    # Add per-FX averages
    if fx_avgs:
        parts.append("Per-FX pair averages since report date:")
        for p, avg, cnt in (fx_avgs[:10]):
            parts.append(f"- {p}: {avg:.6f} (n={cnt})")
    else:
        parts.append("Per-FX pair averages: unavailable")

    parts.append("\n--- BASELINE DEEP RESEARCH ---")
    parts.append(deep_research or "<none>")
    parts.append("--- END BASELINE ---\n")

    parts.append(
        "INSTRUCTIONS:\n"
        "1) Provide a single-line numeric 'SHARE PRICE AT SPOT: <numeric>' (use the same units as the report's share price).\n"
        "2) Then give 2-3 brief reasons (one short sentence each) explaining the change based on the commodity and FX context and the deep research.\n"
        "3) Answer in plain text only, no bullets, no markdown, max 6 lines."
    )

    return "\n".join(parts)
