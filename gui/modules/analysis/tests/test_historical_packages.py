import json,sys
import pytest
from pathlib import Path
from datetime import date
from PyPDF2 import PdfWriter
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
import modules.analysis.historical_packages as hp

def make_folder(tmp_path):
 folder=tmp_path/'TRU'/'FY2025';folder.mkdir(parents=True)
 (folder/'TRU_FY2025_SENS.txt').write_text('JSE SENS results',encoding='utf-8')
 writer=PdfWriter();writer.add_blank_page(width=100,height=100)
 with (folder/'TRU_FY2025_AFS.pdf').open('wb') as stream:writer.write(stream)
 manifest={'schema_version':1,'ticker':'TRU.JO','symbol':'TRU','period_label':'FY2025',
  'period_type':'fiscal_year','period_end':'2025-06-29','sources':[
   {'type':'SENS','file':'TRU_FY2025_SENS.txt','published_at':'2025-08-28'},
   {'type':'AFS','file':'TRU_FY2025_AFS.pdf','published_at':'2025-08-28'}]}
 (folder/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
 return folder

def test_historical_folder_structure_and_content_roles_validate(tmp_path,monkeypatch):
 folder=make_folder(tmp_path)
 monkeypatch.setattr(hp,'classify_path',lambda p:hp.RESULTS_SENS if p.suffix=='.txt' else hp.ANNUAL_FINANCIAL_STATEMENTS)
 result=hp.validate_period_folder(folder,'TRU.JO',date(2025,8,28))
 assert result['status']=='VALID' and len(result['sources'])==2

def test_historical_folder_rejects_ticker_period_and_filename_mismatch(tmp_path,monkeypatch):
 folder=make_folder(tmp_path)
 data=json.loads((folder/'manifest.json').read_text());data['sources'][0]['file']='wrong.txt'
 (folder/'manifest.json').write_text(json.dumps(data))
 (folder/'wrong.txt').write_text('text')
 monkeypatch.setattr(hp,'classify_path',lambda p:hp.RESULTS_SENS if p.suffix=='.txt' else hp.ANNUAL_FINANCIAL_STATEMENTS)
 result=hp.validate_period_folder(folder,'TRU.JO',date(2025,8,28))
 assert result['status']=='INVALID'
 assert any('Filename identity mismatch' in x for x in result['errors'])

def test_uncontrolled_interim_label_is_rejected(tmp_path):
 folder=tmp_path/'TRU'/'H1_2026';folder.mkdir(parents=True)
 (folder/'manifest.json').write_text(json.dumps({'ticker':'TRU.JO','symbol':'TRU','period_label':'H1_2026','period_type':'half_year','period_end':'2025-12-28','sources':[]}))
 result=hp.validate_period_folder(folder,'TRU.JO')
 assert result['status']=='INVALID' and 'Uncontrolled historical period label' in result['errors'][0]


def test_create_scaffold_manifest_and_expected_names(tmp_path):
 result=hp.create_package_scaffold('TRU.JO','FY2025',tmp_path)
 folder=tmp_path/'TRU'/'FY2025'
 assert result['folder']==folder.resolve() and result['folder_created']
 assert result['expected_files']=={'SENS':'TRU_FY2025_SENS.txt','AFS':'TRU_FY2025_AFS.pdf'}
 manifest=json.loads((folder/'manifest.json').read_text())
 assert manifest=={'schema_version':1,'ticker':'TRU.JO','symbol':'TRU','period_label':'FY2025',
  'period_type':'fiscal_year','period_start':None,'period_end':None,'sources':[]}
 assert hp.validate_period_folder(folder,'TRU.JO')['status']=='INCOMPLETE'

def test_existing_folder_and_manifest_are_never_overwritten(tmp_path):
 first=hp.create_package_scaffold('TRU.JO','FY2025',tmp_path)
 manifest=first['folder']/'manifest.json';manifest.write_text('{"preserve": true}')
 second=hp.create_package_scaffold('TRU.JO','FY2025',tmp_path)
 assert not second['folder_created'] and not second['manifest_created']
 assert manifest.read_text()=='{"preserve": true}'

def test_missing_manifest_requires_explicit_create(tmp_path):
 folder=tmp_path/'TRU'/'FY2025';folder.mkdir(parents=True)
 untouched=hp.create_package_scaffold('TRU.JO','FY2025',tmp_path)
 assert not untouched['manifest_created'] and not (folder/'manifest.json').exists()
 created=hp.create_package_scaffold('TRU.JO','FY2025',tmp_path,create_missing_manifest=True)
 assert created['manifest_created'] and (folder/'manifest.json').exists()

@pytest.mark.parametrize('ticker',['../TRU.JO','C:/TRU.JO','TRU','CON.JO','TRU?.JO'])
def test_invalid_ticker_and_path_traversal_rejected(tmp_path,ticker):
 with pytest.raises(ValueError):
  hp.create_package_scaffold(ticker,'FY2025',tmp_path)

@pytest.mark.parametrize('period',['FY25','H1_2026','../FY2025','FY2025/other','CON'])
def test_invalid_period_and_windows_names_rejected(tmp_path,period):
 with pytest.raises(ValueError):
  hp.create_package_scaffold('TRU.JO',period,tmp_path)

def test_second_creation_is_idempotent_and_source_files_untouched(tmp_path):
 first=hp.create_package_scaffold('TRU.JO','FY2025',tmp_path)
 sens=first['folder']/first['expected_files']['SENS'];sens.write_text('real SENS')
 second=hp.create_package_scaffold('TRU.JO','FY2025',tmp_path)
 assert not second['folder_created'] and sens.read_text()=='real SENS'
 assert len(list((tmp_path/'TRU').iterdir()))==1

def test_status_progresses_to_ready_to_validate(tmp_path):
 result=hp.create_package_scaffold('TRU.JO','FY2025',tmp_path);folder=result['folder']
 status=hp.package_status('TRU.JO','FY2025',tmp_path)
 assert status['status']=='INCOMPLETE' and not status['sens_exists'] and not status['afs_exists']
 (folder/'TRU_FY2025_SENS.txt').write_text('real results')
 assert hp.package_status('TRU.JO','FY2025',tmp_path)['status']=='INCOMPLETE'
 (folder/'TRU_FY2025_AFS.pdf').write_bytes(b'%PDF-real')
 status=hp.package_status('TRU.JO','FY2025',tmp_path)
 assert status['status']=='READY TO VALIDATE' and status['sens_exists'] and status['afs_exists']
 assert status['validation']['status']=='INCOMPLETE'

def test_scaffolding_has_no_database_or_execution_dependency(tmp_path,monkeypatch):
 monkeypatch.setattr(hp,'HISTORICAL_RESULTS_ROOT',tmp_path)
 result=hp.create_package_scaffold('TRU.JO','FY2025')
 assert result['folder'].exists()
 assert 'core.db' not in hp.__dict__ and 'valuation' not in hp.create_package_scaffold.__code__.co_names

def test_controlled_selector_values_match_validator():
 values=hp.controlled_period_values(2025,2026)
 assert all(hp.PERIOD_RE.fullmatch(x) for x in values)
 assert {'FY2025','H1_FY2026','Q3_FY2026','9M_FY2026'} <= set(values)
