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
    """
    Sends a prompt to Gemini via Vertex AI only and returns the full response object.
    
    Args:
        prompt: The text prompt to send.
        model: The Gemini model ID to use (e.g., 'gemini-3-flash-preview').
        
    Returns:
        The GenerativeModel response object or an error string.
    """
    import time
    import asyncio
    import os
    from google.api_core import exceptions as google_exceptions
    from google import genai
    from google.genai import types
    
    start_time = time.time()
    
    # 1. Check Vertex Credentials
    project_id = os.getenv("VERTEX_PROJECT_ID")
    location = os.getenv("VERTEX_LOCATION", "global")
    
    if not project_id:
        logging.error("VERTEX_PROJECT_ID is missing from .env")
        return "Error: Vertex AI not configured. Check your .env file."

    # Attempt the call with retries and exponential backoff
    for attempt in range(3):
        try:
            logging.info("Querying Vertex AI model: %s (Prompt length: %d, Attempt: %d)", model, len(prompt), attempt + 1)
            
            # Use the google-genai Vertex AI Client
            # Note: Uses GOOGLE_APPLICATION_CREDENTIALS for auth
            client = genai.Client(
                vertexai=True, 
                project=project_id, 
                location=location,
                http_options=types.HttpOptions(api_version=os.getenv("VERTEX_API_VERSION", "v1beta1"))
            )
            
            # Vertex endpoints require the full publisher path
            v_model = f"publishers/google/models/{model}"
            
            # Run the synchronous client call in a thread to keep the event loop responsive
            response = await asyncio.wait_for(
                asyncio.to_thread(client.models.generate_content, model=v_model, contents=prompt),
                timeout=120.0
            )
            
            duration = time.time() - start_time
            logging.info("AI response received in %.2f seconds", duration)
            
            return response

        except asyncio.TimeoutError:
            duration = time.time() - start_time
            logging.error("Vertex query timed out after %.2f seconds", duration)
            if attempt < 2:
                logging.info("Retrying after timeout...")
                continue
            return "Error: Vertex AI generation timed out."

        except Exception as e:
            duration = time.time() - start_time
            logging.exception("Vertex AI ERROR after %.2f seconds: %s", duration, e)
            
            if attempt < 2:
                wait_time = (attempt + 1) * 2
                logging.info("Retrying in %ds...", wait_time)
                await asyncio.sleep(wait_time)
                continue
            
            return f"Error generating Vertex AI response: {e}"
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
