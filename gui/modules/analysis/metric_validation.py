"""Advisory checks for typed metrics. These do not change report values."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from .financial_metrics import (
    AssumptionType, FinancialMetric, PRODUCTION_UNITS, ProductionStage,
    ShareCountType, SourceType, Unit,
)


def warning(code: str, metric: FinancialMetric, message: str, newer: FinancialMetric | None = None, severity: str | None = None) -> dict:
    result = {"code": code, "metric_id": str(metric.metric_id), "name": metric.name, "message": message}
    if severity:
        result["severity"] = severity
    if newer:
        result["newer_metric_id"] = str(newer.metric_id)
        result["newer_value"] = str(newer.value)
        result["newer_source_date"] = newer.source_date.isoformat() if newer.source_date else None
    return result


def comparable_key(metric: FinancialMetric) -> tuple:
    return (metric.name, metric.commodity, metric.operation_segment, metric.production_stage,
            metric.share_count_type, metric.unit)


def metric_date(metric: FinancialMetric):
    return metric.period_end or metric.source_date


def validate_metrics(metrics: list[FinancialMetric]) -> list[dict]:
    warnings = []
    for metric in metrics:
        raw = metric.raw_value or ""
        match = re.search(r"(?<!\d)[+-]?(?:\d{1,3}(?:[ ,]\d{3})+|\d+)(?:\.\d+)?", raw)
        if match and metric.value is not None and metric.assumption_type != AssumptionType.PYTHON_CALCULATION:
            try:
                expected = Decimal(match.group().replace(",", "").replace(" ", ""))
                tail = raw[match.end():]
                scale = re.match(r"\s*(thousand|million|billion|bn|mn)\b", tail, re.I)
                if scale:
                    expected *= {"thousand": 10**3, "million": 10**6, "mn": 10**6,
                                 "billion": 10**9, "bn": 10**9}[scale.group(1).lower()]
                if expected != metric.value:
                    warnings.append(warning("RAW_SCALE_MISMATCH", metric,
                        f"Typed value {metric.value} disagrees with raw evidence magnitude {expected}.", severity="ERROR"))
            except InvalidOperation:
                pass
        if "%" in raw and metric.unit == Unit.PERCENTAGE and metric.value is not None:
            shown = Decimal(match.group().replace(",", "").replace(" ", "")) if match else None
            if shown is not None and shown != metric.value:
                warnings.append(warning("PERCENT_SCALE_MISMATCH", metric,
                    "Percentage must retain the displayed percentage-point value.", severity="ERROR"))
        if re.search(r"(?i)\bcents?\b", raw) and metric.unit == Unit.ZAR:
            warnings.append(warning("CENTS_AS_ZAR_WITHOUT_CONVERSION", metric,
                "Raw cents were typed as ZAR without an explicit conversion.", severity="ERROR"))
        if metric.production_stage and metric.unit and metric.unit not in PRODUCTION_UNITS[metric.production_stage]:
            warnings.append(warning("STAGE_UNIT_MISMATCH", metric,
                                    f"{metric.production_stage.value} cannot use {metric.unit.value} without an explicit conversion."))
        if metric.name.startswith("production_") and "cost" not in metric.name and metric.production_stage is None:
            warnings.append(warning("PRODUCTION_STAGE_UNRESOLVED", metric, "Production stage is unresolved."))
        if metric.share_count_type is None and metric.name == "share_count_unresolved":
            warnings.append(warning("SHARE_BASIS_UNRESOLVED", metric, "Issued, historical weighted-average and forecast diluted shares must stay distinct."))
        if metric.name.startswith("commodity_price") and metric.unit is None:
            warnings.append(warning("MISSING_PRICE_UNIT", metric, "Commodity price has no controlled unit."))
        if (metric.production_stage is not None or "cost" in metric.name) and (
            metric.period_start is None or metric.period_end is None
        ):
            warnings.append(warning("MISSING_PERIOD", metric, "Production or cost metric has no complete period."))
        if metric.intended_use == "revenue" and metric.production_stage in {
            ProductionStage.ORE_MINED, ProductionStage.ROM_FEED, ProductionStage.PROCESSED_ORE,
            ProductionStage.CONCENTRATE, ProductionStage.CONTAINED_METAL, ProductionStage.CAPACITY,
        }:
            warnings.append(warning("NOT_SALEABLE_REVENUE_VOLUME", metric,
                                    "This stage cannot be multiplied directly by a commodity price as saleable revenue."))
        if metric.production_stage == ProductionStage.CAPACITY and metric.intended_use in {"production", "base_production"}:
            warnings.append(warning("CAPACITY_NOT_PRODUCTION", metric, "Capacity needs a utilisation and production bridge."))
        if metric.assumption_type == AssumptionType.MANAGEMENT_TARGET and metric.intended_use in {"formal_guidance", "base_production"}:
            warnings.append(warning("TARGET_NOT_GUIDANCE", metric, "Management target cannot silently replace formal guidance."))
        if metric.production_stage == ProductionStage.CONTAINED_METAL and metric.intended_use == "saleable_product":
            warnings.append(warning("CONTAINED_NOT_SALEABLE", metric, "Contained metal needs recovery/payability before saleable output."))
        if metric.share_count_type in {
            ShareCountType.WEIGHTED_AVERAGE_BASIC_SHARES, ShareCountType.WEIGHTED_AVERAGE_DILUTED_SHARES,
        } and metric.intended_use == "forward_target_price":
            warnings.append(warning("HISTORICAL_SHARES_FORWARD", metric,
                                    "Historical EPS/HEPS share denominator is not automatically the forward valuation denominator."))
        for newer in metrics:
            if newer.metric_id == metric.metric_id or comparable_key(newer) != comparable_key(metric):
                continue
            older_date, newer_date = metric_date(metric), metric_date(newer)
            if (older_date and newer_date and older_date < newer_date
                    and newer.source_type == SourceType.COMPANY_DISCLOSURE):
                # Do not overwrite or select either value; disclose the comparison.
                warnings.append(warning("STALE_INPUT", metric,
                                        "The selected metric predates a newer comparable company disclosure.", newer))
                break
    return warnings


def assert_compatible_for_revenue(volume: FinancialMetric, price: FinancialMetric) -> None:
    """Guard any future use; current valuation code does not call this helper."""
    if volume.production_stage not in {ProductionStage.SALEABLE_PRODUCT, ProductionStage.SALES_VOLUME}:
        raise ValueError("Revenue requires saleable product or sales volume, not ROM/contained metal/capacity")
    if volume.commodity is None or price.commodity is None or volume.commodity != price.commodity:
        raise ValueError("Revenue inputs need the same explicit commodity")
    if price.unit not in {Unit.USD_PER_TONNE}:
        raise ValueError("Revenue price needs an explicit price per tonne; normalize USD/lb first")


def assert_compatible_shares_for_target(shares: FinancialMetric) -> None:
    if shares.share_count_type not in {ShareCountType.ISSUED_SHARES_CURRENT, ShareCountType.FORECAST_DILUTED_SHARES}:
        raise ValueError("Forward target needs an explicit current or forecast diluted share-count basis")
