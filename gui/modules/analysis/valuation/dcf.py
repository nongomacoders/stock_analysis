"""Explicit-year DCF with one terminal method and currency/basis checks."""
from datetime import date
from decimal import Decimal
from pydantic import BaseModel, Field, model_validator
from .models import Basis, TerminalMethod, ValuationMethodResult, MethodStatus


class ForecastYear(BaseModel):
    period_end: date
    revenue: Decimal
    ebitda: Decimal
    ebit: Decimal
    tax: Decimal
    sustaining_capex: Decimal = Decimal(0)
    growth_capex: Decimal = Decimal(0)
    total_capex: Decimal | None = None
    working_capital_change: Decimal
    fcf: Decimal
    depreciation_addback: Decimal = Decimal(0)
    attributable_earnings: Decimal | None = None
    other_recurring_cash: Decimal = Decimal(0)
    source_input_ids: list[str] = Field(default_factory=list)
    operational_schedule: dict | None = None

    @model_validator(mode="after")
    def reconciles(self):
        capex = (self.total_capex if self.total_capex is not None
                 else self.sustaining_capex + self.growth_capex)
        if self.total_capex is not None and (self.sustaining_capex != 0 or self.growth_capex != 0):
            raise ValueError("Total capex cannot be combined with sustaining/growth capex")
        expected = (self.ebit - self.tax + self.depreciation_addback - capex
                    - self.working_capital_change - self.other_recurring_cash)
        if expected != self.fcf:
            raise ValueError("Forecast FCF does not reconcile to EBIT/cash items")
        return self


class DcfInputs(BaseModel):
    valuation_date: date
    forecast: list[ForecastYear]
    wacc: Decimal
    cash_flow_currency: str
    discount_rate_currency: str
    cash_flow_basis: Basis
    discount_rate_basis: Basis
    cash_flow_inflation_basis: str
    discount_rate_inflation_basis: str
    terminal_method: TerminalMethod
    terminal_growth: Decimal | None = None
    exit_multiple: Decimal | None = None
    terminal_metric: Decimal | None = None
    midyear_discounting: bool = False

    @model_validator(mode="after")
    def consistent(self):
        if self.cash_flow_currency != self.discount_rate_currency:
            raise ValueError("Cash-flow and WACC currency mismatch")
        if self.cash_flow_basis != self.discount_rate_basis or self.cash_flow_inflation_basis != self.discount_rate_inflation_basis:
            raise ValueError("Cash-flow and WACC real/nominal or inflation basis mismatch")
        if self.wacc <= 0:
            raise ValueError("WACC must be positive")
        if not self.forecast or any(y.period_end <= self.valuation_date for y in self.forecast):
            raise ValueError("Forecast years must follow valuation date")
        if sorted(y.period_end for y in self.forecast) != [y.period_end for y in self.forecast]:
            raise ValueError("Forecast years must be ordered")
        if self.terminal_method == TerminalMethod.PERPETUITY_GROWTH:
            if self.terminal_growth is None or self.terminal_growth >= self.wacc:
                raise ValueError("Perpetuity growth requires terminal_growth < WACC")
            if self.exit_multiple is not None or self.terminal_metric is not None:
                raise ValueError("Only one terminal method may be active")
        else:
            if self.exit_multiple is None or self.terminal_metric is None or self.exit_multiple < 0:
                raise ValueError("Exit multiple requires metric and multiple")
            if self.terminal_growth is not None:
                raise ValueError("Only one terminal method may be active")
        return self


def calculate_dcf(x: DcfInputs) -> ValuationMethodResult:
    schedule = []
    pv_fcf = Decimal(0)
    for year in x.forecast:
        t = Decimal((year.period_end - x.valuation_date).days) / Decimal("365.25")
        if x.midyear_discounting:
            t = max(Decimal(0), t - Decimal("0.5"))
        factor = Decimal(1) / (Decimal(1) + x.wacc) ** t
        pv = year.fcf * factor
        pv_fcf += pv
        schedule.append({**year.model_dump(mode="json"), "discount_years": str(t),
                         "discount_factor": str(factor), "present_value": str(pv)})
    end = x.forecast[-1]
    if x.terminal_method == TerminalMethod.PERPETUITY_GROWTH:
        next_fcf = end.fcf * (1 + x.terminal_growth)
        tv = next_fcf / (x.wacc - x.terminal_growth)
        terminal_detail = {"method": x.terminal_method.value, "next_fcf": str(next_fcf),
                           "terminal_growth": str(x.terminal_growth)}
    else:
        tv = x.terminal_metric * x.exit_multiple
        terminal_detail = {"method": x.terminal_method.value, "terminal_metric": str(x.terminal_metric),
                           "exit_multiple": str(x.exit_multiple)}
    # Terminal value is discounted once at the end of the explicit forecast.
    terminal_factor = Decimal(1) / (Decimal(1) + x.wacc) ** (Decimal((end.period_end - x.valuation_date).days) / Decimal("365.25"))
    pv_tv = tv * terminal_factor
    schedule.append({"terminal": terminal_detail, "undiscounted_terminal_value": str(tv),
                     "discount_factor": str(terminal_factor), "present_value": str(pv_tv)})
    return ValuationMethodResult(method="DCF", status=MethodStatus.PASS, value=pv_fcf + pv_tv,
                                 currency=x.cash_flow_currency, schedule=schedule,
                                 input_ids=[i for y in x.forecast for i in y.source_input_ids])
