"""Versioned deterministic engine. Plans reference only Phase 3 eligible candidates."""
from __future__ import annotations
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID
from pydantic import BaseModel, Field, model_validator
from ..financial_metrics import AssumptionType, FinancialMetric, CommodityPriceType, ProductionStage, ShareCountType, SourceType, Unit, convert_fx
from ..valuation_preflight import (ValuationInputCandidate, ValuationField,
                                    validate_candidate, run_preflight)
from .cashflow import unlevered_fcf
from .costs import CostSchedule, cost_bridge
from .production import ProductionBridge, DevelopmentPeriod, bridge_production, development_production
from .revenue import commodity_revenue
D = lambda x: Decimal(str(x))
from .dcf import DcfInputs, ForecastYear, calculate_dcf
from .deferred_payments import DeferredPayment, value_payment_scenarios
from .earnings import earnings_bridge
from .implied import implied_checks
from .models import (Basis, InputRef, MethodStatus, TerminalMethod,
                     ValuationMethodResult, ValuationResult, ValuationStatus)
from .reconciliation import recalculate_target, reconcile_equity
from .sotp import SotpComponent, calculate_sotp
from .wacc import WaccInputs, calculate_wacc

ENGINE_VERSION = "1.0"
YEAR_FIELDS = ("revenue", "operating_cost", "corporate_cost", "depreciation",
               "net_finance_cost", "tax_rate", "sustaining_capex", "growth_capex",
               "working_capital", "other_recurring_cash")
WACC_FIELDS = ("risk_free_rate", "equity_risk_premium", "beta", "country_risk_premium",
               "cost_of_debt", "tax_rate", "debt_weight", "equity_weight")
EQUITY_FIELDS = ("non_operating_assets", "receivables", "net_cash", "net_debt",
                 "lease_adjustments", "minorities", "other_equity_adjustments")


class DevelopmentInputSpec(BaseModel):
    start_date: date
    period_start: date
    nameplate_capacity: InputRef
    utilization: InputRef
    ramp_up: InputRef
    grade: InputRef
    recovery: InputRef
    processing_conversion: InputRef
    ownership: InputRef


class OperationalRevenueSpec(BaseModel):
    operation_id: str
    commodity: str
    period_start: date
    production_stage: str
    volume: InputRef | None = None
    grade: InputRef | None = None
    recovery: InputRef | None = None
    processing_conversion: InputRef | None = None
    ownership: InputRef | None = None
    development: DevelopmentInputSpec | None = None
    commodity_price: InputRef
    realization_factor: InputRef
    payability: InputRef
    treatment_charge: InputRef
    fx_rate: InputRef | None = None
    fx_pair: str | None = None


class YearInputSpec(BaseModel):
    period_end: date
    inputs: dict[str, InputRef]
    operational_revenue: OperationalRevenueSpec | None = None
    cost_components: dict[str, InputRef] | None = None


class WaccSpec(BaseModel):
    currency: str
    basis: Basis
    inflation_basis: str
    components: dict[str, InputRef] | None = None
    supported_wacc: InputRef | None = None


class DcfSpec(BaseModel):
    valuation_date: date
    years: list[YearInputSpec]
    cash_flow_currency: str
    cash_flow_basis: Basis
    inflation_basis: str
    wacc: WaccSpec
    terminal_method: TerminalMethod
    terminal_growth: InputRef | None = None
    exit_multiple: InputRef | None = None
    terminal_metric: str | None = None  # EBITDA or EBIT; from final forecast, not Gemini.


class ComponentSpec(BaseModel):
    component_id: str
    name: str
    boundary_id: str
    method: str
    gross_value: InputRef
    ownership: InputRef
    probability: InputRef | None = None
    discount_factor: InputRef | None = None
    currency: str
    valuation_date: date
    value_kind: str = "operating_asset"
    disposed_boundary_id: str | None = None
    risk_basis: str | None = None
    risk_in_discount_rate: bool = False
    fx_rate: InputRef | None = None
    fx_pair: str | None = None


class PaymentSpec(BaseModel):
    payment_id: str
    amount: InputRef
    expected_date: date
    discount_rate: InputRef
    completion_probability: InputRef
    counterparty_factor: InputRef | None = None
    settlement_scenario: str
    currency: str
    asset_boundary_id: str
    ownership: InputRef
    fx_rate: InputRef | None = None
    fx_pair: str | None = None


class SotpSpec(BaseModel):
    components: list[ComponentSpec] = Field(default_factory=list)
    deferred_payments: list[PaymentSpec] = Field(default_factory=list)
    selected_settlement_scenario: str | None = None


class EquitySpec(BaseModel):
    adjustments: dict[str, InputRef]
    shares: InputRef


class CasePlan(BaseModel):
    rationale: str
    primary_method: str
    dcf: DcfSpec | None = None
    sotp: SotpSpec | None = None
    equity: EquitySpec | None = None
    group_dcf_boundaries: set[str] = Field(default_factory=set)
    valuation_fx_rate: InputRef | None = None
    valuation_fx_pair: str | None = None

    @model_validator(mode="after")
    def valid(self):
        if self.primary_method not in {"DCF", "SOTP"}:
            raise ValueError("Primary method must be explicitly DCF or SOTP; no hidden weighting")
        return self


