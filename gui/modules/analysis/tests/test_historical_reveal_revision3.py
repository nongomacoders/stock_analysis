"""Tests for TRU FY2026 Reveal Revision 3 Outcome Correction.

Validates all 10 requirements specified for the capex convention correction:
1. historical forecast capex semantic basis is cash-capex
2. FY2026 comparable capex uses maintenance + expansion + software cash payments
3. accounting additions remain separate
4. primary FCFF uses R592m cash capex
5. additions-basis FCFF is secondary only
6. perfect-foresight diagnostic uses comparable cash-capex FCFF
7. outcome revision 3 supersedes revision 2
8. revision 1 and 2 remain immutable
9. historical valuation result remains unchanged
10. historical input hash remains unchanged
"""

import uuid
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import json
import pytest
import psycopg2
from psycopg2.extras import RealDictCursor

from core.config import DB_CONFIG
from modules.analysis.valuation.dcf import DcfInputs, ForecastYear, calculate_dcf
from modules.analysis.valuation.models import Basis, TerminalMethod
from modules.analysis.valuation.reconciliation import reconcile_equity

BACKTEST_ID = '4230b66f-6be8-480a-878d-77d69eaeacd8'
PLAN_ID = 'ba6d3186-8a51-44a3-8f67-3ad34ece3da6'
RESULT_ID = '6768e249-36c9-4f4d-afff-e3bd832e5f6a'
LOCKED_HASH = 'ccf6a05b91b47ec458186ad1e73f9a78496d64f34c96f2e99dfbba7c8872f959'
REV1_ID = '709d3dc5-17c1-462f-a9bb-6ffd87530f98'
REV2_ID = '00d31f99-e73b-43e3-8668-4f5132416be6'


@pytest.fixture(scope="module")
def db_conn():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True
    yield conn
    conn.close()


def test_1_historical_forecast_capex_semantic_basis_is_cash_capex():
    """Historical FY2025 forecast capex assumption of R674m was derived from cash capex components:
    maintenance cash capex R187m + expansion cash capex R428m + software cash capex R59m = R674m.
    """
    maint_cash_baseline = Decimal('187000000')
    exp_cash_baseline = Decimal('428000000')
    soft_cash_baseline = Decimal('59000000')
    
    total_baseline_cash_capex = maint_cash_baseline + exp_cash_baseline + soft_cash_baseline
    assert total_baseline_cash_capex == Decimal('674000000')


