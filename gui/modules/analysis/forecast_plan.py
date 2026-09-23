"""Versioned, analyst-controlled inputs around the Phase 4 valuation engine."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

from .valuation.engine import ENGINE_VERSION, ValuationPlan, run_valuation
from .valuation.models import ValuationResult, ValuationStatus
from .valuation.production import ProductionBridge, bridge_production, DevelopmentPeriod, development_production
from .valuation.wacc import WaccInputs, calculate_wacc


class Origin(str, Enum):
    HISTORICAL_ACTUAL = "historical_actual"
    FORMAL_GUIDANCE = "formal_guidance"
    MANAGEMENT_TARGET = "management_target"
    EXTERNAL_CONSENSUS = "external_consensus"
    DETERMINISTIC_CALCULATION = "deterministic_calculation"
    ANALYST_ASSUMPTION = "analyst_assumption"
    SCENARIO_ASSUMPTION = "scenario_assumption"
    GEMINI_SUGGESTION = "gemini_suggestion"


FORECAST_FIELD_EXTENSIONS = frozenset({
    "rom", "ownership", "project_start_date", "wacc_override",
    "latest_reported_cost", "inflation", "operational_efficiency",
    "scale_factor", "reagent_energy_factor",
    "store_count", "new_store_openings", "like_for_like_growth",
    "inventory_days", "online_sales", "capex_per_store",
})
FORECAST_CURRENCIES = ("ZAR", "USD", "GBP", "EUR", "HKD")
FORECAST_CASES = ("base", "bear", "bull", "informational")


def allowed_forecast_fields() -> tuple[str, ...]:
    """Fields accepted by plans: engine fields plus explicit schedule helpers."""
    from .valuation_preflight import ValuationField
    engine_fields = {item.value for item in ValuationField if item != ValuationField.TARGET_PRICE}
    return tuple(sorted(engine_fields | FORECAST_FIELD_EXTENSIONS))


def forecast_selector_values() -> dict[str, tuple[str, ...]]:
    """Single source of truth for controlled Forecast-tab selectors."""
    from .financial_metrics import Unit, CommodityPriceType, CostDefinition
    return {
        "case": FORECAST_CASES,
        "field": allowed_forecast_fields(),
        "unit": tuple(item.value for item in Unit),
        "currency": FORECAST_CURRENCIES,
        "price_type": tuple(item.value for item in CommodityPriceType),
        "cost_definition": tuple(item.value for item in CostDefinition),
    }


class ApprovalState(str, Enum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class PlanStatus(str, Enum):
    DRAFT = "draft"
    REVIEW_REQUIRED = "review_required"
    APPROVED = "approved"
    SUPERSEDED = "superseded"


class ForecastPeriod(BaseModel):
    label: str
    start: date
    end: date

    @model_validator(mode="after")
    def valid(self):
        if self.start > self.end or (self.end - self.start).days > 366:
            raise ValueError("Forecast period must be an explicit financial year")
        return self


class ForecastAssumption(BaseModel):
    assumption_id: UUID = Field(default_factory=uuid4)
    field: str
    value: Decimal | None = None
    unit: str | None = None
    currency: str | None = None
    commodity: str | None = None
    period_label: str | None = None
    operation_segment: str | None = None
    case: str = "base"
    origin: Origin
    rationale: str = ""
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    supporting_metric_ids: list[UUID] = Field(default_factory=list)
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    approval_state: ApprovalState = ApprovalState.PROPOSED
    accepted_from_suggestion_id: UUID | None = None
    source_date: date | None = None
    source_id: str | None = None
    effective_date: date | None = None
    price_type: str | None = None
    cost_definition: str | None = None
    operating_currency: str | None = None
    fx_pair: str | None = None

    @model_validator(mode="after")
    def valid(self):
        if self.case not in FORECAST_CASES:
            raise ValueError("Unknown forecast case")
        if self.field not in allowed_forecast_fields():
            raise ValueError(f"Unknown forecast field: {self.field}")
        if self.unit is not None:
            from .financial_metrics import Unit
            if self.unit not in {item.value for item in Unit}:
                raise ValueError(f"Unknown controlled unit: {self.unit}")
        if self.currency is not None and self.currency not in FORECAST_CURRENCIES:
            raise ValueError(f"Unknown controlled currency: {self.currency}")
        if self.field in {"retail_sales_growth", "revenue_growth"}:
            if not self.period_label:
                raise ValueError(f"{self.field} requires a fiscal period")
            if self.unit not in (None, "percentage"):
                raise ValueError(f"{self.field} requires the percentage unit")
        if self.origin == Origin.GEMINI_SUGGESTION and self.approval_state == ApprovalState.ACCEPTED:
            raise ValueError("Gemini suggestions cannot themselves be accepted as valuation inputs")
        if self.origin in {Origin.ANALYST_ASSUMPTION, Origin.SCENARIO_ASSUMPTION} and self.approval_state == ApprovalState.ACCEPTED:
            if (self.value is None and not (self.field == "project_start_date" and self.effective_date)) or not self.unit or not self.rationale.strip() or not self.created_by.strip():
                raise ValueError("Accepted assumptions require value, unit, rationale and author")
            if self.field == "commodity_price" and not (self.period_label and self.commodity and self.currency and self.price_type):
                raise ValueError("Commodity forecast needs fiscal period, commodity, currency and price type")
            if self.field == "fx_rate" and not (self.period_label and self.fx_pair):
                raise ValueError("FX forecast needs fiscal period and explicit pair")
        return self


class ForecastPlan(BaseModel):
    forecast_plan_id: UUID = Field(default_factory=uuid4)
    ticker: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str
    source_report_version_id: UUID
    valuation_engine_version: str = ENGINE_VERSION
    plan_version: int = Field(default=1, ge=1)
    status: PlanStatus = PlanStatus.DRAFT
    approval_status: str = "unapproved"
    approved_by: str | None = None
    approved_at: datetime | None = None
    horizon: list[ForecastPeriod] = Field(default_factory=list)
    valuation_currency: str = "ZAR"
    operating_currency: str | None = None
    assumptions: list[ForecastAssumption] = Field(default_factory=list)
    scenarios: dict[str, str] = Field(default_factory=lambda: {"base": "Analyst base case"})
    engine_plan: ValuationPlan | None = None
    notes: str = ""
    previous_plan_id: UUID | None = None
    legacy_target: Decimal | None = None

    @model_validator(mode="after")
    def valid(self):
        if self.engine_plan and (self.engine_plan.ticker != self.ticker or
                                 self.engine_plan.report_version_id != self.source_report_version_id):
            raise ValueError("Engine plan must match ticker and source report")
        if self.status == PlanStatus.APPROVED and (self.approval_status != "approved" or not self.approved_by or not self.approved_at):
            raise ValueError("Approved plan requires recorded reviewer and time")
        if self.horizon != sorted(self.horizon, key=lambda p: p.start):
            raise ValueError("Forecast periods must be ordered")
        if any(left.end >= right.start for left,right in zip(self.horizon,self.horizon[1:])):
            raise ValueError("Forecast financial periods must not overlap")
        if any(a.period_label and a.period_label not in {p.label for p in self.horizon} for a in self.assumptions):
            raise ValueError("Assumption refers to an unknown financial period")
        return self


def horizon_for_assumption(
    plan: ForecastPlan,
    period_label: str | None,
    *,
    start: date | None = None,
    end: date | None = None,
) -> tuple[list[ForecastPeriod], bool]:
    """Return a horizon containing an assumption's period, creating it when fully specified."""
    label = (period_label or "").strip()
    if not label:
        return list(plan.horizon), False
    existing = next((period for period in plan.horizon if period.label == label), None)
    if existing:
        if start is not None and start != existing.start:
            raise ValueError(f"{label} already exists with start date {existing.start.isoformat()}")
        if end is not None and end != existing.end:
            raise ValueError(f"{label} already exists with end date {existing.end.isoformat()}")
        return list(plan.horizon), False
    if start is None or end is None:
        raise ValueError(
            f"Financial period {label} has not been added. Enter its start and end dates, "
            "or click 'Add financial period' first."
        )
    period = ForecastPeriod(label=label, start=start, end=end)
    return sorted([*plan.horizon, period], key=lambda item: item.start), True


