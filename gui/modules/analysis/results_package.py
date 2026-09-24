"""Structured SENS + annual-financial-statements results packages."""
from __future__ import annotations
import re
from datetime import date,datetime
from decimal import Decimal,InvalidOperation
from pathlib import Path
from uuid import UUID
from .financial_metrics import (AssumptionType,FinancialMetric,ShareCountType,SourceType,Unit,normalize_metric)

PARSER_VERSION="results-package-1.0"
RESULTS_SENS="results_sens"
ANNUAL_FINANCIAL_STATEMENTS="annual_financial_statements"
DETAILED_RESULTS_PACKAGE="DETAILED_RESULTS_PACKAGE"
HEADLINE_RESULTS_ONLY="HEADLINE_RESULTS_ONLY"

def _decimal(raw):
 raw=str(raw).strip(); negative=raw.startswith("(") and raw.endswith(")")
 raw=raw.strip("()").replace(",","").replace(" ","")
 try:value=Decimal(raw)
 except InvalidOperation:return None
 return -value if negative else value

def _period(text):
 m=re.search(r"(?:52\s+weeks\s+(?:to|ended)|period\s+ended)\s+(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})",text,re.I)
 return datetime.strptime(" ".join(m.groups()),"%d %B %Y").date() if m else None

def classify_document(source):
 text=(source.get("text") or "")[:120000].lower(); suffix=Path(source.get("name") or "").suffix.lower()
 if ("produced by the jse sens department" in text or "jse sens" in text) and ("results" in text or "financial statements" in text):return RESULTS_SENS
 if suffix==".pdf" and "annual financial statements" in text and ("statement of financial position" in text or "statement of comprehensive income" in text):return ANNUAL_FINANCIAL_STATEMENTS
 return "other"

def classify_path(path):
 path=Path(path)
 return classify_document({'name':path.name,'text':read_document_text(path)})
def read_document_text(path:Path)->str:
 path=Path(path)
 try:
  if path.suffix.lower()=='.txt':return path.read_text(encoding='utf-8',errors='ignore')
  if path.suffix.lower()=='.pdf':
   from PyPDF2 import PdfReader
   return '\n'.join((page.extract_text() or '') for page in PdfReader(str(path)).pages[:25])
 except Exception:return ''
 return ''

def select_live_sources(sources,requested_period=None):
 inspected=[]
 for source in sources:
  item=dict(source);item['document_role']=classify_document(item);item['reporting_period']=_period(item.get('text') or '')
  inspected.append(item)
 target=requested_period
 if isinstance(target,str):target=date.fromisoformat(target)
 recognized=[x for x in inspected if x['document_role'] in {RESULTS_SENS,ANNUAL_FINANCIAL_STATEMENTS}]
 if target is None:
  sens_periods=[x['reporting_period'] for x in recognized if x['document_role']==RESULTS_SENS and x['reporting_period']]
  periods=sens_periods or [x['reporting_period'] for x in recognized if x['reporting_period']]
  target=max(periods) if periods else None
 selected=[];ignored=[]
 for item in inspected:
  reason=None
  if item['document_role'] not in {RESULTS_SENS,ANNUAL_FINANCIAL_STATEMENTS}:reason='unsupported document role'
  elif item['reporting_period'] is None:reason='reporting period unresolved'
  elif target is None:reason='package reporting period unresolved'
  elif item['reporting_period']!=target:reason=f"reporting period {item['reporting_period']} does not match requested {target}"
  if reason:ignored.append({'source':item,'reason':reason})
  else:selected.append(item)
 roles={x['document_role'] for x in selected}
 warnings=[f"Ignored {x['source'].get('name')}: {x['reason']}" for x in ignored]
 if target and RESULTS_SENS not in roles:warnings.append(f'No results SENS found for {target}')
 if target and ANNUAL_FINANCIAL_STATEMENTS not in roles:warnings.append(f'No annual financial statements found for {target}')
 return {'target_period':target,'selected':selected,'ignored':ignored,'warnings':warnings}

def select_live_result_paths(paths,requested_period=None):
 sources=[{'name':Path(x).name,'path':Path(x),'text':read_document_text(Path(x))} for x in paths]
 result=select_live_sources(sources,requested_period)
 result['selected_paths']=[x['path'] for x in result['selected']]
 return result

def classify_package(sources):
 roles={s.get("document_role") or classify_document(s) for s in sources}
 if RESULTS_SENS in roles and ANNUAL_FINANCIAL_STATEMENTS in roles:return DETAILED_RESULTS_PACKAGE
 return HEADLINE_RESULTS_ONLY