class ValuationPlan(BaseModel):
    ticker: str
    report_version_id: UUID
    valuation_date: date
    currency: str = "ZAR"
    cases: dict[str, CasePlan]
    historical_calibration: dict[str, InputRef] = Field(default_factory=dict)
    market_price: InputRef | None = None
    nav: InputRef | None = None
    production_reference: InputRef | None = None

    @model_validator(mode="after")
    def valid(self):
        if any(name not in {"base", "bear", "bull"} for name in self.cases):
            raise ValueError("Only controlled bear/base/bull cases are supported")
        if self.currency != "ZAR":
            raise ValueError("v1.0 target display currency is ZAR")
        return self


class MissingInput(Exception):
    pass


class IneligibleInput(Exception):
    pass


def _active_refs(case: CasePlan) -> list[InputRef]:
    return (_refs(case.dcf if case.primary_method == "DCF" else case.sotp)
            + _refs(case.equity) + _refs(case.valuation_fx_rate))


def _refs(value: Any) -> list[InputRef]:
    if isinstance(value, InputRef):
        return [value]
    if isinstance(value, BaseModel):
        return [ref for item in vars(value).values() for ref in _refs(item)]
    if isinstance(value, dict):
        return [ref for item in value.values() for ref in _refs(item)]
    if isinstance(value, (list, tuple)):
        return [ref for item in value for ref in _refs(item)]
    return []


class Resolver:
    def __init__(self, candidates: list[ValuationInputCandidate], metrics: list[FinancialMetric], report_id: UUID):
        self.available = {}
        self.decisions = {}
        for item in candidates:
            if item.report_version_id != report_id:
                raise IneligibleInput("Candidate belongs to another report version")
            decided, _ = validate_candidate(item, metrics)
            key = (item.metric_id, item.valuation_field.value, item.case_type.value)
            if key in self.available:
                raise IneligibleInput("Duplicate candidate for the same metric/field/case")
            self.available[key] = item
            self.decisions[key] = decided

    def get(self, ref: InputRef, *, required_case: str | None = None,
            expected_field: str | None = None, fraction: bool = False,
            currency: str | None = None, forecast_period_start: date | None = None) -> Decimal:
        if required_case and ref.case != required_case:
            raise IneligibleInput(f"{ref.field} references {ref.case}, not requested {required_case} case")
        if expected_field and ref.field != expected_field:
            raise IneligibleInput(f"Expected {expected_field}, got {ref.field}")
        key = (ref.metric_id, ref.field, ref.case)
        item = self.available.get(key)
        if item is None:
            raise MissingInput(f"{ref.field}: no version-linked candidate {ref.metric_id}")
        decision = self.decisions[key]
        if decision.validation_status.value not in {"eligible", "eligible_with_warning"}:
            raise IneligibleInput(f"{ref.field}: {decision.validation_status.value}; "
                                  + ", ".join(x.code for x in decision.warnings))
        if item.source_metric.source_type == SourceType.COMPANY_DISCLOSURE and not (
                item.source_metric.evidence_verified and item.source_metric.evidence_quote and item.source_metric.source_id):
            raise IneligibleInput(f"{ref.field}: company disclosure has no verified source excerpt")
        if item.source_metric.source_type in {SourceType.MARKET_DATA, SourceType.EXTERNAL_CONSENSUS} and not (
                item.source_metric.source and item.source_metric.source_date):
            raise IneligibleInput(f"{ref.field}: market/consensus source or date missing")
        if item.source_metric.assumption_type == AssumptionType.MODEL_ASSUMPTION and not (
                (item.source_metric.source and item.source_metric.notes) or item.override):
            raise IneligibleInput(f"{ref.field}: model assumption needs source and rationale or a recorded override")
        if item.selected_value is None:
            raise MissingInput(f"{ref.field}: selected value missing")
        if (forecast_period_start and item.source_metric.assumption_type == AssumptionType.HISTORICAL_ACTUAL
                and item.source_metric.period_end and item.source_metric.period_end < forecast_period_start
                and item.override is None):
            raise IneligibleInput(f"{ref.field}: historical actual cannot silently become a forecast input")
        if currency:
            observed = item.source_metric.currency or (item.source_metric.unit.value if item.source_metric.unit in {Unit.USD, Unit.ZAR} else None)
            if observed != currency or item.source_metric.unit != Unit(currency):
                raise IneligibleInput(f"{ref.field}: expected total-money unit {currency}, got {observed}/{item.source_metric.unit}")
        value = item.selected_value
        if ref.field == "current_share_price" and item.normalized_unit == Unit.ZAR_CENTS:
            value /= 100  # Phase 2 stores this normalization in cents; the engine uses ZAR/share.
        if fraction and item.normalized_unit == Unit.PERCENTAGE:
            value /= 100
        return value

    def metric(self, ref: InputRef) -> FinancialMetric:
        return self.available[(ref.metric_id, ref.field, ref.case)].source_metric


