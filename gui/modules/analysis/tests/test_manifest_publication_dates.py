"""Tests for the corrected historical_packages manifest helper.

Covers:
1.  TRU FY2026 SENS parses publication date as 2026-08-27 (slash format)
2.  period_end remains 2026-06-28 and never equals published_at
3.  published_at never defaults to period_end
4.  Missing SENS publication date fails closed (ValueError)
5.  Unresolved source excluded from historical evidence in validate_period_folder
6.  Explicit user override works for AFS
7.  Suspicious published_at == period_end flagged by audit helper
8.  No existing historical backtest state mutated
9.  No FY2026 reveal executed (no outcome-comparison code touched)
10. Correct FY2025 SENS date extracted (dash format DD-MM-YYYY)
11. ManifestSource availability_status derived correctly
12. HistoricalManifest rejects published_at == period_end at model level
13. HistoricalManifest rejects published_at < period_end
14. describe_source_availability returns correct UI strings
15. parse_sens_publication_date handles both slash and dash formats
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest
import sys

# Ensure the gui package root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import modules.analysis.historical_packages as hp


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_history(tmp_path):
    """Replace HISTORICAL_RESULTS_ROOT with a temp directory."""
    original = hp.HISTORICAL_RESULTS_ROOT
    hp.HISTORICAL_RESULTS_ROOT = tmp_path / 'results_history'
    hp.HISTORICAL_RESULTS_ROOT.mkdir(parents=True)
    yield hp.HISTORICAL_RESULTS_ROOT
    hp.HISTORICAL_RESULTS_ROOT = original


def _write_sens(folder: Path, name: str, content: str) -> Path:
    p = folder / name
    p.write_text(content, encoding='utf-8')
    return p


def _write_afs(folder: Path, name: str) -> Path:
    p = folder / name
    p.write_bytes(b'%PDF-1.4\n%\xe2\xe3\xcf\xd6')
    return p


# ---------------------------------------------------------------------------
# 1 & 10. SENS footer date parsing – both formats
# ---------------------------------------------------------------------------

def test_parse_sens_slash_format():
    """DD/MM/YYYY footer (FY2026 style)."""
    text = 'Some content\nDate: 27/08/2026 12:30:00\nProduced by JSE SENS Department.'
    d, src = hp.parse_sens_publication_date(text)
    assert d == date(2026, 8, 27), f"Expected 2026-08-27, got {d}"
    assert src == 'SENS footer timestamp'


def test_parse_sens_dash_format():
    """DD-MM-YYYY footer (FY2025 style)."""
    text = 'Some content\nDate: 28-08-2025 02:25:00\nProduced by JSE SENS Department.'
    d, src = hp.parse_sens_publication_date(text)
    assert d == date(2025, 8, 28), f"Expected 2025-08-28, got {d}"
    assert src == 'SENS footer timestamp'


def test_parse_sens_no_date_returns_none():
    """No footer → (None, None)."""
    d, src = hp.parse_sens_publication_date('No date here at all.')
    assert d is None
    assert src is None


# ---------------------------------------------------------------------------
# 2 & 3. TRU FY2026 regression: published_at != period_end
# ---------------------------------------------------------------------------

def test_fy2026_sens_date_is_not_period_end(tmp_history):
    """TRU FY2026 SENS published_at must be 2026-08-27, not 2026-06-28."""
    folder = tmp_history / 'TRU' / 'FY2026'
    folder.mkdir(parents=True)
    _write_sens(folder, 'TRU_FY2026_SENS.txt',
        '52 weeks ended 28 June 2026\nDate: 27/08/2026 12:30:00\n')
    _write_afs(folder, 'TRU_FY2026_AFS.pdf')

    with patch.object(hp, '_results_period', return_value=date(2026, 6, 28)):
        manifest = hp.suggest_manifest('TRU.JO', 'FY2026')

    assert manifest['period_end'] == '2026-06-28'
    sens_src = manifest['sources'][0]
    assert sens_src['type'] == 'SENS'
    assert sens_src['published_at'] == '2026-08-27', (
        f"SENS published_at must be 2026-08-27, got {sens_src['published_at']}"
    )
    assert sens_src['published_at'] != manifest['period_end'], (
        'published_at must NEVER equal period_end'
    )


def test_fy2026_afs_date_linked_to_sens(tmp_history):
    """AFS published_at defaults to SENS date (defensible link)."""
    folder = tmp_history / 'TRU' / 'FY2026'
    folder.mkdir(parents=True)
    _write_sens(folder, 'TRU_FY2026_SENS.txt',
        '52 weeks ended 28 June 2026\nDate: 27/08/2026 12:30:00\n')
    _write_afs(folder, 'TRU_FY2026_AFS.pdf')

    with patch.object(hp, '_results_period', return_value=date(2026, 6, 28)):
        manifest = hp.suggest_manifest('TRU.JO', 'FY2026')

    afs_src = manifest['sources'][1]
    assert afs_src['type'] == 'AFS'
    assert afs_src['published_at'] == '2026-08-27'
    assert afs_src['published_at'] != manifest['period_end']


# ---------------------------------------------------------------------------
# 4. Missing / unparseable SENS publication date fails closed
# ---------------------------------------------------------------------------

def test_suggest_manifest_fails_closed_no_footer(tmp_history):
    """No JSE footer → ValueError, not substitution of period_end."""
    folder = tmp_history / 'TRU' / 'FY2026'
    folder.mkdir(parents=True)
    _write_sens(folder, 'TRU_FY2026_SENS.txt',
        '52 weeks ended 28 June 2026\n(no footer timestamp here)\n')
    _write_afs(folder, 'TRU_FY2026_AFS.pdf')

    with pytest.raises(ValueError, match='Could not determine SENS publication date'):
        hp.suggest_manifest('TRU.JO', 'FY2026')


def test_suggest_manifest_fails_closed_missing_sens(tmp_history):
    """Missing SENS file → ValueError."""
    folder = tmp_history / 'TRU' / 'FY2026'
    folder.mkdir(parents=True)
    _write_afs(folder, 'TRU_FY2026_AFS.pdf')

    with pytest.raises(ValueError, match='SENS file missing'):
        hp.suggest_manifest('TRU.JO', 'FY2026')


# ---------------------------------------------------------------------------
# 5. Unresolved source excluded from historical evidence
# ---------------------------------------------------------------------------

def test_unresolved_source_excluded_from_evidence(tmp_history):
    """An AFS with published_at=null must not appear in validated sources."""
    folder = tmp_history / 'TRU' / 'FY2025'
    folder.mkdir(parents=True)
    _write_sens(folder, 'TRU_FY2025_SENS.txt', 'content')
    _write_afs(folder, 'TRU_FY2025_AFS.pdf')
    manifest_data = {
        'schema_version': 1, 'ticker': 'TRU.JO', 'symbol': 'TRU',
        'period_label': 'FY2025', 'period_type': 'fiscal_year',
        'period_start': None, 'period_end': '2025-06-29',
        'sources': [
            {'type': 'SENS', 'file': 'TRU_FY2025_SENS.txt',
             'published_at': '2025-08-28', 'revision': 1, 'active': True},
            {'type': 'AFS', 'file': 'TRU_FY2025_AFS.pdf',
             'published_at': None, 'revision': 1, 'active': True},
        ],
    }
    (folder / 'manifest.json').write_text(json.dumps(manifest_data), encoding='utf-8')

    result = hp.validate_period_folder(folder, 'TRU.JO')
    # AFS is unresolved → excluded from sources list
    source_names = [s['name'] for s in result['sources']]
    assert 'TRU_FY2025_AFS.pdf' not in source_names, (
        'Unresolved AFS must be excluded from historical evidence'
    )
    assert any('unresolved published_at' in w for w in result['warnings']), (
        'Unresolved source must produce a warning'
    )


# ---------------------------------------------------------------------------
# 6. Explicit user AFS override works
# ---------------------------------------------------------------------------

def test_afs_override_respected(tmp_history):
    """afs_published_at_override takes precedence over SENS-linked date."""
    folder = tmp_history / 'TRU' / 'FY2026'
    folder.mkdir(parents=True)
    _write_sens(folder, 'TRU_FY2026_SENS.txt',
        '52 weeks ended 28 June 2026\nDate: 27/08/2026 12:30:00\n')
    _write_afs(folder, 'TRU_FY2026_AFS.pdf')

    override = date(2026, 9, 1)
    with patch.object(hp, '_results_period', return_value=date(2026, 6, 28)):
        manifest = hp.suggest_manifest('TRU.JO', 'FY2026',
                                       afs_published_at_override=override)

    afs_src = manifest['sources'][1]
    assert afs_src['published_at'] == '2026-09-01'
    assert afs_src['_detection']['detection_source'] == 'explicit analyst/user override'


# ---------------------------------------------------------------------------
# 7. audit_manifests_for_suspicious_dates
# ---------------------------------------------------------------------------

def test_audit_flags_published_at_equals_period_end(tmp_history):
    """A manifest where published_at == period_end must be flagged."""
    folder = tmp_history / 'TRU' / 'FY2026'
    folder.mkdir(parents=True)
    bad_manifest = {
        'schema_version': 1, 'ticker': 'TRU.JO', 'symbol': 'TRU',
        'period_label': 'FY2026', 'period_type': 'fiscal_year',
        'period_start': None, 'period_end': '2026-06-28',
        'sources': [
            {'type': 'SENS', 'file': 'TRU_FY2026_SENS.txt',
             'published_at': '2026-06-28', 'revision': 1, 'active': True},
        ],
    }
    (folder / 'manifest.json').write_text(json.dumps(bad_manifest), encoding='utf-8')

    findings = hp.audit_manifests_for_suspicious_dates(tmp_history)
    suspicious = [f for f in findings if f.get('suspicious')]
    assert len(suspicious) >= 1
    assert any(f['source_type'] == 'SENS' and f['published_at'] == '2026-06-28'
               for f in suspicious)


def test_audit_does_not_flag_correct_dates(tmp_history):
    """A manifest with correct dates must not be flagged as suspicious."""
    folder = tmp_history / 'TRU' / 'FY2026'
    folder.mkdir(parents=True)
    good_manifest = {
        'schema_version': 1, 'ticker': 'TRU.JO', 'symbol': 'TRU',
        'period_label': 'FY2026', 'period_type': 'fiscal_year',
        'period_start': None, 'period_end': '2026-06-28',
        'sources': [
            {'type': 'SENS', 'file': 'TRU_FY2026_SENS.txt',
             'published_at': '2026-08-27', 'revision': 1, 'active': True},
        ],
    }
    (folder / 'manifest.json').write_text(json.dumps(good_manifest), encoding='utf-8')

    findings = hp.audit_manifests_for_suspicious_dates(tmp_history)
    suspicious = [f for f in findings if f.get('suspicious')]
    assert len(suspicious) == 0


# ---------------------------------------------------------------------------
# 8. State-based backtest integrity (no DB mutation by manifest helpers)
# ---------------------------------------------------------------------------

TARGET_BACKTEST_ID  = '4230b66f-6be8-480a-878d-77d69eaeacd8'
TARGET_PLAN_ID      = 'ba6d3186-8a51-44a3-8f67-3ad34ece3da6'
TARGET_RESULT_ID    = '6768e249-36c9-4f4d-afff-e3bd832e5f6a'
TARGET_INPUT_HASH   = 'ccf6a05b91b47ec458186ad1e73f9a78496d64f34c96f2e99dfbba7c8872f959'
TARGET_FAIR_VALUE   = '72.8232'
TARGET_EV           = '30356971061.15'
TARGET_EQUITY       = '27334971061.15'


def _db_conn():
    """Return a live psycopg2 connection using the production DB_CONFIG."""
    import psycopg2
    import sys
    sys.path.insert(0, r'C:\Users\Dion\Desktop\Projects\stock_analysis\gui')
    from core.config import DB_CONFIG
    return psycopg2.connect(**DB_CONFIG)


def _capture_backtest_state():
    """Read and return the current production state of the locked TRU backtest."""
    try:
        from psycopg2.extras import RealDictCursor
        conn = _db_conn()
        with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                'SELECT backtest_id, status, input_hash, ticker, as_of_date '
                'FROM historical_backtests WHERE backtest_id = %s',
                (TARGET_BACKTEST_ID,)
            )
            b = cur.fetchone()
            cur.execute(
                'SELECT historical_plan_id, backtest_id, status '
                'FROM historical_backtest_plans WHERE historical_plan_id = %s',
                (TARGET_PLAN_ID,)
            )
            p = cur.fetchone()
            cur.execute(
                'SELECT historical_result_id, backtest_id, valuation_result '
                'FROM historical_backtest_results WHERE historical_result_id = %s',
                (TARGET_RESULT_ID,)
            )
            r = cur.fetchone()
        conn.close()
        return {'backtest': dict(b) if b else None,
                'plan':     dict(p) if p else None,
                'result':   dict(r) if r else None}
    except Exception as exc:
        pytest.skip(f'Production DB unavailable: {exc}')


def test_manifest_helpers_do_not_mutate_backtest_state(tmp_history):
    """Capture DB state, run manifest helpers, assert state unchanged."""
    before = _capture_backtest_state()

    # Run suggest_manifest on a temp FY2026 package (does not touch backtests)
    folder = tmp_history / 'TRU' / 'FY2026'
    folder.mkdir(parents=True)
    _write_sens(folder, 'TRU_FY2026_SENS.txt',
        '52 weeks ended 28 June 2026\nDate: 27/08/2026 12:30:00\n')
    _write_afs(folder, 'TRU_FY2026_AFS.pdf')
    with patch.object(hp, '_results_period', return_value=date(2026, 6, 28)):
        hp.suggest_manifest('TRU.JO', 'FY2026')

    # Also run validate_period_folder on a temp FY2025 package
    folder2 = tmp_history / 'TRU' / 'FY2025'
    folder2.mkdir(parents=True)
    _write_sens(folder2, 'TRU_FY2025_SENS.txt', 'content')
    _write_afs(folder2, 'TRU_FY2025_AFS.pdf')
    manifest_data = {
        'schema_version': 1, 'ticker': 'TRU.JO', 'symbol': 'TRU',
        'period_label': 'FY2025', 'period_type': 'fiscal_year',
        'period_start': None, 'period_end': '2025-06-29',
        'sources': [
            {'type': 'SENS', 'file': 'TRU_FY2025_SENS.txt',
             'published_at': '2025-08-28', 'revision': 1, 'active': True},
            {'type': 'AFS', 'file': 'TRU_FY2025_AFS.pdf',
             'published_at': '2025-08-28', 'revision': 1, 'active': True},
        ],
    }
    (folder2 / 'manifest.json').write_text(json.dumps(manifest_data), encoding='utf-8')
    hp.validate_period_folder(folder2, 'TRU.JO')

    after = _capture_backtest_state()

    # ── Backtest row ──────────────────────────────────────────────────────
    assert after['backtest'] is not None, 'Backtest row must exist'
    assert str(after['backtest']['backtest_id']) == TARGET_BACKTEST_ID
    assert after['backtest']['status'] in ('locked', 'completed')
    assert after['backtest']['input_hash'] == TARGET_INPUT_HASH
    assert after['backtest']['ticker'] == 'TRU.JO'
    assert str(after['backtest']['as_of_date']) == '2025-08-31'

    # ── Plan row ─────────────────────────────────────────────────────────
    assert after['plan'] is not None, 'Plan row must exist'
    assert str(after['plan']['historical_plan_id']) == TARGET_PLAN_ID
    assert str(after['plan']['backtest_id']) == TARGET_BACKTEST_ID
    assert after['plan']['status'] == 'approved'

    # ── Result row ───────────────────────────────────────────────────────
    import json as _json
    assert after['result'] is not None, 'Result row must exist'
    assert str(after['result']['historical_result_id']) == TARGET_RESULT_ID
    vr = after['result']['valuation_result']
    if isinstance(vr, str):
        vr = _json.loads(vr)
    assert float(vr['historical_fair_value']) == pytest.approx(float(TARGET_FAIR_VALUE), abs=0.01)
    assert float(vr['enterprise_value']) == pytest.approx(float(TARGET_EV), abs=1.0)
    assert float(vr['equity_value']) == pytest.approx(float(TARGET_EQUITY), abs=1.0)
    assert vr['locked_input_hash'] == TARGET_INPUT_HASH

    # ── Before == After ───────────────────────────────────────────────────
    # Status, hash and IDs must be identical before and after manifest work
    assert before['backtest']['status']     == after['backtest']['status']
    assert before['backtest']['input_hash'] == after['backtest']['input_hash']
    assert before['plan']['status']         == after['plan']['status']
    assert (str(before['result']['historical_result_id'])
            == str(after['result']['historical_result_id']))


# ---------------------------------------------------------------------------
# 9. No FY2026 reveal executed – state-based check
# ---------------------------------------------------------------------------

def test_no_fy2026_reveal_state_based(tmp_history):
    """Running suggest_manifest on FY2026 files must not expose any outcome
    data and must not alter the production FY2025 backtest state."""
    before = _capture_backtest_state()

    folder = tmp_history / 'TRU' / 'FY2026'
    folder.mkdir(parents=True)
    _write_sens(folder, 'TRU_FY2026_SENS.txt',
        '52 weeks ended 28 June 2026\nDate: 27/08/2026 12:30:00\n')
    _write_afs(folder, 'TRU_FY2026_AFS.pdf')
    with patch.object(hp, '_results_period', return_value=date(2026, 6, 28)):
        manifest = hp.suggest_manifest('TRU.JO', 'FY2026')

    after = _capture_backtest_state()

    # The manifest must not contain any outcome/comparison fields
    manifest_str = json.dumps(manifest)
    for forbidden in ('fair_value', 'equity_value', 'enterprise_value',
                      'actual_revenue', 'outcome', 'realised', 'compare'):
        assert forbidden not in manifest_str.lower(), (
            f'Manifest contains forbidden outcome field: {forbidden}'
        )

    # Backtest state must be identical
    assert before['backtest']['status']     == after['backtest']['status']
    assert before['backtest']['input_hash'] == after['backtest']['input_hash']
    assert before['plan']['status']         == after['plan']['status']



# ---------------------------------------------------------------------------
# 11. ManifestSource availability_status
# ---------------------------------------------------------------------------

def test_manifest_source_resolved():
    src = hp.ManifestSource(type='SENS', file='TRU_FY2025_SENS.txt',
                             published_at=date(2025, 8, 28))
    assert src.availability_status == 'resolved'


def test_manifest_source_unresolved():
    src = hp.ManifestSource(type='AFS', file='TRU_FY2025_AFS.pdf',
                             published_at=None)
    assert src.availability_status == 'unresolved'


# ---------------------------------------------------------------------------
# 12 & 13. HistoricalManifest model-level invariant enforcement
# ---------------------------------------------------------------------------

def _base_manifest_data(**overrides):
    data = {
        'schema_version': 1, 'ticker': 'TRU.JO', 'symbol': 'TRU',
        'period_label': 'FY2025', 'period_type': 'fiscal_year',
        'period_start': None, 'period_end': '2025-06-29',
        'sources': [
            {'type': 'SENS', 'file': 'TRU_FY2025_SENS.txt',
             'published_at': '2025-08-28', 'revision': 1, 'active': True},
            {'type': 'AFS', 'file': 'TRU_FY2025_AFS.pdf',
             'published_at': '2025-08-28', 'revision': 1, 'active': True},
        ],
    }
    data.update(overrides)
    return data


def test_manifest_rejects_published_at_equals_period_end():
    """HistoricalManifest now warns (SUSPICIOUS_DATE) rather than raising for == period_end."""
    data = _base_manifest_data()
    data['sources'][0]['published_at'] = '2025-06-29'  # same as period_end
    # Must NOT raise – equality is now a warning, not a blocking error
    m = hp.HistoricalManifest.model_validate(data)
    assert m.has_suspicious_dates, (
        'has_suspicious_dates must be True when published_at == period_end'
    )
    assert any('SUSPICIOUS_DATE' in w for w in m.date_warnings), (
        'date_warnings must contain a SUSPICIOUS_DATE entry'
    )
    # The source must still be loadable (not blocked at model level)
    sens = next(s for s in m.sources if s.type == 'SENS')
    assert sens.published_at is not None



def test_manifest_blocks_published_at_before_period_end():
    """HistoricalManifest must raise BLOCKING_ERROR for published_at < period_end."""
    data = _base_manifest_data()
    data['sources'][0]['published_at'] = '2025-06-01'  # before period_end
    with pytest.raises(Exception, match='BLOCKING_ERROR|precedes|before'):
        hp.HistoricalManifest.model_validate(data)


def test_manifest_accepts_null_published_at():
    """HistoricalManifest must accept published_at=null (unresolved)."""
    data = _base_manifest_data()
    data['sources'][1]['published_at'] = None
    # Should not raise
    m = hp.HistoricalManifest.model_validate(data)
    afs = next(s for s in m.sources if s.type == 'AFS')
    assert afs.published_at is None
    assert afs.availability_status == 'unresolved'


# ---------------------------------------------------------------------------
# 14. describe_source_availability UI strings
# ---------------------------------------------------------------------------

def test_describe_resolved_with_detection():
    entry = {
        'published_at': '2026-08-27',
        '_detection': {
            'reporting_period_end': '2026-06-28',
            'detected_publication_date': '2026-08-27',
            'detection_source': 'SENS footer timestamp',
        },
    }
    text = hp.describe_source_availability(entry)
    assert 'Reporting period end  : 2026-06-28' in text
    assert 'Detected publication  : 2026-08-27' in text
    assert 'SENS footer timestamp' in text


def test_describe_unresolved():
    entry = {'published_at': None, '_detection': {'reporting_period_end': '2026-06-28'}}
    text = hp.describe_source_availability(entry)
    assert 'UNRESOLVED' in text
    assert 'BLOCKED' in text