def new_version(plan: ForecastPlan, *, changed_by: str, **changes: Any) -> ForecastPlan:
    """Copy on write: an approved snapshot remains reconstructable."""
    data = plan.model_dump()
    data.update(changes)
    data.update(forecast_plan_id=uuid4(), previous_plan_id=plan.forecast_plan_id,
                plan_version=plan.plan_version + 1, created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc), created_by=changed_by,
                status=PlanStatus.DRAFT, approval_status="unapproved", approved_by=None, approved_at=None)
    return ForecastPlan.model_validate(data)


def accept_suggestion(plan: ForecastPlan, suggestion_id: UUID, *, analyst: str,
                      value: Decimal | None = None, rationale: str | None = None) -> ForecastPlan:
    suggestion = next((a for a in plan.assumptions if a.assumption_id == suggestion_id), None)
    if suggestion is None or suggestion.origin != Origin.GEMINI_SUGGESTION or suggestion.approval_state != ApprovalState.PROPOSED:
        raise ValueError("Unknown Gemini suggestion")
    accepted = suggestion.model_copy(update={"assumption_id": uuid4(), "origin": Origin.ANALYST_ASSUMPTION,
        "approval_state": ApprovalState.ACCEPTED, "accepted_from_suggestion_id": suggestion_id,
        "value": value if value is not None else suggestion.value,
        "rationale": rationale if rationale is not None else suggestion.rationale,
        "created_by": analyst, "created_at": datetime.now(timezone.utc)})
    return new_version(plan, changed_by=analyst, assumptions=[*plan.assumptions, ForecastAssumption.model_validate(accepted.model_dump())])


