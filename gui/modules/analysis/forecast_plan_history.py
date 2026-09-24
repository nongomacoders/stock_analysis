"""Read-only ForecastPlan history and safe clone/repair helpers."""
from __future__ import annotations
import json
from .forecast_plan import ForecastPlan,new_version
from .retail_forecast import build_retail_earnings_forecasts,build_retail_forecasts
from .dcf_mapping import map_accepted_fy2027_inputs


def history_rows(plans:list[ForecastPlan])->list[dict]:
    return [{"version":p.plan_version,"status":p.status.value,"created":p.created_at,
             "plan_id":str(p.forecast_plan_id),
             "parent_id":str(p.previous_plan_id) if p.previous_plan_id else None,
             "source_report_id":str(p.source_report_version_id)}
            for p in sorted(plans,key=lambda item:item.plan_version,reverse=True)]


def render_readonly_plan(plan:ForecastPlan)->str:
    lines=[f"ForecastPlan v{plan.plan_version} {plan.status.value.upper()}",
           f"Plan ID: {plan.forecast_plan_id}",f"Parent plan: {plan.previous_plan_id or 'none'}",
           f"Source report: {plan.source_report_version_id}",f"Created: {plan.created_at}",
           f"Approval: {plan.approval_status} | {plan.approved_by or 'not approved'}", "", "ASSUMPTIONS"]
    lines += [f"{a.period_label or '-'} | {a.case} | {a.operation_segment or 'Group'} | "
              f"{a.field} = {a.value} {a.unit or ''} | {a.origin.value} | {a.approval_state.value} | {a.assumption_id}"
              for a in plan.assumptions]
    lines += ["","ENGINE MAPPING",json.dumps(
        plan.engine_plan.model_dump(mode="json") if plan.engine_plan else None,
        indent=2,default=str)]
    return "\n".join(lines)


def derived_reference_status(plan:ForecastPlan,evidence:list)->dict:
    case=plan.engine_plan.cases.get("base") if plan.engine_plan else None
    dcf=case.dcf if case else None
    if not dcf: return {"stale":[],"current":{},"status":"NOT_APPLICABLE"}
    records,_=build_retail_forecasts(plan,evidence,include_proposed=False)
    earnings,_=build_retail_earnings_forecasts(plan,evidence,records=records,include_proposed=False)
    current={"revenue":{str(r.derived_metric_id) for r in records if r.valuation_eligible and r.output_metric=="forecast_revenue"},
             "ebit":{str(r.derived_metric_id) for r in earnings if r.valuation_eligible}}
    stale=[]
    for year in dcf.years:
        for field in ("revenue","ebit"):
            ref=year.inputs.get(field)
            if ref and str(ref.metric_id) not in current[field]:
                stale.append({"period_end":str(year.period_end),"field":field,
                              "metric_id":str(ref.metric_id)})
    return {"status":"STALE" if stale else "CURRENT","stale":stale,"current":current}


def clone_as_repaired_draft(plan:ForecastPlan,evidence:list,*,changed_by:str):
    status=derived_reference_status(plan,evidence)
    if status["status"]=="STALE":
        cloned,resolved=map_accepted_fy2027_inputs(plan,evidence,changed_by=changed_by)
        return cloned,{"repair":"DERIVED_REFERENCES_REGENERATED","before":status,"resolved":resolved}
    return new_version(plan,changed_by=changed_by),{"repair":"NOT_REQUIRED","before":status}
