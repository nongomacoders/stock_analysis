import os
import logging
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Setup logging and environment
load_dotenv()
logging.basicConfig(level=logging.INFO)

def list_vertex_models():
    # 1. Get credentials from .env
    project_id = os.getenv("VERTEX_PROJECT_ID")
    location = os.getenv("VERTEX_LOCATION", "us-central1")
    
    if not project_id:
        print("❌ Error: VERTEX_PROJECT_ID not found in your .env file.")
        return

    # 2. Initialize the Vertex AI Client
    # This uses your GOOGLE_APPLICATION_CREDENTIALS for authentication
    client = genai.Client(
        vertexai=True,
        project=project_id,
        location=location,
        http_options=types.HttpOptions(api_version=os.getenv("VERTEX_API_VERSION", "v1beta1"))
    )

    print(f"\n--- Available Models in {location} for {project_id} ---\n")

    try:
        # 3. Fetch and display models
        # Note: The 'name' usually follows the format 'publishers/google/models/...'
        models = client.models.list()
        
        count = 0
        for model in models:
            # Extract the short ID (e.g., 'gemini-3.1-flash-preview')
            short_id = model.name.split('/')[-1] if '/' in model.name else model.name
            
            print(f"ID: {short_id:<35} | Display Name: {model.display_name}")
            count += 1
            
        if count == 0:
            print("⚠️ No models found. Check if your Service Account has 'Vertex AI User' permissions.")
            
    except Exception as e:
        print(f"❌ Failed to list models: {e}")
        print("\nTroubleshooting Tips:")
        print(f"1. Ensure the Vertex AI API is enabled for project '{project_id}'.")
        print("2. Confirm your location supports these models (try 'us-central1' if using 'global').")
        print("3. Check that your Service Account is added to the IAM list with 'Vertex AI User' role.")

if __name__ == "__main__":
    list_vertex_models()