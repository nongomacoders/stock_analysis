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

_cached_client: genai.Client | None = None


def get_vertex_client() -> genai.Client:
    """Lazily initialize and return a cached singleton genai.Client."""
    global _cached_client
    if _cached_client is None:
        _cached_client = genai.Client(
            vertexai=True,
            project=os.getenv("VERTEX_PROJECT_ID"),
            location=os.getenv("VERTEX_LOCATION", "us-central1"),
            http_options=types.HttpOptions(api_version=os.getenv("VERTEX_API_VERSION", "v1beta1")),
        )
    return _cached_client


async def query_ai(
    prompt: str,
    model: str,
    system_prompt: str | None = None,
    temperature: float = 0.0,
    request_trace: dict | None = None,
    trace_callback=None,
):
    client = get_vertex_client()

    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=temperature,
    )

    for attempt in range(4):
        attempt_record = {"model": model, "temperature": temperature, "attempt": attempt + 1}
        if request_trace is not None:
            request_trace.update(
                provider="gemini",
                model=model,
                temperature=temperature,
                system_prompt=system_prompt,
            )
            request_trace.setdefault("attempts", []).append(attempt_record)
            if trace_callback:
                trace_callback(request_trace)
        try:
            logging.info("Querying %s (Attempt %d, temp=%.2f)", model, attempt + 1, temperature)

            # SDK handles the 'publishers/google/models/' pathing internally
            response = await client.aio.models.generate_content(
                model=model,
                contents=prompt,
                config=config,
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

            if attempt < 3:
                backoff = (attempt + 1) * 3
                logging.warning("Vertex AI query failed (attempt %d/4): %s. Retrying in %ds...", attempt + 1, e, backoff)
                await asyncio.sleep(backoff)
                continue
            raise RuntimeError(f"Vertex AI Error: {e}")