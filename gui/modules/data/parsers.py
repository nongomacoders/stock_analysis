import re
from bs4 import BeautifulSoup
from typing import List, Dict, Any

from modules.data.parse_utils import (
    parse_period_label,
    parse_release_date,
    parse_financial_value,
)


def parse_multi_year_share_statistics(table_html: str) -> List[Dict[str, Any]]:
    """
    Parse share statistics table HTML and extract multi-year financial data.
    
    Args:
        table_html: HTML string containing the share statistics table
        
    Returns:
        List of dictionaries with financial data for each period
    """
    soup = BeautifulSoup(table_html, "html.parser")
    rows = soup.find_all("tr")
    if not rows:
        return []

    # Header Logic
    header_row = None
    headers = None
    for row in rows:
        cells = row.find_all(["th", "td"])
        texts = [c.get_text(strip=True).replace("\n", " ") for c in cells]
        if len(texts) < 2:
            continue
        if any(re.search(r"\b(19|20)\d{2}\b", t) for t in texts[1:]):
            header_row = row
            headers = texts
            break

    if not header_row:
        header_row = rows[0]
        headers = [
            c.get_text(strip=True) for c in header_row.find_all(["th", "td"])
        ]

    # Find columns
    year_indices = []
    for i, h in enumerate(headers):
        if i == 0:
            continue
        if "Avg." in h or "Growth" in h:
            continue
        year_indices.append(i)

    periods_info = []
    for idx in year_indices:
        if idx < len(headers):
            p_label = headers[idx].strip()
            p_end = parse_period_label(p_label)
            if p_end:
                periods_info.append(
                    {
                        "column_idx": idx,
                        "results_period_end": p_end,
                        "results_period_label": p_label,
                        "results_release_date": parse_release_date(p_label),
                    }
                )
    if not periods_info:
        return []

    periods_data = [
        {
            "results_period_end": p["results_period_end"],
            "results_period_label": p["results_period_label"],
            "results_release_date": p["results_release_date"],
            "heps_12m_zarc": None,
            "dividend_12m_zarc": None,
            "cash_gen_ps_zarc": None,
            "nav_ps_zarc": None,
        }
        for p in periods_info
    ]

    field_map = {
        "12 Month HEPS": "heps_12m_zarc",
        "12 Month Dividend": "dividend_12m_zarc",
        "Cash Generated Per Share": "cash_gen_ps_zarc",
        "Net Asset Value Per Share (ZARc)": "nav_ps_zarc",
    }

    for row in rows[1:]:
        cols = row.find_all(["td", "th"])
        if not cols:
            continue
        label = cols[0].get_text(strip=True)

        for f_label, f_key in field_map.items():
            if f_label.lower() in label.lower():
                for p_idx, p_info in enumerate(periods_info):
                    if p_info["column_idx"] < len(cols):
                        val = parse_financial_value(
                            cols[p_info["column_idx"]].get_text(strip=True)
                        )
                        periods_data[p_idx][f_key] = val
                break
    return periods_data


def parse_multi_year_ratios(table_html: str) -> List[Dict[str, Any]]:
    """
    Parse ratios table HTML and extract multi-year ratio data.
    
    Args:
        table_html: HTML string containing the ratios table
        
    Returns:
        List of dictionaries with ratio data for each period
    """
    soup = BeautifulSoup(table_html, "html.parser")
    rows = soup.find_all("tr")
    if not rows:
        return []

    header_row = None
    headers = None
    for row in rows:
        cells = row.find_all(["th", "td"])
        texts = [c.get_text(strip=True).replace("\n", " ") for c in cells]
        if len(texts) < 2:
            continue
        if any(re.search(r"\b(19|20)\d{2}\b", t) for t in texts[1:]):
            header_row = row
            headers = texts
            break

    if not header_row:
        header_row = rows[0]
        headers = [
            c.get_text(strip=True) for c in header_row.find_all(["th", "td"])
        ]

    year_indices = [
        i
        for i, h in enumerate(headers)
        if i > 0 and "Avg" not in h and "Growth" not in h
    ]

    periods_info = []
    for idx in year_indices:
        if idx < len(headers):
            p_end = parse_period_label(headers[idx].strip())
            if p_end:
                periods_info.append(
                    {"column_idx": idx, "results_period_end": p_end}
                )

    periods_data = [
        {"results_period_end": p["results_period_end"], "quick_ratio": None}
        for p in periods_info
    ]

    for row in rows[1:]:
        cols = row.find_all(["td", "th"])
        if not cols:
            continue
        if "Quick Ratio".lower() in cols[0].get_text(strip=True).lower():
            for p_idx, p_info in enumerate(periods_info):
                if p_info["column_idx"] < len(cols):
                    val = parse_financial_value(
                        cols[p_info["column_idx"]].get_text(strip=True)
                    )
                    periods_data[p_idx]["quick_ratio"] = val
            break
    return periods_data

