import google.generativeai as genai
import psycopg2
import os
import threading
from dotenv import load_dotenv
from datetime import datetime
try:
    from config import DB_CONFIG
except ImportError:
    print("FATAL ERROR (AI_BRAIN): config.py not found.")
    exit()

# --- API KEY SETUP ---
load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")

if not API_KEY:
    print("FATAL ERROR (AI_BRAIN): GOOGLE_API_KEY environment variable not set.")
    # exit()
else:
    genai.configure(api_key=API_KEY)

# --- Helper Functions (Internal) ---

def _fetch_master_research(conn, ticker):
    """Fetches the master research and strategy for a given ticker."""
    try:
        with conn.cursor() as cursor:
            query = "SELECT research, strategy FROM stock_analysis WHERE ticker = %s"
            cursor.execute(query, (ticker,))
            result = cursor.fetchone()
            
            if result:
                research, strategy = result
                research = research if research else "No research provided."
                strategy = strategy if strategy else "No strategy provided."
                return research, strategy
            else:
                return None, None
    except Exception as e:
        print(f"AI_BRAIN_DB_ERROR: Could not fetch research for {ticker}: {e}")
        return None, None

def _save_action_log(conn, ticker, trigger_type, trigger_content, ai_analysis):
    """Saves the AI's output to the action_log table."""
    try:
        with conn.cursor() as cursor:
            query = """
                INSERT INTO action_log (ticker, trigger_type, trigger_content, ai_analysis)
                VALUES (%s, %s, %s, %s)
            """
            content_headline = (trigger_content[:200] + '...') if len(trigger_content) > 200 else trigger_content
            cursor.execute(query, (ticker, trigger_type, content_headline, ai_analysis))
            return True
    except Exception as e:
        print(f"AI_BRAIN_DB_ERROR: Could not save action_log for {ticker}: {e}")
        conn.rollback()
        return False

def _build_sens_prompt(research, strategy, sens_content):
    """Builds the prompt for daily SENS analysis."""
    prompt = f"""
    You are a professional JSE (Johannesburg Stock Exchange) financial analyst. 
    Your goal is to provide a concise, actionable recommendation for me, the sole proprietor.

    Here is my master research file for this stock:
    --- MY RESEARCH ---
    {research}
    --- END RESEARCH ---

    Here is my current master strategy for this stock:
    --- MY STRATEGY ---
    {strategy}
    --- END STRATEGY ---

    A new, time-sensitive SENS announcement has just been released:
    --- NEW SENS ---
    {sens_content}
    --- END SENS ---

    INSTRUCTIONS:
    Based *only* on my research, my strategy, and this new SENS, provide the following:
    1.  **Significance:** What is the key takeaway from this SENS? Does it directly relate to any of my "Key Metrics" or "Positive/Negative Catalysts"?
    2.  **Impact:** Does this news positively or negatively impact my thesis? Is it neutral noise?
    3.  **Action Plan:** What is your recommended plan of action? Be specific (Buy, Sell, Hold, Watchlist).
    4.  **Research Update:** * If this SENS contains new, hard financial data (HEPS, dividends, debt) that makes my 'Key Financial Metrics' outdated, state: **"Required."** and briefly explain what needs updating.
        * Otherwise, state: **"Not required."**
    """
    return prompt

def _build_price_prompt(research, strategy, ticker, new_price, price_level_hit):
    """Builds the prompt for a price level trigger."""
    prompt = f"""
    You are a professional JSE financial analyst. 
    
    Here is my master research for: {ticker}
    --- MY RESEARCH ---
    {research}
    --- END RESEARCH ---

    Here is my master strategy:
    --- MY STRATEGY ---
    {strategy}
    --- END STRATEGY ---

    --- PRICE TRIGGER ---
    A critical price trigger has just occurred.
    * Key Level from Strategy: **{price_level_hit}c**
    * New Closing Price: **{new_price}c**
    --- END TRIGGER ---

    INSTRUCTIONS:
    1.  **Significance:** What does this price cross mean relative to the strategy?
    2.  **Action Plan:** What does my *Master Strategy* specifically say to do at this level? (Buy? Sell? Wait?)
    """
    return prompt

