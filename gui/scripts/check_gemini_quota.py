import os
import requests
from dotenv import load_dotenv

load_dotenv()


def check_detailed_quotas():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("❌ Error: GOOGLE_API_KEY not found.")
        return

    # Base URL for the Generative Language API metadata
    # Note: Google doesn't provide a single 'remaining' endpoint,
    # but we can check the headers of a dummy request to see limits.
    url = "https://generativelanguage.googleapis.com/v1beta/models?key=" + api_key

    print("=" * 50)
    print("🔍 GEMINI API QUOTA DIAGNOSTICS")
    print("=" * 50)

    try:
        response = requests.get(url)

        # Check Rate Limit Headers (if present)
        headers = response.headers
        rpm_limit = headers.get("x-goog-ratelimit-limit", "Unknown")
        rpm_remaining = headers.get("x-goog-ratelimit-remaining", "Unknown")

        print(f"📡 API Status: {response.status_code}")
        if response.status_code == 429:
            print("🔴 CURRENT STATE: RESOURCE_EXHAUSTED (Quota Reached)")
        else:
            print("🟢 CURRENT STATE: Healthy")

        print(f"\n📈 Rate Limits (Per Minute):")
        print(f"   Limit:     {rpm_limit}")
        print(f"   Remaining: {rpm_remaining}")

        # Check File Search Storage via the endpoint we used before
        base_url = "https://generativelanguage.googleapis.com/v1beta"
        store_res = requests.get(
            f"{base_url}/fileSearchStores", params={"key": api_key}
        )

        if store_res.status_code == 200:
            stores = store_res.json().get("fileSearchStores", [])
            total_bytes = sum(int(s.get("sizeBytes", 0)) for s in stores)
            print(f"\n📂 File Search Storage:")
            print(f"   Total Stores:   {len(stores)}")
            print(f"   Storage Used:   {total_bytes / (1024*1024):.2f} MB / 1000 MB")

        print("\n📋 Model Constraints (Free Tier):")
        print("   Gemini 3 Flash (2.0): ~20 Requests / Day")
        print("   Gemini 1.5 Flash:     ~15 Requests / Minute | 1,500 Requests / Day")

    except Exception as e:
        print(f"❌ Diagnostic failed: {e}")

    print("=" * 50)


if __name__ == "__main__":
    check_detailed_quotas()
