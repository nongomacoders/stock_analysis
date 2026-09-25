"""Comprehensive audit tests for TRU FY2025 historical data extraction against actual AFS and SENS.

Tests all 18 numbered requirements from the audit mandate:
1. revenue exact extraction
2. sale-of-merchandise exact extraction
3. trading-profit exact extraction
4. trading-margin derivation
5. income-statement D&A = R1.500bn
6. cash-flow D&A = R1.526bn
7. the two D&A concepts remain distinct
8. FCFF D&A cannot silently default between them without semantic mapping
9. FY2025 cash capex = R674m
10. capex semantic basis = cash capex
11. working capital +R166m is interpreted as cash inflow
12. net cash reconciles to R720m after charitable-trust exclusion
13. lease liabilities = R3.742bn
14. period-end shares correct
15. announcement-date shares correct
16. weighted-average basic/diluted shares correct
17. locked result unchanged
18. frozen input hash unchanged
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4
import json
import pytest

from modules.analysis.results_package import (
    build_results_package, observations_to_metrics, ANNUAL_FINANCIAL_STATEMENTS, RESULTS_SENS
)
from modules.analysis.historical_backtest import (
    HistoricalBacktest, HistoricalEvidence, HistoricalMarketObservation, Availability
)
from modules.analysis.historical_readiness import (
    evaluate_historical_baseline, assert_historical_baseline_ready,
    render_historical_readiness_report, ReadinessStatus
)
from modules.analysis.valuation.cashflow import interpret_working_capital, unlevered_fcf
from core.config import DB_CONFIG
import psycopg2

PACKAGE_DIR = Path(__file__).resolve().parents[3] / "results_history" / "TRU" / "FY2025"

EXPECTED_BACKTEST_ID = "4230b66f-6be8-480a-878d-77d69eaeacd8"
EXPECTED_PLAN_ID = "ba6d3186-8a51-44a3-8f67-3ad34ece3da6"
EXPECTED_RESULT_ID = "6768e249-36c9-4f4d-afff-e3bd832e5f6a"
EXPECTED_FAIR_VALUE = Decimal("72.8232")
EXPECTED_EV = Decimal("30356971061.15")
EXPECTED_EQUITY_VALUE = Decimal("27334971061.15")
EXPECTED_FROZEN_HASH = "ccf6a05b91b47ec458186ad1e73f9a78496d64f34c96f2e99dfbba7c8872f959"


@pytest.fixture(scope="module")
def fy2025_readiness(cached_tru_backtest):
    return evaluate_historical_baseline(cached_tru_backtest)


def test_01_accounting_revenue_exact_extraction(cached_tru_backtest, fy2025_readiness):
    """1. Accounting revenue exact extraction = R23,071,000,000."""
    st = fy2025_readiness.concept_statuses["accounting_revenue"]
    assert st.status == ReadinessStatus.AVAILABLE
    assert st.normalized_value == Decimal("23071000000")
    assert st.normalized_unit == "ZAR"
    assert "23,071" in (st.raw_value or "")
    assert st.source_file == "TRU_FY2025_AFS.pdf"
    assert st.publication_date == "2025-08-28"


def test_02_sale_of_merchandise_exact_extraction(cached_tru_backtest, fy2025_readiness):
    """2. Sale of merchandise exact extraction = R21,323,000,000."""
    st = fy2025_readiness.concept_statuses["sale_of_merchandise"]
    assert st.status == ReadinessStatus.AVAILABLE
    assert st.normalized_value == Decimal("21323000000")
    assert st.normalized_unit == "ZAR"
    assert "21,323" in (st.raw_value or "")
    assert st.source_file == "TRU_FY2025_AFS.pdf"
    assert st.publication_date == "2025-08-28"


def test_03_trading_profit_exact_extraction(cached_tru_backtest, fy2025_readiness):
    """3. Trading profit exact extraction = R2,892,000,000."""
    st = fy2025_readiness.concept_statuses["trading_profit"]
    assert st.status == ReadinessStatus.AVAILABLE
    assert st.normalized_value == Decimal("2892000000")
    assert st.normalized_unit == "ZAR"
    assert "2,892" in (st.raw_value or "")
    assert st.source_file == "TRU_FY2025_AFS.pdf"
    assert st.publication_date == "2025-08-28"


def test_04_trading_margin_derivation(cached_tru_backtest, fy2025_readiness):
    """4. Trading margin derivation = 2.892 / 21.323 ≈ 13.5628%."""
    st = fy2025_readiness.concept_statuses["trading_margin"]
    assert st.status == ReadinessStatus.AVAILABLE
    expected_margin = (Decimal("2892000000") / Decimal("21323000000")) * Decimal("100")
    assert round(Decimal(str(st.normalized_value)), 4) == round(expected_margin, 4)
    assert round(Decimal(str(st.normalized_value)), 4) == Decimal("13.5628")
    assert st.normalized_unit == "percentage"


def test_05_income_statement_da_exact_extraction(cached_tru_backtest, fy2025_readiness):
    """5. Income-statement depreciation and amortisation expense = R1,500,000,000."""
    st = fy2025_readiness.concept_statuses["depreciation_amortisation_expense"]
    assert st.status == ReadinessStatus.AVAILABLE
    assert st.normalized_value == Decimal("1500000000")
    assert st.normalized_unit == "ZAR"
    assert "1,500" in (st.raw_value or "")
    assert st.source_file == "TRU_FY2025_AFS.pdf"


def test_06_cash_flow_da_exact_extraction(cached_tru_backtest, fy2025_readiness):
    """6. Cash-flow reconciliation depreciation and amortisation addback = R1,526,000,000."""
    st = fy2025_readiness.concept_statuses["depreciation_amortisation_cashflow_addback"]
    assert st.status == ReadinessStatus.AVAILABLE
    assert st.normalized_value == Decimal("1526000000")
    assert st.normalized_unit == "ZAR"
    assert "1,526" in (st.raw_value or "")
    assert st.source_file == "TRU_FY2025_AFS.pdf"


def test_07_da_concepts_remain_distinct(cached_tru_backtest, fy2025_readiness):
    """7. The two D&A concepts remain distinct and the difference equals Note 27.1 distribution D&A."""
    is_da = fy2025_readiness.concept_statuses["depreciation_amortisation_expense"].normalized_value
    cf_da = fy2025_readiness.concept_statuses["depreciation_amortisation_cashflow_addback"].normalized_value
    assert is_da != cf_da
    diff = Decimal(str(cf_da)) - Decimal(str(is_da))
    assert diff == Decimal("26000000")  # R26m difference explained by Note 27.1 Cost of sales distribution depreciation


def test_08_fcff_da_mapping_gate_status(cached_tru_backtest, fy2025_readiness):
    """8. FCFF D&A mapping status is READY_TO_REMAP_FCFF_DA with clear source rationale."""
    assert fy2025_readiness.fcff_da_mapping_status == "READY_TO_REMAP_FCFF_DA"
    assert "R26m" in fy2025_readiness.fcff_da_reconciliation_note
    assert "Note 27.1" in fy2025_readiness.fcff_da_reconciliation_note


def test_09_fy2025_cash_capex_exact_extraction(cached_tru_backtest, fy2025_readiness):
    """9. FY2025 cash capex = R674m (Expansion R428m + Maintenance R187m + Software R59m)."""
    st = fy2025_readiness.concept_statuses["cash_capex"]
    assert st.status == ReadinessStatus.AVAILABLE
    assert st.normalized_value == Decimal("674000000")
    assert st.normalized_unit == "ZAR"


def test_10_capex_semantic_basis_is_cash_capex(cached_tru_backtest, fy2025_readiness):
    """10. Capex semantic basis is confirmed as cash capex (payments basis)."""
    assert fy2025_readiness.capex_basis == "cash_capex"
    st = fy2025_readiness.concept_statuses["cash_capex"]
    assert st.semantic_role == "cash_capital_expenditure"


def test_11_working_capital_cash_inflow_sign():
    """11. Working capital +R166m is interpreted as a cash inflow."""
    wc_inflow = Decimal("166000000")
    # Using the semantic interpreter: positive cash flow converts to negative investment
    wc_change = interpret_working_capital(cash_flow=wc_inflow)
    assert wc_change == Decimal("-166000000")

    # In the FCFF calculation: FCFF = EBIT - cash_tax + D&A - Capex - working_capital_change
    # Subtracting a negative working capital change adds cash to FCFF
    cf = unlevered_fcf(
        ebit=Decimal("1000"),
        tax_rate=Decimal("0.25"),
        depreciation=Decimal("200"),
        total_capex=Decimal("100"),
        working_capital_change=wc_change,
        other_recurring_cash=Decimal("0"),
    )
    # NOPAT = 750, + D&A 200, - Capex 100, - (-166) = +166 -> 750 + 200 - 100 + 166 = 1016
    assert cf["unlevered_fcf"] == Decimal("750") + Decimal("200") - Decimal("100") + wc_inflow


def test_12_net_cash_reconciles_to_r720m(cached_tru_backtest, fy2025_readiness):
    """12. Net cash reconciles to R720m after charitable-trust exclusion."""
    st = fy2025_readiness.concept_statuses["reported_net_cash"]
    assert st.status == ReadinessStatus.AVAILABLE
    assert st.normalized_value == Decimal("720000000")
    assert st.normalized_unit == "ZAR"
    # Provenance note verifies the exact reconstruction formula
    assert "Charitable Trust (14m)" in (st.notes or "")


def test_13_lease_liabilities_exact_extraction(cached_tru_backtest, fy2025_readiness):
    """13. Lease liabilities = R3.742bn (Current R1.045bn + Non-current R2.697bn)."""
    st = fy2025_readiness.concept_statuses["lease_liabilities"]
    assert st.status == ReadinessStatus.AVAILABLE
    assert st.normalized_value == Decimal("3742000000")
    assert st.normalized_unit == "ZAR"


def test_14_period_end_shares_correct(cached_tru_backtest, fy2025_readiness):
    """14. Period-end external shares = 408,498,899 - 33,138,000 = 375,360,899 with Note 13 / Note 14."""
    st = fy2025_readiness.concept_statuses["period_end_external_shares"]
    assert st.status == ReadinessStatus.AVAILABLE
    assert st.normalized_value == Decimal("375360899")
    assert st.normalized_unit == "shares"
    assert st.source_file == "TRU_FY2025_AFS.pdf"
    assert "Note 13" in str(st.page) and "Note 14" in str(st.page)
    assert "Note 13" in str(st.notes) and "Note 14" in str(st.notes)
    # Ensure neither Note 15 nor Note 14 & 15 is used to label Share Capital
    assert "Note 14 & 15" not in str(st.notes)


def test_15_announcement_date_shares_correct(cached_tru_backtest, fy2025_readiness):
    """15. Announcement-date external shares = 408,498,899 - 25,131,064 = 383,367,835 and warning present."""
    st = fy2025_readiness.concept_statuses["announcement_date_external_shares"]
    assert st.status == ReadinessStatus.AVAILABLE
    assert st.normalized_value == Decimal("383367835")
    assert st.normalized_unit == "shares"
    assert st.source_file == "TRU_FY2025_SENS.txt"
    assert st.publication_date == "2025-08-28"
    assert "2025-08-22" not in str(st.notes)
    assert fy2025_readiness.denominator_policy_warning is not None
    assert "383,367,835" in fy2025_readiness.denominator_policy_warning
    assert "375,360,899" in fy2025_readiness.denominator_policy_warning
    assert "2025-08-22" not in fy2025_readiness.denominator_policy_warning
    assert "2025-08-28" in fy2025_readiness.denominator_policy_warning


def test_15b_announcement_treasury_share_provenance(cached_tru_backtest):
    """Verify SENS observation for treasury shares at announcement has date 2025-08-28 and no 2025-08-22."""
    sens_treasury = [
        ev for ev in cached_tru_backtest.evidence_snapshot
        if ev.kind == "treasury_shares" and ev.payload.get("document_role") == RESULTS_SENS
    ]
    assert len(sens_treasury) >= 1
    tr = sens_treasury[0]
    assert tr.payload.get("value") == "25131064" or tr.payload.get("normalized_value") == "25131064"
    assert str(tr.payload.get("source_date") or tr.available_date) == "2025-08-28"
    assert "2025-08-22" not in str(tr.payload)


def test_16_wanos_shares_correct(cached_tru_backtest, fy2025_readiness):
    """16. Weighted-average basic = 374.4m, diluted = 378.8m."""
    basic = fy2025_readiness.concept_statuses["weighted_average_basic_shares"]
    diluted = fy2025_readiness.concept_statuses["weighted_average_diluted_shares"]
    assert basic.status == ReadinessStatus.AVAILABLE
    assert basic.normalized_value == Decimal("374400000")
    assert diluted.status == ReadinessStatus.AVAILABLE
    assert diluted.normalized_value == Decimal("378800000")


def test_17_locked_historical_result_unchanged():
    """17. Verify locked historical valuation result in production DB remains unchanged."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute(
        "SELECT historical_result_id, backtest_id, historical_plan_id, valuation_result, input_hash "
        "FROM historical_backtest_results WHERE historical_result_id = %s",
        (EXPECTED_RESULT_ID,)
    )
    row = cur.fetchone()
    conn.close()
    assert row is not None, "Locked historical result row must exist in DB"
    res_id, bt_id, plan_id, vr, h = row
    if isinstance(vr, str):
        vr = json.loads(vr)

    assert str(res_id) == EXPECTED_RESULT_ID
    assert str(bt_id) == EXPECTED_BACKTEST_ID
    assert str(plan_id) == EXPECTED_PLAN_ID
    assert Decimal(str(vr["historical_fair_value"])) == EXPECTED_FAIR_VALUE
    assert Decimal(str(vr["enterprise_value"])) == EXPECTED_EV
    assert Decimal(str(vr["equity_value"])) == EXPECTED_EQUITY_VALUE
    assert h == EXPECTED_FROZEN_HASH


