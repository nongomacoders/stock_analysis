import google.generativeai as genai
import os
from dotenv import load_dotenv
import logging

# Initialize
load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")

if not API_KEY:
    logging.warning("GOOGLE_API_KEY not found. AI features will fail.")
else:
    # Use default transport (gRPC) as 'rest' transport can cause async issues with the SDK
    genai.configure(api_key=API_KEY)


async def query_ai(prompt: str, model: str = "gemini-3-flash-preview"):
    """Sends a prompt to Gemini and returns the text response asynchronously."""
    import time
    import asyncio
    import os
    from google.api_core import exceptions as google_exceptions
    start_time = time.time()
    
    # Ensure API key is present
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logging.error("GOOGLE_API_KEY is missing or empty in query_ai")
        return "Error: GOOGLE_API_KEY not configured. Check your .env file."

    # Use specified model
    model_name = model
    
    # Attempt the call with retries and exponential backoff
    for attempt in range(3):
        try:
            logging.info("Querying AI model: %s (Prompt length: %d, Attempt: %d)", model_name, len(prompt), attempt + 1)
            
            # Use default configuration
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(model_name)
            
            # Use generate_content_async with a substantial timeout
            # We wrap it carefully to handle the case where the SDK might return a non-awaitable
            request = model.generate_content_async(prompt)
            
            if not asyncio.iscoroutine(request) and not hasattr(request, "__await__"):
                logging.error("SDK Error: generate_content_async returned a non-awaitable %s", type(request))
                # Fallback to sync if needed, but this should not happen with gRPC
                response = request
            else:
                response = await asyncio.wait_for(request, timeout=120.0)
            
            duration = time.time() - start_time
            logging.info("AI response received in %.2f seconds", duration)
            
            return response.text

        except asyncio.TimeoutError:
            duration = time.time() - start_time
            logging.error("AI query timed out after %.2f seconds", duration)
            if attempt < 2:
                logging.info("Retrying after timeout...")
                continue
            return "Error: AI generation timed out. The model took too long to respond."

        except (google_exceptions.Cancelled, google_exceptions.ServiceUnavailable, google_exceptions.ResourceExhausted) as e:
            # 499 (Cancelled), 503 (Unavailable), 429 (ResourceExhausted)
            duration = time.time() - start_time
            error_type = type(e).__name__
            logging.warning("AI query failed with %s after %.2f seconds: %s", error_type, duration, e)
            
            if attempt < 2:
                wait_time = (attempt + 1) * 2 # 2s, 4s
                logging.info("Retrying in %ds...", wait_time)
                await asyncio.sleep(wait_time)
                continue
            return f"Error: The AI service is currently busy or interrupted ({error_type}). Please try again in a moment."

        except Exception as e:
            duration = time.time() - start_time
            logging.exception("LLM ERROR after %.2f seconds: %s", duration, e)
            
            # Fallback attempt for model naming issues
            if ("not found" in str(e).lower() or "404" in str(e)) and attempt == 0:
                logging.info("Model name issue? Attempting fallback to gemini-3-pro-preview...")
                model_name = "gemini-3-pro-preview"
                continue
            
            return f"Error generating AI response: {e}"