def approve_plan(plan: ForecastPlan, reviewer: str) -> ForecastPlan:
    if not reviewer.strip():
        raise ValueError("Reviewer required")
    if any(a.origin in {Origin.ANALYST_ASSUMPTION, Origin.SCENARIO_ASSUMPTION}
           and a.approval_state == ApprovalState.PROPOSED for a in plan.assumptions):
        raise ValueError("Review proposed assumptions before approving")
    approved = new_version(plan, changed_by=reviewer)
    return approved.model_copy(update={"status": PlanStatus.APPROVED, "approval_status": "approved",
                                   "approved_by": reviewer, "approved_at": datetime.now(timezone.utc),
                                   "updated_at": datetime.now(timezone.utc)})


def eligible_assumptions(plan: ForecastPlan) -> list[ForecastAssumption]:
    return [a for a in plan.assumptions if a.origin != Origin.GEMINI_SUGGESTION and
            (a.origin not in {Origin.ANALYST_ASSUMPTION, Origin.SCENARIO_ASSUMPTION} or
             a.approval_state == ApprovalState.ACCEPTED)]


def scenario_differences(plan: ForecastPlan) -> list[dict[str, str]]:
    base = {(a.field, a.period_label, a.operation_segment): a for a in eligible_assumptions(plan) if a.case == "base"}
    out = []
    for a in eligible_assumptions(plan):
        if a.case not in {"bear", "bull"}:
            continue
        prior = base.get((a.field, a.period_label, a.operation_segment))
        out.append({"case": a.case, "field": a.field, "period": a.period_label or "",
                    "operation": a.operation_segment or "", "base": str(prior.value) if prior else "missing",
                    "scenario": str(a.value), "assumption_id": str(a.assumption_id)})
    return out


