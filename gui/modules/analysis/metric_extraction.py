"""Convert Gemini's reported candidate facts to typed records conservatively."""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import UUID

from .financial_metrics import (
    AssumptionType, CommodityPriceType, CostDefinition, FinancialMetric, ProductionStage, ShareCountType,
    SourceType, Unit, normalize_metric,
)
from .metric_validation import validate_metrics


EXACT_UNIT_ALIASES = {
    "USD/lb": Unit.USD_PER_LB, "US$/lb": Unit.USD_PER_LB,
    "USD/tonne": Unit.USD_PER_TONNE, "USD/t": Unit.USD_PER_TONNE,
    "US$/tonne": Unit.USD_PER_TONNE, "US$/t": Unit.USD_PER_TONNE,
    "ZAR": Unit.ZAR, "ZARc": Unit.ZAR_CENTS, "cents": Unit.ZAR_CENTS,
    "%": Unit.PERCENTAGE, "x": Unit.MULTIPLE, "shares": Unit.SHARES,
}


def _unit(raw):
    if raw is None:
        return None
    try:
        return Unit(raw)
    except ValueError:
        return EXACT_UNIT_ALIASES.get(str(raw).strip())


def _date(raw):
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def _numeric(raw):
    if raw is None:
        return None, None, None
    text = str(raw)
    # Only an explicit numeric range is split into endpoints.
    pair = re.search(r"(?<!\d)(\d[\d,]*(?:\.\d+)?)\s*(?:to|–|—|-)\s*(\d[\d,]*(?:\.\d+)?)", text, re.I)
    try:
        if pair:
            return None, Decimal(pair.group(1).replace(",", "")), Decimal(pair.group(2).replace(",", ""))
        match = re.search(r"(?<!\d)[+-]?\d[\d,]*(?:\.\d+)?", text)
        return (Decimal(match.group().replace(",", "")), None, None) if match else (None, None, None)
    except InvalidOperation:
        return None, None, None


def _enum(enum_type, raw):
    try:
        return enum_type(raw) if raw is not None else None
    except ValueError:
        return None


def _name(item, share_type, stage):
    key = item["assumption"]
    if key == "shares":
        return share_type.value if share_type else "share_count_unresolved"
    if key == "production":
        return f"production_{stage.value}" if stage else "production_unresolved"
    if key == "production_cost":
        return "production_cost_per_tonne"
    return key


def structure_report_metrics(ticker: str, report_id: str | UUID, audit: dict) -> tuple[list[FinancialMetric], list[dict]]:
    metrics = []
    warnings = []
    for index, item in enumerate(audit.get("assumptions", [])):
        if not isinstance(item, dict) or not item.get("assumption"):
            continue
        raw = item.get("raw_value") or item.get("value")
        value, low, high = _numeric(raw)
        share_type = _enum(ShareCountType, item.get("share_count_type"))
        stage = _enum(ProductionStage, item.get("production_stage"))
        assumption = _enum(AssumptionType, item.get("classification")) or AssumptionType.UNRESOLVED
        source_type = _enum(SourceType, item.get("source_type")) or SourceType.UNRESOLVED
        if assumption == AssumptionType.PREVIOUS_REPORT:
            source_type = SourceType.PREVIOUS_REPORT
        if source_type == SourceType.COMPANY_DISCLOSURE and not item.get("evidence_verified"):
            source_type = SourceType.UNRESOLVED
        raw_unit = item.get("raw_unit") or item.get("unit")
        unit = _unit(item.get("unit_code") or item.get("unit"))
        if item.get("unit_code") and unit is None:
            warnings.append({"code": "UNKNOWN_UNIT", "index": index, "message": "Unrecognized controlled unit; preserved raw unit and left unit null."})
        if item.get("production_stage") and stage is None:
            warnings.append({"code": "UNKNOWN_PRODUCTION_STAGE", "index": index, "message": "Unrecognized production stage; preserved raw claim and left stage null."})
        if item.get("share_count_type") and share_type is None:
            warnings.append({"code": "UNKNOWN_SHARE_BASIS", "index": index, "message": "Unrecognized share-count basis; preserved raw claim and left basis null."})
        confidence = item.get("confidence")
        if confidence is not None:
            try:
                confidence = Decimal(str(confidence))
                if confidence < 0 or confidence > 1:
                    raise ValueError()
            except (InvalidOperation, ValueError):
                confidence = None
                warnings.append({"code": "UNKNOWN_CONFIDENCE", "index": index, "message": "Confidence must be between zero and one."})
        try:
            metric = FinancialMetric(
                ticker=ticker, report_id=UUID(str(report_id)), name=_name(item, share_type, stage),
                value=value, value_low=low, value_high=high,
                currency=item.get("currency"), unit=unit,
                period_start=_date(item.get("period_start")), period_end=_date(item.get("period_end")),
                source_date=_date(item.get("source_date")), source=item.get("source"),
                source_type=source_type, assumption_type=assumption, confidence=confidence,
                operation_segment=item.get("operation_segment"), commodity=item.get("commodity"),
                price_type=_enum(CommodityPriceType, item.get("price_type")),
                cost_definition=_enum(CostDefinition, item.get("cost_definition")),
                production_stage=stage, share_count_type=share_type, annualised=item.get("annualised"),
                notes=item.get("notes"), raw_value=str(raw) if raw is not None else None,
                raw_unit=str(raw_unit) if raw_unit is not None else None,
                evidence_quote=item.get("evidence_quote"), source_id=item.get("source_id") or item.get("source"),
                intended_use=item.get("intended_use"),
            )
            metrics.append(normalize_metric(metric))
        except Exception as exc:
            warnings.append({"code": "INVALID_METRIC", "index": index, "message": str(exc), "raw": item})
    warnings.extend(validate_metrics(metrics))
    return metrics, warnings