# --- REMOVED earnings_data_str from arguments ---
def _build_research_prompt(ticker, sens_data_str, deep_research_str=None):
    """Builds the prompt for generating a new research report (The Summary)."""
    
    blank_template = """
### 🎯 Price Levels & Targets
* **Report Date Share Price:** [Insert price]
* **Report 12-Month Target Price:** [Insert range]
* **Analyst Consensus 12-Month Target:** [Insert price]
* **Valuation Floor (e.g., NAV):** [Insert price]

### 📊 Key Financial Metrics (Most Recent Period)
* **Period End Date:** [Insert date]
* **Headline Earnings Per Share (HEPS):** [Insert value and % change]
* **Full-Year EPS Forecast (if specified):** [Insert value]
* **Interim/Final Dividend:** [Insert value and % change]
* **Net Debt-to-Equity Ratio:** [Insert value]
* **Total Borrowings:** [Insert value]
* **Cash from Operations:** [Insert value]

### 🗓️ Key Dates & Project Timelines
* **Debt Repayment:** [Dates]
* **Project Milestones:** [Dates]
* **Asset Disposals:** [Status]

### ⚠️ Price Sensitive Catalysts & Risks (Watch List)
* **Positive Catalysts:**
    * [Catalyst 1]
    * [Catalyst 2]
* **Negative Risks:**
    * [Risk 1]
    * [Risk 2]
"""
    
    deep_research_context = ""
    if deep_research_str and len(deep_research_str) > 10:
        deep_research_context = f"""
    --- EXISTING DEEP RESEARCH REPORT (BASE TRUTH) ---
    Use this as your PRIMARY source for targets, strategy, and analysis.
    {deep_research_str}
    --- END DEEP RESEARCH ---
        """

    prompt = f"""
    You are an expert JSE financial analyst. 
    Your task is to create a **One-Page Executive Summary** for {ticker}.

    SOURCES:
    1.  **Deep Research Report:** (If provided below) This is the baseline truth.
    2.  **Recent SENS:** Only NEW announcements released *after* the Deep Research report. Use these to update the baseline figures.
    
    INSTRUCTIONS:
    1.  **Synthesize:** Extract key targets, dates, and risks from the Deep Research.
    2.  **Update:** Check the "Recent SENS". If a SENS announcement contains newer data than the Deep Research (e.g., a newer dividend declaration), OVERWRITE the Deep Research data with the SENS data.
    3.  **Format:** Fill in the "Blank Research Template" below. Keep it concise.

    {deep_research_context}

    --- RAW DATA: NEW SENS (Since Report Date) ---
    {sens_data_str}
    --- END SENS ---

    --- BLANK RESEARCH TEMPLATE ---
    {blank_template}
    --- END TEMPLATE ---

    Your final output must be *only* the completed template.
    """
    return prompt


# --- Public Functions ---

def analyze_new_sens(ticker, sens_content):
    """Analyzes a new SENS announcement."""
    print(f"\nAI_BRAIN: Received new SENS for {ticker}. Starting analysis...")
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        research, strategy = _fetch_master_research(conn, ticker)
        
        if research is None or strategy is None:
            print(f"AI_BRAIN: No master research found for {ticker}. Skipping.")
            return

        prompt = _build_sens_prompt(research, strategy, sens_content)
        
        print(f"AI_BRAIN: Sending prompt to Gemini for {ticker}...")
        model = genai.GenerativeModel('gemini-2.5-pro')
        response = model.generate_content(prompt)
        
        if _save_action_log(conn, ticker, 'SENS', sens_content, response.text):
            conn.commit()
            print(f"AI_BRAIN: Successfully logged SENS analysis for {ticker}.")
        else:
            print(f"AI_BRAIN: Failed to save analysis.")

    except Exception as e:
        print(f"AI_BRAIN_ERROR: Fatal error analyzing SENS for {ticker}: {e}")
        if conn: conn.rollback()
    finally:
        if conn: conn.close()