def forecast_operating_schedule(plan: ForecastPlan, operation: str, case: str = "base") -> list[dict]:
    """Derive production only from explicit accepted period inputs; never fill gaps."""
    rows = []
    for period in plan.horizon:
        values = {a.field: a for a in eligible_assumptions(plan) if a.period_label == period.label
                  and a.operation_segment == operation and a.case == case}
        def val(key):
            a = values.get(key)
            return a.value if a else None
        def fraction(key):
            a = values.get(key)
            if a is None or a.value is None:
                return None
            return a.value / 100 if a.unit == "percentage" else a.value
        missing = [x for x in ("rom", "grade", "recovery", "processing_conversion", "ownership") if val(x) is None]
        if val("nameplate_capacity") is not None:
            missing = [x for x in ("nameplate_capacity", "utilization", "ramp_up", "project_start_date",
                                  "grade", "recovery", "processing_conversion", "ownership") if x not in values or (x == "project_start_date" and values[x].effective_date is None)]
        primary = values.get("nameplate_capacity") or values.get("rom")
        if primary is not None and not primary.commodity:
            missing.append("commodity")
        if missing:
            rows.append({"period": period.label, "status": "NOT_CALCULABLE", "missing": missing})
            continue
        if val("nameplate_capacity") is not None:
            x = DevelopmentPeriod(period_start=period.start, period_end=period.end,
                start_date=values["project_start_date"].effective_date,
                annual_nameplate_rom_tonnes=val("nameplate_capacity"), utilization=fraction("utilization"),
                ramp_up=fraction("ramp_up"), grade=fraction("grade"), recovery=fraction("recovery"),
                processing_conversion=fraction("processing_conversion"), ownership=fraction("ownership"))
            out = development_production(x)
        else:
            out = bridge_production(ProductionBridge(period_start=period.start, period_end=period.end,
                operation_id=operation, commodity=primary.commodity, rom_tonnes=val("rom"), grade=fraction("grade"),
                recovery=fraction("recovery"), processing_conversion=fraction("processing_conversion"),
                ownership=fraction("ownership")))
        rows.append({"period": period.label, "status": "PASS", **out})
    return rows


def preview_valuation(plan: ForecastPlan, metrics: list, candidates: list) -> ValuationResult:
    if plan.status != PlanStatus.APPROVED:
        raise ValueError("Only approved forecast plans may enter the valuation engine")
    if plan.engine_plan is None:
        raise ValueError("Approved plan has no explicit engine input mapping")
    allowed_ids = {a.assumption_id for a in eligible_assumptions(plan)}
    # Any plan-generated candidate must be linked to an accepted assumption. Source-backed
    # metric candidates retain the Phase 3 validation and need no analyst-assumption link.
    accepted = {a.assumption_id: a for a in eligible_assumptions(plan)}
    from .financial_metrics import AssumptionType
    for c in candidates:
        if c.source_metric.assumption_type == AssumptionType.MODEL_ASSUMPTION:
            sid = c.source_metric.source_id or ""
            if sid.startswith("forecast_assumption:"):
                ident = UUID(sid.split(":", 1)[1])
                a = accepted.get(ident)
                valid = (a is not None and a.value == c.source_metric.value
                         and a.case == c.case_type.value and a.field == c.valuation_field.value)
            elif sid.startswith("retail_forecast:"):
                ident = UUID(sid.split(":", 1)[1])
                a = accepted.get(ident)
                valid = (a is not None and a.field == "revenue_growth"
                         and c.valuation_field.value == "revenue"
                         and a.case == c.case_type.value)
            else:
                raise ValueError("Model input lacks an accepted forecast-assumption link")
            if not valid:
                raise ValueError("Unaccepted or altered forecast assumption in engine candidates")
    result = run_valuation(ticker=plan.ticker, report_version_id=plan.source_report_version_id,
        candidates=candidates, metrics=metrics, plan=plan.engine_plan,
        legacy_gemini_target=plan.legacy_target, legacy_target_derivation="carried_forward")
    result.calculation_inputs["forecast_plan"] = plan.model_dump(mode="json")
    return result


def deterministic_impact(plan: ForecastPlan, changed: ForecastPlan, metrics: list, candidates: list,
                         changed_metrics: list, changed_candidates: list) -> dict:
    before = preview_valuation(plan, metrics, candidates)
    after = preview_valuation(changed, changed_metrics, changed_candidates)
    return {"before_status": before.status.value, "after_status": after.status.value,
            "before_target": before.target_price, "after_target": after.target_price,
            "impact_per_share": (after.target_price - before.target_price)
            if before.target_price is not None and after.target_price is not None else None}




def calculate_plan_wacc(plan: ForecastPlan, case: str = "base") -> dict:
    """Show the component calculation and an explicit override independently."""
    keys = ("risk_free_rate", "equity_risk_premium", "beta", "country_risk_premium",
            "cost_of_debt", "tax_rate", "debt_weight", "equity_weight")
    accepted = {(a.case, a.field): a for a in eligible_assumptions(plan)}
    missing = [key for key in keys if (case, key) not in accepted]
    override = accepted.get((case, "wacc_override"))
    if missing:
        return {"status": "NOT_CALCULABLE", "missing": missing,
                "override": str(override.value) if override else None}
    values = {k: accepted[(case, k)].value for k in keys}
    from .valuation.models import Basis
    calc = calculate_wacc(WaccInputs(**values, currency=plan.valuation_currency,
        basis=Basis.NOMINAL, inflation_basis=f"{plan.valuation_currency}_CPI"))
    return {"status": "PASS", "calculated": calc,
            "override": str(override.value) if override else None,
            "override_reason": override.rationale if override else None}


