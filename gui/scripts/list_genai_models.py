"""List available Gemini models for your current API key.

This uses the new `google-genai` SDK (imported as `from google import genai`).

Examples:
  python gui/scripts/list_genai_models.py
  python gui/scripts/list_genai_models.py | Select-String generateContent

Notes:
- Requires `GOOGLE_API_KEY` to be set in the environment.
- Output fields vary slightly across SDK versions; this script prints best-effort details.
"""

from __future__ import annotations

import os
import sys
from typing import Any


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if hasattr(obj, key):
        return getattr(obj, key)
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default


def main() -> int:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("GOOGLE_API_KEY is not set; cannot list models.")
        return 2

    try:
        from google import genai
    except Exception as e:
        print(f"Failed to import google.genai (google-genai). Install/upgrade via: python -m pip install -U google-genai\n{e}")
        return 2

    client = genai.Client()

    try:
        models_iter = client.models.list()
    except Exception as e:
        print(f"Failed to list models: {e}")
        return 1

    count = 0
    for m in models_iter:
        count += 1
        name = _get(m, "name", "(no name)")

        # Different SDK versions expose different fields.
        supported_methods = (
            _get(m, "supported_generation_methods")
            or _get(m, "supported_methods")
            or _get(m, "supported_actions")
            or []
        )

        # Normalize to a list of strings.
        if isinstance(supported_methods, str):
            supported_methods_list = [supported_methods]
        elif supported_methods is None:
            supported_methods_list = []
        else:
            try:
                supported_methods_list = list(supported_methods)
            except Exception:
                supported_methods_list = []

        # Some responses nest methods under "methods".
        if not supported_methods_list:
            methods = _get(m, "methods")
            if isinstance(methods, (list, tuple)):
                supported_methods_list = [str(x) for x in methods]

        methods_str = ", ".join([str(x) for x in supported_methods_list]) if supported_methods_list else "(unknown)"

        print(f"{name}\t{methods_str}")

    if count == 0:
        print("No models returned.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
