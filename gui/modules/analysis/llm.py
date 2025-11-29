import google.generativeai as genai
import os
from dotenv import load_dotenv

# Initialize
load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")

if not API_KEY:
    print("WARNING: GOOGLE_API_KEY not found. AI features will fail.")
else:
    genai.configure(api_key=API_KEY)


async def query_ai(prompt: str):
    """Sends a prompt to Gemini and returns the text response asynchronously."""
    try:
        model = genai.GenerativeModel("gemini-2.5-pro")
        # Use generate_content_async for non-blocking calls
        response = await model.generate_content_async(prompt)
        return response.text
    except Exception as e:
        print(f"LLM ERROR: {e}")
        return f"Error generating AI response: {e}"
