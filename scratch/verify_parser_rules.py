import re
from typing import Any
from enum import Enum
from pydantic import BaseModel, Field

from modules.analysis.financial_concept_dictionary import (
    AliasStatus,
    BasisEvidence,
    CapexBasis,
    DilutionBasis,
    DividendTaxBasis,
    LeaseInclusion,
    MarginDenominator,
    MetricBasis,
    OperationScope,
    ProfitAttribution,
    SemanticQualifiers,
)

# Enums
class ValuationEligibility(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    ELIGIBLE_WITH_QUALIFIER = "ELIGIBLE_WITH_QUALIFIER"
    REQUIRES_SCOPE = "REQUIRES_SCOPE"
    REQUIRES_BASIS = "REQUIRES_BASIS"
    REQUIRES_PERIOD = "REQUIRES_PERIOD"
    REQUIRES_SOURCE_SECTION = "REQUIRES_SOURCE_SECTION"
    INFORMATIONAL_ONLY = "INFORMATIONAL_ONLY"
    PROHIBITED = "PROHIBITED"

class AliasRole(str, Enum):
    DIRECT_VALUE_LABEL = "DIRECT_VALUE_LABEL"
    CHANGE_STATEMENT = "CHANGE_STATEMENT"
    GUIDANCE_STATEMENT = "GUIDANCE_STATEMENT"
    CONCEPT_MENTION_ONLY = "CONCEPT_MENTION_ONLY"

class ValuePattern(str, Enum):
    DIRECT_LEVEL = "DIRECT_LEVEL"
    CHANGE_RATE_ONLY = "CHANGE_RATE_ONLY"
    CHANGE_RATE_TO_LEVEL = "CHANGE_RATE_TO_LEVEL"
    FROM_TO_LEVEL = "FROM_TO_LEVEL"
    RANGE = "RANGE"
    UNKNOWN = "UNKNOWN"

class ReviewStatus(str, Enum):
    AUTO_SEEDED = "AUTO_SEEDED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    GOLD_CONFIRMED = "GOLD_CONFIRMED"

class BenchmarkDifficulty(str, Enum):
    EASY_DIRECT = "A. Easy/direct"
    CHANGE_STATEMENTS = "B. Change statements"
    SCOPE_AMBIGUITY = "C. Scope ambiguity"
    BASIS_AMBIGUITY = "D. Basis ambiguity"
    DEBT_LEASE_AMBIGUITY = "E. Debt/lease ambiguity"
    SHARES_AMBIGUITY = "F. Shares ambiguity"
    CAPEX_AMBIGUITY = "G. Capex ambiguity"
    PROFIT_EBIT_AMBIGUITY = "H. Profit/EBIT/trading-profit ambiguity"
    UNKNOWN_LONG_TAIL = "I. Unknown/long-tail"

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

NUMERIC_TOKEN_REGEX = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?P<prefix>(?:\b(?:US\$|USD|EUR|GBP|ZAR)\b|R(?=\s*[+\-\u2013\u2014]?\s*\d)|[\$€£])\s*)?"
    r"(?P<sign>[+\-\u2013\u2014])?\s*"
    r"(?P<num>\d{1,3}(?:[ \u00a0]\d{3}(?!\d))+(?:[.,]\d+)?|\d{1,3}(?:,\d{3}(?!\d))+(?:\.\d+)?|\d+[.,]\d+|\d+)"
    r"(?P<suffix>%(?:\s*points?)?|\s*(?:billion|milli?on|cents?|c\b|bn\b|m\b|thousand|k\b))?",
    re.IGNORECASE
)

DATE_EXPRESSION_REGEX = re.compile(
    r"\b(?P<day>\d{1,2})\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(?P<year>\d{4})\b",
    re.IGNORECASE
)

PERIOD_PREFIX_REGEX = re.compile(
    r"\b(?:FY|Q[1-4]|H[1-2])\s*20\d\d\b",
    re.IGNORECASE
)

def normalize_number_string(num_str: str) -> float | None:
    cleaned = num_str.replace(" ", "").replace("\u00a0", "")
    if "," in cleaned and "." not in cleaned:
        cleaned = cleaned.replace(",", ".")
    elif "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None

