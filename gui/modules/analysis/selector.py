import logging
from modules.analysis import gemini_vertex_llm, openrouter_llm, ollama_llm

logger = logging.getLogger(__name__)

# 1. Define Model Groups
# Access these via MODELS["ollama"][0], etc.
MODELS = {
    "ollama": [
        "gemma4:e4b",  # Index 0
        "qwen3:8b"               # Index 1
    ],
    "gemini": [
        "gemini-3-flash-preview",          # Index 0
        "gemini-3.1-flash-lite-preview"                   # Index 1
    ],
    "openrouter": [
        "google/gemma-4-26b-a4b-it:free",         # Index 0
        "nvidia/nemotron-3-super-120b-a12b:free" # Index 1
    ]
}

# 2. Task mapping using the new structure
# This is much cleaner and shows exactly which "tier" of a provider you are using.
TASK_MAP = {
    "sens":                {"p": "gemini",     "m": MODELS["gemini"][1]},
    "price_change":        {"p": "ollama",     "m": MODELS["ollama"][0]},
    "research_summary":    {"p": "ollama",     "m": MODELS["ollama"][0]},
    "spot_price":          {"p": "ollama",     "m": MODELS["ollama"][0]},
    "research_extraction": {"p": "ollama",     "m": MODELS["ollama"][0]},
    "deep_research":       {"p": "gemini",     "m": MODELS["gemini"][0]},
}

DEFAULT_TASK = {"p": "ollama", "m": MODELS["ollama"][0]}

async def managed_query_ai(task_name: str, prompt: str, **kwargs) -> str:
    config = TASK_MAP.get(task_name, DEFAULT_TASK)
    provider = config["p"]
    model = config["m"]

    logger.info(f"Routing task '{task_name}' to {provider} using {model}")

    # Routing logic remains clean
    if provider == "openrouter":
        return await openrouter_llm.query_ai(prompt, model=model)
    elif provider == "gemini":
        return await gemini_vertex_llm.query_ai(prompt, model=model)
    elif provider == "ollama":
        return await ollama_llm.query_ai(prompt, model=model)
    
    logger.error(f"Unknown provider '{provider}'")
    return f"Error: Unknown provider {provider}"