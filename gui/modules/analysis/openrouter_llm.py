from openai import AsyncOpenAI
import os
import asyncio
from dotenv import load_dotenv
import logging
from openai import AsyncOpenAI, APIStatusError, APITimeoutError, RateLimitError

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


async def query_ai(prompt: str, model: str = "stepfun/step-3.5-flash:free", max_retries: int = 3):
    """Sends a prompt to OpenRouter with retries for transient errors."""
    if not client:
        return "Error generating AI response: OPENROUTER_API_KEY not found."
    
    backoff = 2  # Starting backoff in seconds
    
    for attempt in range(max_retries):
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
                ],
                timeout=45.0
            )
            return completion.choices[0].message.content

        except RateLimitError as e:
            if attempt == max_retries - 1:
                raise # Re-raise to trigger failure in engine.py
            logging.warning("OpenRouter Rate Limit (429). Retrying in %ds...", backoff)
            await asyncio.sleep(backoff)
            backoff *= 2

        except (APIStatusError, APITimeoutError) as e:
            # Retry on 5xx or timeouts
            status_code = getattr(e, "status_code", 500)
            if status_code >= 500 or isinstance(e, APITimeoutError):
                if attempt == max_retries - 1:
                    raise # Re-raise to trigger failure in engine.py
                logging.warning("OpenRouter Server Error (%s). Retrying in %ds...", status_code, backoff)
                await asyncio.sleep(backoff)
                backoff *= 2
            else:
                # 4xx errors that aren't 429 shouldn't be retried (e.g. 401, 400)
                logging.error("OpenRouter Non-Retryable Error: %s", e)
                raise # Re-raise

        except Exception as e:
            logging.exception("OPENROUTER UNEXPECTED ERROR")
            raise # Re-raise
    
    raise Exception("Maximum retries reached.")
