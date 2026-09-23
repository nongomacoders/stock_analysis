"""Persistence and orchestration for isolated post-publication report reviews."""
from __future__ import annotations
import json,re
from uuid import uuid4
from modules.analysis.research_comparison import (COMPARISON_ENGINE_VERSION,COMPARISON_PROMPT_VERSION,ComparisonType,
 build_prompt,classify_comparison,compare_forecasts,compare_metrics,parse_review,reporting_period_identity,
 reporting_transition_key,unsupported_legacy,metric_key,LearningPoint,LearningCategory)
def _json(value):return json.loads(value) if isinstance(value,str) else (value or {})
def _metric_rows(rows):return [_json(r["metric"]) for r in rows]
async def _load_bundle(report_id,db):
 rows=await db.fetch("SELECT report_id,ticker,status,report_content,audit FROM deepresearch_versions WHERE report_id=$1::uuid",report_id)
 if not rows:return None
 row=dict(rows[0]); row["audit"]=_json(row.get("audit")); row["metrics"]=_metric_rows(await db.fetch("SELECT metric FROM financial_metrics WHERE report_id=$1::uuid",report_id))
 vals=await db.fetch("SELECT status,result,valuation_id FROM deterministic_valuations WHERE report_version_id=$1::uuid ORDER BY generated_at DESC LIMIT 1",report_id)
 if vals:
  result=_json(vals[0]["result"]); row["valuation"]={"status":vals[0]["status"],"valuation_id":str(vals[0]["valuation_id"]),"target_price":result.get("target_price"),"legacy_gemini_target":result.get("legacy_gemini_target"),"valuation_engine_version":result.get("valuation_engine_version")}
 else:row["valuation"]=None
 return row
async def _approved_plans(ticker,previous_report_id,db):
 rows=await db.fetch("SELECT plan FROM forecast_plans WHERE ticker=$1 AND source_report_version_id=$2::uuid AND status='approved' ORDER BY plan_version",ticker,previous_report_id)
 return [_json(r["plan"]) for r in rows]
def newly_typed_metrics(previous,current):
 old={metric_key(m) for m in previous}
 return [{"metric_name":m.get("name"),"value":m.get("normalized_value") or m.get("value"),"unit":m.get("normalized_unit") or m.get("unit"),"metric_id":m.get("metric_id"),"evidence_quote":m.get("evidence_quote")} for m in current if metric_key(m) not in old]
def deterministic_summary(previous,current,plans):
 previous_period=reporting_period_identity(previous["metrics"]); current_period=reporting_period_identity(current["metrics"]); kind=classify_comparison(previous_period,current_period); transition=reporting_transition_key(kind,previous_period,current_period)
 return {"comparison_type":kind.value,"previous_period":previous_period,"current_period":current_period,"reporting_transition_key":transition,
  "metric_deltas":compare_metrics(previous["metrics"],current["metrics"]),
  "forecast_outcomes":compare_forecasts(plans,current["metrics"]) if kind==ComparisonType.NEW_REPORTING_PERIOD else [],
  "unsupported_legacy_assumptions":unsupported_legacy(previous["metrics"]),"newly_typed_metrics":newly_typed_metrics(previous["metrics"],current["metrics"]),
  "valuation":{"previous":previous.get("valuation"),"current":current.get("valuation")}}
def deterministic_learning(summary):
 points=[]
 for item in summary["unsupported_legacy_assumptions"]:
  points.append(LearningPoint(category=LearningCategory.UNSUPPORTED_ASSUMPTION,scope="valuation_process",severity="high",information_availability="available",previous_analysis_quality="unsupported",area=item["metric_name"],finding=f"Previous report retained an unsupported legacy {item['metric_name']} value.",evidence=[f"Value {item.get('value')} {item.get('unit') or ''}; metric {item.get('metric_id')}"],source_metric_ids=[item["metric_id"]] if item.get("metric_id") else [],recommended_action="Require current evidence or an explicitly approved ForecastPlan assumption."))
 if summary["comparison_type"]==ComparisonType.SAME_PERIOD_REVISION.value:
  for item in summary["newly_typed_metrics"]:
   if item["metric_name"]=="treasury_shares":points.append(LearningPoint(category=LearningCategory.SHARE_COUNT_ERROR,scope="data_pipeline",severity="high",information_availability="uncertain",previous_analysis_quality="missed",area="Treasury Share Accounting",finding="The revised same-period extraction typed treasury shares that the earlier extraction omitted.",evidence=[f"Typed treasury shares: {item['value']} {item.get('unit') or ''}; metric {item.get('metric_id')}",item.get("evidence_quote") or "Same-period disclosure"],source_metric_ids=[item["metric_id"]] if item.get("metric_id") else [],recommended_action="Extract and reconcile gross issued, treasury, net external, weighted-average and diluted shares from the same-period evidence."))
 for item in summary["forecast_outcomes"]:
  if item["classification"] in {"optimistic","pessimistic","materially_wrong"}:
   severity="high" if item["classification"]=="materially_wrong" else "medium"; points.append(LearningPoint(category=LearningCategory.FORECAST_ERROR,scope="ticker_analysis",severity=severity,information_availability="unavailable",previous_analysis_quality="incorrect",area=item["field"],finding=f"Approved forecast was {item['classification']} versus the subsequent actual.",evidence=[f"Forecast {item['forecast']} versus actual {item['actual']} {item.get('unit') or ''}; error {item.get('error_percent')}%"],source_metric_ids=[item["actual_metric_id"]] if item.get("actual_metric_id") else [],recommended_action="Review the forecast driver and evidence before the next plan approval."))
 return points