def price_fx_schedule(plan: ForecastPlan, field: str, case: str = "base") -> list[dict]:
    if field not in {"commodity_price", "fx_rate"}:
        raise ValueError("Only explicit commodity or FX schedules supported")
    return [{"period": p.label, "status": "PASS" if a else "NOT_CALCULABLE",
             "value": str(a.value) if a else None, "unit": a.unit if a else None,
             "currency": a.currency if a else None, "origin": a.origin.value if a else None,
             "price_type": a.price_type if a else None}
            for p in plan.horizon
            for a in [next((x for x in eligible_assumptions(plan) if x.field == field and
                          x.period_label == p.label and x.case == case), None)]]



def reject_suggestion(plan: ForecastPlan, suggestion_id: UUID, analyst: str) -> ForecastPlan:
    if not analyst.strip():
        raise ValueError("Analyst required")
    found = False
    revised = []
    for a in plan.assumptions:
        if a.assumption_id == suggestion_id:
            if a.origin != Origin.GEMINI_SUGGESTION:
                raise ValueError("Only Gemini suggestions can be rejected here")
            a = a.model_copy(update={"approval_state": ApprovalState.REJECTED})
            found = True
        revised.append(a)
    if not found:
        raise ValueError("Unknown suggestion")
    return new_version(plan, changed_by=analyst, assumptions=revised)


def critique_prompt(plan: ForecastPlan, result: ValuationResult) -> str:
    """Advisory prompt only; the response is never parsed as a target."""
    if result.calculation_inputs.get("forecast_plan", {}).get("forecast_plan_id") != str(plan.forecast_plan_id):
        raise ValueError("Critique needs the exact valuation plan snapshot")
    return ("Critique the following analyst-approved plan and Python valuation. "
            "Identify assumptions above guidance, aggressive ramp-up, margin expansion, "
            "commodity-price dependence, terminal-value dependence, cost and capex omissions, "
            "potential double counting, and sensitivity drivers. Your response is advisory only. "
            "Do not replace or calculate the deterministic target.\nPLAN:\n"
            + plan.model_dump_json() + "\nPYTHON RESULT:\n" + result.model_dump_json())


def materialize_assumption(plan: ForecastPlan, assumption_id: UUID):
    """Create a Phase 3 candidate without disguising an analyst view as company evidence."""
    from .financial_metrics import (AssumptionType, SourceType, FinancialMetric, Unit,
        ProductionStage, CostDefinition, CommodityPriceType, ShareCountType)
    from .valuation_preflight import ValuationField, candidate
    a = next((x for x in eligible_assumptions(plan) if x.assumption_id == assumption_id), None)
    if a is None or a.origin not in {Origin.ANALYST_ASSUMPTION, Origin.SCENARIO_ASSUMPTION}:
        raise ValueError("Only accepted analyst or scenario assumptions can be materialized")
    if a.value is None or a.unit is None:
        raise ValueError("Numeric assumption and controlled unit required")
    field = ValuationField(a.field)
    unit = Unit(a.unit)
    period = next((p for p in plan.horizon if p.label == a.period_label), None)
    stage = {"mining_throughput": ProductionStage.ROM_FEED,
             "production_volume": ProductionStage.CONTAINED_METAL,
             "saleable_volume": ProductionStage.SALEABLE_PRODUCT}.get(a.field)
    share_basis = ShareCountType.FORECAST_DILUTED_SHARES if a.field == "forecast_diluted_shares" else None
    metric = FinancialMetric(metric_id=a.assumption_id, ticker=plan.ticker, report_id=plan.source_report_version_id,
        name=share_basis.value if share_basis else (f"production_{stage.value}" if stage else a.field), value=a.value, unit=unit,
        currency=a.currency, period_start=period.start if period else None,
        period_end=period.end if period else None, source_date=a.created_at.date(),
        source=f"Analyst forecast plan {plan.forecast_plan_id}", source_type=SourceType.MODEL,
        assumption_type=AssumptionType.MODEL_ASSUMPTION, notes=a.rationale,
        source_id=f"forecast_assumption:{a.assumption_id}",
        operation_segment=a.operation_segment, commodity=a.commodity, production_stage=stage,
        share_count_type=share_basis, cost_definition=CostDefinition(a.cost_definition) if a.cost_definition else None,
        price_type=CommodityPriceType(a.price_type) if a.price_type else None)
    return metric, candidate(metric,plan.source_report_version_id,field,a.case,
        f"Accepted forecast-plan assumption {a.assumption_id}")



