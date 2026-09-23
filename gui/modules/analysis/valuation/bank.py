"""Bank equity residual-income valuation; all amounts in parent currency units."""
from __future__ import annotations
from datetime import date
from decimal import Decimal
from pydantic import BaseModel, Field, model_validator
from .models import MethodStatus, ValuationMethodResult

class BankYear(BaseModel):
    period_end: date
    roe: Decimal | None = None
    earnings: Decimal | None = None
    payout_ratio: Decimal | None = None
    dividends: Decimal | None = None
    other_equity_movement: Decimal = Decimal(0)
    cet1_ratio: Decimal | None = None

    @model_validator(mode="after")
    def valid(self):
        if (self.roe is None) == (self.earnings is None):
            raise ValueError("Choose exactly one of forecast ROE or earnings")
        if (self.payout_ratio is None) == (self.dividends is None):
            raise ValueError("Choose exactly one of payout ratio or dividends")
        if self.payout_ratio is not None and not 0 <= self.payout_ratio <= 1:
            raise ValueError("Payout ratio must be between zero and one")
        if self.dividends is not None and self.dividends < 0:
            raise ValueError("Dividends cannot be negative")
        if self.cet1_ratio is not None and not 0 <= self.cet1_ratio <= 1:
            raise ValueError("CET1 ratio must be a fraction")
        return self

class BankInputs(BaseModel):
    valuation_date: date
    opening_common_equity: Decimal
    years: list[BankYear]
    cost_of_equity: Decimal
    terminal_roe: Decimal
    terminal_growth: Decimal
    cet1_minimum: Decimal | None = None
    cet1_target: Decimal | None = None

    @model_validator(mode="after")
    def valid(self):
        if self.opening_common_equity <= 0:
            raise ValueError("Opening common equity must be positive")
        if not 0 < self.cost_of_equity < 1 or not -1 < self.terminal_growth < self.cost_of_equity:
            raise ValueError("Terminal growth must be below positive cost of equity")
        if not 0 <= self.terminal_roe < 1:
            raise ValueError("Terminal ROE must be a fraction")
        if not self.years or any(y.period_end <= self.valuation_date for y in self.years):
            raise ValueError("Annual forecast years must follow valuation date")
        if [y.period_end for y in self.years] != sorted({y.period_end for y in self.years}):
            raise ValueError("Forecast years must be unique and ordered")
        previous = self.valuation_date
        for year in self.years:
            if not 300 <= (year.period_end - previous).days <= 399:
                raise ValueError("Residual-income forecast requires consecutive annual periods")
            previous = year.period_end
        if any(not 0 <= x <= 1 for x in (self.cet1_minimum, self.cet1_target) if x is not None):
            raise ValueError("CET1 constraints must be fractions")
        return self

def cost_of_equity(*, risk_free_rate: Decimal, beta: Decimal, equity_risk_premium: Decimal,
                   country_risk_premium: Decimal = Decimal(0)) -> Decimal:
    if risk_free_rate < 0 or beta < 0 or equity_risk_premium < 0 or country_risk_premium < 0:
        raise ValueError("Cost-of-equity components cannot be negative")
    result = risk_free_rate + beta * equity_risk_premium + country_risk_premium
    if not 0 < result < 1:
        raise ValueError("Calculated cost of equity must be a positive fraction")
    return result

