"""Tests for suggest_manifest - simplified to focus on classification and date extraction."""
import json
from datetime import date
import pytest
from pathlib import Path
from unittest.mock import patch
import sys

# Ensure historical_packages module is loaded
original_path = sys.path[:]
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import modules.analysis.historical_packages as hp

@pytest.fixture
def tmp_history_root(tmp_path):
 """Temporarily replace HISTORICAL_RESULTS_ROOT with a temp path."""
 original = hp.HISTORICAL_RESULTS_ROOT
 try:
  hp.HISTORICAL_RESULTS_ROOT = Path(tmp_path) / 'results_history'
  yield hp.HISTORICAL_RESULTS_ROOT
 finally:
  hp.HISTORICAL_RESULTS_ROOT = original

def test_suggest_manifest_basic_classification(tmp_history_root):
 """Test suggest_manifest with realistic SENS and AFS content."""
 tmp_folder = hp.HISTORICAL_RESULTS_ROOT / 'TRU' / 'FY2025'
 tmp_folder.mkdir(parents=True)
 sens = tmp_folder / 'TRU_FY2025_SENS.txt'
 # Write realistic SENS content with date patterns
 sens.write_text('"""SENS SENS Announcement"""\nDate: 28-08-2025\n52 weeks ended 29 June 2025')
 afs = tmp_folder / 'TRU_FY2025_AFS.pdf'
 # Write binary PDF marker that PyPDF2 can parse
 afs.write_bytes(b'%PDF-1.4\n%\xe2\xe3\xcf\xd6')
 manifest = hp.suggest_manifest('TRU.JO', 'FY2025', force_afs_date_override=True)
 assert manifest['ticker'] == 'TRU.JO'
 assert manifest['period_label'] == 'FY2025'
 assert manifest['period_end'] == '2025-06-29'
 assert manifest['sources'][0]['type'] == 'SENS'
 assert manifest['sources'][0]['file'] == 'TRU_FY2025_SENS.txt'
 assert manifest['sources'][0]['published_at'] == '2025-08-28'
 assert manifest['sources'][1]['type'] == 'AFS'
 assert manifest['sources'][1]['file'] == 'TRU_FY2025_AFS.pdf'
 assert manifest['sources'][1]['published_at'] == '2025-08-28'

def test_suggest_manifest_sens_date_extracted(tmp_history_root):
 """When SENS has no footer date, suggest_manifest now fails closed (no fallback)."""
 tmp_folder = hp.HISTORICAL_RESULTS_ROOT / 'TRU' / 'FY2025'
 tmp_folder.mkdir(parents=True)
 sens = tmp_folder / 'TRU_FY2025_SENS.txt'
 sens.write_text('No date here, just content')
 afs = tmp_folder / 'TRU_FY2025_AFS.pdf'
 afs.write_bytes(b'%PDF-1.4\n%\xe2\xe3\xcf\xd6')
 # New behaviour: fail closed when no footer date found, even with force_afs_date_override.
 with patch.object(hp, '_results_period', return_value=date(2025,6,29)):
  with pytest.raises(ValueError, match='Could not determine SENS publication date'):
   hp.suggest_manifest('TRU.JO', 'FY2025', force_afs_date_override=True)

def test_suggest_manifest_sens_date_available(tmp_history_root):
 """Test suggest_manifest when SENS date IS available."""
 tmp_folder = hp.HISTORICAL_RESULTS_ROOT / 'TRU' / 'FY2025'
 tmp_folder.mkdir(parents=True)
 sens = tmp_folder / 'TRU_FY2025_SENS.txt'
 sens.write_text('Date: 15-09-2025\n')
 afs = tmp_folder / 'TRU_FY2025_AFS.pdf'
 afs.write_bytes(b'%PDF-1.4\n%\xe2\xe3\xcf\xd6')
 manifest = hp.suggest_manifest('TRU.JO', 'FY2025', force_afs_date_override=False)
 # Should use SENS date (2025-09-15), not fallback
 assert manifest['sources'][0]['published_at'] == '2025-09-15'
 assert manifest['sources'][1]['published_at'] == '2025-09-15'  # when force_afs_date_override is False

def test_suggest_manifest_errors(tmp_history_root):
 """Missing SENS file should raise ValueError mentioning 'published_at'."""
 with pytest.raises(ValueError, match='Cannot determine published_at'):
  hp.suggest_manifest('TRU.JO', 'FY2025')

# Add a simple test for the classification fix we made in results_package.py
import modules.analysis.results_package as rp

def test_classification_fix_accepts_plural_statements():
 """Test that classification now accepts both singular and plural statement forms."""
 # Create a mock PDF text with plural form (like TRU_FY2025_AFS.pdf)
 pdf_text = 'These are annual financial statements with statements of financial position and statements of comprehensive income from 2025'
 # The classify_document function should now return ANNUAL_FINANCIAL_STATEMENTS
 # because we accept both 'statement of' and 'statements of'
 assert rp.classify_document({'name': 'test.AFS.pdf', 'text': pdf_text}) == rp.ANNUAL_FINANCIAL_STATEMENTS
