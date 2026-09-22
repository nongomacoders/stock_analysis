"""Probability-weighted present value of staged, alternative consideration."""
from datetime import date
from decimal import Decimal
from pydantic import BaseModel, Field, model_validator


class DeferredPayment(BaseModel):
    payment_id: str
    amount: Decimal
    currency: str
    expected_date: date
    discount_rate: Decimal
    completion_probability: Decimal
    counterparty_factor: Decimal = Decimal(1)
    settlement_scenario: str
    source_input_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid(self):
        if self.amount < 0 or self.discount_rate < 0 or not 0 <= self.completion_probability <= 1 or not 0 <= self.counterparty_factor <= 1:
            raise ValueError("Invalid deferred-payment amount, rate or probability")
        if not self.settlement_scenario:
            raise ValueError("Settlement scenario required to keep alternatives separate")
        return self


def present_value_payment(x: DeferredPayment, valuation_date: date) -> Decimal:
    if x.expected_date < valuation_date:
        raise ValueError("Past payment needs a verified outstanding receivable; do not revalue received cash")
    years = Decimal((x.expected_date - valuation_date).days) / Decimal("365.25")
    return x.amount * x.completion_probability * x.counterparty_factor / (1 + x.discount_rate) ** years


def value_payment_scenarios(payments: list[DeferredPayment], valuation_date: date) -> dict:
    groups = {}
    seen = set()
    for payment in payments:
        if payment.payment_id in seen:
            raise ValueError("Duplicate payment ID")
        seen.add(payment.payment_id)
        group = groups.setdefault(payment.settlement_scenario, {"currency": payment.currency,
                                                              "payments": [], "present_value": Decimal(0)})
        if group["currency"] != payment.currency:
            raise ValueError("Scenario payment currencies cannot be silently mixed")
        pv = present_value_payment(payment, valuation_date)
        group["payments"].append({**payment.model_dump(mode="json"), "present_value": str(pv)})
        group["present_value"] += pv
    return groups  # Alternative scenarios are never added together.
