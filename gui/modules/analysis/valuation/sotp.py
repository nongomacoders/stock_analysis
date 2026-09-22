"""Configurable asset-boundary SOTP, ownership and explicit risk factors."""
from datetime import date
from decimal import Decimal
from pydantic import BaseModel, Field, model_validator
from .models import MethodStatus, ValuationMethodResult


class SotpComponent(BaseModel):
    component_id: str
    name: str
    boundary_id: str
    method: str
    gross_value: Decimal
    currency: str
    valuation_date: date
    ownership: Decimal
    probability: Decimal = Decimal(1)
    discount_factor: Decimal = Decimal(1)
    source_input_ids: list[str] = Field(default_factory=list)
    included_boundary_ids: set[str] = Field(default_factory=set)
    value_source_date: date | None = None
    ownership_source_date: date | None = None
    fx_source_date: date | None = None
    native_currency: str | None = None
    native_gross_value: Decimal | None = None
    fx_rate_applied: Decimal | None = None
    fx_pair: str | None = None
    value_kind: str = "operating_asset"
    disposed_boundary_id: str | None = None
    included_in_group_dcf: bool = False
    risk_basis: str | None = None
    risk_in_discount_rate: bool = False

    @model_validator(mode="after")
    def valid(self):
        if self.gross_value < 0 or not 0 <= self.ownership <= 1 or not 0 <= self.probability <= 1 or not 0 <= self.discount_factor <= 1:
            raise ValueError("Invalid SOTP value, ownership or risk factor")
        if self.probability < 1 and not self.risk_basis:
            raise ValueError("Probability weighting requires visible risk rationale")
        if self.probability < 1 and self.risk_in_discount_rate:
            raise ValueError("Project risk cannot be counted in both probability and discount rate")
        if not self.boundary_id or self.boundary_id in self.included_boundary_ids:
            raise ValueError("Unique asset boundary required; component cannot contain itself")
        return self


def calculate_sotp(components: list[SotpComponent], *, currency: str, valuation_date: date,
                   group_dcf_boundaries: set[str] | None = None) -> ValuationMethodResult:
    if not components:
        return ValuationMethodResult(method="SOTP", status=MethodStatus.NOT_CALCULABLE,
                                     missing_inputs=["component_schedule"])
    seen_id, seen_boundary, seen_exposure = set(), set(), set()
    warnings = []
    disposed = {c.disposed_boundary_id for c in components if c.disposed_boundary_id}
    schedule = []
    total = Decimal(0)
    for c in components:
        if c.component_id in seen_id or c.boundary_id in seen_boundary:
            raise ValueError("Duplicate SOTP component or asset boundary")
        exposures = {c.boundary_id} | c.included_boundary_ids
        if exposures & seen_exposure:
            raise ValueError("Duplicate economic exposure or parent/subsidiary boundary")
        seen_exposure.update(exposures)
        seen_id.add(c.component_id); seen_boundary.add(c.boundary_id)
        for label, observed in (("value", c.value_source_date), ("ownership", c.ownership_source_date),
                                ("FX", c.fx_source_date)):
            if observed and (valuation_date - observed).days > 90:
                warnings.append(f"{c.name}: {label} source date {observed} is >90 days before valuation date")
        if c.value_source_date and c.ownership_source_date and abs((c.value_source_date - c.ownership_source_date).days) > 90:
            warnings.append(f"{c.name}: value and ownership source dates differ by >90 days")
        if c.currency != currency or c.valuation_date != valuation_date:
            raise ValueError("SOTP currency/date mismatch requires explicit conversion")
        if c.included_in_group_dcf or c.boundary_id in (group_dcf_boundaries or set()):
            raise ValueError("Asset already included in group DCF")
        if c.boundary_id in disposed and c.value_kind == "operating_asset":
            raise ValueError("Disposed asset cannot retain operating value alongside sale proceeds")
        gross_attributable = c.gross_value * c.ownership
        final = gross_attributable * c.probability * c.discount_factor
        total += final
        schedule.append({**c.model_dump(mode="json"), "gross_attributable": str(gross_attributable),
                         "final_attributable": str(final)})
    return ValuationMethodResult(method="SOTP", status=MethodStatus.PASS, value=total,
                                 currency=currency, schedule=schedule, warnings=warnings,
                                 input_ids=[i for c in components for i in c.source_input_ids])


def listed_holding_value(*, share_price: Decimal, underlying_shares: Decimal,
                         ownership: Decimal, currency: str, price_date: date,
                         ownership_date: date, price_source: str, ownership_source: str) -> dict:
    """Source-explicit listed equity value; caller records input IDs in its plan."""
    if share_price < 0 or underlying_shares < 0 or not 0 <= ownership <= 1:
        raise ValueError("Invalid listed holding price, shares or ownership")
    if not currency or not price_source or not ownership_source:
        raise ValueError("Listed holding currency and source identifiers are required")
    gross = share_price * underlying_shares
    return {"gross_equity_value": gross, "attributable_value": gross * ownership,
            "currency": currency, "price_date": price_date, "ownership_date": ownership_date,
            "price_source": price_source, "ownership_source": ownership_source,
            "ownership": ownership}


def holding_discount_schedule(*, nav_per_share: Decimal, discount: Decimal,
                              rationale: str, origin: str, approved: bool,
                              sensitivity: tuple[Decimal, ...] = ()) -> dict:
    """Keep a separately approved holding discount outside component NAV."""
    if not approved or not rationale.strip() or origin not in {"analyst_assumption", "scenario_assumption"}:
        raise ValueError("Holding discount requires an approved, reasoned analyst or scenario assumption")
    if nav_per_share < 0 or not 0 <= discount <= 1 or any(not 0 <= x <= 1 for x in sensitivity):
        raise ValueError("Invalid NAV or holding discount")
    return {"nav_per_share": nav_per_share, "discount": discount, "rationale": rationale,
            "origin": origin, "approved": approved,
            "target_per_share": nav_per_share * (1 - discount),
            "sensitivity": {str(x): nav_per_share * (1 - x) for x in sensitivity}}
