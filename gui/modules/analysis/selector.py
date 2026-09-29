import logging
from modules.analysis import gemini_vertex_llm, openrouter_llm, ollama_llm

logger = logging.getLogger(__name__)

# 1. Define Model Groups
# Access these via MODELS["ollama"][0], etc.
MODELS = {
    "ollama": [
        "gemma4:e4b-it-q8_0",  # Index 0
        "qwen3:8b"               # Index 1
    ],
    "gemini": [
        "gemini-3.8-flash",          # Index 0
        "gemini-3.6-flash"                   # Index 1
    ],
    "openrouter": [
        "google/gemma-4-26b-a4b-it:free",         # Index 0
        "nvidia/nemotron-3-super-120b-a12b:free" # Index 1
    ]
}

# 2. Task mapping using the new structure
# Maps tasks to provider ('p'), model ('m'), and appropriate temperature ('t')
TASK_MAP = {
    # Deterministic financial extraction & adjudication: 0.0
    "sens":                {"p": "gemini",     "m": MODELS["gemini"][0], "t": 0.0},
    "price_change":        {"p": "gemini",     "m": MODELS["gemini"][0], "t": 0.0},
    "spot_price":          {"p": "gemini",     "m": MODELS["gemini"][0], "t": 0.0},
    "research_extraction": {"p": "gemini",     "m": MODELS["gemini"][0], "t": 0.0},
    "afs_adjudication":    {"p": "gemini",     "m": MODELS["gemini"][0], "t": 0.0},
    "afs_gemini_candidate": {"p": "gemini",    "m": MODELS["gemini"][0], "t": 0.0},
    "afs_gemini_paragraph": {"p": "gemini",    "m": MODELS["gemini"][0], "t": 0.0},
    "afs_gemini_mode_a":   {"p": "gemini",     "m": MODELS["gemini"][0], "t": 0.0},
    "afs_gemini_mode_b":   {"p": "gemini",     "m": MODELS["gemini"][0], "t": 0.0},

    # Analytical synthesis, comparison, & challenge passes: 0.2
    "research_summary":    {"p": "gemini",     "m": MODELS["gemini"][0], "t": 0.2},
    "deep_research":       {"p": "gemini",     "m": MODELS["gemini"][0], "t": 0.2},
    "research_comparison": {"p": "gemini",     "m": MODELS["gemini"][0], "t": 0.2},
    "afs_challenge":       {"p": "gemini",     "m": MODELS["gemini"][0], "t": 0.2},
}

DEFAULT_TASK = {"p": "gemini", "m": MODELS["gemini"][0], "t": 0.0}

async def managed_query_ai(task_name: str, prompt: str, **kwargs) -> str:
    config = TASK_MAP.get(task_name, DEFAULT_TASK)
    provider = config["p"]
    model = config["m"]
    temperature = kwargs.pop("temperature", config.get("t", 0.0))
    trace = kwargs.get("request_trace")
    if trace is not None:
        trace.update(provider=provider, model=model, temperature=temperature)

    logger.info(f"Routing task '{task_name}' to {provider} using {model} (temp={temperature})")

    # Routing logic remains clean
    if provider == "openrouter":
        return await openrouter_llm.query_ai(prompt, model=model)
    elif provider == "gemini":
        return await gemini_vertex_llm.query_ai(
            prompt,
            model=model,
            system_prompt=kwargs.get("system_prompt"),
            temperature=temperature,
            request_trace=trace,
            trace_callback=kwargs.get("trace_callback"),
        )
    elif provider == "ollama":
        return await ollama_llm.query_ai(prompt, model=model)
    
    logger.error(f"Unknown provider '{provider}'")
    return f"Error: Unknown provider {provider}"