"""Strict parser and importer for historical Backtest ForecastPlan assumption TXT files."""
from __future__ import annotations
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any
from modules.analysis.forecast_plan import (
    ApprovalState, ForecastAssumption, Origin
)
from modules.analysis.historical_plan import HistoricalForecastPlan, MATERIAL_FIELDS

ALLOWED_HISTORICAL_FIELDS = frozenset({
    "revenue_growth", "sale_of_merchandise_growth", "trading_margin",
    "depreciation", "tax_rate", "total_capex", "working_capital",
    "other_recurring_cash", "wacc", "terminal_growth",
    "lease_adjustments", "minorities", "non_operating_assets",
    "other_equity_adjustments"
})

def parse_historical_forecast_txt(text: str, plan: HistoricalForecastPlan) -> list[ForecastAssumption]:
    lines = [line.strip() for line in text.lstrip("\ufeff").splitlines() if line.strip()]
    if not lines:
        raise ValueError("Empty historical assumption file")
    header_idx = -1
    for i, line in enumerate(lines):
        if line.upper() == "BACKTEST":
            header_idx = i
            break
    if header_idx == -1:
        raise ValueError("Missing BACKTEST header marker")
    header: dict[str, str] = {}
    blocks: list[dict[str, str]] = []
    current: dict[str, str] = {}
    in_assumptions = False
    for line in lines[header_idx + 1:]:
        if line.upper() == "ASSUMPTION":
            if current:
                blocks.append(current)
                current = {}
            in_assumptions = True
            continue
        if "=" not in line:
            continue
        k, v = (part.strip() for part in line.split("=", 1))
        k = k.casefold()
        if not in_assumptions and k in {"ticker", "as_of_date", "forecast_period", "case"}:
            header[k] = v
        else:
            in_assumptions = True
            if k == "field" and "field" in current:
                blocks.append(current)
                current = {}
            current[k] = v
    if current:
        blocks.append(current)
    file_ticker = header.get("ticker", "").upper()
    if not file_ticker or file_ticker != plan.ticker.upper():
        raise ValueError(f"Historical TXT ticker mismatch: expected {plan.ticker}, got {file_ticker or 'empty'}")
    file_as_of = header.get("as_of_date", "")
    if not file_as_of or file_as_of != str(plan.as_of_date):
        raise ValueError(f"Historical TXT as-of date mismatch: expected {plan.as_of_date}, got {file_as_of or 'empty'}")
    forecast_period = header.get("forecast_period", "FY2026")
    if not blocks:
        raise ValueError("No historical assumptions found in file")
    parsed: list[ForecastAssumption] = []
    for num, b in enumerate(blocks, 1):
        f = b.get("field", "").strip()
        if not f or f not in ALLOWED_HISTORICAL_FIELDS:
            raise ValueError(f"Block {num}: unknown or unsupported historical field '{f}'")
        raw_val = b.get("value", "").strip()
        if not raw_val:
            raise ValueError(f"Block {num} ({f}): value is required")
        try: val = Decimal(raw_val)
        except InvalidOperation:
            raise ValueError(f"Block {num} ({f}): invalid decimal value '{raw_val}'")
        unit = b.get("unit", "percentage" if "growth" in f or "margin" in f or "rate" in f or f in {"wacc", "terminal_growth"} else "ZAR")
        analyst = b.get("analyst", b.get("created_by", plan.created_by)).strip()
        rationale = b.get("rationale", "").strip()
        if f in MATERIAL_FIELDS and not rationale:
            raise ValueError(f"Block {num} ({f}): material assumption requires explicit rationale")
        p_label = b.get("period", forecast_period).strip()
        op = b.get("operation", "Group").strip()
        case = b.get("case", "base").strip()
        a = ForecastAssumption(
            field=f, value=val, unit=unit, period_label=p_label,
            operation_segment=op, case=case, origin=Origin.ANALYST_ASSUMPTION,
            approval_state=ApprovalState.PROPOSED, rationale=rationale,
            created_by=analyst or "analyst", source_date=plan.as_of_date
        )
        parsed.append(a)
    return parsed
