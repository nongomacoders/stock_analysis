import re
from modules.analysis.financial_classifier_benchmark import (
    NumericTokenType,
    DetectedNumericToken,
    parse_detected_numeric_tokens,
)

LEXICAL_CONNECTORS_AFTER = re.compile(
    r"^\s*(?:of|at|to|from|between|was|is|were|amounted\s+to|increased\s+to|decreased\s+to|improved\s+to|fell\s+to|rose\s+to|reached|stood\s+at|by|:|=)\s*",
    re.IGNORECASE
)

def associate_numeric_tokens(
    alias_text: str,
    alias_start_in_sent: int,
    alias_end_in_sent: int,
    sentence: str,
    concept_id: str | None,
    norm_label: str,
    tokens: list[DetectedNumericToken],
    token_spans: list[tuple[int, int]]
) -> tuple[str | None, str | None, float, str]:
    """Deterministically associates detected numeric tokens with matched alias based on distance, connectors, and unit compatibility."""
    
    # Filter out dates, section numbers, list markers, and other
    valid_candidates = []
    for tok, span in zip(tokens, token_spans):
        if tok.token_type in (NumericTokenType.YEAR_OR_DATE, NumericTokenType.OTHER):
            continue
        valid_candidates.append((tok, span))
        
    if not valid_candidates:
        return None, None, 1.0, "No valid numeric metric candidates found in sentence context"
        
    is_margin = (concept_id in {"gross_margin", "trading_margin", "operating_margin", "ebitda_margin"}) or ("margin" in norm_label)
    is_per_share = (concept_id in {"eps", "heps", "diluted_eps", "diluted_heps", "dividend_per_share", "nav_per_share", "cash_flow_per_share"}) or ("per share" in norm_label)
    is_currency = (concept_id in {"accounting_revenue", "trading_profit", "operating_profit", "ebit", "pbit", "ebitda", "reported_net_debt", "cash_and_cash_equivalents", "total_capex"}) or any(k in norm_label for k in ["revenue", "profit", "ebit", "capex", "debt", "cash"])
    is_share_count = (concept_id in {"issued_shares_current", "treasury_shares", "wanos", "diluted_wanos"}) or ("shares in issue" in norm_label)

    metric_cand = None
    change_cand = None
    reasons = []

    # Score candidates
    scored = []
    for tok, (t_start, t_end) in valid_candidates:
        is_after = t_start >= alias_end_in_sent
        dist = t_start - alias_end_in_sent if is_after else alias_start_in_sent - t_end
        
        # Check connector
        between_text = sentence[alias_end_in_sent:t_start] if is_after else sentence[t_end:alias_start_in_sent]
        has_connector = bool(LEXICAL_CONNECTORS_AFTER.search(between_text)) if is_after else bool(re.search(r"\b(?:of|was|is|were)\s*$", between_text, re.I))

        # Check unit compatibility
        compatible = True
        is_change_type = tok.is_percentage or tok.token_type == NumericTokenType.PERCENTAGE
        
        if is_margin:
            if not is_change_type:
                compatible = False
        elif is_per_share:
            if tok.token_type == NumericTokenType.CURRENCY_LEVEL and tok.scale in {"million", "billion"}:
                compatible = False
        elif is_currency:
            if is_change_type:
                # Percentage for currency concept is a change/growth rate, not metric level
                pass
        elif is_share_count:
            if tok.currency or is_change_type:
                compatible = False

        scored.append({
            "token": tok,
            "span": (t_start, t_end),
            "is_after": is_after,
            "dist": dist,
            "has_connector": has_connector,
            "compatible": compatible,
            "is_change_type": is_change_type
        })

    # Find candidate metric token: prefer compatible, closest, with connector
    metric_candidates = [c for c in scored if c["compatible"] and (not c["is_change_type"] or is_margin)]
    if metric_candidates:
        # Sort by: has_connector desc, is_after desc, dist asc
        metric_candidates.sort(key=lambda c: (-int(c["has_connector"]), -int(c["is_after"]), c["dist"]))
        best_m = metric_candidates[0]
        metric_cand = best_m["token"].raw_text
        reasons.append(f"Associated metric level '{metric_cand}' (dist={best_m['dist']}, connector={best_m['has_connector']}, compatible=True)")

    # Find candidate change token
    change_candidates = [c for c in scored if c["is_change_type"] and not is_margin]
    if change_candidates:
        change_candidates.sort(key=lambda c: (-int(c["has_connector"]), -int(c["is_after"]), c["dist"]))
        best_c = change_candidates[0]
        change_cand = best_c["token"].raw_text
        reasons.append(f"Associated change rate '{change_cand}'")

    confidence = 0.95 if (metric_cand or change_cand) else 0.50
    return metric_cand, change_cand, confidence, "; ".join(reasons)

# Test BENCH-0012
sent_0012 = "mine operating loss of $1.0 million) as gross margin improved to -1.8% in Q3 2025 from -9.4% in"
toks_0012 = parse_detected_numeric_tokens(sent_0012)
# Find spans
spans_0012 = []
for t in toks_0012:
    idx = sent_0012.find(t.raw_text.replace(" cents", ""))
    spans_0012.append((idx, idx + len(t.raw_text)))

alias_0012 = "gross margin improved to"
a_start = sent_0012.find(alias_0012)
a_end = a_start + len(alias_0012)

m, c, conf, r = associate_numeric_tokens(
    alias_text=alias_0012,
    alias_start_in_sent=a_start,
    alias_end_in_sent=a_end,
    sentence=sent_0012,
    concept_id="gross_margin",
    norm_label="gross margin improved to",
    tokens=toks_0012,
    token_spans=spans_0012
)
print("BENCH-0012 Metric cand:", m)
print("BENCH-0012 Change cand:", c)
print("BENCH-0012 Reason:", r)