def compile_plan_inputs(plan: ForecastPlan, evidence_metrics: list):
    """Resolve every explicit engine reference from an accepted assumption or source metric."""
    if plan.engine_plan is None:
        raise ValueError("No explicit engine input mapping")
    from .valuation.engine import _refs
    from .valuation_preflight import candidate
    evidence = {m.metric_id: m for m in evidence_metrics}
    accepted = {a.assumption_id: a for a in eligible_assumptions(plan)}
    from .retail_forecast import build_retail_forecasts, materialize_retail_forecast
    retail_records, _ = build_retail_forecasts(plan, evidence_metrics, include_proposed=False)
    derived = {}
    for record in retail_records:
        if record.valuation_eligible:
            metric, derived_candidate = materialize_retail_forecast(record, plan.source_report_version_id)
            derived[metric.metric_id] = (metric, derived_candidate)
    metrics = list(evidence_metrics)
    candidates = []
    seen = set()
    for ref in _refs(plan.engine_plan):
        key = (ref.metric_id, ref.field, ref.case)
        if key in seen:
            continue
        seen.add(key)
        if ref.metric_id in accepted:
            m, c = materialize_assumption(plan, ref.metric_id)
            if c.valuation_field.value != ref.field or c.case_type.value != ref.case:
                raise ValueError("Engine reference differs from accepted assumption field/case")
            metrics.append(m)
        elif ref.metric_id in derived:
            m, c = derived[ref.metric_id]
            if c.valuation_field.value != ref.field or c.case_type.value != ref.case:
                raise ValueError("Engine reference differs from derived retail forecast field/case")
            metrics.append(m)
        elif ref.metric_id in evidence:
            m = evidence[ref.metric_id]
            if m.report_id != plan.source_report_version_id:
                raise ValueError("Evidence metric belongs to a different report")
            c = candidate(m, plan.source_report_version_id, ref.field, ref.case,
                          "Explicit analyst engine-plan reference to source evidence")
        else:
            raise ValueError(f"Unresolved engine reference {ref.metric_id}")
        candidates.append(c)
    return metrics, candidates


def accept_assumption(plan: ForecastPlan, assumption_id: UUID, analyst: str) -> ForecastPlan:
    if not analyst.strip():
        raise ValueError("Analyst required")
    revised = []
    found = False
    for a in plan.assumptions:
        if a.assumption_id == assumption_id:
            if a.origin not in {Origin.ANALYST_ASSUMPTION, Origin.SCENARIO_ASSUMPTION} or a.approval_state != ApprovalState.PROPOSED:
                raise ValueError("Only proposed analyst/scenario assumptions may be accepted")
            a = ForecastAssumption.model_validate({**a.model_dump(), "approval_state": ApprovalState.ACCEPTED})
            found = True
        revised.append(a)
    if not found:
        raise ValueError("Unknown assumption")
    return new_version(plan, changed_by=analyst, assumptions=revised)


def terminal_value_summary(result: ValuationResult, warning_threshold: Decimal = Decimal("0.7")) -> dict:
    method = result.methods.get("DCF")
    if method is None or not method.schedule or method.value is None:
        return {"status": "NOT_CALCULABLE"}
    terminal = method.schedule[-1]
    if "terminal" not in terminal or not method.value:
        return {"status": "NOT_CALCULABLE"}
    share = Decimal(terminal["present_value"]) / method.value
    return {"status": "PASS", "method": terminal["terminal"]["method"],
            "terminal": terminal, "enterprise_value": str(method.value),
            "terminal_share_of_ev": str(share),
            "warning": "Excessive terminal-value dependence" if share >= warning_threshold else None}