def _operational_revenue(spec: OperationalRevenueSpec, period_end: date,
                         resolver: Resolver, case: str, currency: str) -> tuple[Decimal, dict]:
    if spec.development:
        if spec.volume is not None:
            raise IneligibleInput("Development nameplate and direct volume cannot both be counted")
        d = spec.development
        produced = development_production(DevelopmentPeriod(
            period_start=d.period_start, period_end=period_end, start_date=d.start_date,
            annual_nameplate_rom_tonnes=resolver.get(d.nameplate_capacity, required_case=case, expected_field="nameplate_capacity"),
            utilization=resolver.get(d.utilization, required_case=case, expected_field="utilization", fraction=True),
            ramp_up=resolver.get(d.ramp_up, required_case=case, expected_field="ramp_up", fraction=True),
            grade=resolver.get(d.grade, required_case=case, expected_field="grade", fraction=True),
            recovery=resolver.get(d.recovery, required_case=case, expected_field="recovery", fraction=True),
            processing_conversion=resolver.get(d.processing_conversion, required_case=case,
                                               expected_field="processing_conversion", fraction=True),
            ownership=resolver.get(d.ownership, required_case=case,
                                   expected_field="ownership_percentage", fraction=True)))
        saleable = produced["attributable_saleable_tonnes"]
    else:
        if spec.volume is None:
            raise MissingInput("operational volume")
        volume_metric = resolver.metric(spec.volume)
        if volume_metric.production_stage is None or volume_metric.commodity != spec.commodity:
            raise IneligibleInput("Production stage/commodity is unresolved or mismatched")
        if volume_metric.production_stage.value != spec.production_stage:
            raise IneligibleInput("Operational stage differs from underlying metric")
        expected_field = {"rom_feed": "mining_throughput", "contained_metal": "production_volume",
                          "saleable_product": "saleable_volume"}.get(spec.production_stage)
        if expected_field is None:
            raise IneligibleInput("Operational revenue requires ROM, contained or saleable stage")
        if (volume_metric.unit == Unit.TONNES_ROM_PER_MONTH and
                (volume_metric.period_start is None or volume_metric.period_end is None)):
            raise MissingInput("Monthly ROM target needs explicit forecast timing/ramp; use development plan")
        volume = resolver.get(spec.volume, required_case=case, expected_field=expected_field,
                              forecast_period_start=spec.period_start)
        bridge = ProductionBridge(period_start=spec.period_start, period_end=period_end,
            operation_id=spec.operation_id, commodity=spec.commodity,
            rom_tonnes=volume if spec.production_stage == "rom_feed" else None,
            grade=resolver.get(spec.grade, required_case=case, expected_field="grade", fraction=True) if spec.grade else None,
            contained_tonnes_direct=volume if spec.production_stage == "contained_metal" else None,
            recovery=resolver.get(spec.recovery, required_case=case, expected_field="recovery", fraction=True) if spec.recovery else None,
            processing_conversion=resolver.get(spec.processing_conversion, required_case=case,
                                               expected_field="processing_conversion", fraction=True) if spec.processing_conversion else None,
            saleable_tonnes_direct=volume if spec.production_stage == "saleable_product" else None,
            ownership=resolver.get(spec.ownership, required_case=case,
                                   expected_field="ownership_percentage", fraction=True) if spec.ownership else Decimal(1),
            source_input_ids=[str(r.metric_id) for r in _refs(spec)])
        produced = bridge_production(bridge)
        if produced["status"] != "PASS":
            raise MissingInput("production bridge: " + ", ".join(produced["missing_inputs"]))
        saleable = produced["attributable_saleable_tonnes"]
    price_metric = resolver.metric(spec.commodity_price)
    if price_metric.commodity != spec.commodity or price_metric.currency != "USD":
        raise IneligibleInput("Commodity price commodity/currency mismatch")
    if price_metric.price_type is None:
        raise MissingInput("commodity-price horizon/type")
    if price_metric.price_type == CommodityPriceType.CURRENT_SPOT and period_end > spec.period_start + timedelta(days=365):
        raise IneligibleInput("Current spot price cannot be silently projected long term")
    if price_metric.price_type == CommodityPriceType.HISTORICAL_AVERAGE and price_metric.intended_use != "long_term":
        raise IneligibleInput("Historical average needs an explicit long-term modeling decision")
    price = resolver.get(spec.commodity_price, required_case=case, expected_field="commodity_price")
    if resolver.available[(spec.commodity_price.metric_id, spec.commodity_price.field, spec.commodity_price.case)].normalized_unit != Unit.USD_PER_TONNE:
        raise IneligibleInput("Commodity price needs deterministic USD/tonne normalization")
    realization = resolver.get(spec.realization_factor, required_case=case, expected_field="realization_factor", fraction=True)
    payability = resolver.get(spec.payability, required_case=case, expected_field="payability", fraction=True)
    charge_metric = resolver.metric(spec.treatment_charge)
    if charge_metric.unit != Unit.USD_PER_TONNE or charge_metric.currency != "USD":
        raise IneligibleInput("Treatment charge must be USD per tonne")
    charge = resolver.get(spec.treatment_charge, required_case=case, expected_field="treatment_charge")
    revenue = commodity_revenue(saleable_tonnes=saleable, benchmark_usd_per_tonne=price,
        realization_factor=realization, payability=payability, treatment_charge_usd_per_tonne=charge)
    converted = _convert(revenue["revenue"], "USD", spec.fx_rate, spec.fx_pair, resolver, case, currency)
    return converted, {"production": {k: str(v) for k, v in produced.items()},
                       "realization": {k: str(v) for k, v in revenue.items()},
                       "cash_flow_currency": currency, "revenue_in_cash_flow_currency": str(converted)}