def annotate_sources(sources):
 for source in sources:
  source["document_role"]=classify_document(source); source["parser_version"]=PARSER_VERSION
  source["reporting_period"]=str(_period(source.get("text") or "") or "") or None
 return classify_package(sources)

def _obs(source,role,name,value,unit,period_end,page,section,raw_label,raw_value,*,segment=None,scale=None,effective_date=None,notes=None):
 normalized=value
 if value is not None and scale=="millions":normalized=value*Decimal(1000000)
 if value is not None and scale=="thousands":normalized=value*Decimal(1000)
 return {"name":name,"raw_label":raw_label,"raw_value":raw_value,"value":str(value) if value is not None else None,
  "normalized_value":str(normalized) if normalized is not None else None,"unit":unit,"currency":"ZAR" if unit=="ZAR" else None,
  "period_end":str(period_end) if period_end else None,"effective_date":str(effective_date) if effective_date else str(period_end) if period_end else None,
  "source_id":source["source_id"],"source_document_id":source["source_id"],"document_role":role,"source_path":source.get("archive_path") or source.get("original_path"),
  "source_hash":source.get("sha256"),"source_date":source.get("source_date"),"page_number":page,"statement_section":section,
  "parser_version":PARSER_VERSION,"operation_segment":segment,"assumption_type":"historical_actual","evidence_verified":value is not None,
  "notes":notes}

def _line_pair(text,label):
 pattern=rf"(?im)^\s*{label}\s+(?:\d+(?:\.\d+)?(?:,\s*\d+)?\s+)?(\(?[\d,]+(?:\.\d+)?\)?)\s+(\(?[\d,]+(?:\.\d+)?\)?)\s*$"
 m=re.search(pattern,text)
 return (m.group(1),m.group(2),m.group(0).strip()) if m else (None,None,None)

STATEMENT_MAP={
 "GROUP STATEMENT OF FINANCIAL POSITION":("balance_sheet",{
  "Property, plant and equipment":"property_plant_equipment",r"Right\s*-of-use assets":"right_of_use_assets","Intangible assets":"intangible_assets",
  "Inventories":"inventory","Trade and other receivables":"trade_and_other_receivables","Cash and cash equivalents":"cash_and_cash_equivalents",
  "Total assets":"total_assets","Total equity":"total_equity","Lease liabilities":"lease_liabilities_noncurrent",
  "Trade and other payables":"trade_and_other_payables",r"Interest\s*-bearing borrowings":"borrowings","Total liabilities":"total_liabilities"}),
 "GROUP STATEMENT OF COMPREHENSIVE INCOME":("income_statement",{
  "Revenue":"revenue","Sale of merchandise":"sale_of_merchandise","Cost of sales":"cost_of_sales","Gross profit":"gross_profit",
  "Other income":"other_income","Trading expenses":"operating_expenses","Depreciation and amortisation":"depreciation_and_amortisation",
  "Trading profit":"trading_profit","Interest income":"finance_income","Finance costs":"finance_costs","Profit before tax":"profit_before_tax",
  "Tax expense":"tax","Profit for the period":"profit_for_period","Equity holders of the Company":"attributable_earnings",
  r"Basic earnings per share \(cents\)":"eps",r"Diluted basic earnings per share \(cents\)":"diluted_eps"}),
 "GROUP STATEMENT OF CASH FLOWS":("cash_flow_statement",{
  "Working capital movements":"working_capital_movement","Cash generated from operations":"cash_generated_from_operations",
  "Tax paid":"tax_paid","Dividends paid":"dividends_paid","Net cash from operating activities":"operating_cash_flow",
  "Acquisition of plant and equipment to expand operations":"capex_expansion","Acquisition of plant and equipment to maintain operations":"capex_maintenance",
  "Acquisition of computer software":"intangible_additions","Net cash used in investing activities":"investing_cash_flow",
  "Shares repurchased by the Company and its subsidiaries":"share_repurchases_cash","Lease liability payments":"lease_payments",
  "Net cash used in financing activities":"financing_cash_flow"})
}
CENTS={"eps","diluted_eps","heps","diluted_heps","nav_per_share"}
SHARES={"issued_shares_current","treasury_shares","external_shares_ex_treasury","weighted_average_basic_shares","weighted_average_diluted_shares"}

