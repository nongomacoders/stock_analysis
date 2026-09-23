"""Convert Gemini's reported candidate facts to typed records conservatively."""
from __future__ import annotations

import re
from datetime import date, datetime
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


def _timestamp(raw):
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def _date(raw):
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


NUMBER = re.compile(r"(?<!\d)[+-]?(?:\d{1,3}(?:[ ,]\d{3})+|\d+)(?:\.\d+)?")
SCALE = re.compile(r"^\s*(thousand|million|billion|bn|mn)\b", re.I)
SCALE_FACTOR = {"thousand": 10**3, "million": 10**6, "mn": 10**6,
                "billion": 10**9, "bn": 10**9}


def parse_numeric_value(raw):
    """Parse a stated quantity, retaining grouping and scale semantics."""
    if raw is None:
        return None, None
    text = str(raw)
    match = NUMBER.search(text)
    if not match:
        return None, None
    token = match.group().replace(",", "").replace(" ", "")
    try:
        value = Decimal(token)
    except InvalidOperation:
        return None, None
    scale = SCALE.match(text[match.end():])
    if scale:
        factor = SCALE_FACTOR[scale.group(1).lower()]
        return value * factor, f"grouped_digits_and_{scale.group(1).lower()}_scale"
    return value, "grouped_digits" if ("," in match.group() or " " in match.group()) else "literal_decimal"


def _numeric(raw):
    if raw is None:
        return None, None, None, None
    text = str(raw)
    pair = re.search(r"(?<!\d)(\d[\d, ]*(?:\.\d+)?)\s*(?:to|\u2013|\u2014|-)\s*(\d[\d, ]*(?:\.\d+)?)", text, re.I)
    if pair:
        low, _ = parse_numeric_value(pair.group(1))
        high, _ = parse_numeric_value(pair.group(2))
        return None, low, high, "explicit_range"
    value, rule = parse_numeric_value(text)
    return value, None, None, rule


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
        value, low, high, rule = _numeric(raw)
        declared, _ = parse_numeric_value(item.get("value"))
        mismatch = (declared is not None and value is not None and low is None and declared != value)
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
        if isinstance(confidence, str) and confidence.lower() in {"low", "medium", "high"}:
            confidence = {"low": "0.33", "medium": "0.66", "high": "1.0"}[confidence.lower()]
        if confidence is not None:
            try:
                confidence = Decimal(str(confidence))
                if confidence < 0 or confidence > 1:
                    raise ValueError()
            except (InvalidOperation, ValueError):
                confidence = None
                warnings.append({"code": "UNKNOWN_CONFIDENCE", "index": index, "message": "Confidence must be between zero and one."})
        try:
            if mismatch:
                assumption = AssumptionType.UNRESOLVED
                source_type = SourceType.UNRESOLVED
            metric = FinancialMetric(
                ticker=ticker, report_id=UUID(str(report_id)), name=_name(item, share_type, stage),
                value=value, value_low=low, value_high=high,
                currency=item.get("currency"), unit=unit,
                period_start=_date(item.get("period_start")), period_end=_date(item.get("period_end")),
                effective_date=_date(item.get("effective_date") or item.get("as_of_date")),
                source_date=_date(item.get("source_date")), observed_at=_timestamp(item.get("observed_at") or item.get("fetched_at")),
                report_date=_date(item.get("report_date")),
                source=item.get("source"),
                source_type=source_type, assumption_type=assumption, confidence=confidence,
                operation_segment=item.get("operation_segment"), commodity=item.get("commodity"),
                price_type=_enum(CommodityPriceType, item.get("price_type")),
                cost_definition=_enum(CostDefinition, item.get("cost_definition")),
                production_stage=stage, share_count_type=share_type, annualised=item.get("annualised"),
                notes=item.get("notes"), raw_value=str(raw) if raw is not None else None,
                normalization_rule=rule,
                raw_unit=str(raw_unit) if raw_unit is not None else None,
                evidence_quote=item.get("evidence_quote"), evidence_verified=bool(item.get("evidence_verified")),
                source_id=item.get("source_id") or item.get("source"),
                intended_use=item.get("intended_use"),
            )
            metrics.append(normalize_metric(metric))
            if mismatch:
                warnings.append({"code": "RAW_VALUE_MISMATCH", "severity": "ERROR",
                    "metric_id": str(metric.metric_id), "name": metric.name,
                    "message": f"Declared value {declared} disagrees with raw evidence {value}; ineligible for valuation."})
        except Exception as exc:
            warnings.append({"code": "INVALID_METRIC", "index": index, "message": str(exc), "raw": item})
    warnings.extend(validate_metrics(metrics))
    return metrics, warnings