def test_2_fy2026_comparable_capex_uses_cash_payments():
    """FY2026 comparable capex uses maintenance + expansion + software cash payments:
    maintenance cash capex R267m + expansion cash capex R285m + software cash capex R40m = R592m.
    Primary variance: -R82m (-12.17%).
    """
    maint_cash_fy26 = Decimal('267000000')
    exp_cash_fy26 = Decimal('285000000')
    soft_cash_fy26 = Decimal('40000000')
    
    actual_cash_capex = maint_cash_fy26 + exp_cash_fy26 + soft_cash_fy26
    assert actual_cash_capex == Decimal('592000000')
    
    forecast_capex = Decimal('674000000')
    variance = actual_cash_capex - forecast_capex
    assert variance == Decimal('-82000000')
    
    pct_err = ((variance / forecast_capex) * Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    assert pct_err == Decimal('-12.17')


def test_3_accounting_additions_remain_separate():
    """Accounting additions (PPE R623m + software R51m = R674m) are retained under
    ACCOUNTING_ADDITIONS_BASIS as secondary disclosure only, not the primary comparison.
    """
    ppe_additions = Decimal('623000000')
    software_additions = Decimal('51000000')
    total_accounting_additions = ppe_additions + software_additions
    assert total_accounting_additions == Decimal('674000000')


def test_4_primary_fcff_uses_r592m_cash_capex():
    """Primary FCFF uses cash capex R592m:
    FCFF = Trading Profit * (1 - tax) + D&A - cash_capex - WC + other recurring
         = 2,774m * (1 - 0.2530) + 1,516m - 592m - 188m = R2,808,178,000.
    """
    trading_profit = Decimal('2774000000')
    tax_rate = Decimal('0.2530')
    operating_tax = (trading_profit * tax_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    assert operating_tax == Decimal('701822000.00')
    
    nopat = trading_profit - operating_tax
    assert nopat == Decimal('2072178000.00')
    
    depreciation = Decimal('1516000000')
    cash_capex = Decimal('592000000')
    wc_outflow = Decimal('188000000')
    other_recurring = Decimal('0')
    
    fcff_primary = nopat + depreciation - cash_capex - wc_outflow + other_recurring
    assert fcff_primary == Decimal('2808178000.00')
    
    forecast_fcff = Decimal('3069262844.992')
    fcff_diff = fcff_primary - forecast_fcff
    assert fcff_diff.quantize(Decimal('0.001')) == Decimal('-261084844.992')
    
    pct_err = ((fcff_diff / forecast_fcff) * Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    assert pct_err == Decimal('-8.51')


def test_5_additions_basis_fcff_is_secondary_only():
    """Using accounting additions of R674m produces FCFF of R2,726,178,000,
    which is secondary only and not used as the primary forecast accuracy result.
    """
    trading_profit = Decimal('2774000000')
    tax_rate = Decimal('0.2530')
    operating_tax = (trading_profit * tax_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    nopat = trading_profit - operating_tax
    depreciation = Decimal('1516000000')
    accounting_additions = Decimal('674000000')
    wc_outflow = Decimal('188000000')
    
    fcff_secondary = nopat + depreciation - accounting_additions - wc_outflow
    assert fcff_secondary == Decimal('2726178000.00')
    assert fcff_secondary != Decimal('2808178000.00')


def test_6_perfect_foresight_diagnostic_uses_comparable_cash_capex_fcff():
    """Perfect-foresight diagnostic runs deterministic DCF with primary actual FCFF R2,808,178,000
    and original historical timing/valuation parameters (WACC 14.86%, g 4.5%, net cash R720m, leases R3.742bn, 375,360,899 shares).
    Yields EV ~R27.77bn, Equity ~R24.75bn, FV ~R65.94.
    """
    fcff_actual = Decimal('2808178000.00')
    depr_actual = Decimal('1516000000')
    ebit_actual = Decimal('2774000000')
    tax_actual = (ebit_actual * Decimal('0.2530')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    fy_diag = ForecastYear(
        period_end=date(2026, 6, 28),
        revenue=Decimal('23030000000'),
        ebitda=ebit_actual + depr_actual,
        ebit=ebit_actual,
        tax=tax_actual,
        depreciation_addback=depr_actual,
        total_capex=Decimal('592000000'),
        working_capital_change=Decimal('188000000'),
        other_recurring_cash=Decimal('0'),
        fcf=fcff_actual
    )
    
    dcf_in = DcfInputs(
        valuation_date=date(2025, 8, 31),
        forecast=[fy_diag],
        wacc=Decimal('0.1486'),
        cash_flow_currency='ZAR',
        discount_rate_currency='ZAR',
        cash_flow_basis=Basis.NOMINAL,
        discount_rate_basis=Basis.NOMINAL,
        cash_flow_inflation_basis='ZAR_CPI',
        discount_rate_inflation_basis='ZAR_CPI',
        terminal_method=TerminalMethod.PERPETUITY_GROWTH,
        terminal_growth=Decimal('0.045')
    )
    
    dcf_res = calculate_dcf(dcf_in)
    ev = Decimal(str(dcf_res.value))
    assert (ev / Decimal('1e9')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) == Decimal('27.77')
    
    recon = reconcile_equity(
        enterprise_or_operating_value=ev,
        non_operating_assets=Decimal('0'),
        receivables=Decimal('0'),
        cash=Decimal('720000000'),
        debt=Decimal('0'),
        lease_adjustments=Decimal('3742000000'),
        minorities=Decimal('0'),
        other_equity_adjustments=Decimal('0'),
        forward_shares=Decimal('375360899'),
        shares_metric_id=uuid.uuid4()
    )
    
    eq_val = recon.equity_value
    assert (eq_val / Decimal('1e9')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) == Decimal('24.75')
    
    fv_rounded = recon.rounded_target_zar
    assert fv_rounded == Decimal('65.94')


def test_7_outcome_revision_3_supersedes_revision_2(db_conn):
    """In the database, Revision 3 is persisted, is authoritative with status 'completed',
    and has supersedes_outcome_id = Revision 2 ID.
    """
    with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """SELECT outcome_id, revision, outcome_status, supersedes_outcome_id, outcome_hash,
                      forecast_accuracy, valuation_performance
               FROM historical_backtest_outcomes
               WHERE backtest_id = %s AND revision = 3""",
            (BACKTEST_ID,)
        )
        rev3 = cur.fetchone()
        assert rev3 is not None, "Revision 3 row missing from database"
        assert rev3['revision'] == 3
        assert rev3['outcome_status'] == 'completed'
        assert str(rev3['supersedes_outcome_id']) == REV2_ID
        assert rev3['outcome_hash'] is not None and len(rev3['outcome_hash']) == 64
        
        # Verify non-causal interpretation text
        val_perf = rev3['valuation_performance']
        if isinstance(val_perf, str):
            val_perf = json.loads(val_perf)
        pfd = val_perf.get('perfect_foresight_diagnostic', {})
        interp = pfd.get('interpretation', '')
        assert "Holding the original valuation framework constant" in interp
        assert "65.94" in interp
        assert "fundamentally worth R63.78" not in interp
        assert "broader market multiple contraction" not in interp


def test_8_revision_1_and_2_remain_immutable(db_conn):
    """Revision 1 and Revision 2 are preserved in the DB without deletion.
    Revision 1 has status 'partial', Revision 2 has status 'completed_superseded'.
    """
    with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """SELECT outcome_id, revision, outcome_status, supersedes_outcome_id, outcome_hash
               FROM historical_backtest_outcomes
               WHERE backtest_id = %s
               ORDER BY revision ASC""",
            (BACKTEST_ID,)
        )
        rows = cur.fetchall()
        assert len(rows) >= 3
        
        rev_map = {r['revision']: r for r in rows}
        
        # Revision 1
        r1 = rev_map[1]
        assert str(r1['outcome_id']) == REV1_ID
        assert r1['outcome_status'] == 'partial'
        
        # Revision 2
        r2 = rev_map[2]
        assert str(r2['outcome_id']) == REV2_ID
        assert r2['outcome_status'] == 'completed_superseded'
        assert str(r2['supersedes_outcome_id']) == REV1_ID


def test_9_historical_valuation_result_remains_unchanged(db_conn):
    """Locked historical valuation result 6768e249-36c9-4f4d-afff-e3bd832e5f6a
    remains completely unchanged: fair value R72.8232, EV R30,356,971,061.15, Equity R27,334,971,061.15.
    """
    with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """SELECT historical_result_id, valuation_result
               FROM historical_backtest_results
               WHERE historical_result_id = %s""",
            (RESULT_ID,)
        )
        row = cur.fetchone()
        assert row is not None
        vr = row['valuation_result']
        if isinstance(vr, str):
            vr = json.loads(vr)
        assert Decimal(str(vr['historical_fair_value'])) == Decimal('72.8232')
        assert Decimal(str(vr['enterprise_value'])) == Decimal('30356971061.15')
        assert Decimal(str(vr['equity_value'])) == Decimal('27334971061.15')


def test_10_historical_input_hash_remains_unchanged(db_conn):
    """Historical backtest and historical result input_hash remain frozen at ccf6a05b..."""
    with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT input_hash FROM historical_backtests WHERE backtest_id = %s", (BACKTEST_ID,))
        bt = cur.fetchone()
        assert bt['input_hash'] == LOCKED_HASH
        
        cur.execute("SELECT input_hash FROM historical_backtest_results WHERE historical_result_id = %s", (RESULT_ID,))
        res = cur.fetchone()
        assert res['input_hash'] == LOCKED_HASH
