"""Versioned post-publication comparisons; never mutates reports or valuations."""
from __future__ import annotations
import json,re
from collections import Counter
from datetime import date
from decimal import Decimal,InvalidOperation
from enum import Enum
from typing import Literal
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field,model_validator
COMPARISON_ENGINE_VERSION="1.1"; COMPARISON_PROMPT_VERSION="2"
class ComparisonType(str,Enum):
 SAME_PERIOD_REVISION="SAME_PERIOD_REVISION"; NEW_REPORTING_PERIOD="NEW_REPORTING_PERIOD"; MANUAL_OTHER="MANUAL_OTHER"
class LearningCategory(str,Enum):
 MISSED_RISK="MISSED_RISK"; MISSED_CATALYST="MISSED_CATALYST"; UNDERWEIGHTED_AREA="UNDERWEIGHTED_AREA"; OVERWEIGHTED_AREA="OVERWEIGHTED_AREA"; UNSUPPORTED_ASSUMPTION="UNSUPPORTED_ASSUMPTION"; FORECAST_ERROR="FORECAST_ERROR"; CAUSAL_INFERENCE_ERROR="CAUSAL_INFERENCE_ERROR"; SOURCE_GAP="SOURCE_GAP"; STALE_DATA="STALE_DATA"; UNIT_ERROR="UNIT_ERROR"; SHARE_COUNT_ERROR="SHARE_COUNT_ERROR"; VALUATION_ERROR="VALUATION_ERROR"; THESIS_ERROR="THESIS_ERROR"; GOOD_CALL="GOOD_CALL"; GOOD_DISCIPLINE="GOOD_DISCIPLINE"; NEW_INFORMATION="NEW_INFORMATION"; MODEL_LIMITATION="MODEL_LIMITATION"
class LearningPoint(BaseModel):
 model_config=ConfigDict(extra="forbid")
 category:LearningCategory; scope:Literal["ticker_analysis","sector_analysis","research_process","valuation_process","data_pipeline"]; severity:Literal["low","medium","high","critical"]; information_availability:Literal["available","unavailable","uncertain"]; previous_analysis_quality:Literal["adequate","underweighted","missed","unsupported","incorrect"]
 area:str=Field(min_length=1); finding:str=Field(min_length=1); evidence:list[str]=Field(min_length=1); previous_report_reference:str|None=None; current_report_reference:str|None=None; source_metric_ids:list[UUID]=Field(default_factory=list); recommended_action:str=Field(min_length=1)
class Outcome(BaseModel):
 model_config=ConfigDict(extra="forbid")
 item:str; outcome:Literal["materialised","partially_materialised","did_not_materialise","unresolved","no_longer_relevant"]; evidence:list[str]=Field(min_length=1)
class ThesisChange(BaseModel):
 model_config=ConfigDict(extra="forbid")
 area:str; change:str; evidence:list[str]=Field(min_length=1); classification:Literal["strengthened","weakened","new_issue","no_longer_supported","unchanged"]
class QualitativeReview(BaseModel):
 model_config=ConfigDict(extra="forbid")
 thesis_changes:list[ThesisChange]=Field(default_factory=list); risk_outcomes:list[Outcome]=Field(default_factory=list); catalyst_outcomes:list[Outcome]=Field(default_factory=list); learning_points:list[LearningPoint]=Field(default_factory=list); positive_lessons:list[LearningPoint]=Field(default_factory=list); new_information:list[LearningPoint]=Field(default_factory=list); overall_summary:str
 @model_validator(mode="after")
 def controlled_groups(self):
  if any(x.category not in {LearningCategory.GOOD_CALL,LearningCategory.GOOD_DISCIPLINE} for x in self.positive_lessons):raise ValueError("positive_lessons require GOOD_CALL or GOOD_DISCIPLINE")
  if any(x.category!=LearningCategory.NEW_INFORMATION for x in self.new_information):raise ValueError("new_information requires NEW_INFORMATION")
  if any(x.information_availability!="unavailable" for x in self.new_information):raise ValueError("NEW_INFORMATION requires information unavailable to the earlier analysis")
  return self
