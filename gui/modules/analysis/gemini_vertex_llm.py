import os
import asyncio
import logging
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

# Configuration
PROJECT_ID = os.getenv("VERTEX_PROJECT_ID")
# IMPORTANT: Gemma does not support the "global" location. 
LOCATION = os.getenv("VERTEX_LOCATION", "us-central1") 

async def query_ai(
    prompt: str, 
    model: str , # Use the short ID from your list
    system_prompt: str | None = None,
    request_trace: dict | None = None,
    trace_callback=None,
):
    from google import genai
    from google.genai import types

    # Initialize Client - ensure GOOGLE_API_KEY is NOT in your .env
    # to avoid auth ambiguity with the Service Account.
    client = genai.Client(
        vertexai=True,
        project=os.getenv("VERTEX_PROJECT_ID"),
        location=os.getenv("VERTEX_LOCATION", "us-central1"),
        http_options=types.HttpOptions(api_version=os.getenv("VERTEX_API_VERSION", "v1beta1"))
    )

    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=0.7
    )

    for attempt in range(3):
        attempt_record = {"model": model, "temperature": 0.7, "attempt": attempt + 1}
        if request_trace is not None:
            request_trace.update(provider="gemini", model=model, temperature=0.7,
                                 system_prompt=system_prompt)
            request_trace.setdefault("attempts", []).append(attempt_record)
            if trace_callback:
                trace_callback(request_trace)
        try:
            logging.info(f"Querying {model} (Attempt {attempt + 1})")
            
            # SDK handles the 'publishers/google/models/' pathing internally
            response = await client.aio.models.generate_content(
                model=model, 
                contents=prompt,
                config=config
            )
            if request_trace is not None:
                request_trace["response_model_version"] = getattr(response, "model_version", None)
                attempt_record["status"] = "succeeded"
                if trace_callback:
                    trace_callback(request_trace)
            return response

        except Exception as e:
            attempt_record.update(status="failed", error=str(e))
            if request_trace is not None and trace_callback:
                trace_callback(request_trace)
            err_msg = str(e).lower()
            if ("not found" in err_msg or "404" in err_msg) and attempt == 0:
                # Fallback to a model that doesn't require billing for testing
                logging.info("Model not found/No access. Falling back to gemini-3-flash-preview...")
                model = "gemini-3.1-pro-preview"
                continue
            
            if attempt < 2:
                await asyncio.sleep((attempt + 1) * 2)
                continue
            raise RuntimeError(f"Vertex AI Error: {e}")