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
    Based *only* on the research, strategy, and this new SENS:
    1. **Significance:** What is the key takeaway? Relate it to "Key Metrics".
    2. **Impact:** Positive, Negative, or Neutral?
    3. **Action Plan:** Buy, Sell, Hold, or Watchlist?
    4. **Research Update:** If this contains new hard financial data (HEPS, Dividends) state "Required", otherwise "Not required".
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
    CRITICAL EVENT: {ticker} crossed **{price_level}c** (Current: {new_price}c).
    --- END TRIGGER ---

    INSTRUCTIONS:
    1. **Significance:** What does this price cross mean relative to the strategy?
    2. **Action Plan:** What does the Master Strategy specifically say to do at this level?
    """


def build_research_prompt(ticker, sens_data_str, deep_research_str=None):
    base_context = ""
    if deep_research_str:
        base_context = f"--- BASELINE TRUTH (DEEP RESEARCH) ---\n{deep_research_str}\n--- END BASELINE ---\n"

    template = """
### 🎯 Price Levels & Targets
* **Report Date Share Price:** [Insert]
* **Report 12-Month Target:** [Insert]
* **Consensus Target:** [Insert]
* **Valuation Floor (NAV):** [Insert]

### 📊 Key Financial Metrics
* **Period End Date:** [Insert]
* **HEPS:** [Insert]
* **Dividend:** [Insert]
* **Net Debt-to-Equity:** [Insert]
* **Cash from Ops:** [Insert]

### ⚠️ Catalysts & Risks
* **Positive:** [List]
* **Negative:** [List]
"""
    return f"""
    You are an expert JSE financial analyst. Create a One-Page Executive Summary for {ticker}.
    
    SOURCES:
    1. Deep Research Report (Baseline Truth).
    2. Recent SENS (Updates to Baseline).
    
    {base_context}

    --- RECENT SENS DATA ---
    {sens_data_str}
    --- END SENS ---

    INSTRUCTIONS:
    Synthesize the Deep Research with the Recent SENS updates. 
    Fill out the template below.
    
    --- TEMPLATE ---
    {template}
    """
