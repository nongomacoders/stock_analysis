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

async def query_ai(prompt: str, model: str = "gemma3") -> str:
    """
    Sends a prompt to a local Ollama instance and returns the response text.
    
    Args:
        prompt: The text prompt to send.
        model: The Ollama model name to use (e.g., 'gemma3', 'llama3').
        
    Returns:
        The text response from the model or an error message.
    """
    try:
        client = AsyncClient(host=OLLAMA_HOST)
        
        message = {'role': 'user', 'content': prompt}
        
        logger.info("Querying Ollama model: %s (Prompt length: %d)", model, len(prompt))
        
        # chat() returns a mapping with 'message', 'done', etc.
        response = await client.chat(model=model, messages=[message])
        
        content = response.get('message', {}).get('content', '')
        
        if not content:
            logger.warning("Ollama returned an empty response.")
            return "Error: Empty response from Ollama."
            
        return content

    except ConnectionError as e:
        logger.error("Failed to connect to Ollama at %s: %s", OLLAMA_HOST or "localhost:11434", e)
        return f"Error: Could not connect to Ollama. Ensure it is running at {OLLAMA_HOST or 'localhost:11434'}."
    
    except Exception as e:
        logger.exception("Unexpected error during Ollama query: %s", e)
        return f"Error querying Ollama: {e}"

# Optional: Simple main for testing
if __name__ == "__main__":
    async def test():
        logging.basicConfig(level=logging.INFO)
        res = await query_ai("Why is the sky blue?")
        print(f"Response: {res}")
    
    asyncio.run(test())
