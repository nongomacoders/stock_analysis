import re
from datetime import date
from typing import Optional


def parse_period_label(header: str) -> Optional[date]:
    """
    Extract period end date from a header label.
    
    Args:
        header: Header text containing date information
        
    Returns:
        Date object representing the period end, or None if parsing fails
    """
    try:
        m = re.match(r"([A-Za-z]+)\s*(\d{4})", header)
        if not m:
            return None
        from dateutil import parser

        # Parse only Month YYYY from matched groups
        date_str = f"{m.group(1)} {m.group(2)}"
        return parser.parse(date_str).date()
    except:
        return None


def parse_release_date(header: str) -> Optional[date]:
    """
    Extract release date from a header label.
    
    Args:
        header: Header text containing release date
        
    Returns:
        Date object representing the release date, or None if parsing fails
    """
    try:
        m = re.search(r"(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})", header)
        if not m:
            return None
        from dateutil import parser

        return parser.parse(m.group(0)).date()
    except:
        return None


def parse_financial_value(text: str) -> Optional[float]:
    """
    Parse a financial value from text, handling various formats and edge cases.
    
    Args:
        text: Text containing a financial value
        
    Returns:
        Float value, or None if parsing fails or value is N/A
    """
    if not text or text in ["-", "—", "N/A"]:
        return None
    try:
        return float(text.replace(" ", "").replace("\xa0", "").replace("−", "-"))
    except:
        return None
