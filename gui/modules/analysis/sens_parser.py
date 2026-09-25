"""SENS announcement parser extracting headline results observations."""
from __future__ import annotations
import re
from datetime import date
from decimal import Decimal
from modules.analysis.afs_parser import _decimal, _obs, RESULTS_SENS, PARSER_VERSION

def parse_sens(source: dict) -> list[dict]:
    text = source.get("text") or ""
    from modules.analysis.results_package import _period
    period_end = _period(text); observations = []
    
    # Specific patterns for robust extraction from SENS tables and body
    patterns = [
        ("Retail sales", "retail_sales", "ZAR", r"Retail sales\s+up\s+[\d.]+%\s+to\s+R?([\d.]+)\s+billion", 1000000000),
        ("Sale of merchandise", "sale_of_merchandise", "ZAR", r"Sale of merchandise\s+up\s+[\d.]+%\s+to\s+R?([\d.]+)\s+billion", 1000000000),
        ("Gross profit margin", "gross_margin", "percentage", r"Gross profit margin\s+([\d.]+)%", 1),
        ("Operating margin", "operating_margin", "percentage", r"Operating margin\s+([\d.]+)%", 1),
        ("Earnings per share", "eps", "ZAR_cents", r"Earnings per share\s+([\d.]+)\s+cents", 1),
        ("Headline earnings per share", "heps", "ZAR_cents", r"Headline earnings per share\s+([\d.]+)\s+cents", 1),
        ("Diluted headline earnings per share", "diluted_heps", "ZAR_cents", r"(\d+(?:\.\d+)?)\s+cents\s*\r?\n\s*Diluted headline earnings per share", 1),
        ("Cash generated from operations", "cash_generated_from_operations", "ZAR", r"R?([\d.]+)\s+billion\s*\r?\n\s*Cash generated from operations", 1000000000),
        ("Net asset value per share", "nav_per_share", "ZAR_cents", r"(\d[\d ]+)\s+cents\s*\r?\n\s*Net asset value per share", 1),
        ("Net cash", "net_debt_cash", "ZAR", r"Net cash of R?([\d,]+)\s+million", 1000000),
        ("Annual dividend per share", "annual_dividend_per_share", "ZAR_cents", r"Annual dividend per share\s+(?:down\s+[\d.]+%\s+to\s+)?(\d+)\s+cents", 1),
    ]

    for raw_label, name, unit, pat, multiplier in patterns:
        m = re.search(pat, text, re.I)
        if m:
            val = _decimal(m.group(1))
            if val is not None:
                norm = val * Decimal(multiplier) if multiplier != 1 else val
                observations.append(_obs(source, RESULTS_SENS, name, val, unit, period_end, None, "sens_headline", raw_label, m.group(1), scale="billions" if multiplier == 1000000000 else "millions" if multiplier == 1000000 else None, notes=m.group(0)))
                if name == "net_debt_cash":
                    observations.append(_obs(source, RESULTS_SENS, "reported_net_cash", val, unit, period_end, None, "sens_headline", "Reported net cash", m.group(1), scale="millions", notes=m.group(0)))

    # Fallback to line mappings if any headline is missing
    missing_names = {"retail_sales", "sale_of_merchandise", "gross_margin", "operating_margin", "eps", "heps", "diluted_heps", "nav_per_share", "cash_generated_from_operations", "net_debt_cash", "annual_dividend_per_share"} - {x["name"] for x in observations}
    if missing_names:
        fallback_mappings = [
            ("Retail sales", "retail_sales", "ZAR", "billions"),
            ("Sale of merchandise", "sale_of_merchandise", "ZAR", "billions"),
            ("Gross profit margin", "gross_margin", "percentage", None),
            ("Operating margin", "operating_margin", "percentage", None),
            ("Earnings per share", "eps", "ZAR_cents", None),
            ("Headline earnings per share", "heps", "ZAR_cents", None),
            ("Diluted headline earnings per share", "diluted_heps", "ZAR_cents", None),
            ("Net asset value per share", "nav_per_share", "ZAR_cents", None),
            ("Cash generated from operations", "cash_generated_from_operations", "ZAR", "billions"),
            (r"Net cash\*?", "net_debt_cash", "ZAR", "millions"),
            ("Annual dividend per share", "annual_dividend_per_share", "ZAR_cents", None)
        ]
        for label, name, unit, scale in fallback_mappings:
            if name not in missing_names: continue
            m = re.search(rf"(?im)^\s*{label}\s+([^\r\n]+)", text)
            if not m: continue
            raw = m.group(1)
            if "URL Link" in raw or "http" in raw: continue
            nums = re.findall(r"-?\d[\d ,]*(?:\.\d+)?", raw)
            if not nums: continue
            chosen = nums[-1] if ("R" in raw or "cents" in raw.lower()) else nums[0]; value = _decimal(chosen)
            observations.append(_obs(source, RESULTS_SENS, name, value, unit, period_end, None, "sens_headline", label, chosen, scale=scale, notes=m.group(0)))
            if name == "net_debt_cash":
                observations.append(_obs(source, RESULTS_SENS, "reported_net_cash", value, unit, period_end, None, "sens_headline", "Reported net cash", chosen, scale=scale, notes=m.group(0)))

    issued = re.search(r"(\d[\d ]+)\s+ordinary shares in issue", text, re.I)
    treasury = re.search(r"dividend on\s+(\d[\d ]+)\s+of\s+these shares.*?treasury shares", text, re.I | re.S)
    for match, name in ((issued, "issued_shares_current"), (treasury, "treasury_shares")):
        if match:
            s_val = _decimal(match.group(1))
            eff_date = date.fromisoformat(source["source_date"][:10]) if source.get("source_date") else None
            observations.append(_obs(source, RESULTS_SENS, name, s_val, "shares", period_end, None, "sens_corporate_action", name, match.group(1), effective_date=eff_date, notes=match.group(0)[:300]))
    if issued and treasury:
        iss_val = _decimal(issued.group(1))
        tr_val = _decimal(treasury.group(1))
        if iss_val is not None and tr_val is not None:
            ann_ext = iss_val - tr_val
            eff_date = date.fromisoformat(source["source_date"][:10]) if source.get("source_date") else None
            observations.append(_obs(source, RESULTS_SENS, "announcement_date_external_shares", ann_ext, "shares", period_end, None, "sens_corporate_action", "Announcement date external shares", str(ann_ext), effective_date=eff_date, notes=f"Issued shares ({iss_val}) less treasury shares at announcement ({tr_val}) = {ann_ext}"))
    return observations
