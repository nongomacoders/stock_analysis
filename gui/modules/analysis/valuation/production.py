"""Explicit production-stage and development timing bridges."""
from __future__ import annotations
from datetime import date
from decimal import Decimal
from pydantic import BaseModel, Field, model_validator

D = lambda x: Decimal(str(x))


class ProductionBridge(BaseModel):
    period_start: date
    period_end: date
    operation_id: str
    commodity: str
    rom_tonnes: Decimal | None = None
    grade: Decimal | None = None
    contained_tonnes_direct: Decimal | None = None
    recovery: Decimal | None = None
    recovered_tonnes_direct: Decimal | None = None
    processing_conversion: Decimal | None = None
    saleable_tonnes_direct: Decimal | None = None
    ownership: Decimal = Decimal(1)
    source_input_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid(self):
        if self.period_end < self.period_start:
            raise ValueError("Production period ends before start")
        for name in ("grade", "recovery", "processing_conversion", "ownership"):
            value = getattr(self, name)
            if value is not None and not 0 <= value <= 1:
                raise ValueError(f"{name} must be a fraction between zero and one")
        if self.rom_tonnes is not None and self.contained_tonnes_direct is not None:
            raise ValueError("Cannot sum ROM-derived and directly reported contained metal")
        if self.saleable_tonnes_direct is not None and any(v is not None for v in
                (self.rom_tonnes, self.contained_tonnes_direct, self.recovered_tonnes_direct)):
            raise ValueError("Direct saleable output cannot be added to its upstream feed")
        return self


def bridge_production(x: ProductionBridge) -> dict:
    contained = x.contained_tonnes_direct
    if contained is None and x.rom_tonnes is not None:
        if x.grade is None:
            return {"status": "NOT_CALCULABLE", "missing_inputs": ["grade"]}
        contained = x.rom_tonnes * x.grade
    recovered = x.recovered_tonnes_direct
    if recovered is None and contained is not None:
        if x.recovery is None:
            return {"status": "NOT_CALCULABLE", "missing_inputs": ["recovery"]}
        recovered = contained * x.recovery
    saleable = x.saleable_tonnes_direct
    if saleable is None and recovered is not None:
        if x.processing_conversion is None:
            return {"status": "NOT_CALCULABLE", "missing_inputs": ["processing_conversion_or_payability"]}
        saleable = recovered * x.processing_conversion
    if saleable is None:
        return {"status": "NOT_CALCULABLE", "missing_inputs": ["saleable_output_or_conversion_bridge"]}
    return {"status": "PASS", "rom_tonnes": x.rom_tonnes, "contained_tonnes": contained,
            "recovered_tonnes": recovered, "saleable_tonnes": saleable,
            "attributable_saleable_tonnes": saleable * x.ownership,
            "period_start": x.period_start, "period_end": x.period_end,
            "operation_id": x.operation_id, "source_input_ids": x.source_input_ids}


class DevelopmentPeriod(BaseModel):
    period_start: date
    period_end: date
    start_date: date
    annual_nameplate_rom_tonnes: Decimal
    utilization: Decimal
    ramp_up: Decimal
    grade: Decimal
    recovery: Decimal
    processing_conversion: Decimal
    ownership: Decimal


def development_production(x: DevelopmentPeriod) -> dict:
    if x.period_end < x.period_start or x.annual_nameplate_rom_tonnes < 0:
        raise ValueError("Invalid development period/capacity")
    if any(not 0 <= v <= 1 for v in (x.utilization, x.ramp_up, x.grade, x.recovery,
                                       x.processing_conversion, x.ownership)):
        raise ValueError("Development fractions must be between zero and one")
    active_start = max(x.period_start, x.start_date)
    active_days = max(0, (x.period_end - active_start).days + 1)
    period_days = (x.period_end - x.period_start).days + 1
    if period_days > 366:
        raise ValueError("DevelopmentPeriod must describe one forecast year at a time")
    days_in_year = 366 if _leap(x.period_start.year) else 365
    rom = x.annual_nameplate_rom_tonnes * D(active_days) / D(days_in_year) * x.utilization * x.ramp_up
    contained = rom * x.grade
    recovered = contained * x.recovery
    return {"active_days": active_days, "period_days": period_days, "rom_tonnes": rom,
            "contained_tonnes": contained, "recovered_tonnes": recovered,
            "saleable_tonnes": recovered * x.processing_conversion,
            "attributable_saleable_tonnes": recovered * x.processing_conversion * x.ownership}


def _leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
