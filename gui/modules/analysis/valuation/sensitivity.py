"""Recalculate DCF scenarios without mutating the stored base."""
from decimal import Decimal
from .dcf import DcfInputs, ForecastYear, calculate_dcf


def dcf_sensitivity(base: DcfInputs, *, wacc_values: list[Decimal], growth_values: list[Decimal],
                    commodity_price_factors: list[Decimal] | None = None,
                    production_factors: list[Decimal] | None = None,
                    operating_cost_factors: list[Decimal] | None = None,
                    fx_factors: list[Decimal] | None = None,
                    usd_revenue_fraction: Decimal | None = None,
                    usd_cost_fraction: Decimal | None = None) -> dict:
    if base.terminal_method.value != "perpetuity_growth":
        raise ValueError("WACC/growth grid requires perpetuity-growth base")
    if fx_factors and any(x != 1 for x in fx_factors):
        if usd_revenue_fraction is None or usd_cost_fraction is None:
            raise ValueError("FX sensitivity requires explicit revenue and cost currency exposure")
        if not 0 <= usd_revenue_fraction <= 1 or not 0 <= usd_cost_fraction <= 1:
            raise ValueError("FX exposure fractions must be between zero and one")
    results = []
    for wacc in wacc_values:
        for growth in growth_values:
            if growth >= wacc:
                results.append({"wacc": str(wacc), "terminal_growth": str(growth), "status": "NOT_CALCULABLE"})
                continue
            scenario = base.model_copy(update={"wacc": wacc, "terminal_growth": growth})
            value = calculate_dcf(scenario).value
            results.append({"wacc": str(wacc), "terminal_growth": str(growth), "status": "PASS", "value": str(value)})
    commodity = []
    for pf in commodity_price_factors or [Decimal(1)]:
        for vf in production_factors or [Decimal(1)]:
            for cf in operating_cost_factors or [Decimal(1)]:
                for fx in fx_factors or [Decimal(1)]:
                    if min(pf, vf, cf, fx) <= 0:
                        raise ValueError("Sensitivity factors must be positive")
                    adjusted = []
                    for y in base.forecast:
                        # Explicit sensitivity approximation: revenue scales with
                        # realized commodity price, saleable volume and FX; operating
                        # expense scales with volume and its own factor. The baseline
                        # expense is the reconciled EBITDA-to-revenue difference.
                        operating = y.revenue - y.ebitda
                        revenue_fx = 1 + (usd_revenue_fraction or Decimal(0)) * (fx - 1)
                        cost_fx = 1 + (usd_cost_fraction or Decimal(0)) * (fx - 1)
                        revenue = y.revenue * pf * vf * revenue_fx
                        expense = operating * vf * cf * cost_fx
                        ebitda = revenue - expense
                        ebit = ebitda - (y.ebitda - y.ebit)
                        tax = max(ebit, Decimal(0)) * (y.tax / y.ebit if y.ebit > 0 else Decimal(0))
                        fcf = (ebit - tax + y.depreciation_addback - y.sustaining_capex
                               - y.growth_capex - y.working_capital_change - y.other_recurring_cash)
                        adjusted.append(y.model_copy(update={"revenue": revenue, "ebitda": ebitda,
                                                       "ebit": ebit, "tax": tax, "fcf": fcf}))
                    scenario = base.model_copy(update={"forecast": adjusted})
                    commodity.append({"price_factor": str(pf), "volume_factor": str(vf),
                                      "cost_factor": str(cf), "fx_factor": str(fx),
                                      "value": str(calculate_dcf(scenario).value)})
    return {"wacc_terminal_growth": results, "operating_factors": commodity}