def parse_afs(source):
 warnings=[]; observations=[]
 if source.get("extraction_error"):warnings.append(f"PDF extraction warning: {source['extraction_error']}")
 try:
  from PyPDF2 import PdfReader
  reader=PdfReader(source["archive_path"])
 except Exception as exc:return [],[f"PDF open failed: {exc}"]
 all_text=source.get("text") or ""; period_end=_period(all_text)
 for page_no,page in enumerate(reader.pages,1):
  try:text=page.extract_text() or ""
  except Exception as exc:warnings.append(f"Page {page_no}: {exc}");continue
  for title,(section,mapping) in STATEMENT_MAP.items():
   if title not in text:continue
   for label,name in mapping.items():
    current,prior,quote=_line_pair(text,label)
    if current is None:continue
    value=_decimal(current); unit="ZAR_cents" if name in CENTS else "ZAR"; scale=None if name in CENTS else "millions"
    observations.append(_obs(source,ANNUAL_FINANCIAL_STATEMENTS,name,value,unit,period_end,page_no,section,re.sub(r"\\s\*"," ",label),current,scale=scale,notes=quote))
  if "9INVENTORIES" in text or "9 INVENTORIES" in text:
   for label,name in {"Gross inventories":"gross_inventory","Finished goods":"finished_goods_inventory",r"Raw materials and work\s*-in-progress":"raw_materials_inventory","Net inventories at the reporting date":"inventory"}.items():
    current,prior,quote=_line_pair(text,label)
    if current:observations.append(_obs(source,ANNUAL_FINANCIAL_STATEMENTS,name,_decimal(current),"ZAR",period_end,page_no,"note_9_inventories",label,current,scale="millions",notes=quote))
  if "10TRADE AND OTHER RECEIVABLES" in text or "10 TRADE AND OTHER RECEIVABLES" in text:
   for label,name in {"Trade receivables: Active portfolio":"trade_receivables_active",r"Trade receivables: Charged\s*-off portfolio":"trade_receivables_charged_off","Other receivables":"other_receivables","Trade and other receivables at the reporting date":"trade_and_other_receivables"}.items():
    current,prior,quote=_line_pair(text,label)
    if current:observations.append(_obs(source,ANNUAL_FINANCIAL_STATEMENTS,name,_decimal(current),"ZAR",period_end,page_no,"note_10_receivables",label,current,scale="millions",notes=quote))
  if "32.2 Working capital movements" in text:
   for label,name in {"Increase in inventories":"inventory_cash_movement","Increase in trade and other receivables and prepayments":"receivables_cash_movement","Increase in trade and other payables and provisions":"payables_cash_movement",r"Cash \(outflow\)/inflow":"working_capital_movement"}.items():
    current,prior,quote=_line_pair(text,label)
    if current:observations.append(_obs(source,ANNUAL_FINANCIAL_STATEMENTS,name,_decimal(current),"ZAR",period_end,page_no,"note_32_2_working_capital",label,current,scale="millions",notes=quote))
  if "EARNINGS AND CASH FLOW PER SHARE" in text:
   special={r"Weighted average number of shares for the reporting period \(millions\)":"weighted_average_basic_shares",r"Diluted weighted average number of shares for the reporting period \(millions\)":"weighted_average_diluted_shares",r"Headline earnings per share \(cents\)":"heps",r"Diluted headline earnings per share \(cents\)":"diluted_heps"}
   for label,name in special.items():
    current,prior,quote=_line_pair(text,label)
    if current:
     value=_decimal(current); unit="shares" if name in SHARES else "ZAR_cents"; scale="millions" if unit=="shares" else None
     observations.append(_obs(source,ANNUAL_FINANCIAL_STATEMENTS,name,value,unit,period_end,page_no,"note_30_per_share",label,current,scale=scale,notes=quote))
  if "Issued and fully paid" in text and ("12SHARE CAPITAL" in text or "12 SHARE CAPITAL" in text):
   m=re.search(r"Issued and fully paid\s+([\d ]+)\s+\(2025:",text)
   if m:observations.append(_obs(source,ANNUAL_FINANCIAL_STATEMENTS,"issued_shares_current",_decimal(m.group(1)),"shares",period_end,page_no,"note_12_share_capital","Issued and fully paid",m.group(1),notes=m.group(0)))
   for label,name in {"Treasury shares held by subsidiaries":"treasury_shares",r"Number of shares in issue \(net of treasury shares\)":"external_shares_ex_treasury"}.items():
    current,prior,quote=_line_pair(text,label)
    if current:
     share_value=_decimal(current)
     if name=="treasury_shares" and share_value is not None:share_value=abs(share_value)
     observations.append(_obs(source,ANNUAL_FINANCIAL_STATEMENTS,name,share_value,"shares",period_end,page_no,"note_12_share_capital",label,current,scale="thousands",notes=quote))
  if re.search(r"34\.1 Reportable segment information(?: \(continued\))?\s*2026",text):
   segment_map={r"Total third\s*-party revenue":"segment_revenue","Sale of merchandise":"segment_sale_of_merchandise","Gross profit":"segment_gross_profit","Trading profit":"segment_trading_profit","Profit before tax":"segment_profit_before_tax","EBITDA":"segment_ebitda","Segment assets":"segment_assets","Segment liabilities":"segment_liabilities","Capital expenditure":"segment_capex",r"Gross margin \(%\)":"segment_gross_margin",r"Trading margin \(%\)":"segment_trading_margin",r"Operating margin \(%\)":"segment_operating_margin"}
   for label,name in segment_map.items():
    m=re.search(rf"(?im)^\s*{label}\s+(?:\d+(?:\.\d+)?\s+)?(\(?[\d,]+(?:\.\d+)?\)?)\s+(\(?[\d,]+(?:\.\d+)?\)?)\s+(?:-|\(?[\d,]+(?:\.\d+)?\)?)\s+(\(?[\d,]+(?:\.\d+)?\)?)\s*$",text)
    if not m:continue
    unit="percentage" if "margin" in name else "ZAR"; scale=None if unit=="percentage" else "millions"
    for segment,raw in (("Truworths Africa",m.group(1)),("Office UK",m.group(2)),("Group",m.group(3))):
     observations.append(_obs(source,ANNUAL_FINANCIAL_STATEMENTS,name,_decimal(raw),unit,period_end,page_no,"note_34_segment_reporting",label,raw,segment=segment,scale=scale,notes=m.group(0)))
 if not period_end:warnings.append("Reporting period unresolved from AFS text")
 return observations,warnings

