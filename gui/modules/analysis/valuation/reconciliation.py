"""Enterprise-to-equity and reproducible ZAR/cents per-share target."""
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID
from .models import TargetReconciliation, BankTargetReconciliation

CENT = Decimal("0.01")


def reconcile_equity(*, enterprise_or_operating_value: Decimal, non_operating_assets: Decimal,
                     receivables: Decimal, cash: Decimal, debt: Decimal, lease_adjustments: Decimal,
                     minorities: Decimal, other_equity_adjustments: Decimal,
                     forward_shares: Decimal, shares_metric_id: UUID) -> TargetReconciliation:
    if forward_shares <= 0:
        raise ValueError("Forward share count must be positive")
    if cash != 0 and debt != 0:
        raise ValueError("Net cash and net debt are mutually exclusive")
    equity = (enterprise_or_operating_value + non_operating_assets + receivables + cash
              - debt - lease_adjustments - minorities + other_equity_adjustments)
    if equity < 0:
        raise ValueError("Negative equity value cannot become a published per-share target")
    unrounded = equity / forward_shares
    rounded_zar = unrounded.quantize(CENT, rounding=ROUND_HALF_UP)
    return TargetReconciliation(
        enterprise_or_operating_value=enterprise_or_operating_value,
        non_operating_assets=non_operating_assets, receivables=receivables,
        cash=cash, debt=debt, lease_adjustments=lease_adjustments,
        minorities=minorities, other_equity_adjustments=other_equity_adjustments,
        equity_value=equity, shares=forward_shares, shares_metric_id=shares_metric_id,
        unrounded_target_zar=unrounded, rounded_target_zar=rounded_zar,
        rounded_target_cents=rounded_zar * 100,
    )


def reconcile_bank_equity(*, opening_common_equity: Decimal, pv_forecast_residual_income: Decimal,
                          pv_terminal_residual_income: Decimal, approved_equity_adjustments: Decimal,
                          forward_diluted_shares: Decimal, shares_metric_id: UUID) -> BankTargetReconciliation:
    if forward_diluted_shares <= 0:
        raise ValueError("Forward diluted shares must be positive")
    equity = (opening_common_equity + pv_forecast_residual_income
              + pv_terminal_residual_income + approved_equity_adjustments)
    if equity < 0:
        raise ValueError("Negative bank equity cannot become a published target")
    unrounded = equity / forward_diluted_shares
    rounded = unrounded.quantize(CENT, rounding=ROUND_HALF_UP)
    return BankTargetReconciliation(opening_common_equity=opening_common_equity,
        pv_forecast_residual_income=pv_forecast_residual_income,
        pv_terminal_residual_income=pv_terminal_residual_income,
        approved_equity_adjustments=approved_equity_adjustments, equity_value=equity,
        shares=forward_diluted_shares, shares_metric_id=shares_metric_id,
        unrounded_target_zar=unrounded, rounded_target_zar=rounded, rounded_target_cents=rounded * 100)


def recalculate_target(result) -> Decimal:
    r = result.reconciliation
    if r is None:
        raise ValueError("Target reconciliation unavailable")
    if isinstance(r, BankTargetReconciliation):
        expected_equity = (r.opening_common_equity + r.pv_forecast_residual_income
                           + r.pv_terminal_residual_income + r.approved_equity_adjustments)
    else:
        expected_equity = (r.enterprise_or_operating_value + r.non_operating_assets + r.receivables
                           + r.cash - r.debt - r.lease_adjustments - r.minorities + r.other_equity_adjustments)
    if expected_equity != r.equity_value or r.shares <= 0:
        raise ValueError("Enterprise-to-equity schedule does not reconcile")
    recalculated = (expected_equity / r.shares).quantize(CENT, rounding=ROUND_HALF_UP)
    if abs(recalculated - r.rounded_target_zar) > r.rounding_tolerance:
        raise ValueError("Stored target is not reproducible")
    if result.target_price is not None and abs(recalculated - result.target_price) > r.rounding_tolerance:
        raise ValueError("Published target differs from deterministic reconciliation")
    if r.rounded_target_cents != r.rounded_target_zar * 100:
        raise ValueError("ZAR and cents display disagree")
    return recalculated
