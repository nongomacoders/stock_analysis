"""Deterministic valuation-input gate. No fair-value calculation or publication."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from .financial_metrics import (
    AssumptionType, CommodityPriceType, CostDefinition, FinancialMetric, ProductionStage, ShareCountType,
    SourceType, Unit, normalize_metric,
)


class ValuationField(str, Enum):
    COMMODITY_PRICE = "commodity_price"
    PRODUCTION_VOLUME = "production_volume"
    MINING_THROUGHPUT = "mining_throughput"
    SALEABLE_VOLUME = "saleable_volume"
    REVENUE = "revenue"
    PRODUCTION_COST = "production_cost"
    CASH_COST = "cash_cost"
    AISC = "aisc"
    OPERATING_COST = "operating_cost"
    MINING_COST = "mining_cost"
    PROCESSING_COST = "processing_cost"
    REFINING_COST = "refining_cost"
    TRANSPORT_COST = "transport_cost"
    TREATMENT_COST = "treatment_cost"
    ROYALTIES = "royalties"
    OTHER_OPERATING_COST = "other_operating_cost"
    TAX_RATE = "tax_rate"
    CURRENT_ISSUED_SHARES = "current_issued_shares"
    WEIGHTED_AVERAGE_BASIC_SHARES = "weighted_average_basic_shares"
    WEIGHTED_AVERAGE_DILUTED_SHARES = "weighted_average_diluted_shares"
    FORECAST_DILUTED_SHARES = "forecast_diluted_shares"
    NET_DEBT = "net_debt"
    NET_CASH = "net_cash"
    CAPEX = "capex"
    SUSTAINING_CAPEX = "sustaining_capex"
    GROWTH_CAPEX = "growth_capex"
    WORKING_CAPITAL = "working_capital"
    ROYALTY_RATE = "royalty_rate"
    WACC = "wacc"
    TERMINAL_GROWTH = "terminal_growth"
    EXIT_MULTIPLE = "exit_multiple"
    OWNERSHIP_PERCENTAGE = "ownership_percentage"
    PRODUCTION_GROWTH = "production_growth"
    OPERATING_MARGIN = "operating_margin"
    GRADE = "grade"
    RECOVERY = "recovery"
    PROCESSING_CONVERSION = "processing_conversion"
    TREATMENT_CHARGE = "treatment_charge"
    PAYABILITY = "payability"
    REALIZATION_FACTOR = "realization_factor"
    UTILIZATION = "utilization"
    RAMP_UP = "ramp_up"
    NAMEPLATE_CAPACITY = "nameplate_capacity"
    RISK_FREE_RATE = "risk_free_rate"
    EQUITY_RISK_PREMIUM = "equity_risk_premium"
    BETA = "beta"
    COUNTRY_RISK_PREMIUM = "country_risk_premium"
    COST_OF_DEBT = "cost_of_debt"
    DEBT_WEIGHT = "debt_weight"
    EQUITY_WEIGHT = "equity_weight"
    DEPRECIATION = "depreciation"
    NET_FINANCE_COST = "net_finance_cost"
    CORPORATE_COST = "corporate_cost"
    OTHER_RECURRING_CASH = "other_recurring_cash"
    ASSET_VALUE = "asset_value"
    PROBABILITY = "probability"
    DISCOUNT_FACTOR = "discount_factor"
    DEFERRED_PAYMENT = "deferred_payment"
    FX_RATE = "fx_rate"
    DEFERRED_DISCOUNT_RATE = "deferred_discount_rate"
    COUNTERPARTY_FACTOR = "counterparty_factor"
    LEASE_ADJUSTMENTS = "lease_adjustments"
    MINORITIES = "minorities"
    NON_OPERATING_ASSETS = "non_operating_assets"
    RECEIVABLES = "receivables"
    OTHER_EQUITY_ADJUSTMENTS = "other_equity_adjustments"
    CURRENT_SHARE_PRICE = "current_share_price"
    NET_ASSET_VALUE = "net_asset_value"
    TARGET_PRICE = "target_price"  # Reconciliation only, never a valuation input.


class CaseType(str, Enum):
    BASE = "base"
    BULL = "bull"
    BEAR = "bear"
    SENSITIVITY = "sensitivity"
    INFORMATIONAL = "informational"


class Severity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    BLOCKING = "BLOCKING"


class Eligibility(str, Enum):
    ELIGIBLE = "eligible"
    ELIGIBLE_WITH_WARNING = "eligible_with_warning"
    INELIGIBLE = "ineligible"
    UNRESOLVED = "unresolved"


class FreshnessStatus(str, Enum):
    CURRENT = "current"
    SUPERSEDED = "superseded"
    HISTORICAL_REFERENCE = "historical_reference"
    INCOMPARABLE = "incomparable"
    UNKNOWN = "unknown"


class TargetDerivation(str, Enum):
    REPRODUCIBLE_PYTHON = "reproducible_python"
    REPRODUCIBLE_FROM_REPORT = "reproducible_from_report"
    PARTIAL_RECONCILIATION = "partial_reconciliation"
    CARRIED_FORWARD = "carried_forward"
    UNSUPPORTED = "unsupported"
    UNRESOLVED = "unresolved"


class ValidationResult(BaseModel):
    code: str
    severity: Severity
    message: str
    metric_id: UUID | None = None
    related_metric_id: UUID | None = None


class OverrideRecord(BaseModel):
    original_validation_result: list[ValidationResult]
    override_timestamp: datetime
    override_reason: str = Field(min_length=10)
    overridden_by: str = Field(min_length=1)
    selected_replacement: str = Field(min_length=1)
    case_type: CaseType


class ValuationInputCandidate(BaseModel):
    metric_id: UUID
    report_version_id: UUID
    valuation_field: ValuationField
    selected_value: Decimal | None
    normalized_unit: Unit | None
    source_metric: FinancialMetric
    assumption_type: AssumptionType
    source_date: date | None = None
    period_start: date | None = None
    period_end: date | None = None
    operation_segment: str | None = None
    confidence: Decimal | None = None
    selection_reason: str
    combination_group: str | None = None
    case_type: CaseType
    validation_status: Eligibility = Eligibility.UNRESOLVED
    warnings: list[ValidationResult] = Field(default_factory=list)
    override: OverrideRecord | None = None

    @model_validator(mode="after")
    def linked_to_metric(self):
        if self.metric_id != self.source_metric.metric_id:
            raise ValueError("Candidate metric_id must reference source_metric")
        if self.source_metric.report_id and self.report_version_id != self.source_metric.report_id:
            raise ValueError("Candidate report_version_id must match source metric report_id")
        if self.assumption_type != self.source_metric.assumption_type:
            raise ValueError("Candidate assumption_type must match source metric")
        allowed = {self.source_metric.value, self.source_metric.normalized_value,
                   normalize_metric(self.source_metric).normalized_value}
        if self.source_metric.value_low is not None and self.source_metric.value_high is not None:
            allowed.add((self.source_metric.value_low + self.source_metric.value_high) / 2)
        if self.selected_value not in allowed and self.override is None:
            raise ValueError("Selected value must be source value, normalized value, or range midpoint unless overridden")
        return self


def candidate(metric: FinancialMetric, report_version_id: UUID | str, field: ValuationField | str,
              case: CaseType | str, reason: str, *, override: OverrideRecord | None = None,
              selected_value: Decimal | str | int | None = None,
              combination_group: str | None = None) -> ValuationInputCandidate:
    normal = normalize_metric(metric)
    if selected_value is None:
        selected_value = normal.normalized_value if normal.normalized_value is not None else metric.value
        if selected_value is None and metric.value_low is not None and metric.value_high is not None:
            selected_value = (metric.value_low + metric.value_high) / 2
    return ValuationInputCandidate(
        metric_id=metric.metric_id, report_version_id=UUID(str(report_version_id)),
        valuation_field=field, selected_value=selected_value, normalized_unit=normal.normalized_unit or normal.unit,
        source_metric=metric, assumption_type=metric.assumption_type,
        source_date=metric.source_date, period_start=metric.period_start, period_end=metric.period_end,
        operation_segment=metric.operation_segment, confidence=metric.confidence,
        selection_reason=reason, combination_group=combination_group, case_type=case, override=override,
    )


def issue(code: str, severity: Severity, message: str, metric: FinancialMetric,
          related: FinancialMetric | None = None) -> ValidationResult:
    return ValidationResult(code=code, severity=severity, message=message,
                            metric_id=metric.metric_id,
                            related_metric_id=related.metric_id if related else None)


def _date(metric: FinancialMetric):
    return metric.period_end or metric.source_date


def _comparable(a: FinancialMetric, b: FinancialMetric) -> bool:
    # Definitions, stage, operation and basis must all match. A newer but different
    # production stage or cost definition is context, not a replacement.
    return (a.name, a.commodity, a.operation_segment, a.production_stage,
            a.share_count_type, a.unit, a.assumption_type) == (b.name, b.commodity, b.operation_segment,
            b.production_stage, b.share_count_type, b.unit, b.assumption_type)


def freshness(selected: FinancialMetric, metrics: list[FinancialMetric], *, historical: bool = False) -> dict:
    dated = [m for m in metrics if m.metric_id != selected.metric_id and _comparable(selected, m)
             and m.source_type == SourceType.COMPANY_DISCLOSURE and _date(m)]
    current_date = _date(selected)
    latest = max(dated, key=_date) if dated else None
    if historical:
        status = FreshnessStatus.HISTORICAL_REFERENCE
    elif not current_date:
        status = FreshnessStatus.UNKNOWN
    elif latest and _date(latest) > current_date:
        status = FreshnessStatus.SUPERSEDED
    elif selected.source_type == SourceType.COMPANY_DISCLOSURE or latest:
        status = FreshnessStatus.CURRENT
    else:
        status = FreshnessStatus.INCOMPARABLE
    newer_date = _date(latest) if latest else None
    return {"selected_metric_date": current_date.isoformat() if current_date else None,
            "latest_comparable_metric_date": newer_date.isoformat() if newer_date else None,
            "age_difference_days": (newer_date - current_date).days if newer_date and current_date and newer_date > current_date else 0 if current_date else None,
            "freshness_status": status.value,
            "comparable_metric_id": str(latest.metric_id) if latest else None}


COST_FIELDS = {ValuationField.PRODUCTION_COST, ValuationField.CASH_COST,
               ValuationField.AISC, ValuationField.OPERATING_COST}
SHARE_FIELDS = {ValuationField.CURRENT_ISSUED_SHARES, ValuationField.FORECAST_DILUTED_SHARES,
                ValuationField.WEIGHTED_AVERAGE_BASIC_SHARES, ValuationField.WEIGHTED_AVERAGE_DILUTED_SHARES}
SHARE_BASIS = {
    ValuationField.CURRENT_ISSUED_SHARES: ShareCountType.ISSUED_SHARES_CURRENT,
    ValuationField.FORECAST_DILUTED_SHARES: ShareCountType.FORECAST_DILUTED_SHARES,
    ValuationField.WEIGHTED_AVERAGE_BASIC_SHARES: ShareCountType.WEIGHTED_AVERAGE_BASIC_SHARES,
    ValuationField.WEIGHTED_AVERAGE_DILUTED_SHARES: ShareCountType.WEIGHTED_AVERAGE_DILUTED_SHARES,
}


def validate_candidate(c: ValuationInputCandidate, metrics: list[FinancialMetric], *,
                       guidance_warn: Decimal = Decimal("1.25"), guidance_error: Decimal = Decimal("1.50"),
                       margin_history: Decimal | None = None, margin_guidance: Decimal | None = None,
                       peer_margin_range: tuple[Decimal, Decimal] | None = None) -> tuple[ValuationInputCandidate, dict]:
    m, f = c.source_metric, c.valuation_field
    results: list[ValidationResult] = []
    add = lambda code, severity, msg, related=None: results.append(issue(code, severity, msg, m, related))
    base = c.case_type == CaseType.BASE
    historical = c.case_type == CaseType.INFORMATIONAL and m.assumption_type == AssumptionType.HISTORICAL_ACTUAL
    fresh = freshness(m, metrics, historical=historical)

    if m.assumption_type == AssumptionType.UNRESOLVED:
        add("UNRESOLVED_ASSUMPTION", Severity.ERROR, "Provenance or classification is unresolved.")
    if base and m.assumption_type == AssumptionType.PREVIOUS_REPORT:
        add("PREVIOUS_REPORT_BASE", Severity.ERROR, "Previous-report value needs current revalidation.")
    if c.selected_value is None:
        add("MISSING_VALUE", Severity.ERROR, "No selected numeric value is established.")
    if m.unit is None or c.normalized_unit is None:
        add("MISSING_UNIT", Severity.ERROR, "Unit is unresolved.")
        if m.raw_unit is not None:
            add("UNRESOLVED_CONVERSION", Severity.BLOCKING, "Raw unit could not be normalized to a controlled unit.")
    if f == ValuationField.COMMODITY_PRICE:
        if not m.currency or m.unit is None:
            add("PRICE_CURRENCY_UNIT", Severity.ERROR, "Commodity price needs explicit currency and unit.")
        if m.unit and m.unit not in {Unit.USD_PER_LB, Unit.USD_PER_TONNE}:
            add("PRICE_UNIT_INCOMPATIBLE", Severity.BLOCKING, "Commodity price unit is incompatible with metal pricing.")
        if base and m.price_type == CommodityPriceType.CURRENT_SPOT and (m.intended_use or "").lower() in {"long_term", "perpetual", "terminal"}:
            add("SPOT_PERPETUAL", Severity.WARNING, "Spot price used as a long-term valuation assumption.")
        if base and (m.price_type is None or m.price_type == CommodityPriceType.CURRENT_SPOT) and m.period_start is None and m.period_end is None:
            add("SPOT_HORIZON_UNKNOWN", Severity.WARNING, "Market price has no stated averaging or forecast horizon.")
    if f in {ValuationField.PRODUCTION_VOLUME, ValuationField.SALEABLE_VOLUME, ValuationField.REVENUE}:
        if m.production_stage is None and f != ValuationField.REVENUE:
            add("PRODUCTION_STAGE_UNKNOWN", Severity.ERROR, "Production stage is unknown.")
        if f == ValuationField.SALEABLE_VOLUME and m.production_stage not in {ProductionStage.SALEABLE_PRODUCT, ProductionStage.SALES_VOLUME}:
            add("NOT_SALEABLE", Severity.BLOCKING, "Contained metal, ROM and capacity cannot automatically become saleable volume.")
        if f == ValuationField.REVENUE and m.production_stage in {ProductionStage.ROM_FEED, ProductionStage.CAPACITY,
                                                                  ProductionStage.CONTAINED_METAL, ProductionStage.ORE_MINED,
                                                                  ProductionStage.PROCESSED_ORE, ProductionStage.CONCENTRATE}:
            add("UPSTREAM_REVENUE", Severity.BLOCKING, "Upstream volume cannot directly be multiplied by metal price for revenue.")
        if f == ValuationField.PRODUCTION_VOLUME and m.production_stage == ProductionStage.CAPACITY:
            add("CAPACITY_AS_PRODUCTION", Severity.BLOCKING, "Capacity requires a utilisation and production bridge.")
        if f == ValuationField.PRODUCTION_VOLUME and m.production_stage == ProductionStage.ROM_FEED and m.commodity:
            add("ROM_AS_METAL", Severity.BLOCKING, "ROM feed is not contained copper production.")
        if m.production_stage == ProductionStage.CONTAINED_METAL and (m.intended_use or "") == "saleable_product":
            add("CONTAINED_AS_SALEABLE", Severity.BLOCKING, "Contained metal needs recovery and payability bridge.")
        if m.production_stage in {ProductionStage.ROM_FEED, ProductionStage.CONTAINED_METAL} and m.intended_use == "direct_revenue":
            add("UPSTREAM_REVENUE", Severity.BLOCKING, "Upstream output is not direct saleable revenue.")
    if f == ValuationField.MINING_THROUGHPUT:
        if m.production_stage not in {ProductionStage.ROM_FEED, ProductionStage.ORE_MINED, ProductionStage.PROCESSED_ORE}:
            add("THROUGHPUT_STAGE_MISMATCH", Severity.BLOCKING, "Mining throughput needs an ore or ROM stage.")
        if m.assumption_type == AssumptionType.MANAGEMENT_TARGET:
            add("TARGET_THROUGHPUT", Severity.WARNING, "Management throughput target is a scenario assumption, not copper production.")
    if f in COST_FIELDS:
        if m.cost_definition is None:
            add("COST_DEFINITION_UNKNOWN", Severity.ERROR, "Source has not established whether cost means production cost, cash cost, AISC or operating cost.")
        elif m.cost_definition.value != f.value:
            add("COST_DEFINITION_MISMATCH", Severity.BLOCKING, "Cost definition cannot be silently relabeled.")
        if not m.source or not m.period_start or not m.period_end:
            add("COST_SOURCE_PERIOD", Severity.ERROR, "Cost needs source and historical or forecast period.")
        if base and fresh["freshness_status"] == FreshnessStatus.SUPERSEDED.value:
            add("STALE_COST", Severity.ERROR, "Older cost predates a newer comparable company disclosure.")
    if f in SHARE_FIELDS:
        if m.share_count_type != SHARE_BASIS[f]:
            add("SHARE_BASIS_MISMATCH", Severity.BLOCKING, "Share-count basis differs from selected valuation field.")
        if base and f in {ValuationField.WEIGHTED_AVERAGE_BASIC_SHARES, ValuationField.WEIGHTED_AVERAGE_DILUTED_SHARES}:
            add("HISTORICAL_SHARES_FORWARD", Severity.ERROR, "Historical EPS/HEPS denominator is not a forward target denominator.")
        if base and f == ValuationField.CURRENT_ISSUED_SHARES:
            if any(x.share_count_type == ShareCountType.FORECAST_DILUTED_SHARES for x in metrics):
                add("FORECAST_DILUTION_AVAILABLE", Severity.ERROR, "Forecast diluted shares are available and should be preferred.")
            else:
                add("DILUTION_UNMODELED", Severity.WARNING, "Current issued shares used without a forecast diluted share count.")
        if base and fresh["freshness_status"] == FreshnessStatus.SUPERSEDED.value:
            add("STALE_FORWARD_SHARES", Severity.ERROR, "Newer comparable issued shares exist.")
        if base and m.share_count_type is None:
            add("SHARE_BASIS_UNKNOWN", Severity.ERROR, "Share-count basis is unresolved.")
    if base and f == ValuationField.WACC and not (m.notes and "derived" in m.notes.lower() and m.source):
        add("WACC_UNSUPPORTED", Severity.ERROR, "WACC needs documented components or explicit override.")
    if base and f in {ValuationField.EXIT_MULTIPLE, ValuationField.TERMINAL_GROWTH, ValuationField.PRODUCTION_GROWTH} and not m.source:
        add("TERMINAL_ASSUMPTION_UNSUPPORTED", Severity.ERROR, "Growth or exit assumption has no supported basis.")
    hierarchy = {AssumptionType.FORMAL_GUIDANCE: 4, AssumptionType.HISTORICAL_ACTUAL: 3,
                 AssumptionType.EXTERNAL_CONSENSUS: 2, AssumptionType.MODEL_ASSUMPTION: 1}
    if base and m.assumption_type in hierarchy:
        better = [x for x in metrics if x.metric_id != m.metric_id and x.name == m.name
                  and x.production_stage == m.production_stage and x.commodity == m.commodity
                  and x.operation_segment == m.operation_segment and x.unit == m.unit
                  and hierarchy.get(x.assumption_type, 0) > hierarchy[m.assumption_type]]
        if better:
            add("GUIDANCE_PREFERRED" if any(x.assumption_type == AssumptionType.FORMAL_GUIDANCE for x in better)
                else "HIGHER_EVIDENCE_AVAILABLE", Severity.WARNING,
                "A comparable higher-ranked source is available for base-case selection.", better[0])
    if base and m.assumption_type == AssumptionType.MANAGEMENT_TARGET:
        guidance = [x for x in metrics if x.assumption_type == AssumptionType.FORMAL_GUIDANCE
                    and x.production_stage == m.production_stage and x.commodity == m.commodity
                    and x.operation_segment == m.operation_segment and x.unit == m.unit]
        if guidance:
            add("TARGET_VS_GUIDANCE", Severity.ERROR, "Management target cannot replace formal guidance in base case.", guidance[-1])
        else:
            add("MANAGEMENT_TARGET_BASE", Severity.WARNING, "Management target requires explicit base-case justification.")
    if base and f in {ValuationField.PRODUCTION_VOLUME, ValuationField.SALEABLE_VOLUME} and c.selected_value is not None:
        comparators = [x for x in metrics if x.metric_id != m.metric_id and x.production_stage == m.production_stage
                       and x.commodity == m.commodity and x.operation_segment == m.operation_segment
                       and x.unit == m.unit and x.assumption_type in {AssumptionType.FORMAL_GUIDANCE, AssumptionType.HISTORICAL_ACTUAL}]
        bounds = [x.value_high or x.value for x in comparators if x.value_high is not None or x.value is not None]
        if bounds:
            reference = max(bounds)
            if reference > 0 and c.selected_value > reference * guidance_error:
                add("PRODUCTION_GROWTH_HIGH", Severity.ERROR, "Base production exceeds comparable guidance/history by >50%.")
            elif reference > 0 and c.selected_value > reference * guidance_warn:
                add("PRODUCTION_GROWTH_ELEVATED", Severity.WARNING, "Base production exceeds comparable guidance/history by >25%.")
    if f == ValuationField.OPERATING_MARGIN and c.selected_value is not None:
        # Margin comparisons require explicitly supplied data. No peer range is invented.
        observed = c.selected_value
        references = [v for v in (margin_history, margin_guidance, peer_margin_range[1] if peer_margin_range else None) if v is not None]
        if observed is not None and references and observed > max(references) * Decimal("1.25"):
            add("MARGIN_OPTIMISM", Severity.WARNING, "Forecast margin materially exceeds supplied history/guidance/peer range.")
    if base and fresh["freshness_status"] == FreshnessStatus.SUPERSEDED.value and f not in COST_FIELDS | SHARE_FIELDS:
        add("STALE_COMPARABLE", Severity.ERROR, "A newer like-for-like company disclosure exists.")

    if c.override:
        if c.override.case_type != c.case_type:
            add("OVERRIDE_CASE_MISMATCH", Severity.ERROR, "Override case must match candidate case.")
        expected = [x.model_dump(mode="json") for x in results if x.severity == Severity.ERROR]
        stored = [x.model_dump(mode="json") for x in c.override.original_validation_result if x.severity == Severity.ERROR]
        if not expected or stored != expected:
            add("OVERRIDE_ORIGINAL_MISMATCH", Severity.ERROR, "Override must retain the actual original ERROR findings.")
    severities = {x.severity for x in results}
    if Severity.BLOCKING in severities:
        eligibility = Eligibility.INELIGIBLE
    elif m.assumption_type == AssumptionType.UNRESOLVED:
        eligibility = Eligibility.UNRESOLVED
    elif Severity.ERROR in severities:
        override_valid = c.override and c.override.case_type == c.case_type and not any(x.code == "OVERRIDE_ORIGINAL_MISMATCH" for x in results)
        eligibility = Eligibility.ELIGIBLE_WITH_WARNING if override_valid else Eligibility.INELIGIBLE
    elif c.selected_value is None:
        eligibility = Eligibility.UNRESOLVED
    elif results:
        eligibility = Eligibility.ELIGIBLE_WITH_WARNING
    else:
        eligibility = Eligibility.ELIGIBLE
    return c.model_copy(update={"validation_status": eligibility, "warnings": results}), fresh


def check_double_counting(candidates: list[ValuationInputCandidate]) -> list[ValidationResult]:
    findings = []
    for i, a in enumerate(candidates):
        if a.valuation_field not in {ValuationField.PRODUCTION_VOLUME, ValuationField.SALEABLE_VOLUME}:
            continue
        for b in candidates[i + 1:]:
            if b.case_type != a.case_type or b.source_metric.commodity != a.source_metric.commodity:
                continue
            stages = {a.source_metric.production_stage, b.source_metric.production_stage}
            if (a.source_metric.operation_segment == b.source_metric.operation_segment
                    and stages & {ProductionStage.ROM_FEED, ProductionStage.CONTAINED_METAL,
                                  ProductionStage.REFINED_PRODUCT, ProductionStage.SALEABLE_PRODUCT}
                    and len(stages) > 1 and a.combination_group
                    and a.combination_group == b.combination_group):
                findings.append(issue("UPSTREAM_DOWNSTREAM_DOUBLE_COUNT", Severity.BLOCKING,
                                      "Feed and downstream output from the same operation cannot be added as independent production.",
                                      a.source_metric, b.source_metric))
    return findings


def reconcile_target(target_assumption: dict | None, *, registered_python_calculation: bool = False) -> TargetDerivation:
    if registered_python_calculation and target_assumption and target_assumption.get("python_calculated"):
        return TargetDerivation.REPRODUCIBLE_PYTHON
    if not target_assumption:
        return TargetDerivation.UNRESOLVED
    if target_assumption.get("classification") == "previous_report" or target_assumption.get("source") == "previous_report":
        return TargetDerivation.CARRIED_FORWARD
    if target_assumption.get("verified_reconciliation") and target_assumption.get("calculation") and target_assumption.get("supporting_inputs"):
        return TargetDerivation.REPRODUCIBLE_FROM_REPORT
    if target_assumption.get("calculation") or target_assumption.get("supporting_inputs"):
        return TargetDerivation.PARTIAL_RECONCILIATION
    if target_assumption.get("classification") == "model_assumption":
        return TargetDerivation.UNSUPPORTED
    return TargetDerivation.UNRESOLVED


def run_preflight(ticker: str, report_version_id: UUID | str, candidates: list[ValuationInputCandidate],
                  available_metrics: list[FinancialMetric], *, current_price: Decimal | str | None = None,
                  target_price: Decimal | str | None = None, target_assumption: dict | None = None,
                  required_fields: set[ValuationField] | None = None) -> dict:
    if any(c.report_version_id != UUID(str(report_version_id)) for c in candidates):
        raise ValueError("All candidates must belong to the report version under review")
    checked = [validate_candidate(c, available_metrics) for c in candidates]
    decisions = [c for c, _ in checked]
    double_counts = check_double_counting(decisions)
    blocked_ids = {x.metric_id for x in double_counts} | {x.related_metric_id for x in double_counts}
    decisions = [c.model_copy(update={"validation_status": Eligibility.INELIGIBLE,
                                      "warnings": c.warnings + [x for x in double_counts if c.metric_id in {x.metric_id, x.related_metric_id}]})
                 if c.metric_id in blocked_ids else c for c in decisions]
    rows = [{"candidate": c.model_dump(mode="json"), "freshness": fresh} for c, (_, fresh) in zip(decisions, checked)]
    base = [row for row in rows if row["candidate"]["case_type"] == "base"]
    eligible = [row for row in base if row["candidate"]["validation_status"] in {"eligible", "eligible_with_warning"}]
    ineligible = [row for row in base if row not in eligible]
    missing = sorted(f.value for f in (required_fields or set()) - {ValuationField(row["candidate"]["valuation_field"]) for row in eligible})
    derivation = reconcile_target(target_assumption)
    warnings = [x.model_dump(mode="json") for c in decisions for x in c.warnings if x.severity in {Severity.INFO, Severity.WARNING, Severity.ERROR}]
    blocking = [x.model_dump(mode="json") for c in decisions for x in c.warnings if x.severity == Severity.BLOCKING]
    review = None
    if current_price is not None and target_price is not None and Decimal(str(current_price)) > 0:
        upside = Decimal(str(target_price)) / Decimal(str(current_price)) - 1
        if upside > 1:
            checks = {"target_provenance": derivation.value,
                      "share_count": [x for x in rows if "shares" in x["candidate"]["valuation_field"]],
                      "production_classification": [x for x in rows if x["candidate"]["valuation_field"] in {"production_volume", "saleable_volume"}],
                      "stale_cost_metrics": [x for x in rows if "cost" in x["candidate"]["valuation_field"] or x["candidate"]["valuation_field"] == "aisc"],
                      "commodity_price_horizon": [x for x in rows if x["candidate"]["valuation_field"] == "commodity_price"],
                      "wacc": [x for x in rows if x["candidate"]["valuation_field"] == "wacc"],
                      "terminal_assumptions": [x for x in rows if x["candidate"]["valuation_field"] in {"terminal_growth", "exit_multiple"}],
                      "unresolved_units": [x for x in rows if x["candidate"]["normalized_unit"] is None],
                      "prior_report_carry_forward": derivation == TargetDerivation.CARRIED_FORWARD,
                      "target_reconciliation": derivation.value}
            review = {"implied_upside_pct": str(upside * 100), "severity": "ERROR" if upside > 2 else "WARNING",
                      "audit_only": True, "requires_reconciliation": upside > 2, "checks": checks}
            warnings.append({"code": "HIGH_UPSIDE_REVIEW", "severity": review["severity"],
                             "message": "Enhanced evidence review required; legacy target is not automatically rejected."})
    return {"ticker": ticker, "report_version_id": str(report_version_id), "case": "base", 
            "status": "FAIL" if not base or ineligible or missing or blocking else "PASS",
            "eligible_inputs": eligible, "ineligible_inputs": ineligible,
            "all_candidates": rows, "missing_required_fields": missing,
            "warnings": warnings, "blocking_errors": blocking,
            "target_reconciliation": derivation.value, "enhanced_target_review": review,
            "reasons": (["no base-case candidates"] if not base else []) + [f"{row['candidate']['valuation_field']}: {row['candidate']['validation_status']}" for row in ineligible]
                       + [f"missing required field: {f}" for f in missing]}


def render_preflight(result: dict) -> str:
    lines = ["VALUATION PREFLIGHT", f"Ticker: {result['ticker']}", f"Case: {result['case'].title()}"]
    for row in result["all_candidates"]:
        c = row["candidate"]
        m = c["source_metric"]
        lines.append(f"{c['valuation_field']}: {c['selected_value']} {c['normalized_unit'] or m['raw_unit'] or ''} | "
                     f"{m['operation_segment'] or 'group'} | {c['assumption_type']} | {c['validation_status']}")
        for w in c["warnings"]:
            lines.append(f"  {w['severity']} {w['code']}: {w['message']}")
    lines.extend([f"Target reconciliation: {result['target_reconciliation']}",
                  f"Overall preflight: {result['status']}"])
    lines.extend(f"Reason: {x}" for x in result["reasons"])
    return "\n".join(lines)


def propose_report_candidates(metrics: list[FinancialMetric], report_version_id: UUID | str) -> tuple[list[ValuationInputCandidate], list[str]]:
    """Conservative proposal from a report audit, never a claim of engine selection."""
    mapping = {
        "commodity_price": ValuationField.COMMODITY_PRICE,
        "production_cost_per_tonne": ValuationField.PRODUCTION_COST,
        "cash_cost_per_tonne": ValuationField.CASH_COST,
        "aisc_per_tonne": ValuationField.AISC,
        "operating_cost_per_tonne": ValuationField.OPERATING_COST,
        "tax": ValuationField.TAX_RATE,
        "wacc": ValuationField.WACC,
        "terminal_growth": ValuationField.TERMINAL_GROWTH,
        "growth": ValuationField.PRODUCTION_GROWTH,
        "exit_multiple": ValuationField.EXIT_MULTIPLE,
        "issued_shares_current": ValuationField.CURRENT_ISSUED_SHARES,
        "weighted_average_basic_shares": ValuationField.WEIGHTED_AVERAGE_BASIC_SHARES,
        "weighted_average_diluted_shares": ValuationField.WEIGHTED_AVERAGE_DILUTED_SHARES,
        "forecast_diluted_shares": ValuationField.FORECAST_DILUTED_SHARES,
        "share_count_unresolved": ValuationField.CURRENT_ISSUED_SHARES,
    }
    proposals = []
    unmapped = []
    for metric in metrics:
        if metric.name == "target_price":
            continue
        if metric.name.startswith("production_") and "cost" not in metric.name:
            field = ValuationField.PRODUCTION_VOLUME
        else:
            field = mapping.get(metric.name)
        if field is None:
            unmapped.append(metric.name)
            continue
        # Historical facts without a stated valuation use are contextual. All
        # other reported assumptions are proposed as base inputs for Python review.
        case = CaseType.INFORMATIONAL if metric.assumption_type == AssumptionType.HISTORICAL_ACTUAL and not metric.intended_use else CaseType.BASE
        if metric.intended_use in {x.value for x in CaseType}:
            case = CaseType(metric.intended_use)
        proposals.append(candidate(metric, report_version_id, field, case,
                                   "Conservative proposal from report assumption audit; Python eligibility governs use"))
    return proposals, unmapped
