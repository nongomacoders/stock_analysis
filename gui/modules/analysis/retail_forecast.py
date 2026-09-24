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
from .valuation.cashflow import unlevered_fcf

RETAIL_BRIDGE_VERSION = "retail-forecast-1.1"


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
        earnings, earnings_warnings = build_retail_earnings_forecasts(
            plan, metrics, records=records, include_proposed=True)
        fcff_previews = preview_retail_fcff(plan, earnings)
        return {
            "route": route,
            "retail_records": records,
            "retail_earnings_records": earnings,
            "historical_retail_earnings": historical_retail_earnings(metrics),
            "retail_fcff_previews": fcff_previews,
            "warnings": [*warnings, *earnings_warnings],
        }
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
    if field == "sale_of_merchandise_growth":
        return ("sale_of_merchandise", "segment_sale_of_merchandise") if group else ("segment_sale_of_merchandise",)
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
        role_rank = (2 if metric.get("document_role") == "annual_financial_statements"
                     else 1 if metric.get("document_role") == "results_sens" else 0)
        name_rank = 1 if metric.get("name") == names[0] else 0
        candidates.append((period_end or date.min, role_rank, name_rank, metric))
    if not candidates:
        return None
    if currency:
        native = [item for item in candidates if item[3].get('currency') == currency]
        if native:
            candidates = native
    return max(candidates, key=lambda item: item[:3])[3]


def build_retail_forecasts(plan: ForecastPlan, metrics: list[Any], *,
                           include_proposed: bool = True) -> tuple[list[RetailForecastRecord], list[dict]]:
    """Apply growth only to the exact historical concept named by the assumption."""
    records: list[RetailForecastRecord] = []
    warnings: list[dict] = []
    periods = {period.label: period for period in plan.horizon}
    for assumption in plan.assumptions:
        if assumption.field not in {
                "retail_sales_growth", "revenue_growth", "sale_of_merchandise_growth"}:
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
        output = {
            "retail_sales_growth": "forecast_retail_sales",
            "revenue_growth": "forecast_revenue",
            "sale_of_merchandise_growth": "forecast_sale_of_merchandise",
        }[assumption.field]
        derived_metric_id = uuid5(
            assumption.assumption_id,
            f"{plan.ticker}:{plan.source_report_version_id}:{assumption.period_label}:"
            f"{operation}:{output}:{RETAIL_BRIDGE_VERSION}",
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
            unit=(baseline.get("unit").value
                  if hasattr(baseline.get("unit"), "value")
                  else str(baseline.get("unit"))),
            currency=baseline.get("currency"),
            formula=f"{baseline_value} * (1 + {assumption.value} / 100)",
            valuation_eligible=(assumption.approval_state == ApprovalState.ACCEPTED
                                and output == "forecast_revenue"),
        ))
    return records, warnings



class RetailTradingForecastRecord(BaseModel):
    ticker: str
    forecast_plan_id: UUID
    plan_version: int
    period: str
    period_start: date
    period_end: date
    operation: str
    case: str
    output_metric: str = "forecast_trading_profit"
    derived_metric_id: UUID
    historical_sale_metric_id: UUID
    historical_sale_source_id: str | None = None
    historical_trading_profit_metric_id: UUID
    historical_trading_profit_source_id: str | None = None
    historical_trading_margin_metric_id: UUID | None = None
    historical_period: date | None = None
    historical_sale_of_merchandise: Decimal
    historical_trading_profit: Decimal
    historical_trading_margin: Decimal
    sale_growth_assumption_id: UUID
    trading_margin_assumption_id: UUID
    sale_growth: Decimal
    trading_margin: Decimal
    approval_state: ApprovalState
    forecast_sale_of_merchandise: Decimal
    forecast_trading_profit: Decimal
    unit: str
    currency: str | None = None
    formula: str
    engine_version: str = RETAIL_BRIDGE_VERSION
    valuation_eligible: bool = False