def _year(spec: YearInputSpec, resolver: Resolver, case: str, currency: str) -> ForecastYear:
    missing = [field for field in YEAR_FIELDS if field not in spec.inputs
               and not (field == "revenue" and spec.operational_revenue)
               and not (field == "operating_cost" and spec.cost_components)]
    if missing:
        raise MissingInput("Forecast year missing " + ", ".join(missing))
    ids = [str(ref.metric_id) for ref in _refs(spec)]
    values = {}
    operational_schedule = None
    for field in YEAR_FIELDS:
        if field == "revenue" and spec.operational_revenue:
            if field in spec.inputs:
                raise IneligibleInput("Direct and bridged revenue cannot both be counted")
            values[field], operational_schedule = _operational_revenue(spec.operational_revenue,
                spec.period_end, resolver, case, currency)
        elif field == "operating_cost" and spec.cost_components:
            if field in spec.inputs:
                raise IneligibleInput("Direct and component operating costs cannot both be counted")
            needed = {"mining", "processing", "refining", "transport", "treatment", "royalties", "other_operating"}
            if set(spec.cost_components) != needed:
                raise MissingInput("Explicit operating-cost components: " + ", ".join(sorted(needed - set(spec.cost_components))))
            expected = {"mining": "mining_cost", "processing": "processing_cost",
                        "refining": "refining_cost", "transport": "transport_cost",
                        "treatment": "treatment_cost", "royalties": "royalties",
                        "other_operating": "other_operating_cost"}
            costs = {name: resolver.get(ref, required_case=case,
                                        expected_field=expected[name], currency=currency,
                                        forecast_period_start=spec.operational_revenue.period_start if spec.operational_revenue else None)
                     for name, ref in spec.cost_components.items()}
            values[field] = cost_bridge(CostSchedule(**costs))["operating_cost"]
        else:
            values[field] = resolver.get(spec.inputs[field], required_case=case, expected_field=field,
                                         fraction=field == "tax_rate", currency=None if field == "tax_rate" else currency,
                                         forecast_period_start=spec.operational_revenue.period_start if spec.operational_revenue else None)
    accounting = earnings_bridge(revenue=values["revenue"], operating_cost=values["operating_cost"],
                                 corporate_cost=values["corporate_cost"], depreciation=values["depreciation"],
                                 net_finance_cost=values["net_finance_cost"], tax_rate=values["tax_rate"])
    cash = unlevered_fcf(ebit=accounting["ebit"], tax_rate=values["tax_rate"],
                        depreciation=values["depreciation"], sustaining_capex=values["sustaining_capex"],
                        growth_capex=values["growth_capex"], working_capital_change=values["working_capital"],
                        other_recurring_cash=values["other_recurring_cash"])
    return ForecastYear(period_end=spec.period_end, revenue=values["revenue"],
                        ebitda=accounting["ebitda"], ebit=accounting["ebit"], tax=cash["cash_tax"],
                        sustaining_capex=values["sustaining_capex"], growth_capex=values["growth_capex"],
                        working_capital_change=values["working_capital"],
                        depreciation_addback=values["depreciation"],
                        other_recurring_cash=values["other_recurring_cash"],
                        fcf=cash["unlevered_fcf"],
                        attributable_earnings=accounting["attributable_earnings"],
                        source_input_ids=ids, operational_schedule=operational_schedule)


def _wacc(spec: WaccSpec, resolver: Resolver, case: str) -> Decimal:
    if spec.supported_wacc and spec.components:
        raise IneligibleInput("Choose derived WACC or supported assumption, not both")
    if spec.supported_wacc:
        ref = spec.supported_wacc
        if resolver.metric(ref).currency != spec.currency:
            raise IneligibleInput("Supported WACC currency unresolved or mismatched")
        return resolver.get(ref, required_case=case, expected_field="wacc", fraction=True)
    if not spec.components:
        raise MissingInput("WACC components")
    missing = [f for f in WACC_FIELDS if f not in spec.components]
    if missing:
        raise MissingInput("WACC missing " + ", ".join(missing))
    vals = {f: resolver.get(spec.components[f], required_case=case, expected_field=f,
                            fraction=f != "beta") for f in WACC_FIELDS}
    if resolver.metric(spec.components["risk_free_rate"]).currency != spec.currency or resolver.metric(spec.components["cost_of_debt"]).currency != spec.currency:
        raise IneligibleInput("Risk-free or debt rate currency mismatches WACC")
    return calculate_wacc(WaccInputs(**vals, currency=spec.currency, basis=spec.basis,
                                     inflation_basis=spec.inflation_basis))["wacc"]