def parse_sens(source):
 text=source.get("text") or ""; period_end=_period(text); observations=[]
 mappings=[("Retail sales","retail_sales","ZAR","billions"),("Sale of merchandise","sale_of_merchandise","ZAR","billions"),("Gross profit margin","gross_margin","percentage",None),("Operating margin","operating_margin","percentage",None),("Earnings per share","eps","ZAR_cents",None),("Headline earnings per share","heps","ZAR_cents",None),("Diluted headline earnings per share","diluted_heps","ZAR_cents",None),("Net asset value per share","nav_per_share","ZAR_cents",None),("Cash generated from operations","cash_generated_from_operations","ZAR","billions"),(r"Net cash\*?","net_debt_cash","ZAR","millions"),("Annual dividend per share","annual_dividend_per_share","ZAR_cents",None)]
 for label,name,unit,scale in mappings:
  m=re.search(rf"(?im)^\s*{label}\s+([^\r\n]+)",text)
  if not m:continue
  raw=m.group(1); nums=re.findall(r"-?\d[\d ,]*(?:\.\d+)?",raw)
  if not nums:continue
  chosen=nums[-1] if ("R" in raw or "cents" in raw.lower()) else nums[0]; value=_decimal(chosen)
  factor={"billions":Decimal(1000000000),"millions":Decimal(1000000)}.get(scale,Decimal(1)); value=value*factor if value is not None else None
  observations.append(_obs(source,RESULTS_SENS,name,value,unit,period_end,None,"sens_headline",label,chosen,notes=m.group(0)))
 issued=re.search(r"(\d[\d ]+)\s+ordinary shares in issue",text,re.I)
 treasury=re.search(r"dividend on\s+(\d[\d ]+)\s+of these shares.*?treasury shares",text,re.I|re.S)
 for match,name in ((issued,"issued_shares_current"),(treasury,"treasury_shares")):
  if match:observations.append(_obs(source,RESULTS_SENS,name,_decimal(match.group(1)),"shares",period_end,None,"sens_corporate_action",name,match.group(1),effective_date=date.fromisoformat(source["source_date"]) if source.get("source_date") else None,notes=match.group(0)[:300]))
 return observations