def _exact_metric(metrics: list[Any], *, names: tuple[str, ...], operation: str,
                  forecast_start: date | None = None,
                  currency: str | None = None) -> dict | None:
    candidates = []
    for raw in metrics:
        metric = _metric_dict(raw)
        if metric.get("name") not in names or metric.get("value") is None:
            continue
        metric_operation = metric.get("operation_segment")
        if operation.casefold() == "group":
            if metric_operation not in (None, "", "Group"):
                continue
            # Prefer the primary statement concept over its segment-table duplicate.
            name_rank = 1 if metric.get("name") == names[0] else 0
        else:
            if metric_operation != operation:
                continue
            name_rank = 1
        period_end = _period(metric.get("period_end"))
        if forecast_start and period_end and period_end >= forecast_start:
            continue
        currency_rank = 1 if not currency or metric.get("currency") == currency else 0
        candidates.append((period_end or date.min, currency_rank, name_rank, metric))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[:3])[3]


def historical_retail_earnings(metrics: list[Any]) -> list[dict]:
    """Reconcile disclosed trading profit to sale of merchandise by exact concept."""
    operations = {"Group"}
    operations.update(
        _metric_dict(item).get("operation_segment") for item in metrics
        if _metric_dict(item).get("name") == "segment_sale_of_merchandise"
        and _metric_dict(item).get("operation_segment") not in (None, "", "Group")
    )
    rows = []
    for operation in sorted(x for x in operations if x):
        sale_names = ("sale_of_merchandise", "segment_sale_of_merchandise") if operation == "Group" else ("segment_sale_of_merchandise",)
        profit_names = ("trading_profit", "segment_trading_profit") if operation == "Group" else ("segment_trading_profit",)
        margin_names = ("trading_margin", "segment_trading_margin") if operation == "Group" else ("segment_trading_margin",)
        sale = _exact_metric(metrics, names=sale_names, operation=operation)
        profit = _exact_metric(metrics, names=profit_names, operation=operation)
        reported_margin = _exact_metric(metrics, names=margin_names, operation=operation)
        if not sale or not profit or Decimal(str(sale["value"])) == 0:
            continue
        calculated = Decimal(str(profit["value"])) / Decimal(str(sale["value"])) * Decimal("100")
        rows.append({
            "operation": operation,
            "period": str(sale.get("period_end") or ""),
            "sale_of_merchandise": Decimal(str(sale["value"])),
            "sale_of_merchandise_metric_id": str(sale["metric_id"]),
            "sale_of_merchandise_source_id": sale.get("source_id") or sale.get("source"),
            "trading_profit": Decimal(str(profit["value"])),
            "trading_profit_metric_id": str(profit["metric_id"]),
            "trading_profit_source_id": profit.get("source_id") or profit.get("source"),
            "calculated_trading_margin": calculated,
            "reported_trading_margin": Decimal(str(reported_margin["value"])) if reported_margin else None,
            "reported_trading_margin_metric_id": str(reported_margin["metric_id"]) if reported_margin else None,
            "definition": "trading_profit / sale_of_merchandise",
        })
    return rows


