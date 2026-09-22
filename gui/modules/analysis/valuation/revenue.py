"""Commodity realization from saleable quantities only."""
from decimal import Decimal
from .production import D


def commodity_revenue(*, saleable_tonnes: Decimal, benchmark_usd_per_tonne: Decimal,
                      realization_factor: Decimal = Decimal(1), payability: Decimal = Decimal(1),
                      treatment_charge_usd_per_tonne: Decimal = Decimal(0)) -> dict:
    if saleable_tonnes < 0 or benchmark_usd_per_tonne < 0 or treatment_charge_usd_per_tonne < 0:
        raise ValueError("Negative volume, price or charge")
    if not 0 <= realization_factor <= 1 or not 0 <= payability <= 1:
        raise ValueError("Realization and payability must be explicit fractions")
    realized = benchmark_usd_per_tonne * realization_factor * payability - treatment_charge_usd_per_tonne
    if realized < 0:
        raise ValueError("Charges exceed realized commodity price")
    return {"saleable_tonnes": saleable_tonnes, "benchmark_price": benchmark_usd_per_tonne,
            "realization_factor": realization_factor, "payability": payability,
            "treatment_charge_per_tonne": treatment_charge_usd_per_tonne,
            "realized_price": realized, "revenue": saleable_tonnes * realized, "currency": "USD"}
