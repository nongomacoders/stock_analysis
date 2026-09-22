"""Unlevered FCF: EBIT(1-tax) + D&A - sustaining/growth capex - ?WC - other cash."""
from decimal import Decimal


def unlevered_fcf(*, ebit: Decimal, tax_rate: Decimal, depreciation: Decimal,
                  sustaining_capex: Decimal, growth_capex: Decimal,
                  working_capital_change: Decimal, other_recurring_cash: Decimal = Decimal(0)) -> dict:
    if not 0 <= tax_rate <= 1:
        raise ValueError("Tax rate must be a fraction")
    if min(depreciation, sustaining_capex, growth_capex) < 0:
        raise ValueError("Depreciation and capex cannot be negative")
    cash_tax = max(ebit, Decimal(0)) * tax_rate
    fcf = ebit - cash_tax + depreciation - sustaining_capex - growth_capex - working_capital_change - other_recurring_cash
    return {"ebit": ebit, "cash_tax": cash_tax, "depreciation_addback": depreciation,
            "sustaining_capex": sustaining_capex, "growth_capex": growth_capex,
            "working_capital_change": working_capital_change,
            "other_recurring_cash": other_recurring_cash, "unlevered_fcf": fcf}