def build_retail_earnings_forecasts(
        plan: ForecastPlan, metrics: list[Any], *,
        records: list[RetailForecastRecord] | None = None,
        include_proposed: bool = True) -> tuple[list[RetailTradingForecastRecord], list[dict]]:
    """Apply trading margin only to forecast sale of merchandise; never to revenue."""
    growth_records = records
    if growth_records is None:
        growth_records, _ = build_retail_forecasts(
            plan, metrics, include_proposed=include_proposed)
    sale_records = [
        item for item in growth_records
        if item.output_metric == "forecast_sale_of_merchandise"
        and (include_proposed or item.approval_state == ApprovalState.ACCEPTED)
    ]
    allowed_states = {ApprovalState.ACCEPTED}
    if include_proposed:
        allowed_states.add(ApprovalState.PROPOSED)
    margins = [
        item for item in plan.assumptions
        if item.field == "trading_margin" and item.approval_state in allowed_states
    ]
    output: list[RetailTradingForecastRecord] = []
    warnings: list[dict] = []
    for sale in sale_records:
        margin = next((
            item for item in margins
            if item.period_label == sale.period and item.case == sale.case
            and (item.operation_segment or "Group") == sale.operation
        ), None)
        if margin is None:
            warnings.append({
                "code": "TRADING_MARGIN_MISSING", "period": sale.period,
                "operation": sale.operation, "field": "trading_margin",
                "message": "Forecast sale of merchandise has no matching trading-margin assumption.",
            })
            continue
        if margin.value is None or margin.unit != "percentage":
            warnings.append({
                "code": "TRADING_MARGIN_INVALID", "period": sale.period,
                "operation": sale.operation, "field": "trading_margin",
                "message": "Trading margin requires a numeric percentage assumption.",
            })
            continue
        if margin.currency and sale.currency and margin.currency != sale.currency:
            warnings.append({
                "code": "TRADING_MARGIN_CURRENCY_MISMATCH", "period": sale.period,
                "operation": sale.operation, "field": "trading_margin",
                "message": "Trading-margin metadata conflicts with the sale-of-merchandise currency.",
            })
            continue
        profit_names = ("trading_profit", "segment_trading_profit") if sale.operation == "Group" else ("segment_trading_profit",)
        margin_names = ("trading_margin", "segment_trading_margin") if sale.operation == "Group" else ("segment_trading_margin",)
        historical_profit = _exact_metric(
            metrics, names=profit_names, operation=sale.operation,
            forecast_start=sale.period_start, currency=sale.currency)
        reported_margin = _exact_metric(
            metrics, names=margin_names, operation=sale.operation,
            forecast_start=sale.period_start)
        if historical_profit is None:
            warnings.append({
                "code": "TRADING_PROFIT_BASELINE_MISSING", "period": sale.period,
                "operation": sale.operation, "field": "trading_margin",
                "message": "Exact historical trading-profit baseline is missing; finance income was not substituted.",
            })
            continue
        historical_sale = sale.historical_baseline_value
        historical_profit_value = Decimal(str(historical_profit["value"]))
        historical_margin = historical_profit_value / historical_sale * Decimal("100")
        forecast_profit = sale.derived_forecast_value * margin.value / Decimal("100")
        state = (ApprovalState.ACCEPTED
                 if sale.approval_state == margin.approval_state == ApprovalState.ACCEPTED
                 else ApprovalState.PROPOSED)
        output.append(RetailTradingForecastRecord(
            ticker=plan.ticker, forecast_plan_id=plan.forecast_plan_id,
            plan_version=plan.plan_version, period=sale.period,
            period_start=sale.period_start, period_end=sale.period_end,
            operation=sale.operation, case=sale.case,
            derived_metric_id=uuid5(
                sale.assumption_id,
                f"{plan.ticker}:{plan.source_report_version_id}:{margin.assumption_id}:"
                f"{sale.period}:{sale.operation}:forecast_trading_profit:{RETAIL_BRIDGE_VERSION}"),
            historical_sale_metric_id=sale.historical_baseline_metric_id,
            historical_sale_source_id=sale.historical_source_id,
            historical_trading_profit_metric_id=UUID(str(historical_profit["metric_id"])),
            historical_trading_profit_source_id=historical_profit.get("source_id") or historical_profit.get("source"),
            historical_trading_margin_metric_id=UUID(str(reported_margin["metric_id"])) if reported_margin else None,
            historical_period=sale.historical_period,
            historical_sale_of_merchandise=historical_sale,
            historical_trading_profit=historical_profit_value,
            historical_trading_margin=historical_margin,
            sale_growth_assumption_id=sale.assumption_id,
            trading_margin_assumption_id=margin.assumption_id,
            sale_growth=sale.assumption_value, trading_margin=margin.value,
            approval_state=state,
            forecast_sale_of_merchandise=sale.derived_forecast_value,
            forecast_trading_profit=forecast_profit,
            unit=sale.unit, currency=sale.currency,
            formula=f"{sale.derived_forecast_value} * ({margin.value} / 100)",
            valuation_eligible=(state == ApprovalState.ACCEPTED),
        ))
    for margin in margins:
        matched = any(
            sale.period == margin.period_label and sale.case == margin.case
            and sale.operation == (margin.operation_segment or "Group")
            for sale in sale_records)
        if not matched:
            warnings.append({
                "code": "SALE_OF_MERCHANDISE_FORECAST_MISSING",
                "period": margin.period_label, "operation": margin.operation_segment or "Group",
                "field": "sale_of_merchandise_growth",
                "message": "Trading margin cannot use revenue or retail-sales growth; forecast sale of merchandise is missing.",
            })
    return output, warnings


