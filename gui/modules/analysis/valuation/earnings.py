"""Accounting earnings bridge and separately gated EPS/HEPS."""
from decimal import Decimal


def earnings_bridge(*, revenue: Decimal, operating_cost: Decimal, corporate_cost: Decimal,
                    depreciation: Decimal, net_finance_cost: Decimal, tax_rate: Decimal,
                    ownership: Decimal = Decimal(1), minorities: Decimal = Decimal(0)) -> dict:
    if not 0 <= tax_rate <= 1 or not 0 <= ownership <= 1:
        raise ValueError("Tax and ownership must be fractions")
    contribution = revenue - operating_cost
    ebitda = contribution - corporate_cost
    ebit = ebitda - depreciation
    pbt = ebit - net_finance_cost
    tax = max(pbt, Decimal(0)) * tax_rate
    attributable = (pbt - tax) * ownership - minorities
    return {"revenue": revenue, "operating_contribution": contribution, "ebitda": ebitda,
            "ebit": ebit, "profit_before_tax": pbt, "tax": tax,
            "attributable_earnings": attributable}


def per_share_earnings(*, attributable_earnings: Decimal, weighted_average_shares: Decimal,
                       headline_adjustments: Decimal | None = None) -> dict:
    if weighted_average_shares <= 0:
        raise ValueError("Weighted-average shares must be positive")
    eps = attributable_earnings / weighted_average_shares
    if headline_adjustments is None:
        return {"eps": eps, "heps_status": "HEPS_NOT_CALCULABLE", "heps": None,
                "missing_inputs": ["headline_adjustments"]}
    return {"eps": eps, "heps_status": "PASS",
            "heps": (attributable_earnings + headline_adjustments) / weighted_average_shares}