def normalized_recurrence_key(ticker,point):
 area_value=point.get("area") if isinstance(point,dict) else point.area
 category=point.get("category") if isinstance(point,dict) else point.category.value
 scope=point.get("scope") if isinstance(point,dict) else point.scope
 area=re.sub(r"[^a-z0-9]+"," ",area_value.casefold()).strip()
 return f"{ticker.casefold()}|{category}|{scope}|{area}"
def next_learning_lifecycle(distinct_transition_count,transition_already_seen):
 recurrence=distinct_transition_count+(0 if transition_already_seen else 1)
 return max(1,recurrence),("reinforced" if recurrence>1 else "open")
async def _insert_learning(comparison_id,ticker,points,transition,db):
 for point in points:
  key=normalized_recurrence_key(ticker,point)
  rows=await db.fetch("""SELECT reporting_transition_key FROM research_learning_points
   WHERE recurrence_key=$1 AND reporting_transition_key IS NOT NULL""",key)
  transitions={r["reporting_transition_key"] for r in rows}; recurrence,status=next_learning_lifecycle(len(transitions),transition in transitions)
  if status=="reinforced":await db.execute("UPDATE research_learning_points SET status='reinforced',recurrence_count=$2 WHERE recurrence_key=$1 AND status IN ('open','reinforced')",key,recurrence)
  await db.execute("""INSERT INTO research_learning_points
   (learning_point_id,comparison_id,ticker,category,scope,severity,area,finding,evidence,previous_report_reference,current_report_reference,source_metric_ids,recommended_action,status,recurrence_count,information_availability,previous_analysis_quality,recurrence_key,reporting_transition_key)
   VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10,$11,$12::uuid[],$13,$14,$15,$16,$17,$18,$19)""",
   uuid4(),comparison_id,ticker,point.category.value,point.scope,point.severity,point.area,point.finding,json.dumps(point.evidence),point.previous_report_reference,point.current_report_reference,point.source_metric_ids,point.recommended_action,status,recurrence,point.information_availability,point.previous_analysis_quality,key,transition)
