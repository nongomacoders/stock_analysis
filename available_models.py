import os
from google import genai

# Manually set the path so the SDK can find your "identity"
# Ensure the filename matches exactly what you downloaded
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = (
    "C:/Users/Dion/Desktop/Projects/stock_analysis/service_account_key.json"
)

client = genai.Client(
    vertexai=True, project="gen-lang-client-0567329878", location="us-central1"
)

print("--- Available Models ---")
try:
    # This will now succeed and list the IDs you can use
    for model in client.models.list():
        print(model.name)
except Exception as e:
    print(f"Failed to list models: {e}")