def render_historical_retail_earnings(rows: list[dict]) -> str:
    if not rows:
        return "Historical sale of merchandise/trading margin: unavailable."
    lines = ["Historical retailer earnings baselines "
             "(trading margin = trading profit / sale of merchandise):"]
    for row in rows:
        reported = (f"{row['reported_trading_margin']}%"
                    if row["reported_trading_margin"] is not None
                    else f"{row['calculated_trading_margin']:.4f}% calculated")
        lines.append(
            f"{row['operation']}: sale of merchandise {row['sale_of_merchandise']} "
            f"| trading profit {row['trading_profit']} | trading margin {reported} "
            f"| metrics {row['sale_of_merchandise_metric_id']}, {row['trading_profit_metric_id']}")
    return "\n".join(lines)


def render_retail_earnings_records(records: list[RetailTradingForecastRecord]) -> str:
    if not records:
        return "No complete sale-of-merchandise/trading-margin forecast bridge."
    lines = []
    for record in records:
        lines.extend([
            f"{record.period} - {record.operation} trading earnings bridge",
            f"Historical sale of merchandise: {record.historical_sale_of_merchandise} {record.unit}",
            f"Historical trading margin: {record.historical_trading_margin:.4f}% "
            f"(trading profit / sale of merchandise)",
            f"{record.approval_state.value.upper()} sale-of-merchandise growth: {record.sale_growth}%",
            f"{record.approval_state.value.upper()} trading margin: {record.trading_margin}%",
            f"Derived forecast sale of merchandise: {record.forecast_sale_of_merchandise} {record.unit}",
            f"Derived forecast trading profit: {record.forecast_trading_profit} {record.unit}",
            ("DCF mapping: eligible as direct EBIT when accepted; depreciation remains "
             "a separate FCFF add-back input." if record.valuation_eligible else
             "DCF mapping: proposed / informational only."),
            f"Provenance: sale metric {record.historical_sale_metric_id}; trading-profit metric "
            f"{record.historical_trading_profit_metric_id}; assumptions "
            f"{record.sale_growth_assumption_id}, {record.trading_margin_assumption_id}", "",
        ])
    return "\n".join(lines)


