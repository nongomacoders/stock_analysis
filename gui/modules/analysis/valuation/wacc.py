"""Currency- and nominal-basis-explicit weighted average cost of capital."""
from decimal import Decimal
from pydantic import BaseModel, model_validator
from .models import Basis


class WaccInputs(BaseModel):
    risk_free_rate: Decimal
    equity_risk_premium: Decimal
    beta: Decimal
    country_risk_premium: Decimal
    cost_of_debt: Decimal
    tax_rate: Decimal
    debt_weight: Decimal
    equity_weight: Decimal
    currency: str
    basis: Basis
    inflation_basis: str

    @model_validator(mode="after")
    def valid(self):
        if self.debt_weight < 0 or self.equity_weight < 0 or self.debt_weight + self.equity_weight != 1:
            raise ValueError("Debt and equity weights must be nonnegative and sum to one")
        if not 0 <= self.tax_rate <= 1 or self.beta < 0:
            raise ValueError("Invalid tax or beta")
        if not self.currency or not self.inflation_basis:
            raise ValueError("WACC currency and inflation basis required")
        return self


def calculate_wacc(x: WaccInputs) -> dict:
    equity = x.risk_free_rate + x.beta * x.equity_risk_premium + x.country_risk_premium
    debt_after_tax = x.cost_of_debt * (1 - x.tax_rate)
    result = equity * x.equity_weight + debt_after_tax * x.debt_weight
    if result <= 0:
        raise ValueError("WACC must be positive")
    return {"cost_of_equity": equity, "cost_of_debt_after_tax": debt_after_tax,
            "wacc": result, "currency": x.currency, "basis": x.basis.value,
            "inflation_basis": x.inflation_basis, "inputs": x.model_dump(mode="json")}