def analyze_price_change(ticker, new_price, price_level_hit):
    # Print the level that was hit, not the new price, for clarity.
    print(f"\nAI_BRAIN: Received PRICE HIT for {ticker} at {price_level_hit}c. Starting analysis...")
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        research, strategy = _fetch_master_research(conn, ticker)
        
        if research is None or strategy is None:
            print(f"AI_BRAIN: No master research found for {ticker}. Skipping.")
            return

        prompt = _build_price_prompt(research, strategy, ticker, new_price, price_level_hit)
        
        print(f"AI_BRAIN: Sending prompt to Gemini for {ticker}...")
        model = genai.GenerativeModel('gemini-2.5-pro')
        response = model.generate_content(prompt)
        
        trigger_content = f"Price crossed {price_level_hit}c, closing at {new_price}c."
        if _save_action_log(conn, ticker, 'Price Level', trigger_content, response.text):
            conn.commit()
            print(f"AI_BRAIN: Successfully logged Price analysis for {ticker}.")
        else:
            print(f"AI_BRAIN: Failed to save analysis.")

    except Exception as e:
        print(f"AI_BRAIN_ERROR: Fatal error analyzing Price for {ticker}: {e}")
        if conn: conn.rollback()
    finally:
        if conn: conn.close()

def generate_master_research(ticker, deep_research_content=None, sens_cutoff_date=None):
    """Generates a Research Summary using a smart filter for SENS."""
    print(f"AI_BRAIN: Generating master research summary for {ticker}...")
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        
        # 1. Fetch SENS Data
        sens_data = []
        with conn.cursor() as cursor:
            if sens_cutoff_date:
                print(f"AI_BRAIN: Filtering for SENS after {sens_cutoff_date}")
                query_sens = """
                    SELECT publication_datetime, content 
                    FROM SENS 
                    WHERE ticker = %s AND publication_datetime > %s
                    ORDER BY publication_datetime DESC
                """
                cursor.execute(query_sens, (ticker, sens_cutoff_date))
            else:
                query_sens = """
                    SELECT publication_datetime, content 
                    FROM SENS WHERE ticker = %s 
                    ORDER BY publication_datetime DESC
                    LIMIT 20
                """
                cursor.execute(query_sens, (ticker,))
            
            for row in cursor.fetchall():
                sens_data.append(f"Date: {row[0].strftime('%Y-%m-%d')}\nContent: {row[1]}\n---")
        
        sens_data_str = "\n".join(sens_data) if sens_data else "No new SENS data found in relevant period."
        
        # --- REMOVED Earnings Fetching Block ---

        # 3. Build Prompt (Removed earnings argument)
        prompt = _build_research_prompt(ticker, sens_data_str, deep_research_content)
        
        # 4. Call AI
        print(f"AI_BRAIN: Sending summary generation prompt to Gemini for {ticker}...")
        model = genai.GenerativeModel('gemini-2.5-pro')
        response = model.generate_content(prompt)
        
        print(f"AI_BRAIN: Research summary for {ticker} generated successfully.")
        return response.text

    except Exception as e:
        print(f"AI_BRAIN_ERROR: Fatal error generating research for {ticker}: {e}")
        return f"Error generating research. Check logs: {e}"
    finally:
        if conn:
            conn.close()

# --- Test Block ---
if __name__ == "__main__":
    print("--- AI BRAIN TEST MODE ---")
    if not API_KEY:
        print("Test failed: GOOGLE_API_KEY is not set.")
    else:
        print("Attempting to connect to Google AI...")
        try:
            model = genai.GenerativeModel('gemini-2.5-pro')
            response = model.generate_content("Hello, world. Test connection.")
            print("\n--- TEST RESPONSE ---")
            print(response.text)
            print("-----------------------\n")
            print("SUCCESS: Google AI connection is working.")
        except Exception as e:
            print(f"FAILURE: Could not connect to Google AI: {e}")
    print("\n--- TEST COMPLETE ---")