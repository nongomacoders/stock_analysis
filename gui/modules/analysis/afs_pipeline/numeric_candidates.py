"""Stage 3: Deterministic Candidate Numeric Extraction and Role Parsing.

Extracts all candidate numbers from sentences with exact token spans,
normalized numeric values, scale, currency, unit, and deterministic syntactic roles
(e.g., CHANGE_AMOUNT vs ENDING_VALUE / DIRECT_LEVEL in 'increased by X to Y').
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class NumericCandidate:
    candidate_id: str
    raw_token: str
    normalized_value: Optional[Decimal]
    currency: Optional[str]
    unit: Optional[str]
    scale: Optional[str]
    sign: int  # +1 or -1
    span_start: int
    span_end: int
    page_number: int
    paragraph_id: str
    sentence_id: str
    sentence_text: str
    nearby_label: Optional[str]
    numeric_role: str  # DIRECT_LEVEL, ENDING_VALUE, CHANGE_AMOUNT, CHANGE_RATE, STARTING_VALUE, UNKNOWN
    value_pattern: str  # direct_level, change_rate_only, change_rate_to_level, from_to_level, range, unknown
    note_reference: Optional[str] = None
    temporal_role: str = "STANDALONE"  # CURRENT_PERIOD, COMPARATIVE_PERIOD, STANDALONE

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["normalized_value"] = str(self.normalized_value) if self.normalized_value is not None else None
        return d


SCALE_FACTORS = {
    "billion": Decimal(10**9),
    "billions": Decimal(10**9),
    "bn": Decimal(10**9),
    "b": Decimal(10**9),
    "million": Decimal(10**6),
    "millions": Decimal(10**6),
    "mn": Decimal(10**6),
    "m": Decimal(10**6),
    "thousand": Decimal(10**3),
    "thousands": Decimal(10**3),
    "k": Decimal(10**3),
}

CURRENCY_PREFIXES = {
    "R": "ZAR",
    "ZAR": "ZAR",
    "US$": "USD",
    "USD": "USD",
    "$": "USD",
    "£": "GBP",
    "€": "EUR",
}

UNIT_KEYWORDS = {
    "%": "percentage",
    "percent": "percentage",
    "percentage": "percentage",
    "cents": "ZAR_cents",
    "cent": "ZAR_cents",
    "c": "ZAR_cents",
    "cps": "ZAR_cents",
    "shares": "shares",
    "share": "shares",
    "koz": "koz",
    "oz": "oz",
    "tonnes": "tonnes",
    "tonne": "tonnes",
    "t": "tonnes",
    "usd/oz": "USD_per_oz",
    "us$/oz": "USD_per_oz",
    "usd/tonne": "USD_per_tonne",
    "us$/tonne": "USD_per_tonne",
    "usd/lb": "USD_per_lb",
    "us$/lb": "USD_per_lb",
}


# Token regex matching numbers with possible currency prefixes, brackets, spaces/commas, and scale/unit suffixes
NUMERIC_TOKEN_REGEX = re.compile(
    r"""
    (?<!\w)
    (?P<prefix>US\$|USD|\$|ZAR|R|£|€)?\s*
    (?P<negative>-|\+)?
    (?P<open_paren>\()?
    (?P<digits>\d{1,3}(?:[ ,]\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)
    (?P<close_paren>\))?
    \s*
    (?P<suffix>
        (?:billion|billions|bn|b|million|millions|mn|m|thousand|thousands|k)\b
        |%
        |cents?\b|cps\b|c\b
        |shares?\b
        |koz\b|oz\b|tonnes?\b|t\b
        |US\$/oz\b|USD/oz\b|US\$/tonne\b|USD/tonne\b|US\$/lb\b|USD/lb\b
        |/oz\b|/tonne\b|/t\b|/lb\b
    )?
    """,
    re.VERBOSE | re.IGNORECASE,
)


def parse_raw_numeric_token(
    raw_match: re.Match,
) -> Tuple[Optional[Decimal], Optional[str], Optional[str], Optional[str], int]:
    """Parse regex match groups into (normalized_value, currency, unit, scale, sign)."""
    prefix = raw_match.group("prefix")
    neg_sign = raw_match.group("negative")
    open_paren = raw_match.group("open_paren")
    close_paren = raw_match.group("close_paren")
    digits_str = raw_match.group("digits")
    suffix = raw_match.group("suffix")

    # Determine sign
    is_neg = (neg_sign == "-") or (open_paren is not None and close_paren is not None)
    sign = -1 if is_neg else 1

    clean_digits = digits_str.replace(",", "").replace(" ", "")
    try:
        base_value = Decimal(clean_digits)
    except InvalidOperation:
        return None, None, None, None, sign

    # Currency
    currency = None
    if prefix:
        norm_p = prefix.upper().strip()
        currency = CURRENCY_PREFIXES.get(norm_p, norm_p)

    # Scale & Unit
    scale = None
    unit = None
    if suffix:
        norm_s = suffix.lower().strip()
        if norm_s in SCALE_FACTORS:
            scale = norm_s
            base_value = base_value * SCALE_FACTORS[norm_s]
        elif norm_s in UNIT_KEYWORDS:
            unit = UNIT_KEYWORDS[norm_s]
        elif norm_s.startswith("/"):
            denominator = norm_s.lstrip("/").lower()
            if currency:
                unit = f"{currency}_per_{denominator}"
            else:
                unit = f"per_{denominator}"
        elif "/" in norm_s:
            unit = UNIT_KEYWORDS.get(norm_s, norm_s)

    # Additional contextual unit
    if unit is None and currency == "ZAR":
        unit = "ZAR"
    elif unit is None and currency == "USD":
        unit = "USD"

    normalized_value = base_value * sign
    return normalized_value, currency, unit, scale, sign


# High-confidence Syntactic Role / Value Pattern Matchers
ROLE_PATTERNS = [
    # 1. "increased by X to Y" / "rose by X to Y" / "grew by X to Y"
    (
        re.compile(
            r"(?i)\b(?:increased|rose|grew|improved|up)\s+(?:by\s+)?(?P<change>[^\n,;]+?)\s+(?:to|reaching)\s+(?P<level>[^\n,;]+)"
        ),
        "change_rate_to_level",
    ),
    # 2. "decreased by X to Y" / "fell by X to Y" / "declined by X to Y"
    (
        re.compile(
            r"(?i)\b(?:decreased|fell|declined|dropped|down)\s+(?:by\s+)?(?P<change>[^\n,;]+?)\s+(?:to|reaching)\s+(?P<level>[^\n,;]+)"
        ),
        "change_rate_to_level",
    ),
    # 3. "from X to Y"
    (
        re.compile(r"(?i)\bfrom\s+(?P<start>[^\n,;]+?)\s+to\s+(?P<end>[^\n,;]+)"),
        "from_to_level",
    ),
    # 4. "was Y, an increase of X" / "of Y, an increase of X"
    (
        re.compile(
            r"(?i)(?P<level>[^\n,;]+?),\s*(?:an?\s+)?(?:increase|rise|growth)\s+of\s+(?P<change>[^\n,;]+)"
        ),
        "change_rate_to_level",
    ),
    # 5. "was Y, a decrease of X" / "of Y, a decrease of X"
    (
        re.compile(
            r"(?i)(?P<level>[^\n,;]+?),\s*(?:an?\s+)?(?:decrease|decline|drop)\s+of\s+(?P<change>[^\n,;]+)"
        ),
        "change_rate_to_level",
    ),
    # 6. "Y (up X%)" / "Y (down X%)"
    (
        re.compile(
            r"(?i)(?P<level>[^\n,;\(\)]+?)\s*\(\s*(?:up|down|increased by|decreased by)\s+(?P<change>[^\n\)]+)\)"
        ),
        "change_rate_to_level",
    ),
]


def determine_candidate_role_in_sentence(
    sentence_text: str, token_start: int, token_end: int, is_percentage: bool
) -> Tuple[str, str]:
    """Determine (numeric_role, value_pattern) for token in sentence."""
    for pattern_re, val_pattern in ROLE_PATTERNS:
        match = pattern_re.search(sentence_text)
        if not match:
            continue

        # Check if token falls inside one of the captured groups
        groups = match.groupdict()
        for gname, gtext in groups.items():
            if gtext is None:
                continue
            g_start = match.start(gname)
            g_end = match.end(gname)
            if g_start <= token_start and token_end <= g_end:
                if gname in ("change", "rate"):
                    role = "CHANGE_RATE" if is_percentage else "CHANGE_AMOUNT"
                    return role, val_pattern
                elif gname in ("level", "end"):
                    return "ENDING_VALUE", val_pattern
                elif gname == "start":
                    return "STARTING_VALUE", val_pattern

    # Standalone percentage without matching level
    if is_percentage:
        return "CHANGE_RATE", "change_rate_only"

    # Default standalone level
    return "DIRECT_LEVEL", "direct_level"


def extract_nearby_label(sentence_text: str, token_start: int) -> Optional[str]:
    """Extract preceding text or words that serve as the syntactic label."""
    prefix = sentence_text[:token_start].strip()
    if not prefix:
        return None
    # If ends with punctuation like 'was', 'to', ':', strip them
    words = re.split(r"[,\n:;]\s*", prefix)
    candidate_phrase = words[-1].strip()
    candidate_phrase = re.sub(r"\b(?:was|is|at|of|by|to)\s*$", "", candidate_phrase, flags=re.I).strip()
    return candidate_phrase if len(candidate_phrase) > 1 else None


TABLE_ROW_REGEX = re.compile(
    r"^\s*(?P<label>[A-Za-z\s\(\)/,–\-'\":]+?)\s+(?:(?P<note>\d{1,2}(?:\.\d{1,2})?)\s+)?(?P<curr>\(?[\d,]+(?:\.\d+)?\)?|-)\s+(?P<prior>\(?[\d,]+(?:\.\d+)?\)?|-)\s*$"
)

NOTE_REF_REGEX = re.compile(r"^\d{1,2}(?:\.\d{1,2})?$")


def extract_numeric_candidates_from_sentence(
    sentence_id: str,
    paragraph_id: str,
    page_number: int,
    sentence_text: str,
) -> List[NumericCandidate]:
    """Locate all numeric candidates within a sentence, tagging note references and binding periods."""
    candidates: List[NumericCandidate] = []

    # Check for two-column table row structure first
    table_match = TABLE_ROW_REGEX.match(sentence_text.strip())
    if table_match:
        label = table_match.group("label").strip()
        note_ref = table_match.group("note")
        curr_str = table_match.group("curr")
        prior_str = table_match.group("prior")

        # Current period candidate
        if curr_str and curr_str != "-":
            curr_match = NUMERIC_TOKEN_REGEX.search(curr_str)
            if curr_match:
                norm_val, currency, unit, scale, sign = parse_raw_numeric_token(curr_match)
                cand_id = f"{sentence_id}_c0_curr"
                candidates.append(
                    NumericCandidate(
                        candidate_id=cand_id,
                        raw_token=curr_str,
                        normalized_value=norm_val,
                        currency=currency,
                        unit=unit,
                        scale=scale,
                        sign=sign,
                        span_start=table_match.start("curr"),
                        span_end=table_match.end("curr"),
                        page_number=page_number,
                        paragraph_id=paragraph_id,
                        sentence_id=sentence_id,
                        sentence_text=sentence_text,
                        nearby_label=label,
                        numeric_role="ENDING_VALUE",
                        value_pattern="direct_level",
                        note_reference=note_ref,
                        temporal_role="CURRENT_PERIOD",
                    )
                )

        # Comparative period candidate
        if prior_str and prior_str != "-":
            prior_match = NUMERIC_TOKEN_REGEX.search(prior_str)
            if prior_match:
                norm_val, currency, unit, scale, sign = parse_raw_numeric_token(prior_match)
                cand_id = f"{sentence_id}_c1_prior"
                candidates.append(
                    NumericCandidate(
                        candidate_id=cand_id,
                        raw_token=prior_str,
                        normalized_value=norm_val,
                        currency=currency,
                        unit=unit,
                        scale=scale,
                        sign=sign,
                        span_start=table_match.start("prior"),
                        span_end=table_match.end("prior"),
                        page_number=page_number,
                        paragraph_id=paragraph_id,
                        sentence_id=sentence_id,
                        sentence_text=sentence_text,
                        nearby_label=label,
                        numeric_role="STARTING_VALUE",
                        value_pattern="direct_level",
                        note_reference=note_ref,
                        temporal_role="COMPARATIVE_PERIOD",
                    )
                )

        if candidates:
            return candidates

    # Fall back to narrative / sentence matching
    matches = list(NUMERIC_TOKEN_REGEX.finditer(sentence_text))
    active_note_ref = None

    for idx, m in enumerate(matches):
        raw_token = m.group(0).strip()
        digits_only = re.sub(r"[^\d]", "", raw_token)
        if not digits_only:
            continue

        token_start = m.start()
        token_end = m.end()

        # Check if this token is a note reference before a subsequent number
        if NOTE_REF_REGEX.match(raw_token) and not m.group("prefix") and not m.group("suffix"):
            # If followed by another numeric token in the same sentence, treat this as note reference!
            if idx + 1 < len(matches):
                next_m = matches[idx + 1]
                next_raw = next_m.group(0).strip()
                if ("," in next_raw or len(next_raw) >= 3 or next_m.group("prefix")):
                    active_note_ref = raw_token
                    continue

        # Skip obvious page numbers or standalone single digits
        if len(digits_only) == 1 and not m.group("prefix") and not m.group("suffix"):
            continue

        # Skip year tokens like 2024, 2025 unless accompanied by currency or unit
        if re.fullmatch(r"20\d\d", raw_token) and not m.group("prefix"):
            continue

        normalized_value, currency, unit, scale, sign = parse_raw_numeric_token(m)
        is_pct = unit == "percentage"

        role, val_pattern = determine_candidate_role_in_sentence(
            sentence_text, token_start, token_end, is_pct
        )

        nearby_label = extract_nearby_label(sentence_text, token_start)
        assigned_note_ref = active_note_ref
        active_note_ref = None  # Consume note reference

        cand_id = f"{sentence_id}_c{idx}"
        candidates.append(
            NumericCandidate(
                candidate_id=cand_id,
                raw_token=raw_token,
                normalized_value=normalized_value,
                currency=currency,
                unit=unit,
                scale=scale,
                sign=sign,
                span_start=token_start,
                span_end=token_end,
                page_number=page_number,
                paragraph_id=paragraph_id,
                sentence_id=sentence_id,
                sentence_text=sentence_text,
                nearby_label=nearby_label,
                numeric_role=role,
                value_pattern=val_pattern,
                note_reference=assigned_note_ref,
                temporal_role="STANDALONE",
            )
        )

    return candidates
