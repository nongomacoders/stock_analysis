import re
from enum import Enum
from typing import Any
from pydantic import BaseModel

class NumericTokenType(str, Enum):
    YEAR_OR_DATE = "YEAR_OR_DATE"
    PERCENTAGE = "PERCENTAGE"
    CURRENCY_LEVEL = "CURRENCY_LEVEL"
    PER_SHARE_LEVEL = "PER_SHARE_LEVEL"
    PLAIN_LEVEL = "PLAIN_LEVEL"
    RANGE_BOUND = "RANGE_BOUND"
    OTHER = "OTHER"

class DetectedNumericToken(BaseModel):
    raw_text: str
    clean_numeric: str
    normalized_numeric_value: float | None = None
    token_type: NumericTokenType = NumericTokenType.PLAIN_LEVEL
    currency: str | None = None
    scale: str | None = None
    is_percentage: bool = False
    is_per_share: bool = False
    is_year_or_date: bool = False

# Pattern:
# Prefix:
#   ISO codes: US$, USD, EUR, GBP, ZAR with word boundaries
#   Rand: R preceded by boundary/non-alpha and followed by digits: (?<![A-Za-z])R(?=[+\-\u2013\u2014]?\s*\d)
#   Symbols: $, €, £
# Negative lookbehind before num: ensure not attached to letter like Q3, H1, FY24
PATTERN = re.compile(
    r"(?P<prefix>(?:\b(?:US\$|USD|EUR|GBP|ZAR)\b|(?<![A-Za-z])R(?=[+\-\u2013\u2014]?\s*\d)|[\$€£])\s*)?"
    r"(?P<sign>[+\-\u2013\u2014])?\s*"
    r"(?<![A-Za-z])"  # Do not match digit immediately preceded by letter (e.g. Q3, H1, FY2025)
    r"(?P<num>\d{1,3}(?:[ \u00a0]\d{3}(?!\d))+(?:[.,]\d+)?|\d{1,3}(?:,\d{3}(?!\d))+(?:\.\d+)?|\d+[.,]\d+|\d+)"
    r"(?P<suffix>%(?:\s*points?)?|\s*(?:billion|milli?on|cents?|c\b|bn\b|m\b|thousand|k\b))?",
    re.IGNORECASE
)

def parse_detected_numeric_tokens(sentence: str) -> list[DetectedNumericToken]:
    tokens = []
    
    for m in PATTERN.finditer(sentence):
        full_match = m.group(0).strip()
        prefix = (m.group("prefix") or "").strip()
        sign = (m.group("sign") or "").strip()
        num_str = m.group("num") or ""
        suffix = (m.group("suffix") or "").strip()
        
        if not num_str:
            continue
            
        num_clean = num_str.replace("\u00a0", " ")
        
        # Check if year: 4-digit number 1990-2040 with no currency, scale, or %
        is_year = False
        if not prefix and not suffix and not sign:
            if re.fullmatch(r"(?:19|20)\d{2}", num_clean):
                val_int = int(num_clean)
                if 1990 <= val_int <= 2040:
                    is_year = True
        
        clean_num = num_clean
        if " " in num_clean:
            parts = num_clean.split(" ")
            last = parts[-1].replace(",", ".")
            clean_num = "".join(parts[:-1]) + last
        elif "," in num_clean and "." in num_clean:
            clean_num = num_clean.replace(",", "")
        elif "," in num_clean:
            clean_num = num_clean.replace(",", ".")
            
        try:
            val = float(clean_num)
            if sign in {"-", "–", "—", "\u2013", "\u2014"}:
                val = -val
            norm_val = val
        except ValueError:
            norm_val = None

        currency = None
        if prefix:
            p_up = prefix.upper()
            if p_up == "R" or p_up == "ZAR":
                currency = "ZAR"
            elif "$" in p_up or "USD" in p_up:
                currency = "USD"
            elif "EUR" in p_up or "€" in p_up:
                currency = "EUR"
            elif "GBP" in p_up or "£" in p_up:
                currency = "GBP"
            else:
                currency = prefix

        scale = None
        is_pct = False
        is_ps = False
        s_low = suffix.lower()
        if "%" in s_low:
            is_pct = True
        elif "billion" in s_low or s_low == "bn":
            scale = "billion"
        elif "million" in s_low or s_low == "m":
            scale = "million"
        elif "thousand" in s_low or s_low == "k":
            scale = "thousand"
        elif "cent" in s_low or s_low == "c":
            scale = "cents"
            is_ps = True

        # Token type
        if is_year:
            tok_type = NumericTokenType.YEAR_OR_DATE
        elif is_pct:
            tok_type = NumericTokenType.PERCENTAGE
        elif currency or (scale in {"billion", "million", "thousand"}):
            tok_type = NumericTokenType.CURRENCY_LEVEL
        elif is_ps or "cents" in s_low or "per share" in sentence.lower():
            tok_type = NumericTokenType.PER_SHARE_LEVEL
        else:
            tok_type = NumericTokenType.PLAIN_LEVEL

        # Check for range: between X and Y
        start_pos = m.start()
        preceding = sentence[:start_pos].lower()
        if "between" in preceding[-25:] or "from" in preceding[-20:]:
            if tok_type == NumericTokenType.PLAIN_LEVEL:
                tok_type = NumericTokenType.RANGE_BOUND

        tokens.append(DetectedNumericToken(
            raw_text=full_match,
            clean_numeric=num_str,
            normalized_numeric_value=norm_val,
            token_type=tok_type,
            currency=currency,
            scale=scale,
            is_percentage=is_pct,
            is_per_share=is_ps,
            is_year_or_date=is_year
        ))

    return tokens

# Tests on user examples
test_cases = [
    "Revenue R235,6 billion, up 4,3%; up 6,8%",
    "Cash generated ... R16,6 billion",
    "Headline earnings per share 2 562,7 cents",
    "Revenue for Q3 2025 increased to $13.7 million (Q3 2024 – $11.0 million), representing a $2.7 million or 24.5% increase.",
    "anticipates that it will report: a basic loss per share of between 138.30 cents and 138.48 cents",
    "Headline earnings per share increase 14%",
    "-11.6%",
    "EUR 1.8 billion",
    "235,6",
    "235.6",
    "2 562,7",
    "2 562.7",
    "2,562.7",
    "R235,6 million",
    "R2 562 million",
    "$13.7 million",
    "138.30 cents",
    "24.5%",
]

for idx, tc in enumerate(test_cases, 1):
    toks = parse_detected_numeric_tokens(tc)
    print(f"\nCase {idx}: {tc}")
    for t in toks:
        print(f"  raw: {t.raw_text!r:25} clean: {t.clean_numeric!r:10} norm: {t.normalized_numeric_value!r:10} type: {t.token_type.value:15} curr: {t.currency} scale: {t.scale}")