def test_18_frozen_input_hash_unchanged():
    """18. Verify frozen input hash is exactly ccf6a05b... in both backtest and result tables."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute(
        "SELECT backtest_id, status, input_hash FROM historical_backtests WHERE backtest_id = %s",
        (EXPECTED_BACKTEST_ID,)
    )
    row_bt = cur.fetchone()
    conn.close()
    assert row_bt is not None
    assert row_bt[2] == EXPECTED_FROZEN_HASH
    assert row_bt[1] in {"locked", "completed"}


def test_readiness_report_output_complete(cached_tru_backtest):
    """Verify that render_historical_readiness_report contains all 15 concepts and provenance fields."""
    report = render_historical_readiness_report(cached_tru_backtest)
    required = [
        "accounting_revenue",
        "sale_of_merchandise",
        "trading_profit",
        "trading_margin",
        "depreciation_amortisation_expense",
        "depreciation_amortisation_cashflow_addback",
        "cash_capex",
        "working_capital_cash_flow",
        "effective_tax_rate",
        "reported_net_cash",
        "lease_liabilities",
        "period_end_external_shares",
        "announcement_date_external_shares",
        "weighted_average_basic_shares",
        "weighted_average_diluted_shares",
        "TRU_FY2025_AFS.pdf",
        "TRU_FY2025_SENS.txt",
        "2025-08-28",
        "READY_TO_REMAP_FCFF_DA",
        "positive_cash_inflow",
        "cash_capex"
    ]
    for req in required:
        assert req in report, f"Expected '{req}' in readiness report"
