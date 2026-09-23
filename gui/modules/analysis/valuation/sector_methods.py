"""Reviewable sector/method defaults; no Gemini routing."""
DEFAULT_METHODS = {
    "mining": {"DCF", "SOTP"},
    "retail": {"DCF"},
    "holding_company": {"SOTP"},
    "bank": {"RESIDUAL_INCOME"},
}

def validate_sector_method(sector: str | None, method: str, override_rationale: str | None) -> None:
    if sector is None:
        if method == "RESIDUAL_INCOME":
            raise ValueError("Bank residual-income plan requires explicit bank sector")
        return
    if sector not in DEFAULT_METHODS:
        raise ValueError("Unknown sector method mapping")
    if method not in DEFAULT_METHODS[sector] and not (override_rationale and override_rationale.strip()):
        raise ValueError("Non-default sector method requires stored analyst override rationale")
    if sector == "bank" and method != "RESIDUAL_INCOME":
        raise ValueError("Bank equity requires a bank method; enterprise bridge is ineligible")