def rank_assumption_impacts(base_plan: ForecastPlan, base_metrics: list, base_candidates: list,
                            variants: list[tuple[str, ForecastPlan, list, list]]) -> list[dict]:
    """Revalue explicit approved variants; rank absolute per-share effects in Python."""
    ranked = []
    for label, changed, metrics, candidates in variants:
        impact = deterministic_impact(base_plan, changed, base_metrics, base_candidates, metrics, candidates)
        ranked.append({"assumption": label, **impact})
    return sorted(ranked, key=lambda x: abs(x["impact_per_share"]) if x["impact_per_share"] is not None else Decimal("-1"), reverse=True)


def plan_changes(new: ForecastPlan, old: ForecastPlan | None) -> list[dict]:
    if old is None:
        return [{"field": a.field, "from": None, "to": str(a.value), "case": a.case,
                 "period": a.period_label} for a in new.assumptions]
    prior = {(a.field,a.case,a.period_label,a.operation_segment): a for a in old.assumptions}
    changes = []
    for a in new.assumptions:
        key = (a.field,a.case,a.period_label,a.operation_segment)
        was = prior.get(key)
        if was is None or (was.value,was.approval_state) != (a.value,a.approval_state):
            changes.append({"field": a.field,"case": a.case,"period": a.period_label,
                            "operation": a.operation_segment,"from": str(was.value) if was else None,
                            "to": str(a.value),"approval": a.approval_state.value})
    return changes


def cost_forecast_schedule(plan: ForecastPlan, operation: str, case: str = "base") -> list[dict]:
    """Explicit cost bridge; missing factors stay visible and cost type is preserved."""
    rows = []
    keys = ("latest_reported_cost", "inflation", "operational_efficiency", "scale_factor", "reagent_energy_factor")
    for p in plan.horizon:
        selected = {a.field:a for a in eligible_assumptions(plan) if a.period_label == p.label
                    and a.operation_segment == operation and a.case == case}
        missing = [key for key in keys if key not in selected or selected[key].value is None]
        if missing:
            rows.append({"period": p.label, "status": "NOT_CALCULABLE", "missing": missing})
            continue
        a = selected["latest_reported_cost"]
        if not a.cost_definition:
            rows.append({"period": p.label, "status": "NOT_CALCULABLE",
                         "missing": ["cost_definition"]})
            continue
        if a.cost_definition == "aisc" and not a.supporting_metric_ids:
            rows.append({"period": p.label, "status": "NOT_CALCULABLE",
                         "missing": ["AISC derivation/source"]})
            continue
        def factor(key):
            item=selected[key]
            return item.value/100 if item.unit=="percentage" else item.value
        cost=(a.value*(1+factor("inflation"))*(1-factor("operational_efficiency"))
              *factor("scale_factor")*factor("reagent_energy_factor"))
        rows.append({"period":p.label,"status":"PASS","value":cost,"unit":a.unit,
                     "currency":a.currency,"cost_definition":a.cost_definition,
                     "assumption_ids":[str(selected[k].assumption_id) for k in keys]})
    return rows


def suggestion_prompt(plan: ForecastPlan, evidence_metrics: list) -> str:
    """Optional advisory prompt; returned suggestions are never approved inputs."""
    return ("Review only the supplied dated evidence and suggest possible forecast assumptions. "
            "Identify operation, fiscal period, unit, supporting metric IDs and uncertainty. "
            "Distinguish guidance from management targets. Do not claim suggestions are facts "
            "and do not calculate a target price.\nEVIDENCE:\n"
            + str([m.model_dump(mode="json") for m in evidence_metrics])
            + "\nPLAN CONTEXT:\n" + plan.model_dump_json())


def record_gemini_suggestion(plan: ForecastPlan, suggestion: ForecastAssumption) -> ForecastPlan:
    if suggestion.origin != Origin.GEMINI_SUGGESTION or suggestion.approval_state != ApprovalState.PROPOSED:
        raise ValueError("Only proposed Gemini suggestions can enter the suggestion ledger")
    return new_version(plan, changed_by=suggestion.created_by,
                       assumptions=[*plan.assumptions, suggestion])