def _d(value):
 try:return Decimal(str(value)) if value is not None else None
 except InvalidOperation:return None
def _iso_date(value):
 if not value:return None
 try:return date.fromisoformat(str(value)[:10]).isoformat()
 except ValueError:return None
def reporting_period_identity(metrics):
 eligible=[m for m in metrics if m.get("assumption_type") in {"historical_actual","python_calculation"}]; ends=Counter(filter(None,(_iso_date(m.get("period_end")) for m in eligible)))
 if not ends:return {"period_start":None,"period_end":None,"period_type":None,"fiscal_year":None,"label":None,"confidence":"unresolved"}
 period_end=sorted(ends.items(),key=lambda x:(x[1],x[0]),reverse=True)[0][0]; matching=[m for m in eligible if _iso_date(m.get("period_end"))==period_end]; starts=Counter(filter(None,(_iso_date(m.get("period_start")) for m in matching))); labels=Counter(str(m.get("period_label")).strip() for m in matching if m.get("period_label")); types=Counter(str(m.get("period_type")).strip() for m in matching if m.get("period_type"))
 return {"period_start":starts.most_common(1)[0][0] if starts else None,"period_end":period_end,"period_type":types.most_common(1)[0][0] if types else None,"fiscal_year":int(period_end[:4]),"label":labels.most_common(1)[0][0] if labels else None,"confidence":"typed_metric"}
def classify_comparison(previous_period,current_period):
 old,new=previous_period.get("period_end"),current_period.get("period_end")
 return ComparisonType.MANUAL_OTHER if not old or not new else ComparisonType.SAME_PERIOD_REVISION if old==new else ComparisonType.NEW_REPORTING_PERIOD if new>old else ComparisonType.MANUAL_OTHER
def reporting_transition_key(kind,previous_period,current_period):
 old,new=previous_period.get("period_end"),current_period.get("period_end")
 if kind==ComparisonType.SAME_PERIOD_REVISION and old and old==new:return f"same-period:{old}"
 return f"{old}->{new}" if old and new else "unresolved"
def metric_key(m):return (m.get("name"),m.get("operation_segment"),m.get("commodity"),m.get("normalized_unit") or m.get("unit"))
def compare_metrics(previous,current):
 old={metric_key(m):m for m in previous if _d(m.get("normalized_value") or m.get("value")) is not None}; new={metric_key(m):m for m in current if _d(m.get("normalized_value") or m.get("value")) is not None}; changes=[]
 for key in sorted(old.keys()&new.keys(),key=str):
  left,right=old[key],new[key]; before=_d(left.get("normalized_value") or left.get("value")); after=_d(right.get("normalized_value") or right.get("value")); absolute=after-before
  change={"metric_name":key[0],"operation_segment":key[1],"commodity":key[2],"unit":key[3],"previous_value":str(before),"current_value":str(after),"absolute_change":str(absolute),"previous_metric_id":left.get("metric_id"),"current_metric_id":right.get("metric_id")}
  if key[3]=="percentage":change["basis_point_change"]=str(absolute*100)
  if before!=0:change["percentage_change"]=str(absolute/before.copy_abs()*100)
  changes.append(change)
 return changes
def classify_forecast(forecast,actual):
 f,a=_d(forecast),_d(actual)
 if f is None or a is None or f==0:return "not_testable",None
 error=(a-f)/abs(f)*100; magnitude=abs(error)
 return ("accurate" if magnitude<=5 else "broadly_accurate" if magnitude<=10 else "materially_wrong" if magnitude>25 else "optimistic" if f>a else "pessimistic"),error