def _dcf(spec: DcfSpec | None, resolver: Resolver, case: str) -> ValuationMethodResult:
    if spec is None:
        return ValuationMethodResult(method="DCF", status=MethodStatus.NOT_CALCULABLE,
                                     missing_inputs=["DCF forecast/WACC/terminal plan"])
    try:
        if not spec.years:
            raise MissingInput("explicit forecast years")
        years = [_year(y, resolver, case, spec.cash_flow_currency) for y in spec.years]
        wacc = _wacc(spec.wacc, resolver, case)
        g = None; multiple = None; terminal_metric = None
        if spec.terminal_method == TerminalMethod.PERPETUITY_GROWTH:
            if not spec.terminal_growth:
                raise MissingInput("terminal_growth")
            g = resolver.get(spec.terminal_growth, required_case=case,
                             expected_field="terminal_growth", fraction=True)
        else:
            if not spec.exit_multiple or spec.terminal_metric not in {"EBITDA", "EBIT"}:
                raise MissingInput("exit_multiple and terminal_metric basis")
            multiple = resolver.get(spec.exit_multiple, required_case=case, expected_field="exit_multiple")
            terminal_metric = years[-1].ebitda if spec.terminal_metric == "EBITDA" else years[-1].ebit
        dcf = DcfInputs(valuation_date=spec.valuation_date, forecast=years, wacc=wacc,
                        cash_flow_currency=spec.cash_flow_currency,
                        discount_rate_currency=spec.wacc.currency,
                        cash_flow_basis=spec.cash_flow_basis, discount_rate_basis=spec.wacc.basis,
                        cash_flow_inflation_basis=spec.inflation_basis,
                        discount_rate_inflation_basis=spec.wacc.inflation_basis,
                        terminal_method=spec.terminal_method, terminal_growth=g,
                        exit_multiple=multiple, terminal_metric=terminal_metric)
        result = calculate_dcf(dcf)
        result.input_ids = list({r.metric_id for r in _refs(spec)})
        return result
    except MissingInput as exc:
        return ValuationMethodResult(method="DCF", status=MethodStatus.NOT_CALCULABLE,
                                     missing_inputs=[str(exc)])
    except (IneligibleInput, ValueError) as exc:
        return ValuationMethodResult(method="DCF", status=MethodStatus.FAIL, warnings=[str(exc)])


def _convert(value: Decimal, currency: str, fx_ref: InputRef | None, fx_pair: str | None,
             resolver: Resolver, case: str, target: str) -> Decimal:
    if currency == target:
        return value
    if not fx_ref or not fx_pair:
        raise MissingInput(f"FX {currency}->{target} explicit pair/rate")
    rate = resolver.get(fx_ref, required_case=case, expected_field="fx_rate")
    return convert_fx(value, rate=rate, pair=fx_pair, from_currency=currency, to_currency=target)


def _sotp(spec: SotpSpec | None, resolver: Resolver, case: str,
          currency: str, valuation_date: date,
          group_dcf_boundaries: set[str] | None = None) -> ValuationMethodResult:
    if spec is None:
        return ValuationMethodResult(method="SOTP", status=MethodStatus.NOT_CALCULABLE,
                                     missing_inputs=["SOTP component schedule"])
    try:
        components = []
        for item in spec.components:
            gross = resolver.get(item.gross_value, required_case=case, expected_field="asset_value", currency=item.currency)
            gross = _convert(gross, item.currency, item.fx_rate, item.fx_pair, resolver, case, currency)
            ownership = resolver.get(item.ownership, required_case=case, expected_field="ownership_percentage", fraction=True)
            probability = resolver.get(item.probability, required_case=case, expected_field="probability", fraction=True) if item.probability else Decimal(1)
            discount = resolver.get(item.discount_factor, required_case=case, expected_field="discount_factor", fraction=True) if item.discount_factor else Decimal(1)
            components.append(SotpComponent(component_id=item.component_id, name=item.name,
                                            boundary_id=item.boundary_id, method=item.method,
                                            gross_value=gross, currency=currency, valuation_date=valuation_date,
                                            ownership=ownership, probability=probability, discount_factor=discount,
                                            risk_basis=item.risk_basis, risk_in_discount_rate=item.risk_in_discount_rate,
                                            value_kind=item.value_kind,
                                            disposed_boundary_id=item.disposed_boundary_id,
                                            source_input_ids=[str(r.metric_id) for r in _refs(item)]))
        if spec.deferred_payments:
            if not spec.selected_settlement_scenario:
                raise MissingInput("selected settlement scenario")
            selected = [p for p in spec.deferred_payments if p.settlement_scenario == spec.selected_settlement_scenario]
            if not selected:
                raise MissingInput("payments for selected settlement scenario")
            payments = []
            for p in selected:
                payments.append(DeferredPayment(payment_id=p.payment_id,
                    amount=resolver.get(p.amount, required_case=case, expected_field="deferred_payment", currency=p.currency),
                    currency=p.currency, expected_date=p.expected_date,
                    discount_rate=resolver.get(p.discount_rate, required_case=case,
                                               expected_field="deferred_discount_rate", fraction=True),
                    completion_probability=resolver.get(p.completion_probability, required_case=case, expected_field="probability", fraction=True),
                    counterparty_factor=resolver.get(p.counterparty_factor, required_case=case,
                                                     expected_field="counterparty_factor", fraction=True) if p.counterparty_factor else Decimal(1),
                    settlement_scenario=p.settlement_scenario,
                    source_input_ids=[str(r.metric_id) for r in _refs(p)]))
            valued = value_payment_scenarios(payments, valuation_date)[spec.selected_settlement_scenario]
            if len({p.asset_boundary_id for p in selected}) != 1:
                raise IneligibleInput("One settlement scenario must map to one disposed asset boundary")
            p0 = selected[0]
            pv = _convert(valued["present_value"], p0.currency, p0.fx_rate, p0.fx_pair, resolver, case, currency)
            ownership = resolver.get(p0.ownership, required_case=case, expected_field="ownership_percentage", fraction=True)
            components.append(SotpComponent(component_id="deferred:" + spec.selected_settlement_scenario,
                name="Deferred consideration: " + spec.selected_settlement_scenario,
                boundary_id="payment:" + p0.asset_boundary_id, method="staged_payment_pv",
                gross_value=pv, currency=currency, valuation_date=valuation_date,
                ownership=ownership, value_kind="disposal_proceeds", disposed_boundary_id=p0.asset_boundary_id,
                source_input_ids=[str(r.metric_id) for p in selected for r in _refs(p)]))
        result = calculate_sotp(components, currency=currency, valuation_date=valuation_date,
                                group_dcf_boundaries=group_dcf_boundaries)
        return result
    except MissingInput as exc:
        return ValuationMethodResult(method="SOTP", status=MethodStatus.NOT_CALCULABLE,
                                     missing_inputs=[str(exc)])
    except (IneligibleInput, ValueError) as exc:
        return ValuationMethodResult(method="SOTP", status=MethodStatus.FAIL, warnings=[str(exc)])


