import re
from enum import Enum
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
    normalized_numeric_value: float | None = None
    token_type: NumericTokenType = NumericTokenType.OTHER
    currency: str | None = None
    scale: str | None = None
    is_percentage: bool = False
    is_per_share: bool = False

CURRENCY_MAP = {
    "R": "ZAR",
    "ZAR": "ZAR",
    "$": "USD",
    "USD": "USD",
    "US$": "USD",
    "€": "EUR",
    "EUR": "EUR",
    "£": "GBP",
    "GBP": "GBP",
}

SCALE_MAP = {
    "billion": "billion",
    "bn": "billion",
    "million": "million",
    "m": "million",
    "thousand": "thousand",
    "k": "thousand",
    "cents": "cents",
    "cent": "cents",
    "c": "cents",
}

# Regex to detect full JSE numeric tokens with surrounding currency / scale / percent
NUMERIC_TOKEN_REGEX = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?P<prefix>(?:\b(?:US\$|USD|EUR|GBP|ZAR)\b|R(?=\s*[+\-\u2013\u2014]?\s*\d)|[\$€£])\s*)?"
    r"(?P<sign>[+\-\u2013\u2014])?\s*"
    r"(?P<num>\d{1,3}(?:[ \u00a0]\d{3}(?!\d))+(?:[.,]\d+)?|\d{1,3}(?:,\d{3}(?!\d))+(?:\.\d+)?|\d+[.,]\d+|\d+)"
    r"(?P<suffix>%(?:\s*points?)?|\s*(?:billion|milli?on|cents?|c\b|bn\b|m\b|thousand|k\b))?",
    re.IGNORECASE
)

def normalize_number_string(num_str: str) -> float | None:
    cleaned = num_str.replace(" ", "").replace("\u00a0", "")
    # Check if comma is decimal separator (e.g. 235,6 or 2562,7)
    if "," in cleaned and "." not in cleaned:
        cleaned = cleaned.replace(",", ".")
    elif "," in cleaned and "." in cleaned:
        # e.g. 2,562.7
        cleaned = cleaned.replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None

def parse_detected_numeric_tokens(sentence: str) -> list[DetectedNumericToken]:
    tokens: list[DetectedNumericToken] = []
    sent_lower = sentence.lower()
    is_guidance_or_range_context = any(k in sent_lower for k in ["between", "range of", "to report", "anticipates"])

    for match in NUMERIC_TOKEN_REGEX.finditer(sentence):
        raw_full = match.group(0).strip()
        if not raw_full:
            continue
        
        prefix = (match.group("prefix") or "").strip()
        sign = (match.group("sign") or "").strip()
        num_part = (match.group("num") or "").strip()
        suffix = (match.group("suffix") or "").strip()

        # If prefix or suffix matched partial word, check boundaries
        # e.g. num_part in middle of a word is guarded by (?<![A-Za-z0-9])
        # Ensure num_part is valid
        num_val = normalize_number_string(num_part)
        if num_val is None:
            continue
        if sign in {"-", "–", "—"}:
            num_val = -abs(num_val)

        # Detect currency
        currency = None
        if prefix:
            clean_pref = prefix.strip()
            currency = CURRENCY_MAP.get(clean_pref.upper(), clean_pref.upper())

        # Detect scale and percentage
        scale = None
        is_percentage = False
        is_per_share = False

        if suffix:
            s_clean = suffix.strip().lower()
            if s_clean.startswith("%"):
                is_percentage = True
            elif s_clean in SCALE_MAP:
                scale = SCALE_MAP[s_clean]
                if scale == "cents":
                    is_per_share = True

        # Check nearby context for cents/per share or range bounds
        start_idx, end_idx = match.span()
        # Look ahead up to 15 chars for cents or per share if not already detected
        lookahead = sentence[end_idx:end_idx+20].lower()
        if not scale and not is_percentage:
            if re.match(r"^\s*cents?\b", lookahead):
                scale = "cents"
                is_per_share = True
            elif re.match(r"^\s*(?:c\b|cps\b)", lookahead):
                scale = "cents"
                is_per_share = True

        # Check if year/date
        is_year = False
        if not currency and not is_percentage and not scale:
            # 4 digit number in 1990..2040 without decimals
            if re.fullmatch(r"\d{4}", num_part):
                val_int = int(num_part)
                if 1990 <= val_int <= 2040:
                    is_year = True

        # Classify token type
        if is_year:
            token_type = NumericTokenType.YEAR_OR_DATE
        elif is_percentage:
            token_type = NumericTokenType.PERCENTAGE
        elif currency:
            token_type = NumericTokenType.CURRENCY_LEVEL
        elif is_per_share or scale == "cents":
            token_type = NumericTokenType.PER_SHARE_LEVEL
        elif is_guidance_or_range_context and "between" in sent_lower:
            # Check if this number is inside a "between X and Y" clause
            token_type = NumericTokenType.RANGE_BOUND if scale or currency else NumericTokenType.RANGE_BOUND
        elif scale in {"million", "billion", "thousand"}:
            token_type = NumericTokenType.CURRENCY_LEVEL if currency else NumericTokenType.PLAIN_LEVEL
        elif num_val is not None:
            token_type = NumericTokenType.PLAIN_LEVEL
        else:
            token_type = NumericTokenType.OTHER

        tokens.append(DetectedNumericToken(
            raw_text=raw_full,
            normalized_numeric_value=num_val,
            token_type=token_type,
            currency=currency,
            scale=scale,
            is_percentage=is_percentage,
            is_per_share=is_per_share
        ))

    return tokens

# Tests
test_cases = [
    ("Revenue R235,6 billion, up 4,3%; up 6,8%", ["R235,6 billion", "4,3%", "6,8%"]),
    ("Cash generated ... R16,6 billion", ["R16,6 billion"]),
    ("Headline earnings per share 2 562,7 cents", ["2 562,7 cents"]),
    ("235,6", ["235,6"]),
    ("235.6", ["235.6"]),
    ("2 562,7", ["2 562,7"]),
    ("2 562.7", ["2 562.7"]),
    ("2,562.7", ["2,562.7"]),
    ("R235,6 million", ["R235,6 million"]),
    ("R2 562 million", ["R2 562 million"]),
    ("$13.7 million", ["$13.7 million"]),
    ("EUR 1.8 billion", ["EUR 1.8 billion"]),
    ("138.30 cents", ["138.30 cents"]),
    ("24.5%", ["24.5%"]),
    ("-11.6%", ["-11.6%"]),
    ("ended 30 June 2025", ["30", "2025"]),
    ("anticipates that it will report: a basic loss per share of between 138.30 cents and 138.48 cents", ["138.30 cents", "138.48 cents"])
]

for text, expected in test_cases:
    toks = parse_detected_numeric_tokens(text)
    print(f"TEXT: '{text}'")
    for t in toks:
        print(f"  -> raw='{t.raw_text}' norm={t.normalized_numeric_value} type={t.token_type.value} curr={t.currency} scale={t.scale} pct={t.is_percentage} per_share={t.is_per_share}")
