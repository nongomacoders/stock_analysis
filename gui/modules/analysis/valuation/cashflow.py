"""Unlevered FCF: EBIT(1-tax) + D&A - sustaining/growth capex - ?WC - other cash."""
from decimal import Decimal


def unlevered_fcf(*, ebit: Decimal, tax_rate: Decimal, depreciation: Decimal,
                  sustaining_capex: Decimal | None = None,
                  growth_capex: Decimal | None = None,
                  total_capex: Decimal | None = None,
                  working_capital_change: Decimal,
                  other_recurring_cash: Decimal = Decimal(0)) -> dict:
    if not 0 <= tax_rate <= 1:
        raise ValueError("Tax rate must be a fraction")
    split_supplied = sustaining_capex is not None or growth_capex is not None
    if total_capex is not None and split_supplied:
        raise ValueError("Choose total capex or sustaining/growth capex, not both")
    if total_capex is None:
        if sustaining_capex is None or growth_capex is None:
            raise ValueError("Capex requires total capex or both sustaining and growth capex")
        capex = sustaining_capex + growth_capex
    else:
        capex = total_capex
        sustaining_capex = Decimal(0)
        growth_capex = Decimal(0)
    if min(depreciation, capex) < 0:
        raise ValueError("Depreciation and capex cannot be negative")
    cash_tax = max(ebit, Decimal(0)) * tax_rate
    fcf = ebit - cash_tax + depreciation - capex - working_capital_change - other_recurring_cash
    return {"ebit": ebit, "cash_tax": cash_tax, "depreciation_addback": depreciation,
            "sustaining_capex": sustaining_capex, "growth_capex": growth_capex,
            "total_capex": total_capex, "working_capital_change": working_capital_change,
            "other_recurring_cash": other_recurring_cash, "unlevered_fcf": fcf}