def compare_forecasts(plans,current_metrics):
 actuals={m.get("name"):m for m in current_metrics if m.get("assumption_type")=="historical_actual"}; outcomes=[]
 for plan in plans:
  for a in plan.get("assumptions",[]):
   if a.get("approval_state")!="accepted":continue
   actual=actuals.get(a.get("field"))
   if not actual or (a.get("unit") and actual.get("unit") and a["unit"]!=actual["unit"]):continue
   label,error=classify_forecast(a.get("value"),actual.get("value")); outcomes.append({"forecast_plan_id":plan.get("forecast_plan_id"),"assumption_id":a.get("assumption_id"),"field":a.get("field"),"period_label":a.get("period_label"),"forecast":str(a.get("value")),"actual":str(actual.get("value")),"unit":a.get("unit"),"error_percent":str(error) if error is not None else None,"classification":label,"actual_metric_id":actual.get("metric_id")})
 return outcomes
def unsupported_legacy(metrics):return [{"metric_name":m.get("name"),"value":m.get("value"),"unit":m.get("unit"),"metric_id":m.get("metric_id"),"classification":"unsupported_legacy_assumption"} for m in metrics if m.get("assumption_type")=="previous_report"]
def build_prompt(previous_report,current_report,deterministic,previous_audit,current_audit):
 kind=deterministic["comparison_type"]; categories=", ".join(x.value for x in LearningCategory)
 special={ComparisonType.SAME_PERIOD_REVISION.value:"Both reports concern the same economic reporting period. Review research quality, evidence use, extraction and unit accuracy, unsupported inference, analytical emphasis, valuation discipline and process improvements. Do not assess forecast accuracy or subsequent thesis outcomes. risk_outcomes and catalyst_outcomes must be empty. Evidence already available in the same-period sources is not NEW_INFORMATION.",ComparisonType.NEW_REPORTING_PERIOD.value:"The newer report contains a later economic reporting period. You may assess approved forecasts, prior thesis, risks and catalysts against subsequent evidence.",ComparisonType.MANUAL_OTHER.value:"The reporting-period relationship is unresolved. Focus on evidence and process differences; do not claim outcomes without explicit dated evidence."}[kind]
 instructions=f"""You are reviewing two historical reports after publication.
Comparison type: {kind}
{special}
Do not alter reports or generate a target price or assumptions. Every finding needs evidence. NEW_INFORMATION requires evidence unavailable to the earlier analysis. Every learning point must include information_availability (available, unavailable, uncertain) and previous_analysis_quality (adequate, underweighted, missed, unsupported, incorrect).
Return JSON only with exactly: thesis_changes, risk_outcomes, catalyst_outcomes, learning_points, positive_lessons, new_information, overall_summary.
Scopes: ticker_analysis, sector_analysis, research_process, valuation_process, data_pipeline. Severity: low, medium, high, critical.
Learning points require category, scope, severity, information_availability, previous_analysis_quality, area, finding, non-empty evidence, previous_report_reference, current_report_reference, source_metric_ids, recommended_action.
Allowed categories: {categories}"""
 schema=json.dumps(QualitativeReview.model_json_schema(),separators=(",",":"))
 return instructions+"\nValidate against this JSON Schema:\n"+schema+"\nDETERMINISTIC COMPARISON:\n"+json.dumps(deterministic,default=str)+"\nPREVIOUS AUDIT:\n"+json.dumps(previous_audit,default=str)+"\nCURRENT AUDIT:\n"+json.dumps(current_audit,default=str)+"\nPREVIOUS REPORT:\n"+previous_report+"\nCURRENT REPORT:\n"+current_report
def parse_review(text,comparison_type=ComparisonType.MANUAL_OTHER):
 raw=text.strip(); match=re.search(r"```(?:json)?\s*(.*?)```",raw,re.S)
 if match:raw=match.group(1).strip()
 review=QualitativeReview.model_validate_json(raw)
 if comparison_type==ComparisonType.SAME_PERIOD_REVISION and (review.risk_outcomes or review.catalyst_outcomes):raise ValueError("SAME_PERIOD_REVISION cannot contain risk or catalyst outcomes")
 return review