async def run_post_publication_comparison(ticker,previous_report_id,current_report_id,db=None,query=None,require_current=True):
 """Run only after publication. Failures are stored and never affect the report."""
 from core.db.engine import DBEngine
 from modules.analysis.selector import managed_query_ai,TASK_MAP,DEFAULT_TASK
 db=db or DBEngine; previous=await _load_bundle(previous_report_id,db); current=await _load_bundle(current_report_id,db)
 if not previous or not current:raise ValueError("Both exact report versions are required")
 if current["status"]!="published":raise ValueError("Comparison requires a successfully published current report")
 if require_current:
  active=await db.fetch("SELECT current_report_id FROM stock_analysis WHERE ticker=$1",ticker)
  if not active or str(active[0]["current_report_id"])!=str(current_report_id):raise ValueError("Current report pointer does not match comparison")
 plans=await _approved_plans(ticker,previous_report_id,db); deterministic=deterministic_summary(previous,current,plans); kind=deterministic["comparison_type"]; comparison_id=uuid4()
 rows=await db.fetch("""INSERT INTO deepresearch_comparisons
  (comparison_id,ticker,previous_report_id,current_report_id,comparison_engine_version,comparison_prompt_version,status,deterministic_summary_json,comparison_type,previous_period_json,current_period_json,reporting_transition_key)
  VALUES($1,$2,$3::uuid,$4::uuid,$5,$6,'pending',$7::jsonb,$8,$9::jsonb,$10::jsonb,$11)
  ON CONFLICT(previous_report_id,current_report_id,comparison_engine_version,comparison_prompt_version)
  DO UPDATE SET status=CASE WHEN deepresearch_comparisons.status='completed' THEN 'completed' ELSE 'pending' END,error_message=NULL,deterministic_summary_json=EXCLUDED.deterministic_summary_json,comparison_type=EXCLUDED.comparison_type,previous_period_json=EXCLUDED.previous_period_json,current_period_json=EXCLUDED.current_period_json,reporting_transition_key=EXCLUDED.reporting_transition_key
  RETURNING comparison_id,status""",comparison_id,ticker,previous_report_id,current_report_id,COMPARISON_ENGINE_VERSION,COMPARISON_PROMPT_VERSION,json.dumps(deterministic,default=str),kind,json.dumps(deterministic["previous_period"]),json.dumps(deterministic["current_period"]),deterministic["reporting_transition_key"])
 comparison_id=rows[0]["comparison_id"]
 if rows[0]["status"]=="completed":return comparison_id
 prompt=build_prompt(previous["report_content"] or "",current["report_content"] or "",deterministic,previous["audit"],current["audit"]); config=TASK_MAP.get("research_comparison",DEFAULT_TASK)
 try:
  response=await (query or managed_query_ai)("research_comparison",prompt); text=response if isinstance(response,str) else (getattr(response,"text","") or ""); review=parse_review(text,ComparisonType(kind))
  points=[*deterministic_learning(deterministic),*review.learning_points,*review.positive_lessons,*review.new_information]; await _insert_learning(comparison_id,ticker,points,deterministic["reporting_transition_key"],db)
  await db.execute("UPDATE deepresearch_comparisons SET status='completed',completed_at=NOW(),qualitative_review_json=$2::jsonb,overall_summary=$3,model_name=$4,error_message=NULL WHERE comparison_id=$1",comparison_id,review.model_dump_json(),review.overall_summary,config["m"]); return comparison_id
 except Exception as exc:
  await db.execute("UPDATE deepresearch_comparisons SET status='failed',completed_at=NOW(),error_message=$2,model_name=$3 WHERE comparison_id=$1",comparison_id,str(exc),config["m"]); raise
async def list_comparisons(ticker,db=None):
 from core.db.engine import DBEngine
 return [dict(r) for r in await (db or DBEngine).fetch("SELECT * FROM deepresearch_comparisons WHERE ticker=$1 ORDER BY created_at DESC",ticker)]
async def list_learning_points(ticker,db=None):
 from core.db.engine import DBEngine
 return [dict(r) for r in await (db or DBEngine).fetch("SELECT * FROM research_learning_points WHERE ticker=$1 ORDER BY created_at DESC",ticker)]
async def analyst_checklist(ticker,db=None):
 from core.db.engine import DBEngine
 db=db or DBEngine
 points=[dict(r) for r in await db.fetch("""SELECT lp.* FROM research_learning_points lp JOIN deepresearch_comparisons c ON c.comparison_id=lp.comparison_id WHERE lp.ticker=$1 AND c.status='completed' AND NOT EXISTS (SELECT 1 FROM deepresearch_comparisons newer WHERE newer.previous_report_id=c.previous_report_id AND newer.current_report_id=c.current_report_id AND newer.status='completed' AND newer.created_at>c.created_at) ORDER BY lp.created_at DESC""",ticker)]; seen=set(); items=[]
 for p in points:
  if p["status"] not in {"open","reinforced"}:continue
  key=(p.get("recurrence_key") or normalized_recurrence_key(ticker,p)).casefold()
  if key in seen:continue
  seen.add(key); items.append({"area":p["area"],"category":p["category"],"severity":p["severity"],"action":p["recommended_action"],"recurrence_count":p["recurrence_count"]})
 return items
async def update_learning_status(learning_point_id,status,resolution_notes=None,db=None):
 if status not in {"open","reinforced","resolved","superseded","dismissed"}:raise ValueError("Invalid learning status")
 from core.db.engine import DBEngine
 await (db or DBEngine).execute("UPDATE research_learning_points SET status=$2,resolution_notes=$3,resolved_at=CASE WHEN $2 IN ('resolved','superseded','dismissed') THEN NOW() ELSE NULL END WHERE learning_point_id=$1::uuid",learning_point_id,status,resolution_notes)
