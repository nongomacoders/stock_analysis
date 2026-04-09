import asyncio
import os
import sys
import time
from datetime import datetime
import logging

# Set up logging to capture details
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add gui to path for modules
# Assuming script is run from root or project root
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
sys.path.append(project_root)
sys.path.append(os.path.join(project_root, "gui"))

from gui.core.db.engine import DBEngine
from gui.modules.data.research import get_research_data
from gui.modules.analysis.prompts import build_sens_prompt
import gui.modules.analysis.ollama_llm as ollama_llm
import gui.modules.analysis.gemini_vertex_llm as gemini_llm

async def benchmark_llms():
    ticker = "PPE.JO"
    target_time = "2026-04-07 16:00:00"
    ollama_model = "gemma4:e4b" # User specified
    gemini_model = "gemini-3-flash-preview" # User specified
    
    output_file = os.path.join(current_dir, f"analysis_benchmark_PPE_JO.txt")

    print(f"--- Benchmarking LLMs for {ticker} @ {target_time} ---")
    
    # 1. Fetch SENS content
    q_sens = "SELECT content FROM SENS WHERE ticker = $1 AND publication_datetime = $2"
    sens_rows = await DBEngine.fetch(q_sens, ticker, datetime.fromisoformat(target_time))
    if not sens_rows:
        print(f"Error: Could not find SENS record for {ticker} at {target_time}")
        return
    sens_content = sens_rows[0]['content']

    # 2. Fetch Research/Strategy
    research_data = await get_research_data(ticker)
    if not research_data:
        print(f"Warning: No research data found for {ticker}")
        research = "No research available."
        strategy = "No strategy available."
    else:
        research = research_data.get('research', 'No research available.')
        strategy = research_data.get('strategy', 'No strategy available.')

    # 3. Build Prompt
    prompt = build_sens_prompt(research, strategy, sens_content)

    results = []
    results.append(f"BENCHMARK REPORT: {ticker} @ {target_time}")
    results.append("="*50)
    results.append(f"Prompt Length: {len(prompt)} characters\n")

    # 4. Ollama (gemma4:e4b)
    print(f"Querying Ollama ({ollama_model})...")
    start_ollama = time.time()
    ollama_res = await ollama_llm.query_ai(prompt, model=ollama_model)
    ollama_duration = time.time() - start_ollama
    print(f"Ollama took {ollama_duration:.2f} seconds.")
    
    results.append(f"MODEL: Ollama ({ollama_model})")
    results.append(f"TIME: {ollama_duration:.2f} seconds")
    results.append("-" * 30)
    results.append(ollama_res)
    results.append("\n" + "="*50 + "\n")

    # 5. Gemini (gemini-3-flash-preview)
    print(f"Querying Gemini ({gemini_model})...")
    start_gemini = time.time()
    gemini_res_obj = await gemini_llm.query_ai(prompt, model=gemini_model)
    gemini_duration = time.time() - start_gemini
    print(f"Gemini took {gemini_duration:.2f} seconds.")

    # Handle Gemini response object
    gemini_content = ""
    if isinstance(gemini_res_obj, str):
        gemini_content = gemini_res_obj
    else:
        # Assuming gemini_res_obj is a response object with .text or similar
        try:
            gemini_content = gemini_res_obj.text
        except Exception:
            gemini_content = str(gemini_res_obj)

    results.append(f"MODEL: Gemini ({gemini_model})")
    results.append(f"TIME: {gemini_duration:.2f} seconds")
    results.append("-" * 30)
    results.append(gemini_content)
    results.append("\n" + "="*50)

    # 6. Save results
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(results))
    
    print(f"\nResults saved to: {output_file}")

if __name__ == "__main__":
    asyncio.run(benchmark_llms())
