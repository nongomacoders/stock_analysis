import os
import asyncio
import logging
from dotenv import load_dotenv
from ollama import AsyncClient

# Initialize
load_dotenv()
# OLLAMA_HOST can be set in .env, e.g., "http://192.168.1.10:11434"
# If not set, it defaults to localhost:11434
OLLAMA_HOST = os.getenv("OLLAMA_HOST")

logger = logging.getLogger(__name__)

# Global state for concurrency control
# Using a semaphore of 1 is safest for local models on standard hardware
_ollama_semaphore = None
_ollama_client = None

def _get_ollama_resources():
    """Lazily initialize global semaphore and client."""
    global _ollama_semaphore, _ollama_client
    if _ollama_semaphore is None:
        _ollama_semaphore = asyncio.Semaphore(1)
    if _ollama_client is None:
        _ollama_client = AsyncClient(host=OLLAMA_HOST)
    return _ollama_semaphore, _ollama_client

async def query_ai(
    prompt: str, 
    model: str = "jse-analyst", #we created this in ollama create jse-analyst -f analyst.Modelfile
    system_prompt: str | None = None, 
    json_mode: bool = False
) -> str:
    """
    Sends a prompt to a local Ollama instance with optimized parameters for financial analysis.
    Uses a semaphore to prevent overloading the local hardware with concurrent requests.
    """
    semaphore, client = _get_ollama_resources()
    
    async with semaphore:
        try:
            messages = []
            if system_prompt:
                messages.append({'role': 'system', 'content': system_prompt})
            
            messages.append({'role': 'user', 'content': prompt})
            
            # Configuration for strict instruction following
            options = {
                "temperature": 0.0,           # Forces deterministic output
                "stop": ["###", "---"],      # Prevents the model from rambling
                "num_predict": 1000,         # Safety limit for token generation
            }

            logger.info("Querying Ollama model: %s (JSON: %s, User prompt length: %d)", 
                        model, "Yes" if json_mode else "No", len(prompt))
            
            # Call the Ollama API with formatting and options
            response = await client.chat(
                model=model, 
                messages=messages,
                format="json" if json_mode else "",
                options=options
            )
            
            content = response.get('message', {}).get('content', '')
            
            if not content:
                logger.warning("Ollama returned an empty response.")
                raise RuntimeError("Empty response from Ollama.")
                
            return content.strip()

        except ConnectionError as e:
            msg = f"Failed to connect to Ollama at {OLLAMA_HOST or 'localhost:11434'}: {e}"
            logger.error(msg)
            raise RuntimeError(msg)
        
        except Exception as e:
            logger.exception("Unexpected error during Ollama query: %s", e)
            raise RuntimeError(f"Error querying Ollama: {e}")

# Simple main for testing the new configuration
if __name__ == "__main__":
    async def test():
        logging.basicConfig(level=logging.INFO)
        # Testing with the new custom model
        res = await query_ai(
            prompt="Significance: Low\nExplanation: Test run.", 
            model="jse-analyst"
        )
        print(f"Response:\n{res}")
    
    asyncio.run(test())