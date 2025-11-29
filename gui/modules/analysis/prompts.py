def build_sens_prompt(research, strategy, sens_content):
    return f"""
    You are a professional JSE financial analyst.
    
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
    Based only on the research, strategy, and this new SENS:
    1. Significance: What is the key takeaway? Relate it to "Key Metrics".
    2. Impact: Positive, Negative, or Neutral?
    3. Action Plan: Buy, Sell, Hold, or Watchlist?
    4. Research Update: If this contains new hard financial data (HEPS, Dividends) state "Required", otherwise "Not required".
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


