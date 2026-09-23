"""Deterministic historical ratios from supplied company evidence.

These facts are descriptive history. They are never forecast assumptions and are
not inputs to a deterministic valuation unless separately approved elsewhere.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from .financial_metrics import AssumptionType, FinancialMetric, SourceType, Unit, normalize_metric
from .metric_extraction import parse_numeric_value


def _line_value(text: str, label: str, suffix: str):
    match = re.search(rf"(?im)^\s*{label}\s+([^\r\n]+?{suffix})\s*$", text)
    return (match.group(1).strip(), match.group(0).strip()) if match else (None, None)


def _metric(*, ticker, report_id, name, value, unit, period_end, source_date,
            report_date, observed_at, source_id, quote, raw_value, formula):
    return normalize_metric(FinancialMetric(
        ticker=ticker, report_id=UUID(str(report_id)), name=name, value=value,
        unit=unit, period_end=period_end, source_date=source_date,
        effective_date=period_end, report_date=report_date, observed_at=observed_at,
        source=source_id, source_id=source_id, source_type=SourceType.PYTHON,
        assumption_type=AssumptionType.PYTHON_CALCULATION, confidence=Decimal("1"),
        evidence_quote=quote, evidence_verified=True, raw_value=raw_value,
        raw_unit=unit.value, normalization_rule=formula,
        intended_use="PYTHON_DERIVED_HISTORICAL_METRIC",
        notes="Historical descriptive ratio; not a forecast assumption."))


def extract_retail_historical_metrics(ticker: str, report_id, sources, *,
                                      price_zar, report_date: date,
                                      observed_at: datetime | None = None):
    """Calculate retailer ratios only from supplied, dated company evidence."""
    if price_zar is None:
        return []
    for source in sources:
        if not source.get("supplied_to_model") or not source.get("source_date"):
            continue
        text = source.get("text") or ""
        heps_raw, heps_q = _line_value(text, "Headline earnings per share", "cents")
        dheps_raw, dheps_q = _line_value(text, "Diluted headline earnings per share", "cents")
        div_raw, div_q = _line_value(text, "Annual dividend per share", "cents")
        nav_raw, nav_q = _line_value(text, "Net asset value per share", "cents")
        if not all((heps_raw, dheps_raw, div_raw, nav_raw)):
            continue
        values = [parse_numeric_value(x)[0] for x in (heps_raw, dheps_raw, div_raw, nav_raw)]
        if any(v is None or v <= 0 for v in values):
            continue
        heps, dheps, dividend, nav = values
        price = Decimal(str(price_zar))
        source_date = date.fromisoformat(str(source["source_date"])[:10])
        period_match = re.search(r"52 weeks ended (\d{1,2}) (January|February|March|April|May|June|July|August|September|October|November|December) (20\d{2})", text, re.I)
        period_end = None
        if period_match:
            period_end = datetime.strptime(" ".join(period_match.groups()), "%d %B %Y").date()
        sid = source["source_id"]
        common = dict(ticker=ticker, report_id=report_id, period_end=period_end,
                      source_date=source_date, report_date=report_date,
                      observed_at=observed_at, source_id=sid)
        return [
            _metric(**common, name="historical_pe_heps", value=price/(heps/100), unit=Unit.MULTIPLE,
                    quote=heps_q, raw_value=f"price ZAR {price}; {heps_raw}", formula="price_zar / (HEPS_cents / 100)"),
            _metric(**common, name="historical_pe_diluted_heps", value=price/(dheps/100), unit=Unit.MULTIPLE,
                    quote=dheps_q, raw_value=f"price ZAR {price}; {dheps_raw}", formula="price_zar / (diluted_HEPS_cents / 100)"),
            _metric(**common, name="trailing_dividend_yield", value=(dividend/100)/price*100, unit=Unit.PERCENTAGE,
                    quote=div_q, raw_value=f"{div_raw}; price ZAR {price}", formula="(annual_dividend_cents / 100) / price_zar * 100"),
            _metric(**common, name="historical_payout_ratio", value=dividend/heps*100, unit=Unit.PERCENTAGE,
                    quote=f"{div_q}; {heps_q}", raw_value=f"{div_raw} / {heps_raw}", formula="annual_dividend_cents / HEPS_cents * 100"),
            _metric(**common, name="price_to_nav", value=price/(nav/100), unit=Unit.MULTIPLE,
                    quote=nav_q, raw_value=f"price ZAR {price}; {nav_raw}", formula="price_zar / (NAV_per_share_cents / 100)"),
        ]
    return []


def render_historical_metrics(metrics):
    chosen = [m for m in metrics if m.intended_use == "PYTHON_DERIVED_HISTORICAL_METRIC"]
    if not chosen:
        return ""
    labels = {"historical_pe_heps": "Historical P/E (HEPS)",
              "historical_pe_diluted_heps": "Historical P/E (diluted HEPS)",
              "trailing_dividend_yield": "Trailing dividend yield",
              "historical_payout_ratio": "Historical payout ratio",
              "price_to_nav": "Price/NAV"}
    lines = ["## Python-derived historical metrics", "", "Classification: `PYTHON_DERIVED_HISTORICAL_METRIC`. These are historical observations, not forecasts or approved valuation assumptions.", ""]
    for m in chosen:
        suffix = "%" if m.unit == Unit.PERCENTAGE else "x"
        lines.append(f"- {labels[m.name]}: {m.value.quantize(Decimal('0.01'))}{suffix} | period={m.period_end or 'unresolved'} | source={m.source_id} | source_date={m.source_date}")
    return "\n".join(lines)
