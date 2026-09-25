"""Reference backtest constants and regression verification helper for TRU reference retailer.

This module provides developer and test verification helpers to ensure that the
first completed reference retailer backtest (TRU.JO FY2025 -> FY2026) remains
completely immutable across future codebase changes.

This helper is for regression verification only and is NOT wired into production
valuation logic.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID
import json
import psycopg2
from core.config import DB_CONFIG

# Canonical TRU Reference Backtest Identifiers & Frozen State
TRU_REFERENCE_TICKER = "TRU.JO"
TRU_REFERENCE_BACKTEST_ID = UUID("4230b66f-6be8-480a-878d-77d69eaeacd8")
TRU_REFERENCE_PLAN_ID = UUID("ba6d3186-8a51-44a3-8f67-3ad34ece3da6")
TRU_REFERENCE_RESULT_ID = UUID("6768e249-36c9-4f4d-afff-e3bd832e5f6a")
TRU_REFERENCE_FROZEN_HASH = "ccf6a05b91b47ec458186ad1e73f9a78496d64f34c96f2e99dfbba7c8872f959"

# Locked Valuation Values
TRU_REFERENCE_FAIR_VALUE = Decimal("72.8232")
TRU_REFERENCE_ENTERPRISE_VALUE = Decimal("30356971061.15")
TRU_REFERENCE_EQUITY_VALUE = Decimal("27334971061.15")

# Canonical Lifecycle & Outcome States
TRU_REFERENCE_BACKTEST_STATUS = "completed"
TRU_REFERENCE_PLAN_STATUS = "approved"
TRU_REFERENCE_AUTHORITATIVE_REVISION = 3
TRU_REFERENCE_AUTHORITATIVE_OUTCOME_STATUS = "completed"


@dataclass(frozen=True)
class ReferenceVerificationResult:
    """Detailed result of verifying the persisted reference backtest state."""
    is_valid: bool
    backtest_id: UUID
    historical_result_id: UUID
    fair_value: Decimal
    enterprise_value: Decimal
    equity_value: Decimal
    input_hash: str
    backtest_status: str
    plan_status: str
    authoritative_outcome_revision: int
    authoritative_outcome_status: str
    errors: list[str]


def verify_tru_reference_backtest(conn=None) -> ReferenceVerificationResult:
    """Verifies that the canonical TRU reference backtest in PostgreSQL matches locked values.

    Args:
        conn: Optional active psycopg2 connection. If None, opens and closes one.

    Returns:
        ReferenceVerificationResult detailing validation status and any discrepancies.
    """
    close_conn = False
    if conn is None:
        conn = psycopg2.connect(**DB_CONFIG)
        close_conn = True

    errors: list[str] = []
    try:
        cur = conn.cursor()

        # 1. Backtest row check
        cur.execute(
            "SELECT backtest_id, status, input_hash FROM historical_backtests WHERE backtest_id = %s",
            (str(TRU_REFERENCE_BACKTEST_ID),)
        )
        bt_row = cur.fetchone()
        if not bt_row:
            errors.append(f"Backtest {TRU_REFERENCE_BACKTEST_ID} not found in historical_backtests")
            bt_status = "missing"
            bt_hash = ""
        else:
            bt_status = str(bt_row[1])
            bt_hash = str(bt_row[2])
            if bt_status != TRU_REFERENCE_BACKTEST_STATUS:
                errors.append(f"Expected backtest status '{TRU_REFERENCE_BACKTEST_STATUS}', got '{bt_status}'")
            if bt_hash != TRU_REFERENCE_FROZEN_HASH:
                errors.append(f"Backtest hash mismatch: expected {TRU_REFERENCE_FROZEN_HASH}, got {bt_hash}")

        # 2. Plan row check
        cur.execute(
            "SELECT historical_plan_id, status, input_hash FROM historical_backtest_plans WHERE historical_plan_id = %s",
            (str(TRU_REFERENCE_PLAN_ID),)
        )
        plan_row = cur.fetchone()
        if not plan_row:
            errors.append(f"Plan {TRU_REFERENCE_PLAN_ID} not found in historical_backtest_plans")
            p_status = "missing"
        else:
            p_status = str(plan_row[1])
            if p_status != TRU_REFERENCE_PLAN_STATUS:
                errors.append(f"Expected plan status '{TRU_REFERENCE_PLAN_STATUS}', got '{p_status}'")
            if str(plan_row[2]) != TRU_REFERENCE_FROZEN_HASH:
                errors.append(f"Plan hash mismatch: expected {TRU_REFERENCE_FROZEN_HASH}, got {plan_row[2]}")

        # 3. Result row check
        cur.execute(
            "SELECT historical_result_id, backtest_id, historical_plan_id, input_hash, valuation_result "
            "FROM historical_backtest_results WHERE historical_result_id = %s",
            (str(TRU_REFERENCE_RESULT_ID),)
        )
        res_row = cur.fetchone()
        if not res_row:
            errors.append(f"Result {TRU_REFERENCE_RESULT_ID} not found in historical_backtest_results")
            fv = Decimal("0")
            ev = Decimal("0")
            eq = Decimal("0")
            res_hash = ""
        else:
            res_hash = str(res_row[3])
            vr = res_row[4]
            if isinstance(vr, str):
                vr = json.loads(vr)
            fv = Decimal(str(vr.get("historical_fair_value")))
            ev = Decimal(str(vr.get("enterprise_value")))
            eq = Decimal(str(vr.get("equity_value")))

            if fv != TRU_REFERENCE_FAIR_VALUE:
                errors.append(f"Fair value mismatch: expected {TRU_REFERENCE_FAIR_VALUE}, got {fv}")
            if ev != TRU_REFERENCE_ENTERPRISE_VALUE:
                errors.append(f"EV mismatch: expected {TRU_REFERENCE_ENTERPRISE_VALUE}, got {ev}")
            if eq != TRU_REFERENCE_EQUITY_VALUE:
                errors.append(f"Equity value mismatch: expected {TRU_REFERENCE_EQUITY_VALUE}, got {eq}")
            if res_hash != TRU_REFERENCE_FROZEN_HASH:
                errors.append(f"Result hash mismatch: expected {TRU_REFERENCE_FROZEN_HASH}, got {res_hash}")

        # 4. Authoritative Outcome check (latest revision)
        cur.execute(
            "SELECT outcome_id, revision, outcome_status FROM historical_backtest_outcomes "
            "WHERE backtest_id = %s ORDER BY revision DESC LIMIT 1",
            (str(TRU_REFERENCE_BACKTEST_ID),)
        )
        out_row = cur.fetchone()
        if not out_row:
            errors.append("No outcome records found in historical_backtest_outcomes")
            out_rev = 0
            out_status = "missing"
        else:
            out_rev = int(out_row[1])
            out_status = str(out_row[2])
            if out_rev != TRU_REFERENCE_AUTHORITATIVE_REVISION:
                errors.append(f"Authoritative outcome revision mismatch: expected {TRU_REFERENCE_AUTHORITATIVE_REVISION}, got {out_rev}")
            if out_status != TRU_REFERENCE_AUTHORITATIVE_OUTCOME_STATUS:
                errors.append(f"Expected authoritative outcome status '{TRU_REFERENCE_AUTHORITATIVE_OUTCOME_STATUS}', got '{out_status}'")

        is_valid = len(errors) == 0
        return ReferenceVerificationResult(
            is_valid=is_valid,
            backtest_id=TRU_REFERENCE_BACKTEST_ID,
            historical_result_id=TRU_REFERENCE_RESULT_ID,
            fair_value=fv,
            enterprise_value=ev,
            equity_value=eq,
            input_hash=res_hash or bt_hash,
            backtest_status=bt_status,
            plan_status=p_status,
            authoritative_outcome_revision=out_rev,
            authoritative_outcome_status=out_status,
            errors=errors
        )
    finally:
        if close_conn:
            conn.close()
