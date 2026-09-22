"""Only compute meaningful implied valuation ratios from supplied data."""
from decimal import Decimal


def implied_checks(*, equity_value: Decimal, market_price: Decimal | None = None,
                   shares: Decimal | None = None, debt: Decimal | None = None, cash: Decimal | None = None,
                   ebitda: Decimal | None = None, earnings: Decimal | None = None,
                   nav: Decimal | None = None, fcf: Decimal | None = None,
                   production_units: Decimal | None = None) -> dict:
    out = {"implied_market_cap": equity_value}
    if market_price is not None and shares is not None:
        out["current_market_cap"] = market_price * shares
    if debt is not None and cash is not None:
        ev = equity_value + debt - cash
        out["implied_enterprise_value"] = ev
        if ebitda and ebitda > 0:
            out["ev_ebitda"] = ev / ebitda
        if production_units and production_units > 0:
            out["ev_per_production_unit"] = ev / production_units
    if earnings and earnings > 0:
        out["p_e"] = equity_value / earnings
    if nav and nav > 0:
        out["p_nav"] = equity_value / nav
    if fcf and equity_value > 0:
        out["fcf_yield"] = fcf / equity_value
    return out