def reconcile_observations(observations):
 groups={}; results=[]
 for item in observations:
  identity_date=item.get("effective_date") if item["name"] in {"issued_shares_current","treasury_shares","external_shares_ex_treasury"} else item.get("period_end")
  groups.setdefault((item["name"],item.get("operation_segment"),identity_date,item.get("unit")),[]).append(item)
 for key,items in groups.items():
  roles={x["document_role"] for x in items}; values={x["normalized_value"] for x in items}
  if len(roles)>1:
   status="CONFIRMED_BY_MULTIPLE_SOURCES" if len(values)==1 else "SOURCE_CONFLICT"
  else:status="SINGLE_SOURCE"
  name=key[0]; preferred=RESULTS_SENS if name in {"issued_shares_current","treasury_shares","annual_dividend_per_share"} else ANNUAL_FINANCIAL_STATEMENTS if ANNUAL_FINANCIAL_STATEMENTS in roles else next(iter(roles))
  results.append({"metric_name":name,"operation_segment":key[1],"period_end":key[2],"unit":key[3],"status":status,"preferred_role":preferred,"observations":[{"source_id":x["source_id"],"role":x["document_role"],"value":x["normalized_value"],"raw_value":x["raw_value"],"page":x["page_number"]} for x in items]})
 return results

def build_results_package(sources):
 depth=annotate_sources(sources); observations=[]; warnings=[]
 for source in sources:
  if source["document_role"]==RESULTS_SENS:observations.extend(parse_sens(source))
  elif source["document_role"]==ANNUAL_FINANCIAL_STATEMENTS:
   found,issues=parse_afs(source); observations.extend(found); warnings.extend(issues)
 return {"evidence_depth":depth,"parser_version":PARSER_VERSION,"observations":observations,"reconciliations":reconcile_observations(observations),"warnings":warnings}

def observations_to_metrics(ticker,report_id,package,report_date,observed_at):
 metrics=[]
 for item in package["observations"]:
  if item["normalized_value"] is None:continue
  unit={"ZAR":Unit.ZAR,"ZAR_cents":Unit.ZAR_CENTS,"shares":Unit.SHARES,"percentage":Unit.PERCENTAGE}.get(item["unit"])
  if unit is None:continue
  share_type=ShareCountType(item["name"]) if item["name"] in {x.value for x in ShareCountType} else None
  metric=FinancialMetric(ticker=ticker,report_id=UUID(str(report_id)),name=item["name"],value=Decimal(item["normalized_value"]),currency=item["currency"],unit=unit,period_end=date.fromisoformat(item["period_end"]) if item["period_end"] else None,effective_date=date.fromisoformat(item["effective_date"]) if item["effective_date"] else None,source_date=date.fromisoformat(str(item["source_date"])[:10]) if item["source_date"] else None,observed_at=observed_at,report_date=report_date,source=item["source_id"],source_id=item["source_id"],source_type=SourceType.COMPANY_DISCLOSURE,assumption_type=AssumptionType.HISTORICAL_ACTUAL,operation_segment=item["operation_segment"],share_count_type=share_type,raw_value=item["raw_value"],raw_unit=item["unit"],normalized_value=Decimal(item["normalized_value"]),normalized_unit=unit,evidence_quote=item["notes"],evidence_verified=True,intended_use="historical_baseline",notes=f"{item['document_role']} | page {item['page_number'] or 'n/a'} | {item['statement_section']}",source_page=item["page_number"],source_section=item["statement_section"],raw_label=item["raw_label"],parser_version=item["parser_version"],document_role=item["document_role"])
  metrics.append(normalize_metric(metric))
 return metrics

def render_package_for_prompt(package):
 lines=[f"[STRUCTURED RESULTS PACKAGE]\nEvidence depth: {package['evidence_depth']}\nParser version: {package['parser_version']}","Use these Python-extracted observations as the accounting baseline. Preserve distinct concepts and do not invent unresolved values."]
 for item in package["observations"]:
  lines.append(f"- {item['name']} | value={item['normalized_value']} {item['unit']} | period={item['period_end']} | segment={item['operation_segment'] or 'Group'} | role={item['document_role']} | source={item['source_id']} | page={item['page_number'] or 'n/a'} | section={item['statement_section']}")
 conflicts=[x for x in package["reconciliations"] if x["status"]=="SOURCE_CONFLICT"]
 lines.append("\n[RECONCILIATION]")
 for item in package["reconciliations"]:lines.append(f"- {item['metric_name']} | {item['status']} | preferred={item['preferred_role']} | observations={json_compact(item['observations'])}")
 if package["warnings"]:lines.append("\n[PARSER WARNINGS]\n- "+"\n- ".join(package["warnings"]))
 lines.append("\nDo not discuss a specific working-capital cause unless the structured AFS observations support it. Do not create forward assumptions or a target price.\n[END STRUCTURED RESULTS PACKAGE]")
 return "\n".join(lines)

def json_compact(value):
 import json
 return json.dumps(value,separators=(",",":"),default=str)
