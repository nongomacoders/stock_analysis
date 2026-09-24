from datetime import date,datetime,timezone
from decimal import Decimal
from uuid import uuid4
import pytest

from modules.analysis.dcf_mapping import map_accepted_fy2027_inputs
from modules.analysis.forecast_plan import (
    ApprovalState,ForecastAssumption,ForecastPeriod,ForecastPlan,Origin,PlanStatus)
from modules.analysis.retail_forecast import build_retail_earnings_forecasts,build_retail_forecasts
from modules.analysis.valuation.engine import CasePlan,DcfSpec,ValuationPlan,WaccSpec,YearInputSpec
from modules.analysis.valuation.models import Basis,InputRef,TerminalMethod


def assumption(field,value,unit,*,accepted=True):
    return ForecastAssumption(field=field,value=Decimal(str(value)),unit=unit,currency="ZAR",
        period_label="FY2027",operation_segment="Group",case="base",
        origin=Origin.ANALYST_ASSUMPTION,
        approval_state=ApprovalState.ACCEPTED if accepted else ApprovalState.PROPOSED,
        rationale="Synthetic reviewed input",created_by="analyst")


def fixture(*,proposed=None,omit=None,component_conflict=False):
    rid=uuid4(); period=ForecastPeriod(label="FY2027",start=date(2026,6,29),end=date(2027,6,27))
    fields=[("revenue_growth",2.5,"percentage"),("sale_of_merchandise_growth",2,"percentage"),
      ("trading_margin",13,"percentage"),("depreciation",1516,"ZAR"),("tax_rate",25.3,"percentage"),
      ("total_capex",592,"ZAR"),("working_capital",188,"ZAR"),("other_recurring_cash",0,"ZAR"),
      ("wacc",12.5,"percentage"),("terminal_growth",4,"percentage")]
    assumptions=[assumption(f,v,u,accepted=f!=proposed) for f,v,u in fields if f!=omit]
    growth=next(a for a in assumptions if a.field=="terminal_growth")
    years=[]
    if component_conflict:
        years=[YearInputSpec(period_end=period.end,inputs={"operating_cost":InputRef(metric_id=uuid4(),field="operating_cost")})]
    dcf=DcfSpec(valuation_date=date(2026,9,23),years=years,cash_flow_currency="ZAR",
      cash_flow_basis=Basis.NOMINAL,inflation_basis="ZAR_CPI",
      wacc=WaccSpec(currency="ZAR",basis=Basis.NOMINAL,inflation_basis="ZAR_CPI"),
      terminal_method=TerminalMethod.PERPETUITY_GROWTH,
      terminal_growth=InputRef(metric_id=growth.assumption_id,field="terminal_growth"))
    engine=ValuationPlan(ticker="TRU.JO",report_version_id=rid,valuation_date=date(2026,9,23),
      sector="retail",cases={"base":CasePlan(rationale="test",primary_method="DCF",dcf=dcf)})
    plan=ForecastPlan(ticker="TRU.JO",created_by="analyst",source_report_version_id=rid,
      horizon=[period],assumptions=assumptions,engine_plan=engine,status=PlanStatus.APPROVED,
      approval_status="approved",approved_by="reviewer",approved_at=datetime.now(timezone.utc))
    evidence=[
      {"metric_id":str(uuid4()),"name":"revenue","value":"23030","unit":"ZAR","currency":"ZAR","period_end":"2026-06-28","source":"AFS"},
      {"metric_id":str(uuid4()),"name":"sale_of_merchandise","value":"21339","unit":"ZAR","currency":"ZAR","period_end":"2026-06-28","source":"AFS"},
      {"metric_id":str(uuid4()),"name":"trading_profit","value":"2774","unit":"ZAR","currency":"ZAR","period_end":"2026-06-28","source":"AFS"},
    ]
    return plan,evidence


