"""Read-only post-calculation prompt; narrative never feeds a valuation result."""
import json
from .models import ValuationResult

INSTRUCTION = (
    "The valuation numbers below were calculated by Python.\n"
    "Do not change, recalculate, replace or infer alternative target prices.\n"
    "If you disagree with an assumption, flag it qualitatively.\n"
    "Explain the investment thesis, catalysts, risks, assumption changes, sensitivity "
    "and valuation interpretation only from the supplied result.\n"
)


def build_valuation_narrative_prompt(result: ValuationResult) -> str:
    return INSTRUCTION + "\nPYTHON_VALUATION_RESULT_JSON_BEGIN\n" + json.dumps(
        result.model_dump(mode="json"), ensure_ascii=False, indent=2
    ) + "\nPYTHON_VALUATION_RESULT_JSON_END"
