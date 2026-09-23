from decimal import Decimal
from pathlib import Path
import asyncio,sys
from uuid import uuid4
import pytest
from pydantic import ValidationError
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from modules.analysis.research_comparison import (compare_metrics,compare_forecasts,classify_forecast,
 unsupported_legacy,parse_review,LearningPoint,LearningCategory,ComparisonType,reporting_period_identity,
 classify_comparison,reporting_transition_key)
from scripts import generate_deepresearch_from_results as generator
from modules.data.research_comparisons import next_learning_lifecycle,deterministic_summary,deterministic_learning,analyst_checklist

def metric(name,value,unit="percentage",kind="historical_actual"):
 return {"metric_id":str(uuid4()),"name":name,"value":str(value),"normalized_value":str(value),"unit":unit,"normalized_unit":unit,"assumption_type":kind}
def test_deterministic_metric_deltas_use_python_arithmetic():
 result=compare_metrics([metric("operating_margin",20)], [metric("operating_margin",Decimal("19.2"))])[0]
 assert result["absolute_change"]=="-0.8" and result["basis_point_change"]=="-80.0" and result["percentage_change"]=="-4.00"
def test_forecast_outcome_thresholds_are_deterministic():
 assert classify_forecast(760,732.2)[0]=="accurate"
 assert classify_forecast(100,80)[0]=="optimistic"
 assert classify_forecast(100,130)[0]=="materially_wrong"
def test_approved_forecast_is_compared_with_actual():
 actual=metric("heps",732.2,"ZAR_cents")
 plan={"forecast_plan_id":str(uuid4()),"assumptions":[{"assumption_id":str(uuid4()),"field":"heps","value":"760","unit":"ZAR_cents","approval_state":"accepted","period_label":"FY2026"}]}
 outcome=compare_forecasts([plan],[actual])[0]
 assert outcome["forecast"]=="760" and outcome["actual"]=="732.2" and outcome["classification"]=="accurate"
def test_unsupported_legacy_is_separate_from_approved_forecast():
 old=metric("exit_multiple",7.5,"multiple","previous_report")
 assert unsupported_legacy([old])[0]["classification"]=="unsupported_legacy_assumption"
def valid_review():
 point={"category":"UNDERWEIGHTED_AREA","scope":"ticker_analysis","severity":"medium","information_availability":"available","previous_analysis_quality":"underweighted","area":"cash_conversion","finding":"Cash conversion received insufficient attention.","evidence":["Operating cash declined from 4.8bn to 4.2bn."],"previous_report_reference":"Cash flow section","current_report_reference":"FY2026 cash flow","source_metric_ids":[],"recommended_action":"Review cash conversion next period."}
 return {"thesis_changes":[],"risk_outcomes":[{"item":"consumer recovery","outcome":"unresolved","evidence":["Sales declined 0.9%"]}],"catalyst_outcomes":[],"learning_points":[point],"positive_lessons":[{**point,"category":"GOOD_DISCIPLINE","scope":"research_process","area":"evidence discipline"}],"new_information":[{**point,"category":"NEW_INFORMATION","information_availability":"unavailable","previous_analysis_quality":"adequate","area":"new result"}],"overall_summary":"Evidence discipline improved."}
def test_strict_json_validates_outcomes_positive_and_new_information():
 review=parse_review(__import__("json").dumps(valid_review()))
 assert review.risk_outcomes[0].outcome=="unresolved"
 assert review.learning_points[0].category==LearningCategory.UNDERWEIGHTED_AREA
 assert review.positive_lessons[0].category==LearningCategory.GOOD_DISCIPLINE
 assert review.new_information[0].category==LearningCategory.NEW_INFORMATION
def test_strict_json_rejects_vague_or_extra_output():
 bad=valid_review(); bad["learning_points"][0]["evidence"]=[]
 with pytest.raises(ValidationError):parse_review(__import__("json").dumps(bad))
 bad=valid_review(); bad["unexpected"]="free prose"
 with pytest.raises(ValidationError):parse_review(__import__("json").dumps(bad))
def test_company_and_process_learning_scopes_are_distinct():
 company=LearningPoint(**valid_review()["learning_points"][0])
 process=LearningPoint(**valid_review()["positive_lessons"][0])
 assert company.scope=="ticker_analysis" and process.scope=="research_process"
def test_comparison_hook_is_rerun_only_and_retains_exact_ids():
 calls=[]
 async def runner(ticker,previous,current):calls.append((ticker,previous,current));return "comparison-id"
 result=asyncio.run(generator._run_post_publication_comparison(False,"TRU.JO",{"supersedes_report_id":"old"},"new",runner=runner))
 assert result is None and calls==[]
 result=asyncio.run(generator._run_post_publication_comparison(True,"TRU.JO",{"supersedes_report_id":"old"},"new",runner=runner))
 assert result=="comparison-id" and calls==[("TRU.JO","old","new")]