def materialize_retail_trading_profit(
        record: RetailTradingForecastRecord, report_id: UUID):
    """Map an accepted, evidence-linked retail trading-profit forecast to direct EBIT."""
    if (not record.valuation_eligible
            or record.output_metric != "forecast_trading_profit"
            or record.approval_state != ApprovalState.ACCEPTED):
        raise ValueError("Only an accepted retail trading-profit bridge may map to EBIT")
    from .financial_metrics import AssumptionType, FinancialMetric, SourceType, Unit
    from .valuation_preflight import ValuationField, candidate
    metric = FinancialMetric(
        metric_id=record.derived_metric_id, ticker=record.ticker,
        report_id=report_id, name="forecast_trading_profit",
        value=record.forecast_trading_profit, unit=Unit(record.unit),
        currency=record.currency, period_start=record.period_start,
        period_end=record.period_end, source_date=record.historical_period,
        source=f"Retail trading-profit bridge {record.engine_version}",
        source_type=SourceType.PYTHON,
        assumption_type=AssumptionType.MODEL_ASSUMPTION,
        source_id=(
            f"retail_trading_profit:{record.sale_growth_assumption_id}:"
            f"{record.trading_margin_assumption_id}"),
        operation_segment=record.operation,
        notes=(
            "Explicit retailer EBIT mapping: forecast sale of merchandise x "
            f"trading margin. Historical sale metric {record.historical_sale_metric_id}; "
            f"historical trading-profit metric {record.historical_trading_profit_metric_id}; "
            f"formula {record.formula}. Finance and dividend income excluded."),
        evidence_verified=True, intended_use="direct_ebit",
    )
    return metric, candidate(
        metric, report_id, ValuationField.EBIT, record.case,
        "Evidence-aware retailer trading-profit bridge mapped explicitly to direct EBIT")

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


_FCFF_MAPPING_LABELS = {
    "depreciation": "D&A add-back",
    "tax_rate": "cash tax",
    "total_capex": "capex",
    "sustaining_capex": "sustaining capex",
    "growth_capex": "growth capex",
    "working_capital": "change in operating working capital",
    "other_recurring_cash": "recurring operating cash deduction",
    "wacc": "supported_wacc",
}


def preview_retail_fcff(plan: ForecastPlan,
                        earnings: list[RetailTradingForecastRecord]) -> list[dict]:
    """Preview FCFF from accepted retail assumptions without running a valuation."""
    accepted = eligible_assumptions(plan)
    previews: list[dict] = []
    for earning in earnings:
        if not earning.valuation_eligible:
            continue
        matching = {
            item.field: item for item in accepted
            if item.period_label == earning.period and item.case == earning.case
            and (item.operation_segment or "Group") == earning.operation
            and item.field in _FCFF_MAPPING_LABELS
        }
        required = ["depreciation", "tax_rate", "working_capital", "other_recurring_cash"]
        missing = [field for field in required if field not in matching]
        has_total = "total_capex" in matching
        has_split = "sustaining_capex" in matching or "growth_capex" in matching
        if has_total and has_split:
            previews.append({"status": "NOT_CALCULABLE", "period": earning.period,
                             "operation": earning.operation,
                             "reason": "TOTAL_AND_SPLIT_CAPEX_PRESENT"})
            continue
        if not has_total:
            missing.extend(field for field in ("sustaining_capex", "growth_capex")
                           if field not in matching)
        if missing:
            previews.append({"status": "NOT_CALCULABLE", "period": earning.period,
                             "operation": earning.operation,
                             "reason": "MISSING_ACCEPTED_FCFF_INPUTS", "missing": missing})
            continue
        values = {field: item.value for field, item in matching.items()}
        if any(value is None for value in values.values()):
            previews.append({"status": "NOT_CALCULABLE", "period": earning.period,
                             "operation": earning.operation,
                             "reason": "NULL_ACCEPTED_FCFF_INPUT"})
            continue
        result = unlevered_fcf(
            ebit=earning.forecast_trading_profit,
            tax_rate=values["tax_rate"] / Decimal("100"),
            depreciation=values["depreciation"],
            total_capex=values.get("total_capex"),
            sustaining_capex=values.get("sustaining_capex"),
            growth_capex=values.get("growth_capex"),
            working_capital_change=values["working_capital"],
            other_recurring_cash=values["other_recurring_cash"],
        )
        previews.append({
            "status": "PASS", "period": earning.period, "operation": earning.operation,
            "case": earning.case, "currency": earning.currency, "unit": earning.unit,
            "formula": "EBIT - cash tax + depreciation - capex - working capital - other recurring cash",
            "inputs": result,
            "assumption_ids": {field: str(item.assumption_id) for field, item in matching.items()},
            "earnings_assumption_ids": {
                "sale_of_merchandise_growth": str(earning.sale_growth_assumption_id),
                "trading_margin": str(earning.trading_margin_assumption_id),
            },
            "forecast_trading_profit_metric_id": str(earning.derived_metric_id),
        })
    return previews


