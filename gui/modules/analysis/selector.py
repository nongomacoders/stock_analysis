import logging
from modules.analysis import llm, openrouter_llm

logger = logging.getLogger(__name__)

# Task mapping to provider and model
# Format: "task_name": {"provider": "gemini" | "openrouter", "model": "model_name"}
TASK_MAP = {
    "sens": {
        "provider": "openrouter",
        "model": "stepfun/step-3.5-flash:free",
    },
    "price_change": {
        "provider": "gemini",
        "model": "gemini-3-flash-preview", # Upgrade from flash-preview
    },
    "research_summary": {
        "provider": "gemini",
        "model": "gemini-3-flash-preview",
    },
    "spot_price": {
        "provider": "openrouter",
        "model": "stepfun/step-3.5-flash:free",
    },
    "research_extraction": {
        "provider": "openrouter",
        "model": "stepfun/step-3.5-flash:free",
    },
    "deep_research": {
        "provider": "gemini",
        "model": "gemini-3-pro-preview", # Using a strong gemini model for deep research
    },
}

DEFAULT_TASK = {
    "provider": "gemini",
    "model": "gemini-2.0-flash",
}

async def managed_query_ai(task_name: str, prompt: str, **kwargs) -> str:
    """
    Centralized router for AI queries.
    
    Args:
        task_name: Key in TASK_MAP (e.g., 'sens', 'spot_price')
        prompt: The text prompt to send
        **kwargs: Additional arguments to pass to the underlying provider
    """
    config = TASK_MAP.get(task_name, DEFAULT_TASK)
    provider = config["provider"]
    model = config["model"]

    logger.info("Routing task '%s' to provider '%s' using model '%s'", task_name, provider, model)

    if provider == "openrouter":
        return await openrouter_llm.query_ai(prompt, model=model)
    elif provider == "gemini":
        # Pass the model name to our gemini wrapper
        return await llm.query_ai(prompt, model=model)
    else:
        logger.error("Unknown provider '%s' for task '%s'", provider, task_name)
        return f"Error: Unknown provider {provider}"