def test_first_report_does_not_compare():
 async def forbidden(*args):raise AssertionError("must not run")
 assert asyncio.run(generator._run_post_publication_comparison(True,"NEW.JO",{},"new",runner=forbidden)) is None
def test_comparison_failure_is_absorbed_after_publication():
 async def failed(*args):raise RuntimeError("review failed")
 result=asyncio.run(generator._run_post_publication_comparison(True,"TRU.JO",{"supersedes_report_id":"old"},"new",runner=failed))
 assert result=={"status":"failed","error":"review failed"}


def test_recurring_learning_is_reinforced_without_deleting_history():
 assert next_learning_lifecycle(0,False)==(1,"open")
 assert next_learning_lifecycle(1,False)==(2,"reinforced")
 assert next_learning_lifecycle(1,True)==(1,"open")

def period_metric(end,start=None):
 item=metric("revenue",100,"ZAR")
 item["period_end"]=end
 item["period_start"]=start
 return item

def test_reporting_period_comparison_types_are_deterministic():
 old=reporting_period_identity([period_metric("2026-06-28")])
 same=reporting_period_identity([period_metric("2026-06-28")])
 later=reporting_period_identity([period_metric("2027-06-27")])
 unknown=reporting_period_identity([metric("revenue",100,"ZAR")])
 assert classify_comparison(old,same)==ComparisonType.SAME_PERIOD_REVISION
 assert classify_comparison(old,later)==ComparisonType.NEW_REPORTING_PERIOD
 assert classify_comparison(old,unknown)==ComparisonType.MANUAL_OTHER
 assert reporting_transition_key(ComparisonType.SAME_PERIOD_REVISION,old,same)=="same-period:2026-06-28"

def test_same_period_rejects_outcome_hindsight():
 with pytest.raises(ValueError,match="cannot contain risk"):
  parse_review(__import__("json").dumps(valid_review()),ComparisonType.SAME_PERIOD_REVISION)

def test_same_period_missing_extraction_is_not_new_information():
 review=valid_review(); review["risk_outcomes"]=[]
 review["new_information"][0]["information_availability"]="available"
 with pytest.raises(ValidationError,match="NEW_INFORMATION"):
  parse_review(__import__("json").dumps(review),ComparisonType.SAME_PERIOD_REVISION)

def test_genuinely_unavailable_later_information_is_new_information():
 review=valid_review()
 parsed=parse_review(__import__("json").dumps(review),ComparisonType.NEW_REPORTING_PERIOD)
 assert parsed.new_information[0].information_availability=="unavailable"

def test_same_transition_does_not_inflate_recurrence():
 assert next_learning_lifecycle(1,True)==(1,"open")
 assert next_learning_lifecycle(1,False)==(2,"reinforced")
def test_same_period_deterministic_summary_gates_forecasts_and_types_treasury_gap():
 old=period_metric("2026-06-28")
 current=period_metric("2026-06-28")
 treasury=metric("treasury_shares",31279039,"shares"); treasury["evidence_quote"]="31 279 039 treasury shares"
 plan={"forecast_plan_id":"p","assumptions":[{"approval_state":"accepted","field":"revenue","value":"80","unit":"ZAR"}]}
 summary=deterministic_summary({"metrics":[old],"valuation":None},{"metrics":[current,treasury],"valuation":None},[plan])
 assert summary["comparison_type"]=="SAME_PERIOD_REVISION"
 assert summary["forecast_outcomes"]==[]
 points=deterministic_learning(summary)
 treasury_point=next(p for p in points if p.area=="Treasury Share Accounting")
 assert treasury_point.category==LearningCategory.SHARE_COUNT_ERROR
 assert treasury_point.scope=="data_pipeline"
 assert treasury_point.information_availability=="uncertain"

def test_checklist_deduplicates_semantically_identical_items():
 class DB:
  async def fetch(self,*args):
   base={"status":"open","area":"target_price","category":"UNSUPPORTED_ASSUMPTION","scope":"valuation_process","severity":"high","recommended_action":"Verify provenance","recurrence_count":1}
   return [{**base,"recurrence_key":"tru.jo|UNSUPPORTED_ASSUMPTION|valuation_process|target price"},{**base,"recurrence_key":None,"recurrence_count":2}]
 items=asyncio.run(analyst_checklist("TRU.JO",DB()))
 assert len(items)==1 and items[0]["recurrence_count"]==1