def calculate_residual_income(inputs: BankInputs) -> ValuationMethodResult:
    book = inputs.opening_common_equity
    pv_forecast = Decimal(0)
    schedule = []
    warnings = []
    for n, year in enumerate(inputs.years, 1):
        opening = book
        earnings = year.earnings if year.earnings is not None else opening * year.roe
        roe = earnings / opening
        dividends = year.dividends if year.dividends is not None else earnings * year.payout_ratio
        if dividends < 0:
            raise ValueError("Negative forecast dividends require explicit zero or revised earnings")
        retained = earnings - dividends
        book = opening + retained + year.other_equity_movement
        if book <= 0:
            raise ValueError("Closing common equity must be positive")
        required = opening * inputs.cost_of_equity
        residual = earnings - required
        pv = residual / ((1 + inputs.cost_of_equity) ** n)
        pv_forecast += pv
        if dividends > earnings and earnings >= 0:
            warnings.append(f"{year.period_end}: payout exceeds earnings; equity declines absent other movements")
        if inputs.cet1_minimum is not None and year.cet1_ratio is not None and year.cet1_ratio < inputs.cet1_minimum:
            warnings.append(f"{year.period_end}: forecast CET1 below sourced minimum")
        if inputs.cet1_target is not None and year.cet1_ratio is not None and year.cet1_ratio < inputs.cet1_target:
            warnings.append(f"{year.period_end}: forecast CET1 below sourced target")
        schedule.append({"period_end": str(year.period_end), "opening_common_equity": str(opening),
            "roe": str(roe), "cost_of_equity": str(inputs.cost_of_equity),
            "roe_coe_spread": str(roe - inputs.cost_of_equity), "earnings": str(earnings),
            "required_earnings": str(required), "residual_income": str(residual),
            "dividends": str(dividends), "retained_earnings": str(retained),
            "other_equity_movement": str(year.other_equity_movement), "closing_common_equity": str(book),
            "discount_factor": str(1 / ((1 + inputs.cost_of_equity) ** n)),
            "pv_residual_income": str(pv), "cet1_ratio": str(year.cet1_ratio) if year.cet1_ratio is not None else None})
    terminal_payout = (Decimal(1) - inputs.terminal_growth / inputs.terminal_roe
                       if inputs.terminal_roe > 0 else None)
    if terminal_payout is None and inputs.terminal_growth > 0:
        warnings.append("Positive terminal growth has no supporting terminal earnings")
    if terminal_payout is not None and not 0 <= terminal_payout <= 1:
        warnings.append("Terminal growth implies an infeasible dividend payout from terminal ROE")
    last = schedule[-1]
    if terminal_payout is not None and Decimal(last["earnings"]) > 0:
        last_payout = Decimal(last["dividends"]) / Decimal(last["earnings"])
        if abs(terminal_payout - last_payout) > Decimal("0.20"):
            warnings.append("Terminal growth implies payout differing by >20 percentage points from final forecast year")
    terminal_residual = book * (inputs.terminal_roe - inputs.cost_of_equity)
    terminal_value = terminal_residual / (inputs.cost_of_equity - inputs.terminal_growth)
    pv_terminal = terminal_value / ((1 + inputs.cost_of_equity) ** len(inputs.years))
    if (inputs.terminal_roe - inputs.cost_of_equity) > Decimal("0.05"):
        warnings.append("Terminal ROE exceeds cost of equity by more than five percentage points indefinitely")
    if inputs.cost_of_equity - inputs.terminal_growth < Decimal("0.01"):
        warnings.append("Terminal growth is within one percentage point of cost of equity")
    schedule.append({"terminal_book_equity": str(book), "terminal_roe": str(inputs.terminal_roe),
        "terminal_growth": str(inputs.terminal_growth), "cost_of_equity": str(inputs.cost_of_equity),
        "terminal_residual_income": str(terminal_residual), "terminal_value": str(terminal_value),
        "terminal_implied_payout": str(terminal_payout) if terminal_payout is not None else None,
        "pv_terminal_residual_income": str(pv_terminal), "pv_forecast_residual_income": str(pv_forecast),
        "opening_common_equity": str(inputs.opening_common_equity)})
    return ValuationMethodResult(method="RESIDUAL_INCOME", status=MethodStatus.PASS,
        value=inputs.opening_common_equity + pv_forecast + pv_terminal, schedule=schedule, warnings=warnings)

def pb_cross_checks(*, equity_value: Decimal, shares: Decimal, opening_book_equity: Decimal,
                    forecast_book_equity: Decimal, target_pb: Decimal | None = None,
                    terminal_roe: Decimal | None = None, cost_of_equity: Decimal | None = None,
                    growth: Decimal | None = None) -> dict:
    if shares <= 0 or opening_book_equity <= 0 or forecast_book_equity <= 0:
        raise ValueError("P/B requires positive shares and book equity")
    fair = equity_value / shares
    book_per_share = opening_book_equity / shares
    out = {"fair_value_per_share": str(fair), "book_value_per_share": str(book_per_share),
           "implied_pb": str(fair / book_per_share)}
    if target_pb is not None:
        if target_pb < 0:
            raise ValueError("Target P/B cannot be negative")
        out["target_pb_crosscheck_per_share"] = str(target_pb * forecast_book_equity / shares)
    if terminal_roe is not None and cost_of_equity is not None and growth is not None:
        if growth >= cost_of_equity:
            raise ValueError("Justified P/B needs growth below cost of equity")
        out["justified_pb_terminal"] = str((terminal_roe - growth) / (cost_of_equity - growth))
    return out
