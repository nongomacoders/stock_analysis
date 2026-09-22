"""Disaggregated operating costs; reported AISC is a separate cross-check."""
from decimal import Decimal
from pydantic import BaseModel, Field


class CostSchedule(BaseModel):
    mining: Decimal = Decimal(0)
    processing: Decimal = Decimal(0)
    refining: Decimal = Decimal(0)
    transport: Decimal = Decimal(0)
    treatment: Decimal = Decimal(0)
    royalties: Decimal = Decimal(0)
    corporate: Decimal = Decimal(0)
    other_operating: Decimal = Decimal(0)
    sustaining_capex: Decimal = Decimal(0)
    reported_aisc: Decimal | None = None
    reported_aisc_definition: str | None = None
    included_components: list[str] = Field(default_factory=list)


def cost_bridge(x: CostSchedule) -> dict:
    components = {name: getattr(x, name) for name in (
        "mining", "processing", "refining", "transport", "treatment", "royalties", "other_operating")}
    if any(v < 0 for v in (*components.values(), x.corporate, x.sustaining_capex)):
        raise ValueError("Cost components cannot be negative")
    if x.reported_aisc is not None and not x.reported_aisc_definition:
        raise ValueError("Reported AISC needs its source definition")
    operating = sum(components.values(), Decimal(0))
    return {"components": components, "included_components": list(components),
            "operating_cost": operating, "corporate_cost": x.corporate,
            "sustaining_capex": x.sustaining_capex,
            "reported_aisc_crosscheck": x.reported_aisc,
            "reported_aisc_definition": x.reported_aisc_definition}