def parse_detected_numeric_tokens(sentence: str) -> list[DetectedNumericToken]:
    tokens: list[DetectedNumericToken] = []
    sent_lower = sentence.lower()

    # Find date spans to classify days and years accurately
    date_spans: set[tuple[int, int]] = set()
    for dm in DATE_EXPRESSION_REGEX.finditer(sentence):
        date_spans.add(dm.span("day"))
        date_spans.add(dm.span("year"))

    for match in NUMERIC_TOKEN_REGEX.finditer(sentence):
        raw_full = match.group(0).strip()
        if not raw_full:
            continue
        
        start_idx, end_idx = match.span()
        prefix = (match.group("prefix") or "").strip()
        sign = (match.group("sign") or "").strip()
        num_part = (match.group("num") or "").strip()
        suffix = (match.group("suffix") or "").strip()

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

        # Lookahead for cents if not in suffix
        lookahead = sentence[end_idx:end_idx+20].lower()
        if not scale and not is_percentage:
            if re.match(r"^\s*cents?\b", lookahead) or re.match(r"^\s*(?:c\b|cps\b)", lookahead):
                scale = "cents"
                is_per_share = True
                raw_full = f"{raw_full} cents"

        # Check if year or part of date
        is_date_or_year = False
        # Check against date spans
        num_span = match.span("num")
        for ds_s, ds_e in date_spans:
            if ds_s <= num_span[0] and num_span[1] <= ds_e:
                is_date_or_year = True
                break

        if not is_date_or_year and not currency and not is_percentage and not scale:
            if re.fullmatch(r"\d{4}", num_part):
                val_int = int(num_part)
                if 1990 <= val_int <= 2040:
                    is_date_or_year = True
            # Also check if preceded by FY/Q1/H1
            pre_text = sentence[max(0, start_idx-6):start_idx].upper()
            if any(pre_text.endswith(p) for p in ["FY", "Q1", "Q2", "Q3", "Q4", "H1", "H2"]):
                is_date_or_year = True

        # Check if in range clause
        # Look backwards for "between" or "range of"
        lookbehind = sentence[max(0, start_idx-35):start_idx].lower()
        is_in_range = ("between" in lookbehind or "range of" in lookbehind or "to" in lookbehind) and (
            "between" in sent_lower or "range of" in sent_lower or "range" in sent_lower
        )

        if is_date_or_year:
            token_type = NumericTokenType.YEAR_OR_DATE
        elif is_percentage:
            token_type = NumericTokenType.PERCENTAGE
        elif currency:
            token_type = NumericTokenType.CURRENCY_LEVEL
        elif is_per_share or scale == "cents":
            token_type = NumericTokenType.PER_SHARE_LEVEL
        elif is_in_range and not scale and not currency:
            token_type = NumericTokenType.RANGE_BOUND
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

def resolve_nested_alias_spans(matches: list[tuple[int, int, str, Any]]) -> list[tuple[int, int, str, Any]]:
    sorted_matches = sorted(matches, key=lambda m: (-(m[1] - m[0]), m[0]))
    kept: list[tuple[int, int, str, Any]] = []
    for cand in sorted_matches:
        cand_start, cand_end = cand[0], cand[1]
        contained = False
        for k in kept:
            k_start, k_end = k[0], k[1]
            if k_start <= cand_start and cand_end <= k_end and (k_end - k_start) > (cand_end - cand_start):
                contained = True
                break
        if not contained:
            kept.append(cand)
    return sorted(kept, key=lambda m: m[0])

# Verification run
print("Running verification checks...")

