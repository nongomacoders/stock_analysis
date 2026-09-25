import json
import re
from pathlib import Path
from collections import Counter, defaultdict

from modules.analysis.financial_concept_dictionary import (
    AliasStatus,
    BasisEvidence,
    CapexBasis,
    DilutionBasis,
    DividendTaxBasis,
    LeaseInclusion,
    MarginDenominator,
    NumericSign,
    OperationScope,
    ProfitAttribution,
    SemanticQualifiers,
)
from modules.analysis.financial_classifier_benchmark import (
    AliasRole,
    BenchmarkDifficulty,
    BenchmarkItem,
    ReviewDecision,
    ReviewStatus,
    ValuationEligibility,
    ValuePattern,
    NumericTokenType,
    DetectedNumericToken,
    load_benchmark_json,
)

# 1. Test numeric parser
NUM_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?:"
    r"(?P<prefix>(?:\b(?:US\$|USD|EUR|GBP|ZAR)\b|R(?=\s*[+\-\u2013\u2014]?\s*\d)|[\$€£])\s*)"
    r")?"
    r"(?P<sign>[+\-\u2013\u2014])?\s*"
    r"(?P<num>\d{1,3}(?:[ \u00a0]\d{3}(?!\d))+(?:[.,]\d+)?|\d{1,3}(?:,\d{3}(?!\d))+(?:\.\d+)?|\d+[.,]\d+|\d+)"
    r"(?P<suffix>%(?:\s*points?)?|\s*(?:billion|milli?on|cents?|c\b|bn\b|m\b|thousand|k\b))?",
    re.IGNORECASE
)

def parse_numeric_tokens(sentence: str) -> list[DetectedNumericToken]:
    tokens = []
    for m in NUM_PATTERN.finditer(sentence):
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

        clean_token_str = num_str + ("%" if is_pct and not num_str.endswith("%") else "")
        tokens.append(DetectedNumericToken(
            raw_text=full_match,
            clean_numeric=clean_token_str,
            normalized_numeric_value=norm_val,
            token_type=tok_type,
            currency=currency,
            scale=scale,
            is_percentage=is_pct,
            is_per_share=is_ps,
            is_year_or_date=is_year
        ))

    return tokens

print("Numeric parser compiled successfully.")
