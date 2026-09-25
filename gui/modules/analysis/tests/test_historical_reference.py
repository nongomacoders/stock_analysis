"""Tests for TRU reference retailer finalization, lifecycle semantics, and documentation."""
from decimal import Decimal
from pathlib import Path
from uuid import UUID
import psycopg2
import pytest
from core.config import DB_CONFIG
from modules.analysis.historical_backtest import BacktestStatus
from modules.analysis.historical_plan import HistoricalPlanStatus
from modules.analysis.historical_reference import (
    verify_tru_reference_backtest,
    TRU_REFERENCE_BACKTEST_ID,
    TRU_REFERENCE_PLAN_ID,
    TRU_REFERENCE_RESULT_ID,
    TRU_REFERENCE_FROZEN_HASH,
    TRU_REFERENCE_FAIR_VALUE,
    TRU_REFERENCE_ENTERPRISE_VALUE,
    TRU_REFERENCE_EQUITY_VALUE,
    TRU_REFERENCE_AUTHORITATIVE_REVISION,
    TRU_REFERENCE_BACKTEST_STATUS,
    TRU_REFERENCE_PLAN_STATUS,
    TRU_REFERENCE_AUTHORITATIVE_OUTCOME_STATUS,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
RUNBOOK_PATH = REPO_ROOT / "HISTORICAL_BACKTEST_RUNBOOK.md"


def test_1_lifecycle_terminology_reflects_actual_persisted_state_fields():
    """1. Lifecycle terminology matches the actual schema and model enum definitions."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # Backtest table status
    cur.execute("SELECT status FROM historical_backtests WHERE backtest_id = %s", (str(TRU_REFERENCE_BACKTEST_ID),))
    bt_status = cur.fetchone()[0]
    assert bt_status in {s.value for s in BacktestStatus}
    assert bt_status == TRU_REFERENCE_BACKTEST_STATUS  # "completed"

    # Plan table status
    cur.execute("SELECT status FROM historical_backtest_plans WHERE historical_plan_id = %s", (str(TRU_REFERENCE_PLAN_ID),))
    plan_status = cur.fetchone()[0]
    assert plan_status in {s.value for s in HistoricalPlanStatus}
    assert plan_status == TRU_REFERENCE_PLAN_STATUS  # "approved"

    # Outcome table status
    cur.execute("SELECT outcome_status FROM historical_backtest_outcomes WHERE backtest_id = %s ORDER BY revision", (str(TRU_REFERENCE_BACKTEST_ID),))
    outcome_statuses = [r[0] for r in cur.fetchall()]
    assert set(outcome_statuses).issubset({"partial", "completed", "completed_superseded"})
    conn.close()


def test_2_backtest_status_reported_separately_from_result_immutability():
    """2. Backtest status ('completed') is distinct from valuation result immutability (insert-only)."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("SELECT status FROM historical_backtests WHERE backtest_id = %s", (str(TRU_REFERENCE_BACKTEST_ID),))
    bt_status = cur.fetchone()[0]
    assert bt_status == "completed", "Backtest lifecycle status must be 'completed', not conflated"

    # Verify results table has no mutable lifecycle status column; records are immutable insert-only
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'historical_backtest_results'")
    cols = {r[0] for r in cur.fetchall()}
    assert "status" not in cols, "Result immutability is governed by write-once design, not a status column"
    conn.close()


def test_3_outcome_revision_status_separate_from_backtest_lifecycle():
    """3. Outcome revision status is tracked per outcome record and is independent of backtest status."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute(
        "SELECT revision, outcome_status, supersedes_outcome_id FROM historical_backtest_outcomes "
        "WHERE backtest_id = %s ORDER BY revision",
        (str(TRU_REFERENCE_BACKTEST_ID),)
    )
    rows = cur.fetchall()
    conn.close()

    assert len(rows) == 3, "Expected 3 outcome revisions"
    # Revision 1 was partial
    assert rows[0][0] == 1 and rows[0][1] == "partial" and rows[0][2] is None
    # Revision 2 was completed, then superseded
    assert rows[1][0] == 2 and rows[1][1] == "completed_superseded" and rows[1][2] is not None
    # Revision 3 is completed and authoritative
    assert rows[2][0] == 3 and rows[2][1] == "completed" and rows[2][2] is not None


def test_4_tru_historical_result_values_remain_unchanged():
    """4. TRU locked historical valuation result values remain strictly unchanged."""
    res = verify_tru_reference_backtest()
    assert res.is_valid is True, f"Reference check failed: {res.errors}"
    assert res.historical_result_id == TRU_REFERENCE_RESULT_ID
    assert res.fair_value == TRU_REFERENCE_FAIR_VALUE  # Decimal("72.8232")
    assert res.enterprise_value == TRU_REFERENCE_ENTERPRISE_VALUE  # Decimal("30356971061.15")
    assert res.equity_value == TRU_REFERENCE_EQUITY_VALUE  # Decimal("27334971061.15")


def test_5_frozen_input_hash_remains_unchanged():
    """5. Frozen input hash remains ccf6a05b... across backtest, plan, and result."""
    res = verify_tru_reference_backtest()
    assert res.input_hash == TRU_REFERENCE_FROZEN_HASH

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("SELECT input_hash FROM historical_backtests WHERE backtest_id = %s", (str(TRU_REFERENCE_BACKTEST_ID),))
    assert cur.fetchone()[0] == TRU_REFERENCE_FROZEN_HASH

    cur.execute("SELECT input_hash FROM historical_backtest_plans WHERE historical_plan_id = %s", (str(TRU_REFERENCE_PLAN_ID),))
    assert cur.fetchone()[0] == TRU_REFERENCE_FROZEN_HASH

    cur.execute("SELECT input_hash FROM historical_backtest_results WHERE historical_result_id = %s", (str(TRU_REFERENCE_RESULT_ID),))
    assert cur.fetchone()[0] == TRU_REFERENCE_FROZEN_HASH
    conn.close()


def test_6_authoritative_outcome_revision_remains_revision_3():
    """6. Authoritative reveal outcome remains Revision 3."""
    res = verify_tru_reference_backtest()
    assert res.authoritative_outcome_revision == 3
    assert res.authoritative_outcome_status == "completed"


def test_7_no_tru_specific_production_valuation_branch():
    """7. Ensure valuation engine has no TRU-specific production valuation logic."""
    engine_dir = Path(__file__).resolve().parents[1] / "valuation"
    for py_file in engine_dir.glob("*.py"):
        text = py_file.read_text(encoding="utf-8", errors="ignore")
        assert "TRU.JO" not in text, f"Found hardcoded 'TRU.JO' in valuation engine {py_file.name}"
        assert 'ticker == "TRU"' not in text, f"Found hardcoded 'TRU' ticker check in {py_file.name}"


def test_8_generic_retailer_semantic_rules_documentation_exists():
    """8. Verify generic retailer semantic rules documentation exists and covers all required concepts."""
    assert RUNBOOK_PATH.exists(), f"Runbook {RUNBOOK_PATH} must exist"
    content = RUNBOOK_PATH.read_text(encoding="utf-8")

    required_topics = [
        "Accounting Revenue",
        "Sale of Merchandise",
        "Retail Sales",
        "Trading Profit",
        "Trading Margin Denominator",
        "D&A",
        "Cash Capex",
        "Accounting Additions",
        "Working-Capital Sign Convention",
        "Reported Net Cash",
        "Lease Liabilities",
        "Weighted-Average EPS Shares",
        "Treasury Shares",
        "Announcement-Date Shares",
        "AFS Exact Values",
        "Retailer Historical Backtest Workflow",
    ]
    for topic in required_topics:
        assert topic.lower() in content.lower(), f"Missing topic '{topic}' in {RUNBOOK_PATH}"