def test_successful_mapping_creates_new_unapproved_draft_and_exact_contract():
    original,evidence=fixture(); original_json=original.model_dump_json()
    mapped,resolved=map_accepted_fy2027_inputs(original,evidence,changed_by="Dion")
    year=mapped.engine_plan.cases["base"].dcf.years[0]
    assert mapped.forecast_plan_id!=original.forecast_plan_id and mapped.status==PlanStatus.DRAFT
    assert original.model_dump_json()==original_json and original.status==PlanStatus.APPROVED
    assert year.period_end==date(2027,6,27)
    assert set(year.inputs)=={"revenue","ebit","depreciation","tax_rate","total_capex","working_capital","other_recurring_cash"}
    assert "operating_cost" not in year.inputs and "corporate_cost" not in year.inputs
    assert mapped.engine_plan.cases["base"].dcf.wacc.supported_wacc.field=="wacc"
    assert resolved["already_mapped"] is False


@pytest.mark.parametrize("field,message",[
    ("revenue_growth","revenue forecast"),("sale_of_merchandise_growth","direct EBIT"),
    ("depreciation","depreciation"),("tax_rate","tax_rate"),("total_capex","total_capex"),
    ("working_capital","working_capital"),("other_recurring_cash","other_recurring_cash"),
    ("trading_margin","direct EBIT"),("wacc","wacc")])
def test_missing_required_mapping_is_atomic(field,message):
    plan,evidence=fixture(omit=field); before=plan.model_dump_json()
    with pytest.raises(ValueError,match=message): map_accepted_fy2027_inputs(plan,evidence,changed_by="Dion")
    assert plan.model_dump_json()==before


def test_proposed_assumption_is_not_eligible():
    plan,evidence=fixture(proposed="revenue_growth")
    with pytest.raises(ValueError,match="revenue forecast"):
        map_accepted_fy2027_inputs(plan,evidence,changed_by="Dion")


def test_direct_component_conflict_is_rejected():
    plan,evidence=fixture(component_conflict=True)
    with pytest.raises(ValueError,match="conflicts with direct EBIT"):
        map_accepted_fy2027_inputs(plan,evidence,changed_by="Dion")


def test_derived_ids_are_resolved_for_new_draft_and_repeat_is_idempotent():
    plan,evidence=fixture(); mapped,_=map_accepted_fy2027_inputs(plan,evidence,changed_by="Dion")
    records,_=build_retail_forecasts(mapped,evidence,include_proposed=False)
    earnings,_=build_retail_earnings_forecasts(mapped,evidence,records=records,include_proposed=False)
    year=mapped.engine_plan.cases["base"].dcf.years[0]
    assert year.inputs["revenue"].metric_id==next(r.derived_metric_id for r in records if r.output_metric=="forecast_revenue")
    assert year.inputs["ebit"].metric_id==earnings[0].derived_metric_id
    again,resolved=map_accepted_fy2027_inputs(mapped,evidence,changed_by="Dion")
    assert again.forecast_plan_id==mapped.forecast_plan_id and resolved["already_mapped"] is True


def test_save_reload_model_roundtrip_preserves_mapping():
    plan,evidence=fixture(); mapped,_=map_accepted_fy2027_inputs(plan,evidence,changed_by="Dion")
    restored=ForecastPlan.model_validate_json(mapped.model_dump_json())
    assert restored.engine_plan.cases["base"].dcf==mapped.engine_plan.cases["base"].dcf




def test_detailed_afs_baseline_wins_over_rounded_sens_value():
    plan,evidence=fixture()
    evidence.extend([
      {"metric_id":str(uuid4()),"name":"sale_of_merchandise","value":"21300","unit":"ZAR","currency":"ZAR","period_end":"2026-06-28","document_role":"results_sens"},
      {"metric_id":str(uuid4()),"name":"sale_of_merchandise","value":"21339","unit":"ZAR","currency":"ZAR","period_end":"2026-06-28","document_role":"annual_financial_statements"},
    ])
    _,resolved=map_accepted_fy2027_inputs(plan,evidence,changed_by="Dion")
    assert resolved["ebit"].historical_sale_of_merchandise==Decimal("21339")
