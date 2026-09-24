"""Controlled mapping of accepted retail forecasts into the deterministic DCF contract."""
from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal

from .forecast_plan import ApprovalState, ForecastPlan, Origin, new_version
from .retail_forecast import build_retail_earnings_forecasts, build_retail_forecasts
from .valuation.engine import YearInputSpec
from .valuation.models import InputRef

PERIOD = "FY2027"
CASE = "base"


def _accepted(plan: ForecastPlan, field: str):
    matches=[a for a in plan.assumptions
             if a.field==field and a.period_label==PERIOD and a.case==CASE
             and (a.operation_segment or "Group")=="Group"
             and a.origin in {Origin.ANALYST_ASSUMPTION,Origin.SCENARIO_ASSUMPTION}
             and a.approval_state==ApprovalState.ACCEPTED and a.value is not None]
    if len(matches)>1: raise ValueError(f"Multiple accepted Group {field} assumptions")
    return matches[0] if matches else None


def resolve_fy2027_mapping(plan: ForecastPlan,evidence:list)->dict:
    if plan.engine_plan is None or "base" not in plan.engine_plan.cases:
        raise ValueError("Base DCF engine mapping is missing")
    base=plan.engine_plan.cases["base"]
    if base.primary_method!="DCF" or base.dcf is None:
        raise ValueError("Base case must contain a DCF specification")
    period=next((p for p in plan.horizon if p.label==PERIOD),None)
    missing=[]
    if period is None: missing.append("valid FY2027 period")
    forecasts,warnings=build_retail_forecasts(plan,evidence,include_proposed=False)
    revenue=[r for r in forecasts if r.period==PERIOD and r.case==CASE and r.operation=="Group"
             and r.output_metric=="forecast_revenue" and r.valuation_eligible]
    earnings,earnings_warnings=build_retail_earnings_forecasts(
        plan,evidence,records=forecasts,include_proposed=False)
    ebit=[r for r in earnings if r.period==PERIOD and r.case==CASE and r.operation=="Group"
          and r.output_metric=="forecast_trading_profit" and r.valuation_eligible]
    if len(revenue)!=1: missing.append("one accepted Group revenue forecast")
    if len(ebit)!=1: missing.append("one eligible direct EBIT forecast")
    assumptions={}
    for field in ("depreciation","tax_rate","working_capital","other_recurring_cash","wacc"):
        assumptions[field]=_accepted(plan,field)
        if assumptions[field] is None: missing.append(f"accepted {field}")
    total=_accepted(plan,"total_capex")
    sustaining=_accepted(plan,"sustaining_capex")
    growth=_accepted(plan,"growth_capex")
    if total and (sustaining or growth):
        raise ValueError("Direct total capex and split capex cannot both be mapped")
    if total:
        assumptions["total_capex"]=total
    elif sustaining and growth:
        assumptions.update(sustaining_capex=sustaining,growth_capex=growth)
    else:
        missing.append("accepted total_capex or complete sustaining/growth capex")
    existing=next((y for y in base.dcf.years if period and y.period_end==period.end),None)
    if existing and ("operating_cost" in existing.inputs or "corporate_cost" in existing.inputs
                     or existing.cost_components):
        raise ValueError("Existing FY2027 component EBIT mapping conflicts with direct EBIT")
    if missing:
        detail=[]
        for warning in [*warnings,*earnings_warnings]:
            if warning.get("period")==PERIOD and warning.get("operation")=="Group":
                detail.append(f"{warning['code']}: {warning['message']}")
        raise ValueError("DCF mapping incomplete: "+", ".join(missing)+
                         (("\n"+"\n".join(detail)) if detail else ""))
    inputs={
        "revenue":InputRef(metric_id=revenue[0].derived_metric_id,field="revenue",case=CASE),
        "ebit":InputRef(metric_id=ebit[0].derived_metric_id,field="ebit",case=CASE),
    }
    for field,item in assumptions.items():
        if field=="wacc": continue
        if field in inputs: raise ValueError(f"Duplicate DCF field mapping: {field}")
        inputs[field]=InputRef(metric_id=item.assumption_id,field=field,case=CASE)
    year=YearInputSpec(period_end=period.end,inputs=inputs)
    wacc_ref=InputRef(metric_id=assumptions["wacc"].assumption_id,field="wacc",case=CASE)
    return {"period":period,"year":year,"wacc_ref":wacc_ref,
            "revenue":revenue[0],"ebit":ebit[0],"assumptions":assumptions}


def _is_mapped(plan:ForecastPlan,resolved:dict)->bool:
    dcf=plan.engine_plan.cases["base"].dcf
    matches=[y for y in dcf.years if y.period_end==resolved["period"].end]
    return (len(matches)==1 and matches[0]==resolved["year"]
            and dcf.wacc.supported_wacc==resolved["wacc_ref"]
            and not dcf.wacc.components)


def map_accepted_fy2027_inputs(plan:ForecastPlan,evidence:list,*,changed_by:str)->tuple[ForecastPlan,dict]:
    current=resolve_fy2027_mapping(plan,evidence)
    if _is_mapped(plan,current):
        return plan,{**current,"already_mapped":True}
    draft=new_version(plan,changed_by=changed_by)
    resolved=resolve_fy2027_mapping(draft,evidence)
    engine=draft.engine_plan; base=engine.cases["base"]; dcf=base.dcf
    years=[y for y in dcf.years if y.period_end!=resolved["period"].end]
    years=sorted([*years,resolved["year"]],key=lambda y:y.period_end)
    wacc=dcf.wacc.model_copy(update={"supported_wacc":resolved["wacc_ref"],"components":None})
    mapped_dcf=dcf.model_copy(update={"years":years,"wacc":wacc})
    mapped_base=base.model_copy(update={"dcf":mapped_dcf})
    mapped_engine=engine.model_copy(update={"cases":{**engine.cases,"base":mapped_base}})
    mapped=draft.model_copy(update={"engine_plan":mapped_engine,"updated_at":datetime.now(timezone.utc)})
    return mapped,{**resolved,"already_mapped":False}


def render_fy2027_mapping_preview(resolved:dict)->str:
    money=lambda value:f"R{Decimal(str(value)):,.2f}"
    rows=["FY2027 DCF mapping preview",""]
    rows += ["revenue",f"  {money(resolved['revenue'].derived_forecast_value)}",
             f"  source: derived forecast_revenue [{resolved['revenue'].derived_metric_id}]","  status: ELIGIBLE",""]
    rows += ["ebit",f"  {money(resolved['ebit'].forecast_trading_profit)}",
             f"  source: derived forecast_trading_profit [{resolved['ebit'].derived_metric_id}]","  status: ELIGIBLE",""]
    for field in ("depreciation","tax_rate","total_capex","sustaining_capex","growth_capex",
                  "working_capital","other_recurring_cash","wacc"):
        item=resolved["assumptions"].get(field)
        if item: rows += [field,f"  {item.value} {item.unit or ''}",f"  source: accepted assumption [{item.assumption_id}]",""]
    rows += ["period_end",f"  {resolved['period'].end}","",
             "Direct EBIT route: ACTIVE","Component operating/corporate cost route: NOT MAPPED"]
    if resolved.get("already_mapped"): rows += ["","Already mapped"]
    return "\n".join(rows)