def _equity(spec: EquitySpec | None, resolver: Resolver, case: str, operating_value: Decimal):
    if spec is None:
        raise MissingInput("enterprise-to-equity schedule and forward shares")
    missing = [f for f in EQUITY_FIELDS if f not in spec.adjustments]
    if missing:
        raise MissingInput("equity adjustments: " + ", ".join(missing))
    vals = {f: resolver.get(spec.adjustments[f], required_case=case, expected_field=f,
                            currency="ZAR") for f in EQUITY_FIELDS}
    share_ref = spec.shares
    if share_ref.field not in {"forecast_diluted_shares", "current_issued_shares"}:
        raise IneligibleInput("Forward target requires forecast diluted or current issued shares")
    shares = resolver.get(share_ref, required_case=case, expected_field=share_ref.field)
    metric = resolver.metric(share_ref)
    if metric.share_count_type not in {ShareCountType.FORECAST_DILUTED_SHARES, ShareCountType.ISSUED_SHARES_CURRENT}:
        raise IneligibleInput("Historical weighted-average denominator rejected")
    return reconcile_equity(enterprise_or_operating_value=operating_value,
                            non_operating_assets=vals["non_operating_assets"], receivables=vals["receivables"],
                            cash=vals["net_cash"], debt=vals["net_debt"],
                            lease_adjustments=vals["lease_adjustments"], minorities=vals["minorities"],
                            other_equity_adjustments=vals["other_equity_adjustments"],
                            forward_shares=shares, shares_metric_id=share_ref.metric_id)


def _case_differences(resolver: Resolver, case_names: set[str], active_keys: set[tuple]) -> list[dict]:
    grouped = {}
    for key, item in resolver.available.items():
        if item.case_type.value not in case_names or key not in active_keys:
            continue
        m = item.source_metric
        concept = (item.valuation_field.value, m.operation_segment, m.commodity)
        grouped.setdefault(concept, {}).setdefault(item.case_type.value, []).append(item)
    output = []
    for (field, operation, commodity), cases in grouped.items():
        observed = {str(item.selected_value) for group in cases.values() for item in group}
        if len(observed) <= 1:
            continue
        values = {}
        for case, group in cases.items():
            values[case] = [{"metric_id": str(item.metric_id), "value": str(item.selected_value),
                "unit": item.normalized_unit.value if item.normalized_unit else None,
                "rationale": item.selection_reason,
                "provenance": item.source_metric.source,
                "eligibility": resolver.decisions[(item.metric_id, item.valuation_field.value, case)].validation_status.value}
                for item in group]
        output.append({"valuation_field": field, "operation_segment": operation,
                       "commodity": commodity, "cases": values})
    return output