def render_retail_fcff_previews(previews: list[dict]) -> str:
    if not previews:
        return "FY FCFF preview: NOT_CALCULABLE - no accepted direct-EBIT bridge."
    lines = []
    for item in previews:
        if item["status"] != "PASS":
            lines.append(f"{item['period']} - {item['operation']} FCFF preview: "
                         f"NOT_CALCULABLE ({item['reason']}) {item.get('missing', '')}")
            continue
        inputs = item["inputs"]
        capex = (inputs["total_capex"] if inputs["total_capex"] is not None
                 else inputs["sustaining_capex"] + inputs["growth_capex"])
        lines.extend([
            f"{item['period']} - {item['operation']} accepted-only FCFF preview: "
            f"{inputs['unlevered_fcf']} {item.get('currency') or item['unit']}",
            f"Formula: {item['formula']}",
            f"Inputs: EBIT {inputs['ebit']}; cash tax {inputs['cash_tax']}; "
            f"D&A {inputs['depreciation_addback']}; capex {capex}; "
            f"working capital {inputs['working_capital_change']}; "
            f"other recurring cash {inputs['other_recurring_cash']}",
            "Preview only - no WACC, terminal value, valuation, or plan mutation.",
        ])
    return "\n".join(lines)


def retail_engine_mapping(records: list[RetailForecastRecord], warnings: list[dict], *,
                          earnings: list[RetailTradingForecastRecord] | None = None,
                          plan: ForecastPlan | None = None,
                          fcff_previews: list[dict] | None = None) -> str:
    lines = ["ForecastPlan assumption -> retailer forecast bridge -> derived forecast metric -> valuation input"]
    for record in records:
        destination = "revenue (eligible when explicitly mapped)" if record.valuation_eligible else "informational / not valuation eligible"
        lines.append(f"{record.assumption_field} [{record.assumption_id}] -> {record.output_metric} "
                     f"[{record.derived_metric_id}] -> {destination}")
    for record in earnings or []:
        destination = ("direct EBIT (eligible)" if record.valuation_eligible
                       else "direct EBIT (ineligible until both assumptions are accepted)")
        lines.append(f"sale_of_merchandise_growth [{record.sale_growth_assumption_id}] + "
                     f"trading_margin [{record.trading_margin_assumption_id}] -> "
                     f"forecast_trading_profit [{record.derived_metric_id}] -> {destination}")
    if plan is not None:
        for item in plan.assumptions:
            if item.field not in _FCFF_MAPPING_LABELS:
                continue
            state = ("eligible" if item.approval_state == ApprovalState.ACCEPTED
                     else f"{item.approval_state.value} / ineligible")
            lines.append(f"{item.field} [{item.assumption_id}] -> "
                         f"{_FCFF_MAPPING_LABELS[item.field]} ({state})")
    for preview in fcff_previews or []:
        if preview["status"] == "PASS":
            lines.append(f"accepted direct EBIT + accepted cash-flow inputs -> FY FCFF preview "
                         f"{preview['inputs']['unlevered_fcf']} {preview.get('currency') or preview['unit']}")
    lines.append("forecast_revenue -> required by current YearInputSpec/preflight for schedule/cross-check; not used in direct-EBIT FCFF arithmetic")
    for warning in warnings:
        lines.append(f"{warning['field']} -> NOT_CALCULABLE ({warning['code']}) -> not consumed by valuation")
    return "\n".join(lines)
