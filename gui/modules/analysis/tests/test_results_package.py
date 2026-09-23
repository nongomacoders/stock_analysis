from datetime import date
from pathlib import Path
from uuid import uuid4
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from modules.analysis.results_package import (ANNUAL_FINANCIAL_STATEMENTS,DETAILED_RESULTS_PACKAGE,
 HEADLINE_RESULTS_ONLY,RESULTS_SENS,annotate_sources,build_results_package,classify_document,
 classify_package,observations_to_metrics,parse_afs,reconcile_observations,render_package_for_prompt)

SENS="""Group annual financial statements, summarised audited group annual results for the 52 weeks ended 28 June 2026
Headline earnings per share 732.2 cents
Issued and fully paid: 400 551 604 ordinary shares in issue
Date: 27/08/2026 12:30:00
Produced by the JSE SENS Department."""
AFS_TEXT="""Truworths International ANNUAL FINANCIAL STATEMENTS 2026
GROUP STATEMENT OF FINANCIAL POSITION
GROUP STATEMENT OF COMPREHENSIVE INCOME
52 weeks to 28 June 2026"""

def source(name,text,source_id="file:0"):
 return {"name":name,"text":text,"source_id":source_id,"archive_path":name,"sha256":"abc","source_date":"2026-08-27","extraction_error":None}

def observation(role,value,name="heps",effective="2026-06-28"):
 return {"name":name,"operation_segment":None,"period_end":"2026-06-28","effective_date":effective,"unit":"ZAR_cents","normalized_value":str(value),"raw_value":str(value),"document_role":role,"source_id":role,"page_number":1}

def test_document_roles_use_content_and_package_depth():
 sens=source("ambiguous.data",SENS)
 afs=source("document.pdf",AFS_TEXT,"file:1")
 assert classify_document(sens)==RESULTS_SENS
 assert classify_document(afs)==ANNUAL_FINANCIAL_STATEMENTS
 assert classify_package([sens])==HEADLINE_RESULTS_ONLY
 annotate_sources([sens,afs])
 assert classify_package([sens,afs])==DETAILED_RESULTS_PACKAGE

def test_reconciliation_preserves_agreement_and_conflict():
 agreed=reconcile_observations([observation(RESULTS_SENS,732.2),observation(ANNUAL_FINANCIAL_STATEMENTS,732.2)])
 conflict=reconcile_observations([observation(RESULTS_SENS,732.2),observation(ANNUAL_FINANCIAL_STATEMENTS,730)])
 assert agreed[0]["status"]=="CONFIRMED_BY_MULTIPLE_SOURCES"
 assert conflict[0]["status"]=="SOURCE_CONFLICT"
 assert len(conflict[0]["observations"])==2

def test_distinct_accounting_concepts_never_collapse():
 rows=reconcile_observations([observation(RESULTS_SENS,100,"retail_sales"),observation(ANNUAL_FINANCIAL_STATEMENTS,100,"revenue")])
 assert {x["metric_name"] for x in rows}=={"retail_sales","revenue"}

def test_point_in_time_share_dates_do_not_conflict():
 a=observation(RESULTS_SENS,31,"treasury_shares","2026-08-27"); a["unit"]="shares"
 b=observation(ANNUAL_FINANCIAL_STATEMENTS,38,"treasury_shares","2026-06-28"); b["unit"]="shares"
 rows=reconcile_observations([a,b])
 assert len(rows)==2 and all(x["status"]=="SINGLE_SOURCE" for x in rows)

def test_partial_pdf_failure_is_advisory():
 rows,warnings=parse_afs({"archive_path":"missing.pdf","extraction_error":"page 7 failed"})
 assert rows==[] and any("PDF open failed" in x for x in warnings)

def test_prompt_exposes_evidence_depth_and_working_capital_gate():
 package={"evidence_depth":HEADLINE_RESULTS_ONLY,"parser_version":"x","observations":[],"reconciliations":[],"warnings":["page failed"]}
 prompt=render_package_for_prompt(package)
 assert "Evidence depth: HEADLINE_RESULTS_ONLY" in prompt
 assert "Do not discuss a specific working-capital cause" in prompt

def test_share_metrics_remain_separate_with_page_provenance():
 package={"observations":[{"name":"weighted_average_basic_shares","normalized_value":"367400000","unit":"shares","currency":None,"period_end":"2026-06-28","effective_date":"2026-06-28","source_date":"2026-08-27","source_id":"file:1","operation_segment":None,"raw_value":"367.4","notes":"Weighted average","document_role":ANNUAL_FINANCIAL_STATEMENTS,"page_number":84,"statement_section":"note_30_per_share","raw_label":"WANOS","parser_version":"x"}]}
 metrics=observations_to_metrics("TRU.JO",uuid4(),package,date(2026,9,23),None)
 assert metrics[0].name=="weighted_average_basic_shares"
 assert metrics[0].source_page==84 and metrics[0].document_role==ANNUAL_FINANCIAL_STATEMENTS
 assert metrics[0].assumption_type.value=="historical_actual"

def test_tru_actual_package_regression():
 folder=Path(__file__).resolve().parents[3]/"results/TRU"
 pdf=next(folder.glob("*.pdf"),None); txt=next(folder.glob("*.txt"),None)
 if not pdf or not txt:return
 from hashlib import sha256
 from PyPDF2 import PdfReader
 sources=[source(txt.name,txt.read_text(encoding="utf-8",errors="ignore"),"file:0"),
          source(pdf.name,"\n".join(p.extract_text() or "" for p in PdfReader(str(pdf)).pages),"file:1")]
 sources[0].update(archive_path=str(txt),sha256=sha256(txt.read_bytes()).hexdigest())
 sources[1].update(archive_path=str(pdf),sha256=sha256(pdf.read_bytes()).hexdigest())
 package=build_results_package(sources)
 assert package["evidence_depth"]==DETAILED_RESULTS_PACKAGE
 names={x["name"] for x in package["observations"]}
 assert {"inventory","working_capital_movement","weighted_average_basic_shares","weighted_average_diluted_shares","segment_revenue"}<=names
 assert {"Truworths Africa","Office UK"}<={x["operation_segment"] for x in package["observations"]}