# 1. JSE number formats
tests = [
    ("Revenue R235,6 billion, up 4,3%; up 6,8%", [
        ("R235,6 billion", 235.6, NumericTokenType.CURRENCY_LEVEL, "ZAR", "billion", False, False),
        ("4,3%", 4.3, NumericTokenType.PERCENTAGE, None, None, True, False),
        ("6,8%", 6.8, NumericTokenType.PERCENTAGE, None, None, True, False),
    ]),
    ("Cash generated ... R16,6 billion", [
        ("R16,6 billion", 16.6, NumericTokenType.CURRENCY_LEVEL, "ZAR", "billion", False, False),
    ]),
    ("Headline earnings per share 2 562,7 cents", [
        ("2 562,7 cents", 2562.7, NumericTokenType.PER_SHARE_LEVEL, None, "cents", False, True),
    ]),
    ("235,6", [("235,6", 235.6, NumericTokenType.PLAIN_LEVEL, None, None, False, False)]),
    ("235.6", [("235.6", 235.6, NumericTokenType.PLAIN_LEVEL, None, None, False, False)]),
    ("2 562,7", [("2 562,7", 2562.7, NumericTokenType.PLAIN_LEVEL, None, None, False, False)]),
    ("2 562.7", [("2 562.7", 2562.7, NumericTokenType.PLAIN_LEVEL, None, None, False, False)]),
    ("2,562.7", [("2,562.7", 2562.7, NumericTokenType.PLAIN_LEVEL, None, None, False, False)]),
    ("R235,6 million", [("R235,6 million", 235.6, NumericTokenType.CURRENCY_LEVEL, "ZAR", "million", False, False)]),
    ("R2 562 million", [("R2 562 million", 2562.0, NumericTokenType.CURRENCY_LEVEL, "ZAR", "million", False, False)]),
    ("$13.7 million", [("$13.7 million", 13.7, NumericTokenType.CURRENCY_LEVEL, "USD", "million", False, False)]),
    ("EUR 1.8 billion", [("EUR 1.8 billion", 1.8, NumericTokenType.CURRENCY_LEVEL, "EUR", "billion", False, False)]),
    ("138.30 cents", [("138.30 cents", 138.3, NumericTokenType.PER_SHARE_LEVEL, None, "cents", False, True)]),
    ("24.5%", [("24.5%", 24.5, NumericTokenType.PERCENTAGE, None, None, True, False)]),
    ("-11.6%", [("-11.6%", -11.6, NumericTokenType.PERCENTAGE, None, None, True, False)]),
    ("ended 30 June 2025", [
        ("30", 30.0, NumericTokenType.YEAR_OR_DATE, None, None, False, False),
        ("2025", 2025.0, NumericTokenType.YEAR_OR_DATE, None, None, False, False)
    ]),
    ("anticipates that it will report: a basic loss per share of between 138.30 and 138.48 cents", [
        ("138.30", 138.3, NumericTokenType.RANGE_BOUND, None, None, False, False),
        ("138.48 cents", 138.48, NumericTokenType.PER_SHARE_LEVEL, None, "cents", False, True)
    ])
]

for sent, expected in tests:
    toks = parse_detected_numeric_tokens(sent)
    assert len(toks) == len(expected), f"Mismatch count for '{sent}': got {len(toks)}, expected {len(expected)}"
    for t, exp in zip(toks, expected):
        assert t.raw_text == exp[0], f"raw_text mismatch: {t.raw_text} != {exp[0]}"
        assert abs(t.normalized_numeric_value - exp[1]) < 1e-4, f"norm mismatch: {t.normalized_numeric_value} != {exp[1]}"
        assert t.token_type == exp[2], f"token_type mismatch for {t.raw_text}: {t.token_type} != {exp[2]}"
        assert t.currency == exp[3], f"currency mismatch for {t.raw_text}: {t.currency} != {exp[3]}"
        assert t.scale == exp[4], f"scale mismatch for {t.raw_text}: {t.scale} != {exp[4]}"
        assert t.is_percentage == exp[5], f"is_percentage mismatch for {t.raw_text}"
        assert t.is_per_share == exp[6], f"is_per_share mismatch for {t.raw_text}"

print("All numeric extraction tests passed successfully!")

# 2. Nested alias resolution tests
s1 = "Headline earnings per share increase 14%"
matches = [
    (0, 27, "headline earnings per share", "heps"),
    (9, 27, "earnings per share", "eps"),
    (0, 17, "headline earnings", "headline_earnings"),
]
resolved = resolve_nested_alias_spans(matches)
assert len(resolved) == 1
assert resolved[0][2] == "headline earnings per share"

s2 = "diluted headline earnings per share increased by 10%, while headline earnings per share increased by 8%"
matches2 = [
    (0, 35, "diluted headline earnings per share", "diluted_heps"),
    (8, 35, "headline earnings per share", "heps"),
    (17, 35, "earnings per share", "eps"),
    (60, 87, "headline earnings per share", "heps"),
    (69, 87, "earnings per share", "eps"),
]
resolved2 = resolve_nested_alias_spans(matches2)
assert len(resolved2) == 2
assert resolved2[0][2] == "diluted headline earnings per share"
assert resolved2[1][2] == "headline earnings per share"

print("All nested alias resolution tests passed successfully!")