def run_valuation(*, ticker: str, report_version_id: UUID | str,
                  candidates: list[ValuationInputCandidate], metrics: list[FinancialMetric],
                  plan: ValuationPlan | None = None, valuation_date: date | None = None,
                  legacy_gemini_target: Decimal | None = None,
                  legacy_target_derivation: str | None = None,
                  missing_input_reasons: list[str] | None = None) -> ValuationResult:
    report_id = UUID(str(report_version_id))
    today = valuation_date or (plan.valuation_date if plan else date.today())
    base_kwargs = dict(ticker=ticker, report_version_id=report_id, valuation_date=today,
                       valuation_engine_version=ENGINE_VERSION, legacy_gemini_target=legacy_gemini_target,
                       legacy_target_derivation=legacy_target_derivation)
    if plan is None or "base" not in plan.cases:
        reasons = missing_input_reasons or ["No explicit source-backed base-case valuation plan"]
        base_candidates = [c for c in candidates if c.case_type.value == "base"]
        preflight = run_preflight(ticker, report_id, base_candidates, metrics) if base_candidates else None
        return ValuationResult(**base_kwargs, status=ValuationStatus.NOT_CALCULABLE,
            methods={m: ValuationMethodResult(method=m, status=MethodStatus.NOT_CALCULABLE,
                                             missing_inputs=reasons) for m in ("DCF", "SOTP")},
            warnings=reasons, input_ids=[c.metric_id for c in candidates], preflight=preflight,
            calculation_inputs={"candidates": [c.model_dump(mode="json") for c in candidates],
                                "available_metrics": [m.model_dump(mode="json") for m in metrics],
                                "missing_input_reasons": reasons})
    if plan.report_version_id != report_id or plan.ticker != ticker or today != plan.valuation_date:
        return ValuationResult(**base_kwargs, status=ValuationStatus.FAIL,
                               warnings=["Valuation plan ticker/report version/date mismatch"])
    if any(cp.dcf and cp.dcf.valuation_date != plan.valuation_date for cp in plan.cases.values()):
        return ValuationResult(**base_kwargs, status=ValuationStatus.FAIL,
                               warnings=["DCF and plan valuation dates differ"])
    try:
        resolver = Resolver(candidates, metrics, report_id)
    except IneligibleInput as exc:
        return ValuationResult(**base_kwargs, status=ValuationStatus.FAIL, warnings=[str(exc)])
    case_results = {}
    base_methods = {}
    base_recon = None
    base_target = None
    base_warnings = []
    for case_name, case_plan in plan.cases.items():
        refs = _active_refs(case_plan)
        missing_refs = [r for r in refs if (r.metric_id, r.field, r.case) not in resolver.available]
        if missing_refs:
            case_results[case_name] = {"status": "NOT_CALCULABLE", "missing_inputs":
                                       [f"{r.field}:{r.metric_id}" for r in missing_refs]}
            if case_name == "base":
                base_warnings.extend(case_results[case_name]["missing_inputs"])
                base_methods[case_plan.primary_method] = ValuationMethodResult(
                    method=case_plan.primary_method, status=MethodStatus.NOT_CALCULABLE,
                    missing_inputs=case_results[case_name]["missing_inputs"])
            continue
        invalid = [resolver.decisions[(r.metric_id, r.field, r.case)] for r in refs
                   if resolver.decisions[(r.metric_id, r.field, r.case)].validation_status.value not in
                   {"eligible", "eligible_with_warning"}]
        if invalid:
            case_results[case_name] = {"status": "FAIL", "reasons":
                [f"{c.valuation_field.value}:{c.validation_status.value}" for c in invalid]}
            if case_name == "base":
                base_warnings.extend(case_results[case_name]["reasons"])
                base_methods[case_plan.primary_method] = ValuationMethodResult(
                    method=case_plan.primary_method, status=MethodStatus.FAIL,
                    warnings=case_results[case_name]["reasons"])
            continue
        dcf = _dcf(case_plan.dcf, resolver, case_name)
        sotp = _sotp(case_plan.sotp, resolver, case_name, plan.currency, plan.valuation_date,
                     case_plan.group_dcf_boundaries)
        methods = {"DCF": dcf, "SOTP": sotp}
        selected = methods[case_plan.primary_method]
        if selected.status != MethodStatus.PASS:
            case_results[case_name] = {"status": selected.status.value,
                                       "missing_inputs": selected.missing_inputs,
                                       "warnings": selected.warnings}
        else:
            try:
                operating_value = selected.value
                if selected.currency != plan.currency:
                    operating_value = _convert(operating_value, selected.currency,
                        case_plan.valuation_fx_rate, case_plan.valuation_fx_pair,
                        resolver, case_name, plan.currency)
                recon = _equity(case_plan.equity, resolver, case_name, operating_value)
                if case_plan.primary_method == "SOTP":
                    kinds = {row.get("value_kind") for row in selected.schedule}
                    if (kinds & {"cash", "net_cash"} and recon.cash != 0) or (kinds & {"debt", "net_debt"} and recon.debt != 0) or ("receivable" in kinds and recon.receivables != 0):
                        raise IneligibleInput("Cash, debt or receivable appears in both SOTP components and equity bridge")
                provisional = ValuationResult(**base_kwargs, status=ValuationStatus.PASS,
                    target_price=recon.rounded_target_zar, reconciliation=recon)
                recalculate_target(provisional)
                case_results[case_name] = {"status": "PASS", "target_price_zar": str(recon.rounded_target_zar),
                    "equity_value": str(recon.equity_value), "denominator": str(recon.shares),
                    "input_ids": sorted({str(r.metric_id) for r in refs}), "rationale": case_plan.rationale}
                if case_name == "base":
                    base_target = recon.rounded_target_zar; base_recon = recon
            except MissingInput as exc:
                case_results[case_name] = {"status": "NOT_CALCULABLE", "missing_inputs": [str(exc)]}
            except (IneligibleInput, ValueError) as exc:
                case_results[case_name] = {"status": "FAIL", "warnings": [str(exc)]}
        if case_name == "base":
            base_methods = methods
            base_warnings.extend(case_results[case_name].get("missing_inputs", []) + case_results[case_name].get("warnings", []))
    base = case_results.get("base", {"status": "NOT_CALCULABLE", "missing_inputs": ["base case"]})
    if base["status"] == "PASS":
        used = [resolver.decisions[(r.metric_id, r.field, r.case)] for r in _active_refs(plan.cases["base"])]
        warning_codes = sorted({x.code for c in used for x in c.warnings})
        if warning_codes:
            base_warnings.extend(warning_codes)
        status = ValuationStatus.PASS_WITH_WARNINGS if base_warnings else ValuationStatus.PASS
    else:
        status = ValuationStatus(base["status"])
    selected_base = [resolver.available[(r.metric_id, r.field, r.case)] for r in _active_refs(plan.cases["base"])
                     if (r.metric_id, r.field, r.case) in resolver.available]
    market_price_value = None
    if plan.market_price is not None:
        try:
            market_price_value = resolver.get(plan.market_price, expected_field="current_share_price", currency="ZAR")
        except (MissingInput, IneligibleInput):
            base_warnings.append("Current price unavailable for implied-upside review")
    preflight = run_preflight(ticker, report_id, selected_base, metrics,
                              current_price=market_price_value, target_price=base_target)
    if preflight["status"] == "FAIL" and status in {ValuationStatus.PASS, ValuationStatus.PASS_WITH_WARNINGS}:
        status = ValuationStatus.FAIL; base_target = None; base_recon = None
        base_warnings.append("Selected base inputs failed Phase 3 preflight")
    result = ValuationResult(**base_kwargs, status=status, currency=plan.currency,
        cases=case_results, case_differences=_case_differences(
            resolver, set(plan.cases),
            {(r.metric_id, r.field, r.case) for cp in plan.cases.values() for r in _active_refs(cp)}),
        methods=base_methods, target_price=base_target,
        reconciliation=base_recon, warnings=base_warnings, preflight=preflight,
        input_ids=sorted({r.metric_id for case_plan in plan.cases.values() for r in _active_refs(case_plan)}),
        calculation_inputs={"plan": plan.model_dump(mode="json"),
                            "candidates": [c.model_dump(mode="json") for c in candidates],
                            "available_metrics": [m.model_dump(mode="json") for m in metrics]})
    if result.target_price is not None:
        recalculate_target(result)
        if preflight.get("enhanced_target_review"):
            result.warnings.append("HIGH_UPSIDE_REVIEW: " + preflight["enhanced_target_review"]["severity"])
            if result.status == ValuationStatus.PASS:
                result.status = ValuationStatus.PASS_WITH_WARNINGS
        last_year = None
        if plan.cases["base"].primary_method == "DCF" and result.methods.get("DCF") and result.methods["DCF"].status == MethodStatus.PASS:
            forecasts = [row for row in result.methods["DCF"].schedule if "period_end" in row]
            last_year = forecasts[-1] if forecasts else None
        def optional(ref, expected):
            if ref is None:
                return None
            try:
                return resolver.get(ref, expected_field=expected)
            except (MissingInput, IneligibleInput):
                return None
        result.implied_checks = {k: str(v) for k, v in implied_checks(
            equity_value=result.reconciliation.equity_value,
            shares=result.reconciliation.shares,
            cash=result.reconciliation.cash,
            debt=result.reconciliation.debt,
            market_price=optional(plan.market_price, "current_share_price"),
            nav=optional(plan.nav, "net_asset_value"),
            production_units=optional(plan.production_reference, "saleable_volume"),
            ebitda=D(last_year["ebitda"]) if last_year else None,
            earnings=D(last_year["attributable_earnings"]) if last_year and last_year.get("attributable_earnings") else None,
            fcf=D(last_year["fcf"]) if last_year else None).items()}
        if last_year:
            for name, ref in plan.historical_calibration.items():
                if name not in {"revenue", "ebitda", "fcf"}:
                    continue
                historical = optional(ref, name)
                forecast = D(last_year[name])
                if historical is None:
                    result.warnings.append(f"Historical {name} calibration unavailable")
                elif historical > 0 and (forecast > historical * 2 or forecast < historical / 2):
                    result.warnings.append(f"Forecast {name} differs by >2x from sourced historical reference")
            if result.warnings and result.status == ValuationStatus.PASS:
                result.status = ValuationStatus.PASS_WITH_WARNINGS
    return result


def render_valuation_result(result: ValuationResult) -> str:
    """Only Python result fields enter the displayed target/reconciliation."""
    lines = ["DETERMINISTIC VALUATION: PYTHON", f"Engine version: {result.valuation_engine_version}",
             f"Status: {result.status.value}"]
    if result.target_price is None:
        lines.append("Deterministic target price: NOT_CALCULABLE")
        lines.extend(f"Reason: {reason}" for reason in result.warnings)
    else:
        r = result.reconciliation
        lines.extend([f"Enterprise/operating value: ZAR {r.enterprise_or_operating_value}",
                      f"Equity value: ZAR {r.equity_value}", f"Forward shares: {r.shares}",
                      f"Unrounded target: ZAR {r.unrounded_target_zar}",
                      f"Deterministic target: ZAR {r.rounded_target_zar} / {r.rounded_target_cents} cents"])
    if result.legacy_gemini_target is not None:
        lines.append(f"Historical Gemini target (not used): ZAR {result.legacy_gemini_target}")
    return "\n".join(lines)
