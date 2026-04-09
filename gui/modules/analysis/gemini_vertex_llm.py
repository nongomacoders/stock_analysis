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

# Initialize the Native Vertex AI Async Client
client = genai.Client(
    vertexai=True,
    project=PROJECT_ID,
    location=LOCATION
)

async def query_ai(
    prompt: str, 
    model: str , # Use the short ID from your list
    system_prompt: str | None = None
):
    from google import genai
    from google.genai import types

    # Initialize Client - ensure GOOGLE_API_KEY is NOT in your .env
    # to avoid auth ambiguity with the Service Account.
    client = genai.Client(
        vertexai=True,
        project=os.getenv("VERTEX_PROJECT_ID"),
        location=os.getenv("VERTEX_LOCATION", "us-central1")
    )

    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=0.7
    )

    for attempt in range(3):
        try:
            logging.info(f"Querying {model} (Attempt {attempt + 1})")
            
            # SDK handles the 'publishers/google/models/' pathing internally
            response = await client.aio.models.generate_content(
                model=model, 
                contents=prompt,
                config=config
            )
            return response

        except Exception as e:
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