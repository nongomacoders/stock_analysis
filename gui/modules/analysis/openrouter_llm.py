from openai import AsyncOpenAI
import os
from dotenv import load_dotenv
import logging

# Initialize
load_dotenv()
API_KEY = os.getenv("OPENROUTER_API_KEY")
REFERER = os.getenv("OPENROUTER_REFERER", "http://localhost:3000") # Optional
TITLE = os.getenv("OPENROUTER_TITLE", "Stock Analysis Tool") # Optional

if not API_KEY:
    logging.warning("OPENROUTER_API_KEY not found. OpenRouter AI features will fail.")
    client = None
else:
    client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=API_KEY,
    )


async def query_ai(prompt: str, model: str = "stepfun/step-3.5-flash:free"):
    """Sends a prompt to OpenRouter and returns the text response asynchronously."""
    if not client:
        return "Error generating AI response: OPENROUTER_API_KEY not found."
    
    try:
        completion = await client.chat.completions.create(
            extra_headers={
                "HTTP-Referer": REFERER,
                "X-Title": TITLE,
            },
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )
        return completion.choices[0].message.content
    except Exception as e:
        logging.exception("OPENROUTER LLM ERROR")
        return f"Error generating AI response: {e}"
