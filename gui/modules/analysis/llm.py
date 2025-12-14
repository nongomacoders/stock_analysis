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
    genai.configure(api_key=API_KEY)


async def query_ai(prompt: str):
    """Sends a prompt to Gemini and returns the text response asynchronously."""
    try:
        model = genai.GenerativeModel("gemini-3-pro-preview")
        # Use generate_content_async for non-blocking calls
        response = await model.generate_content_async(prompt)
        return response.text
    except Exception as e:
        logging.exception("LLM ERROR")
        return f"Error generating AI response: {e}"
