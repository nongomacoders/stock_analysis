"""Sector routing and deterministic retailer forecast bridges."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID, uuid5

from pydantic import BaseModel

from .financial_metrics import convert_fx
from .forecast_plan import ApprovalState, ForecastPlan, eligible_assumptions

RETAIL_BRIDGE_VERSION = "retail-forecast-1.0"


class WorkbenchRoute(str, Enum):
    RETAIL = "retail"
    MINING = "mining"
    BANK = "bank"
    HOLDING_COMPANY = "holding_company"
    GENERIC = "generic"


def workbench_route(category: str | None) -> WorkbenchRoute:
    normalized = " ".join((category or "").casefold().replace("&", " ").split())
    if "retail" in normalized:
        return WorkbenchRoute.RETAIL
    if any(term in normalized for term in ("mining", "commodit")):
        return WorkbenchRoute.MINING
    if any(term in normalized for term in ("bank", "financial service")):
        return WorkbenchRoute.BANK
    if "holding" in normalized:
        return WorkbenchRoute.HOLDING_COMPANY
    return WorkbenchRoute.GENERIC


def build_sector_schedules(category: str | None, plan: ForecastPlan, metrics: list[Any], *,
                           mining_production_builder=None, mining_cost_builder=None) -> dict:
    """Dispatch schedule builders by sector; non-mining routes never call mining builders."""
    route = workbench_route(category)
    if route == WorkbenchRoute.RETAIL:
        records, warnings = build_retail_forecasts(plan, metrics, include_proposed=True)
        return {"route": route, "retail_records": records, "warnings": warnings}
    if route == WorkbenchRoute.MINING:
        if mining_production_builder is None or mining_cost_builder is None:
            from .forecast_plan import forecast_operating_schedule, cost_forecast_schedule
            mining_production_builder = mining_production_builder or forecast_operating_schedule
            mining_cost_builder = mining_cost_builder or cost_forecast_schedule
        operations = sorted({item.operation_segment for item in plan.assumptions if item.operation_segment})
        return {
            "route": route,
            "production": {operation: mining_production_builder(plan, operation) for operation in operations},
            "costs": {operation: mining_cost_builder(plan, operation) for operation in operations},
        }
    return {"route": route}


class RetailForecastRecord(BaseModel):
    ticker: str
    forecast_plan_id: UUID
    plan_version: int
    period: str
    period_start: date
    period_end: date
    operation: str
    case: str
    output_metric: str
    derived_metric_id: UUID
    historical_baseline_metric_id: UUID
    historical_source_id: str | None = None
    historical_period: date | None = None
    historical_baseline_value: Decimal
    assumption_id: UUID
    assumption_field: str
    assumption_value: Decimal
    approval_state: ApprovalState
    derived_forecast_value: Decimal
    unit: str
    currency: str | None = None
    formula: str
    engine_version: str = RETAIL_BRIDGE_VERSION
    valuation_eligible: bool = False


def _metric_dict(metric: Any) -> dict:
    if isinstance(metric, dict):
        return metric
    return metric.model_dump(mode="python")


def _period(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if value:
        return date.fromisoformat(str(value)[:10])
    return None


def _baseline_names(field: str, operation: str) -> tuple[str, ...]:
    group = operation.casefold() == "group"
    if field == "retail_sales_growth":
        return ("retail_sales",) if group else ("segment_retail_sales",)
    if field == "revenue_growth":
        return ("revenue", "segment_revenue") if group else ("segment_revenue",)
    return ()


def resolve_retail_baseline(metrics: list[Any], *, field: str, operation: str,
                            forecast_start: date | None = None,
                            currency: str | None = None) -> dict | None:
    """Resolve the latest exact-concept baseline without substituting adjacent concepts."""
    names = _baseline_names(field, operation)
    candidates = []
    for raw in metrics:
        metric = _metric_dict(raw)
        if metric.get("name") not in names or metric.get("value") is None:
            continue
        metric_operation = metric.get("operation_segment")
        if operation.casefold() == "group":
            if metric_operation not in (None, "", "Group"):
                continue
        elif metric_operation != operation:
            continue
        period_end = _period(metric.get("period_end"))
        if forecast_start and period_end and period_end >= forecast_start:
            continue
        candidates.append((period_end or date.min, metric))
    if not candidates:
        return None
    if currency:
        native = [item for item in candidates if item[1].get('currency') == currency]
        if native:
            candidates = native
    return max(candidates, key=lambda item: item[0])[1]


def build_retail_forecasts(plan: ForecastPlan, metrics: list[Any], *,
                           include_proposed: bool = True) -> tuple[list[RetailForecastRecord], list[dict]]:
    """Apply growth only to the exact historical concept named by the assumption."""
    records: list[RetailForecastRecord] = []
    warnings: list[dict] = []
    periods = {period.label: period for period in plan.horizon}
    for assumption in plan.assumptions:
        if assumption.field not in {"retail_sales_growth", "revenue_growth"}:
            continue
        if assumption.approval_state != ApprovalState.ACCEPTED and not include_proposed:
            continue
        if assumption.approval_state not in {ApprovalState.PROPOSED, ApprovalState.ACCEPTED}:
            continue
        operation = assumption.operation_segment or "Group"
        period = periods.get(assumption.period_label or "")
        baseline = resolve_retail_baseline(
            metrics, field=assumption.field, operation=operation,
            forecast_start=period.start if period else None,
            currency=assumption.currency)
        if baseline is None:
            warnings.append({
                "code": "RETAIL_BASELINE_MISSING",
                "period": assumption.period_label,
                "operation": operation,
                "field": assumption.field,
                "message": "No exact-concept historical baseline is available; adjacent sales concepts were not substituted.",
            })
            continue
        baseline_currency = baseline.get("currency")
        if operation.casefold() != "group" and not assumption.currency:
            warnings.append({
                "code": "SEGMENT_OPERATING_CURRENCY_MISSING",
                "period": assumption.period_label,
                "operation": operation,
                "field": assumption.field,
                "message": "Segment forecasts require an explicit operating currency.",
            })
            continue
        if assumption.currency and baseline_currency != assumption.currency:
            warnings.append({
                "code": "NATIVE_CURRENCY_BASELINE_MISSING",
                "period": assumption.period_label,
                "operation": operation,
                "field": assumption.field,
                "message": (f"No {assumption.currency} historical baseline is available. The available "
                            f"baseline is {baseline_currency or 'missing'}; forecast FX was not used to "
                            "reconstruct the historical period."),
            })
            continue
        if assumption.value is None or assumption.unit != "percentage":
            warnings.append({
                "code": "RETAIL_GROWTH_INVALID",
                "period": assumption.period_label,
                "operation": operation,
                "field": assumption.field,
                "message": "Retail growth requires a numeric percentage assumption.",
            })
            continue
        baseline_value = Decimal(str(baseline["value"]))
        factor = Decimal("1") + assumption.value / Decimal("100")
        output = "forecast_retail_sales" if assumption.field == "retail_sales_growth" else "forecast_revenue"
        derived_metric_id = uuid5(
            plan.forecast_plan_id,
            f"{assumption.assumption_id}:{assumption.period_label}:{operation}:{output}",
        )
        records.append(RetailForecastRecord(
            ticker=plan.ticker,
            forecast_plan_id=plan.forecast_plan_id,
            plan_version=plan.plan_version,
            period=assumption.period_label or "",
            period_start=period.start,
            period_end=period.end,
            operation=operation,
            case=assumption.case,
            output_metric=output,
            derived_metric_id=derived_metric_id,
            historical_baseline_metric_id=UUID(str(baseline["metric_id"])),
            historical_source_id=baseline.get("source_id") or baseline.get("source"),
            historical_period=_period(baseline.get("period_end")),
            historical_baseline_value=baseline_value,
            assumption_id=assumption.assumption_id,
            assumption_field=assumption.field,
            assumption_value=assumption.value,
            approval_state=assumption.approval_state,
            derived_forecast_value=baseline_value * factor,
            unit=str(baseline.get("unit")),
            currency=baseline.get("currency"),
            formula=f"{baseline_value} * (1 + {assumption.value} / 100)",
            valuation_eligible=(assumption.approval_state == ApprovalState.ACCEPTED
                                and output == "forecast_revenue"),
        ))
    return records, warnings


def materialize_retail_forecast(record: RetailForecastRecord, report_id: UUID):
    """Convert an accepted accounting-revenue forecast into an explicit engine candidate."""
    if not record.valuation_eligible or record.output_metric != "forecast_revenue":
        raise ValueError("Only accepted forecast revenue may enter valuation inputs")
    from .financial_metrics import AssumptionType, FinancialMetric, SourceType, Unit
    from .valuation_preflight import ValuationField, candidate
    metric = FinancialMetric(
        metric_id=record.derived_metric_id, ticker=record.ticker, report_id=report_id,
        name="forecast_revenue", value=record.derived_forecast_value,
        unit=Unit(record.unit), currency=record.currency,
        period_start=record.period_start, period_end=record.period_end,
        source_date=record.historical_period,
        source=f"Retail forecast bridge {record.engine_version}",
        source_type=SourceType.PYTHON, assumption_type=AssumptionType.MODEL_ASSUMPTION,
        source_id=f"retail_forecast:{record.assumption_id}",
        operation_segment=record.operation,
        notes=(f"Baseline metric {record.historical_baseline_metric_id}; source "
              f"{record.historical_source_id}; formula {record.formula}"),
        evidence_verified=True, intended_use="approved_forecast_revenue",
    )
    return metric, candidate(
        metric, report_id, ValuationField.REVENUE, record.case,
        f"Retail bridge from accepted assumption {record.assumption_id}")


def required_revenue_segments(metrics: list[Any]) -> list[str]:
    """Return revenue-bearing segments disclosed in the detailed evidence package."""
    segments = set()
    for raw in metrics:
        metric = _metric_dict(raw)
        operation = metric.get("operation_segment")
        if (metric.get("name") == "segment_revenue" and operation
                and operation.casefold() != "group" and metric.get("value") is not None
                and Decimal(str(metric["value"])) != 0):
            segments.add(operation)
    return sorted(segments)


def aggregate_retail_revenue(plan: ForecastPlan, records: list[RetailForecastRecord], *,
                             period: str, case: str = "base",
                             evidence_metrics: list[Any] | None = None,
                             target_currency: str = "ZAR") -> dict:
    """Aggregate accepted segment accounting revenue with explicit FX only."""
    selected = [record for record in records
                if record.period == period and record.case == case
                and record.output_metric == "forecast_revenue"
                and record.approval_state == ApprovalState.ACCEPTED]
    group = [record for record in selected if record.operation.casefold() == "group"]
    segments = [record for record in selected if record.operation.casefold() != "group"]
    if group and segments:
        return {"status": "NOT_CALCULABLE", "reason": "GROUP_SEGMENT_DOUBLE_COUNT"}
    if len(group) > 1 or len({record.operation for record in segments}) != len(segments):
        return {"status": "NOT_CALCULABLE", "reason": "DUPLICATE_SEGMENT"}
    required = required_revenue_segments(evidence_metrics or [])
    if segments and evidence_metrics is None:
        return {"status": "NOT_CALCULABLE", "reason": "REQUIRED_SEGMENT_EVIDENCE_MISSING",
                "present_segments": sorted(record.operation for record in segments),
                "missing_segments": []}
    if segments and required:
        present = {record.operation for record in segments}
        missing = [operation for operation in required if operation not in present]
        if missing:
            return {"status": "PARTIAL", "reason": "MISSING_REQUIRED_SEGMENTS",
                    "required_segments": required, "present_segments": sorted(present),
                    "missing_segments": missing}
    components = group or segments
    if not components:
        return {"status": "NOT_CALCULABLE", "reason": "NO_ACCEPTED_REVENUE_FORECASTS"}
    fx_assumptions = [item for item in eligible_assumptions(plan)
                      if item.field == "fx_rate" and item.period_label == period and item.case == case]
    total = Decimal("0")
    translated = []
    for record in components:
        source_currency = record.currency
        if not source_currency:
            return {"status": "NOT_CALCULABLE", "reason": "MISSING_SEGMENT_CURRENCY",
                    "operation": record.operation}
        value = record.derived_forecast_value
        fx_id = None
        if source_currency != target_currency:
            fx = next((item for item in fx_assumptions
                       if item.fx_pair and {source_currency, target_currency} ==
                       set(item.fx_pair.upper().split("/"))), None)
            if fx is None or fx.value is None:
                return {"status": "NOT_CALCULABLE", "reason": "MISSING_EXPLICIT_FX",
                        "operation": record.operation, "currency": source_currency,
                        "target_currency": target_currency,
                        "required_segments": required, "missing_segments": []}
            value = convert_fx(value, rate=fx.value, pair=fx.fx_pair,
                               from_currency=source_currency, to_currency=target_currency)
            fx_id = str(fx.assumption_id)
        total += value
        translated.append({"operation": record.operation, "source_value": str(record.derived_forecast_value),
                           "source_currency": source_currency, "translated_value": str(value),
                           "target_currency": target_currency, "fx_assumption_id": fx_id,
                           "forecast_assumption_id": str(record.assumption_id)})
    return {"status": "PASS", "period": period, "case": case,
            "output_metric": "forecast_group_revenue", "value": total,
            "unit": target_currency, "currency": target_currency,
            "required_segments": required, "missing_segments": [],
            "components": translated, "engine_version": RETAIL_BRIDGE_VERSION}


def render_retail_records(records: list[RetailForecastRecord], warnings: list[dict]) -> str:
    lines = []
    for record in records:
        lines.extend([
            f"{record.period} - {record.operation}",
            f"Historical baseline: {record.historical_period or 'unknown'} {record.output_metric.removeprefix('forecast_')}: "
            f"{record.historical_baseline_value} {record.unit} ({record.currency or 'currency missing'})",
            f"{record.approval_state.value.upper()} growth: {record.assumption_value}%",
            f"Status: {record.approval_state.value.upper()}" +
            (" - valuation eligible" if record.valuation_eligible else " - not valuation eligible"),
            f"Derived {record.output_metric}: {record.derived_forecast_value} {record.unit}",
            f"Provenance: metric {record.historical_baseline_metric_id}; source {record.historical_source_id}; "
            f"assumption {record.assumption_id}", "",
        ])
    for warning in warnings:
        lines.append(f"{warning['period']} - {warning['operation']}: NOT_CALCULABLE "
                     f"[{warning['code']}] - {warning['message']}")
    return "\n".join(lines) or "No retailer growth assumptions entered."


def retail_engine_mapping(records: list[RetailForecastRecord], warnings: list[dict]) -> str:
    lines = ["ForecastPlan assumption -> retailer forecast bridge -> derived forecast metric -> valuation input"]
    for record in records:
        destination = "revenue (eligible when explicitly mapped)" if record.valuation_eligible else "informational / not valuation eligible"
        lines.append(f"{record.assumption_field} [{record.assumption_id}] -> {record.output_metric} "
                     f"[{record.derived_metric_id}] -> {destination}")
    for warning in warnings:
        lines.append(f"{warning['field']} -> NOT_CALCULABLE ({warning['code']}) -> not consumed by valuation")
    return "\n".join(lines)
