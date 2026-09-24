import json,sys
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
