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
        if not self.boundary_id:
            raise ValueError("Unique asset boundary required")
        return self


def calculate_sotp(components: list[SotpComponent], *, currency: str, valuation_date: date,
                   group_dcf_boundaries: set[str] | None = None) -> ValuationMethodResult:
    if not components:
        return ValuationMethodResult(method="SOTP", status=MethodStatus.NOT_CALCULABLE,
                                     missing_inputs=["component_schedule"])
    seen_id, seen_boundary = set(), set()
    disposed = {c.disposed_boundary_id for c in components if c.disposed_boundary_id}
    schedule = []
    total = Decimal(0)
    for c in components:
        if c.component_id in seen_id or c.boundary_id in seen_boundary:
            raise ValueError("Duplicate SOTP component or asset boundary")
        seen_id.add(c.component_id); seen_boundary.add(c.boundary_id)
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
                                 currency=currency, schedule=schedule,
                                 input_ids=[i for c in components for i in c.source_input_ids])
