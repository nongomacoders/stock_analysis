"""Strict manual historical results-package discovery and validation."""
from __future__ import annotations
from datetime import date
from hashlib import sha256
from pathlib import Path
from typing import Literal
import json,re
from pydantic import BaseModel,Field,model_validator
from scripts_standalone.results_scraper.utils import sanitize_ticker
from modules.analysis.results_package import (classify_path,build_results_package,
 RESULTS_SENS,ANNUAL_FINANCIAL_STATEMENTS)

PERIOD_RE=re.compile(r'^(FY\d{4}|H[12]_FY\d{4}|Q[1-4]_FY\d{4}|9M_FY\d{4})$')
class ManifestSource(BaseModel):
 type:Literal['SENS','AFS','PRESENTATION','TRANSCRIPT']
 file:str
 published_at:date
 revision:int=Field(default=1,ge=1)
 active:bool=True
 supersedes:str|None=None
class HistoricalManifest(BaseModel):
 schema_version:int=1
 ticker:str
 symbol:str
 period_label:str
 period_type:Literal['fiscal_year','half_year','quarter','nine_month']
 period_start:date|None=None
 period_end:date
 sources:list[ManifestSource]
 @model_validator(mode='after')
 def controlled(self):
  if not PERIOD_RE.fullmatch(self.period_label):raise ValueError('Uncontrolled historical period label')
  if sanitize_ticker(self.ticker).upper()!=self.symbol.upper():raise ValueError('Ticker and symbol disagree')
  if self.period_start and self.period_start>self.period_end:raise ValueError('period_start after period_end')
  for required in ('SENS','AFS'):
   if len([x for x in self.sources if x.type==required and x.active])!=1:raise ValueError(f'Exactly one active {required} source is required')
  return self

def validate_period_folder(folder:Path,expected_ticker:str,as_of_date:date|None=None):
 folder=Path(folder); errors=[];warnings=[]
 manifest_path=folder/'manifest.json'
 if not manifest_path.is_file():return {'status':'INVALID','errors':['Missing manifest.json'],'warnings':[]}
 try:manifest=HistoricalManifest.model_validate_json(manifest_path.read_text(encoding='utf-8-sig'))
 except Exception as exc:return {'status':'INVALID','errors':[str(exc)],'warnings':[]}
 symbol=sanitize_ticker(expected_ticker)
 if folder.parent.name.upper()!=symbol.upper():errors.append('Ticker folder mismatch')
 if folder.name!=manifest.period_label:errors.append('Period folder mismatch')
 if manifest.ticker.upper()!=expected_ticker.upper():errors.append('Manifest ticker mismatch')
 sources=[];hashes={}
 expected_roles={'SENS':RESULTS_SENS,'AFS':ANNUAL_FINANCIAL_STATEMENTS}
 declared={x.file for x in manifest.sources}
 for spec in manifest.sources:
  path=folder/spec.file
  expected=f'{manifest.symbol}_{manifest.period_label}_{spec.type}'
  stem=re.sub(r'_v\d+$','',path.stem)
  if stem!=expected:errors.append(f'Filename identity mismatch: {spec.file}')
  if path.suffix.lower() not in ({'.txt'} if spec.type in {'SENS','TRANSCRIPT'} else {'.pdf'}):errors.append(f'Unsupported extension for {spec.type}: {spec.file}')
  if not path.is_file():errors.append(f'Missing file: {spec.file}');continue
  try:data=path.read_bytes()
  except OSError as exc:errors.append(f'Unreadable file {spec.file}: {exc}');continue
  if not data:errors.append(f'Zero-byte file: {spec.file}');continue
  digest=sha256(data).hexdigest()
  if digest in hashes:errors.append(f'Duplicate file hash: {spec.file} and {hashes[digest]}')
  hashes[digest]=spec.file
  detected=classify_path(path)
  if spec.type in expected_roles and detected!=expected_roles[spec.type]:errors.append(f'Filename says {spec.type} but content classified as {detected}')
  if as_of_date and spec.published_at>as_of_date:continue
  text=''
  if path.suffix.lower()=='.txt':text=data.decode('utf-8',errors='ignore')
  else:
   try:
    from PyPDF2 import PdfReader
    text='\n'.join(page.extract_text() or '' for page in PdfReader(path).pages)
   except Exception as exc:errors.append(f'PDF extraction failed {spec.file}: {exc}')
  sources.append({'source_id':f'historical:{digest}','name':spec.file,'text':text,
   'source_date':spec.published_at.isoformat(),'available_date':spec.published_at.isoformat(),
   'original_path':str(path.resolve()),'archive_path':str(path.resolve()),'sha256':digest,
   'document_role':detected,'period_end':manifest.period_end.isoformat(),'active':spec.active,'revision':spec.revision})
 for item in folder.iterdir():
  if item.is_file() and item.name!='manifest.json' and item.name not in declared:warnings.append(f'Unexpected file: {item.name}')
 status='INVALID' if errors else 'WARNING' if warnings else 'VALID'
 return {'status':status,'errors':errors,'warnings':warnings,'manifest':manifest,'sources':sources}

def discover_packages(root:Path,ticker:str,as_of_date:date):
 ticker_dir=Path(root)/sanitize_ticker(ticker); packages=[]
 if not ticker_dir.is_dir():return packages
 for folder in sorted(x for x in ticker_dir.iterdir() if x.is_dir()):
  result=validate_period_folder(folder,ticker,as_of_date)
  if result['status']!='INVALID' and result.get('sources'):
   active=[x for x in result['sources'] if x['active']]
   package=build_results_package(active)
   packages.append({'folder':str(folder),'validation':result,'results_package':package})
 return packages
