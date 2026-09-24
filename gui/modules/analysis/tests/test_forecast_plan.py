"""Phase 5 forecast-plan controls, with no invented Jubilee assumptions."""
import sys
from pathlib import Path
from uuid import uuid4
from datetime import date
from decimal import Decimal
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from modules.analysis.forecast_plan import (ForecastPlan, ForecastPeriod, ForecastAssumption, Origin,
    ApprovalState, PlanStatus, new_version, accept_suggestion,
    discard_proposed_assumption, reject_suggestion, approve_plan,
    eligible_assumptions, scenario_differences, forecast_operating_schedule, price_fx_schedule,
    calculate_plan_wacc, preview_valuation, materialize_assumption, horizon_for_assumption,
    allowed_forecast_fields, configure_terminal_method, forecast_selector_values,
    terminal_configuration_status, terminal_method_values, terminal_metric_values)

RID=uuid4()

def plan():
    return ForecastPlan(ticker='JBL.JO',created_by='test analyst',source_report_version_id=RID,
        legacy_target=Decimal('1.70'),horizon=[ForecastPeriod(label=f'FY{y}',start=date(y-1,7,1),end=date(y,6,30)) for y in range(2027,2032)])

def assumption(field,value,unit,period='FY2027',case='base',origin=Origin.ANALYST_ASSUMPTION,state=ApprovalState.ACCEPTED,**kw):
    return ForecastAssumption(field=field,value=Decimal(str(value)),unit=unit,period_label=period,case=case,
        origin=origin,approval_state=state,rationale='Explicit synthetic analyst thesis',created_by='analyst',**kw)

def test_fiscal_periods_and_immutable_versions():
    p=plan(); assert len(p.horizon)==5 and p.horizon[0].start==date(2026,7,1)
    q=new_version(p,changed_by='analyst',notes='changed')
    assert q.previous_plan_id==p.forecast_plan_id and q.plan_version==2 and p.notes==''
    approved=approve_plan(p,'reviewer')
    assert approved.status==PlanStatus.APPROVED and approved.plan_version==1
    assert approved.forecast_plan_id==p.forecast_plan_id
    assert approved.legacy_target==Decimal('1.70')

def test_approval_and_suggestion_boundary():
    p=plan()
    suggestion=assumption('commodity_price',11000,'USD_per_tonne',origin=Origin.GEMINI_SUGGESTION,state=ApprovalState.PROPOSED,commodity='copper',currency='USD',price_type='analyst_forecast')
    p=p.model_copy(update={'assumptions':[suggestion]})
    assert not eligible_assumptions(p)
    accepted=accept_suggestion(p,suggestion.assumption_id,analyst='analyst',value=Decimal(12000),rationale='Edited copper view')
    assert accepted.assumptions[0].origin==Origin.GEMINI_SUGGESTION
    assert accepted.assumptions[1].accepted_from_suggestion_id==suggestion.assumption_id
    assert accepted.assumptions[1].value==12000
    assert len(eligible_assumptions(accepted))==1
    rejected=reject_suggestion(p,suggestion.assumption_id,'analyst')
    assert rejected.assumptions[0].approval_state==ApprovalState.REJECTED
    p2=p.model_copy(update={'assumptions':[assumption('recovery',.85,'percentage',state=ApprovalState.PROPOSED)]})
    with pytest.raises(ValueError): approve_plan(p2,'reviewer')
    with pytest.raises(ValueError): preview_valuation(p,[],[])

def test_production_ramp_and_missing_inputs():
    p=plan()
    a=[assumption('rom',120000,'tonnes_rom_per_year',operation_segment='Molefe',commodity='copper'),
       assumption('grade',1.45,'percentage',operation_segment='Molefe'),
       assumption('recovery',85,'percentage',operation_segment='Molefe'),
       assumption('processing_conversion',100,'percentage',operation_segment='Molefe'),
       assumption('ownership',100,'percentage',operation_segment='Molefe')]
    p=p.model_copy(update={'assumptions':a})
    rows=forecast_operating_schedule(p,'Molefe')
    assert rows[0]['contained_tonnes']==1740
    assert rows[0]['recovered_tonnes']==Decimal('1479.000000')
    assert rows[1]['status']=='NOT_CALCULABLE'
    p=p.model_copy(update={'assumptions':a[:-1]})
    assert 'ownership' in forecast_operating_schedule(p,'Molefe')[0]['missing']

def test_period_specific_prices_fx_and_scenarios():
    p=plan(); p=p.model_copy(update={'assumptions':[
        assumption('commodity_price',11000,'USD_per_tonne',currency='USD',commodity='copper',price_type='analyst_forecast'),
        assumption('fx_rate',18,'multiple',currency='ZAR',period='FY2027',fx_pair='USD/ZAR'),
        assumption('commodity_price',9000,'USD_per_tonne',currency='USD',commodity='copper',price_type='analyst_forecast',case='bear')]})
    assert price_fx_schedule(p,'commodity_price')[0]['value']=='11000'
    assert price_fx_schedule(p,'commodity_price')[1]['status']=='NOT_CALCULABLE'
    assert price_fx_schedule(p,'fx_rate')[1]['status']=='NOT_CALCULABLE'
    assert scenario_differences(p)[0]['base']=='11000'

def test_wacc_and_materialized_input():
    p=plan(); values={'risk_free_rate':.05,'equity_risk_premium':.06,'beta':1,
        'country_risk_premium':.02,'cost_of_debt':.08,'tax_rate':.25,'debt_weight':.2,'equity_weight':.8}
    assert calculate_plan_wacc(p)['status']=='NOT_CALCULABLE'
    p=p.model_copy(update={'assumptions':[assumption(k,v,'multiple',period=None) for k,v in values.items()]})
    assert calculate_plan_wacc(p)['calculated']['wacc']==Decimal('.116')
    a=assumption('commodity_price',11000,'USD_per_tonne',currency='USD',commodity='copper',price_type='analyst_forecast')
    p=p.model_copy(update={'assumptions':[a]})
    m,c=materialize_assumption(p,a.assumption_id)
    assert m.source_id==f'forecast_assumption:{a.assumption_id}' and c.metric_id==m.metric_id
    with pytest.raises(ValueError): materialize_assumption(p,uuid4())

def test_jubilee_stays_non_calculable_without_analyst_plan():
    p=plan(); assert p.engine_plan is None
    approved=approve_plan(p,'reviewer')
    with pytest.raises(ValueError,match='engine input mapping'): preview_valuation(approved,[],[])
    assert approved.legacy_target==Decimal('1.70')


def test_ramp_up_does_not_jump_to_nameplate():
    from modules.analysis.forecast_plan import forecast_operating_schedule
    p=plan()
    a=[]
    for year,util in [(2027,30),(2028,70),(2029,90)]:
        period=f"FY{year}"
        a += [assumption("nameplate_capacity",120000,"tonnes_capacity_per_year",period,operation_segment="Molefe",commodity="copper"),
              assumption("utilization",util,"percentage",period,operation_segment="Molefe"),
              assumption("ramp_up",100,"percentage",period,operation_segment="Molefe"),
              ForecastAssumption(field="project_start_date",unit="date",effective_date=date(2026,7,1),
                period_label=period,operation_segment="Molefe",origin=Origin.ANALYST_ASSUMPTION,
                approval_state=ApprovalState.ACCEPTED,rationale="Explicit project timing",created_by="analyst"),
              assumption("grade",1.45,"percentage",period,operation_segment="Molefe"),
              assumption("recovery",85,"percentage",period,operation_segment="Molefe"),
              assumption("processing_conversion",100,"percentage",period,operation_segment="Molefe"),
              assumption("ownership",100,"percentage",period,operation_segment="Molefe")]
    p=p.model_copy(update={"assumptions":a})
    rows=forecast_operating_schedule(p,"Molefe")
    assert [r['status'] for r in rows[:3]]==['PASS']*3
    assert rows[0]['rom_tonnes']<rows[1]['rom_tonnes']<rows[2]['rom_tonnes']
    assert rows[2]['rom_tonnes']<120000
    assert rows[3]['status']=='NOT_CALCULABLE'

def test_accepted_assumption_revalidates_and_draft_db_insert():
    from modules.analysis.forecast_plan import accept_assumption
    from modules.data.forecast_plans import save_plan
    import asyncio
    p=plan().model_copy(update={"assumptions":[assumption("recovery",85,"percentage",state=ApprovalState.PROPOSED)]})
    accepted=accept_assumption(p,p.assumptions[0].assumption_id,"reviewer")
    assert accepted.assumptions[0].approval_state==ApprovalState.ACCEPTED
    bad=p.model_copy(update={"assumptions":[assumption("recovery",85,"percentage",state=ApprovalState.PROPOSED)]})
    bad.assumptions[0].unit=None
    with pytest.raises(Exception): accept_assumption(bad,bad.assumptions[0].assumption_id,"reviewer")
    class FakeDB:
        calls=[]
        async def execute(self,*args): self.calls.append(args)
    fake=FakeDB()
    asyncio.run(save_plan(p,fake))
    assert str(p.forecast_plan_id) in str(fake.calls[0])


def test_valuation_approval_and_publication_are_distinct():
    import asyncio
    from modules.data.forecast_plans import approve_valuation,publish_valuation
    from modules.analysis.valuation.models import ValuationResult,ValuationStatus
    from modules.analysis.valuation.reconciliation import reconcile_equity
    rec=reconcile_equity(enterprise_or_operating_value=Decimal(100),non_operating_assets=Decimal(0),
        receivables=Decimal(0),cash=Decimal(0),debt=Decimal(0),lease_adjustments=Decimal(0),
        minorities=Decimal(0),other_equity_adjustments=Decimal(0),forward_shares=Decimal(100),shares_metric_id=uuid4())
    result=ValuationResult(ticker='TEST.JO',report_version_id=RID,valuation_date=date(2026,9,22),
        status=ValuationStatus.PASS,target_price=Decimal(1),reconciliation=rec)
    class FakeDB:
        state='draft'; calls=[]
        async def fetch(self,*args): return [{'result':result.model_dump(mode='json'),
            'publication_state':self.state,'forecast_plan_id':uuid4(),'plan_status':'approved'}]
        async def execute(self,sql,*args):
            self.calls.append((sql,args))
            self.state='approved' if "SET publication_state='approved'" in sql else 'published'
    db=FakeDB()
    with pytest.raises(ValueError): asyncio.run(publish_valuation(uuid4(),'publisher',db))
    asyncio.run(approve_valuation(uuid4(),'reviewer',db))
    assert db.state=='approved' and db.calls[-1][1][-1]=='reviewer'
    asyncio.run(publish_valuation(uuid4(),'publisher',db))
    assert db.state=='published' and db.calls[-1][1][-1]=='publisher'



def test_cost_schedule_preserves_definition_and_missing_factors():
    from modules.analysis.forecast_plan import cost_forecast_schedule
    p=plan()
    values=[assumption('latest_reported_cost',100,'USD',operation_segment='Roan',
                currency='USD',cost_definition='production_cost'),
            assumption('inflation',10,'percentage',operation_segment='Roan'),
            assumption('operational_efficiency',5,'percentage',operation_segment='Roan'),
            assumption('scale_factor',1,'multiple',operation_segment='Roan'),
            assumption('reagent_energy_factor',1,'multiple',operation_segment='Roan')]
    p=p.model_copy(update={'assumptions':values})
    rows=cost_forecast_schedule(p,'Roan')
    assert rows[0]['status']=='PASS' and rows[0]['value']==Decimal('104.500')
    assert rows[0]['cost_definition']=='production_cost'
    assert rows[1]['status']=='NOT_CALCULABLE'
    values[0]=values[0].model_copy(update={'cost_definition':'aisc'})
    p=p.model_copy(update={'assumptions':values})
    assert cost_forecast_schedule(p,'Roan')[0]['status']=='NOT_CALCULABLE'


def test_persisted_plan_jsonb_text_decodes(monkeypatch):
    import asyncio
    from modules.data.forecast_plans import list_plans,get_plan
    from core.db.engine import DBEngine
    p=plan()
    async def fetch(*args): return [{'plan':p.model_dump_json()}]
    monkeypatch.setattr(DBEngine,'fetch',fetch)
    assert asyncio.run(list_plans('JBL.JO'))[0].forecast_plan_id==p.forecast_plan_id
    assert asyncio.run(get_plan(p.forecast_plan_id)).forecast_plan_id==p.forecast_plan_id


def test_gemini_suggestion_stays_in_advisory_ledger():
    from modules.analysis.forecast_plan import record_gemini_suggestion
    p=plan()
    suggestion=assumption('utilization',70,'percentage',origin=Origin.GEMINI_SUGGESTION,
        state=ApprovalState.PROPOSED,operation_segment='Molefe')
    q=record_gemini_suggestion(p,suggestion)
    assert len(q.assumptions)==1 and eligible_assumptions(q)==[]
    with pytest.raises(ValueError): record_gemini_suggestion(q,assumption('utilization',80,'percentage'))


def test_approved_plan_rejects_unlinked_model_candidate():
    from modules.analysis.valuation.engine import ValuationPlan,CasePlan,SotpSpec
    from modules.analysis.financial_metrics import FinancialMetric,AssumptionType,SourceType,Unit
    from modules.analysis.valuation_preflight import candidate
    p=plan()
    mapping=ValuationPlan(ticker=p.ticker,report_version_id=p.source_report_version_id,valuation_date=date(2026,9,22),
        cases={'base':CasePlan(rationale='Explicit empty test',primary_method='SOTP',sotp=SotpSpec())})
    p=p.model_copy(update={'engine_plan':mapping})
    approved=approve_plan(p,'reviewer')
    m=FinancialMetric(ticker='JBL.JO',report_id=RID,name='asset_value',value=Decimal(100),unit=Unit.ZAR,
        source='Synthetic analyst view',source_type=SourceType.MODEL,
        assumption_type=AssumptionType.MODEL_ASSUMPTION,notes='Synthetic unlinked input')
    c=candidate(m,RID,'asset_value','base','unlinked model input')
    with pytest.raises(ValueError,match='accepted forecast-assumption link'):
        preview_valuation(approved,[m],[c])
    result=preview_valuation(approved,[],[])
    assert result.status.value=='NOT_CALCULABLE' and result.target_price is None
    assert result.calculation_inputs['forecast_plan']['forecast_plan_id']==str(approved.forecast_plan_id)

def test_assumption_can_atomically_add_fully_entered_financial_period():
    empty = ForecastPlan(ticker='TRU.JO', created_by='Dion', source_report_version_id=RID)
    horizon, added = horizon_for_assumption(
        empty, 'FY2027', start=date(2026, 6, 29), end=date(2027, 6, 27))
    assert added is True
    assert [(item.label, item.start, item.end) for item in horizon] == [
        ('FY2027', date(2026, 6, 29), date(2027, 6, 27))]
    proposed = ForecastAssumption(
        field='retail_sales_growth', value=Decimal('2.5'), unit='percentage',
        currency='ZAR', period_label='FY2027', operation_segment='Truworths Africa',
        case='base', origin=Origin.ANALYST_ASSUMPTION,
        rationale='Consumer rebound', created_by='Dion', confidence=Decimal('0.6'))
    updated = new_version(empty, changed_by='Dion', horizon=horizon, assumptions=[proposed])
    assert updated.horizon[0].label == updated.assumptions[0].period_label


def test_assumption_missing_period_dates_has_actionable_error():
    empty = ForecastPlan(ticker='TRU.JO', created_by='Dion', source_report_version_id=RID)
    with pytest.raises(ValueError, match="Enter its start and end dates"):
        horizon_for_assumption(empty, 'FY2027')


def test_existing_assumption_period_is_reused_without_duplicate():
    existing = ForecastPlan(
        ticker='TRU.JO', created_by='Dion', source_report_version_id=RID,
        horizon=[ForecastPeriod(label='FY2027', start=date(2026, 6, 29), end=date(2027, 6, 27))])
    horizon, added = horizon_for_assumption(existing, 'FY2027')
    assert added is False
    assert horizon == existing.horizon

def test_forecast_selectors_match_model_controlled_values():
    selectors = forecast_selector_values()
    assert selectors['case'] == ('base', 'bear', 'bull', 'informational')
    assert 'retail_sales_growth' in selectors['field']
    assert 'target_price' not in selectors['field']
    assert 'percentage' in selectors['unit']
    assert '%' not in selectors['unit']
    assert selectors['currency'] == ('ZAR', 'USD', 'GBP', 'EUR', 'HKD')


@pytest.mark.parametrize('changes, message', [
    ({'field': 'sales growth'}, 'Unknown forecast field'),
    ({'unit': '%'}, 'Unknown controlled unit'),
    ({'currency': 'RAND'}, 'Unknown controlled currency'),
    ({'case': 'upside'}, 'Unknown forecast case'),
    ({'confidence': Decimal('1.1')}, 'less than or equal to 1'),
    ({'period_label': None}, 'requires a fiscal period'),
])
def test_retail_forecast_rejects_uncontrolled_values(changes, message):
    values = dict(
        field='retail_sales_growth', value=Decimal('2.5'), unit='percentage',
        currency='ZAR', period_label='FY2027', operation_segment='Truworths Africa',
        case='base', origin=Origin.ANALYST_ASSUMPTION,
        rationale='Consumer rebound', created_by='Dion', confidence=Decimal('0.6'))
    values.update(changes)
    with pytest.raises(ValueError, match=message):
        ForecastAssumption(**values)


def test_screenshot_error_is_unknown_period_before_ui_resolution():
    proposed = ForecastAssumption(
        field='retail_sales_growth', value=Decimal('2.5'), unit='percentage',
        currency='ZAR', period_label='FY2027', operation_segment='Truworths Africa',
        case='base', origin=Origin.ANALYST_ASSUMPTION,
        rationale='Consumer rebound', created_by='Dion', confidence=Decimal('0.6'))
    with pytest.raises(ValueError, match='unknown financial period'):
        ForecastPlan(ticker='TRU.JO', created_by='Dion',
                     source_report_version_id=RID, assumptions=[proposed])


def test_retail_sales_growth_materializes_as_controlled_candidate():
    accepted = ForecastAssumption(
        field='retail_sales_growth', value=Decimal('2.5'), unit='percentage',
        currency='ZAR', period_label='FY2027', operation_segment='Truworths Africa',
        case='base', origin=Origin.ANALYST_ASSUMPTION,
        approval_state=ApprovalState.ACCEPTED,
        rationale='Consumer rebound', created_by='Dion', confidence=Decimal('0.6'))
    retail_plan = ForecastPlan(
        ticker='TRU.JO', created_by='Dion', source_report_version_id=RID,
        horizon=[ForecastPeriod(label='FY2027', start=date(2026, 6, 29), end=date(2027, 6, 27))],
        assumptions=[accepted])
    metric, candidate = materialize_assumption(retail_plan, accepted.assumption_id)
    assert metric.name == 'retail_sales_growth'
    assert metric.unit.value == 'percentage'
    assert candidate.valuation_field.value == 'retail_sales_growth'
    assert candidate.case_type.value == 'base'



def test_retail_trading_fields_are_controlled_percentage_period_fields():
    from modules.analysis.forecast_plan import allowed_forecast_fields
    assert {"sale_of_merchandise_growth", "trading_margin"} <= set(allowed_forecast_fields())
    for field in ("sale_of_merchandise_growth", "trading_margin"):
        item = ForecastAssumption(
            field=field, value=Decimal("3"), unit="percentage",
            period_label="FY2027", operation_segment="Group", case="base",
            origin=Origin.ANALYST_ASSUMPTION, approval_state=ApprovalState.PROPOSED,
            rationale="Analyst input", created_by="analyst")
        assert item.field == field
        with pytest.raises(ValueError, match="requires the percentage unit"):
            item.model_copy(update={"unit": "multiple"}).__class__.model_validate(
                {**item.model_dump(), "unit": "multiple"})


def terminal_plan(*items):
    return plan().model_copy(update={"assumptions": list(items)})


def test_terminal_selector_values_come_from_engine_enum():
    from modules.analysis.valuation.models import TerminalMethod
    assert terminal_method_values() == tuple(item.value for item in TerminalMethod)
    assert terminal_method_values() == ("perpetuity_growth", "exit_multiple")
    assert terminal_metric_values() == ("EBIT", "EBITDA")


def test_perpetuity_terminal_method_requires_accepted_growth_and_wacc():
    original = terminal_plan()
    configured = configure_terminal_method(
        original, "perpetuity_growth", sector="General Retail")
    status = terminal_configuration_status(configured)
    assert status["method"] == "perpetuity_growth"
    assert set(status["missing"]) == {"terminal_growth", "WACC"}
    assert configured.status == PlanStatus.DRAFT
    assert original.engine_plan is None
    assert configured.assumptions == original.assumptions


def test_exit_multiple_requires_accepted_multiple_and_terminal_metric():
    configured = configure_terminal_method(
        terminal_plan(), "exit_multiple", sector="General Retail")
    status = terminal_configuration_status(configured)
    assert set(status["missing"]) == {"exit_multiple", "terminal_metric"}
    multiple = assumption("exit_multiple", 6, "multiple", period=None)
    configured = configure_terminal_method(
        terminal_plan(multiple), "exit_multiple", terminal_metric="EBIT",
        sector="General Retail")
    status = terminal_configuration_status(configured)
    assert status["status"] == "ready"
    assert status["exit_multiple"] == Decimal("6")
    assert status["terminal_metric"] == "EBIT"


def test_terminal_methods_cannot_coexist():
    growth = assumption("terminal_growth", 4, "percentage", period=None)
    configured = configure_terminal_method(
        terminal_plan(growth), "perpetuity_growth", sector="General Retail")
    with pytest.raises(ValueError, match="Remove terminal-growth"):
        configure_terminal_method(configured, "exit_multiple", terminal_metric="EBIT")


def test_terminal_growth_must_remain_below_wacc():
    growth = assumption("terminal_growth", 5, "percentage", period=None)
    wacc = assumption("wacc_override", 4, "percentage", period=None)
    configured = configure_terminal_method(
        terminal_plan(growth, wacc), "perpetuity_growth",
        sector="General Retail")
    status = terminal_configuration_status(configured)
    assert status["status"] == "invalid"
    assert status["error"] == "WACC must be greater than terminal growth"


def test_terminal_selection_is_draft_only_and_round_trips_in_saved_json():
    source = terminal_plan(
        assumption("terminal_growth", 4, "percentage", period=None),
        assumption("wacc_override", 12.5, "percentage", period=None))
    configured = configure_terminal_method(
        source, "perpetuity_growth", sector="General Retail")
    assert configured.status == PlanStatus.DRAFT
    assert configured.approval_status == "unapproved"
    assert all(item.approval_state == ApprovalState.ACCEPTED
               for item in configured.assumptions)
    assert configured.forecast_plan_id != source.forecast_plan_id
    restored = ForecastPlan.model_validate_json(configured.model_dump_json())
    dcf = restored.engine_plan.cases["base"].dcf
    assert dcf.terminal_method.value == "perpetuity_growth"
    assert str(dcf.terminal_growth.metric_id) == str(
        configured.assumptions[0].assumption_id)
    assert terminal_configuration_status(restored)["status"] == "ready"


def test_tru_perpetuity_selection_reports_missing_growth_without_valuation():
    tru = ForecastPlan(
        ticker="TRU.JO", created_by="analyst",
        source_report_version_id=RID)
    configured = configure_terminal_method(
        tru, "perpetuity_growth", sector="General Retail")
    status = terminal_configuration_status(configured)
    assert status["method"] == "perpetuity_growth"
    assert "terminal_growth" in status["missing"]
    assert configured.status == PlanStatus.DRAFT


def test_terminal_selector_handler_does_not_approve_or_run_valuation(monkeypatch):
    from types import SimpleNamespace
    import components.valuation_workbench_tab as workbench
    source = plan()
    configured = new_version(source, changed_by="analyst")
    calls = []
    monkeypatch.setattr(
        workbench, "configure_terminal_method",
        lambda *args, **kwargs: configured)
    class Var:
        def __init__(self,value): self.value=value
        def get(self): return self.value
    class Status:
        def set(self,value): calls.append(("status",value))
    fake = SimpleNamespace(
        plan=source, terminal_method_var=Var("perpetuity_growth"),
        terminal_metric_var=Var(""), fields={"analyst": Var("Dion")},
        category="General Retail", pending=[], status=Status(),
        _render=lambda: calls.append(("render",None)),
        async_run_bg=lambda *args, **kwargs: calls.append(("valuation",None)),
    )
    fake._stage_plan=lambda proposed: (
        setattr(fake,'plan',proposed), setattr(fake,'pending',[proposed]),
        fake._render())
    workbench.ValuationWorkbenchTab._terminal_method_changed(fake)
    assert fake.plan is configured
    assert fake.pending == [configured]
    assert configured.status == PlanStatus.DRAFT
    assert not any(name == "valuation" for name, _ in calls)


def test_proposed_analyst_assumption_can_be_discarded_copy_on_write():
    proposed = assumption(
        "revenue_growth", 2.5, "percentage",
        origin=Origin.ANALYST_ASSUMPTION, state=ApprovalState.PROPOSED,
        operation_segment="Group")
    original = plan().model_copy(update={"assumptions": [proposed]})
    revised = discard_proposed_assumption(
        original, proposed.assumption_id, "Dion")
    assert revised.assumptions == []
    assert original.assumptions == [proposed]
    assert revised.previous_plan_id == original.forecast_plan_id
    assert revised.plan_version == original.plan_version + 1
    assert revised.status == PlanStatus.DRAFT


def test_accepted_analyst_assumption_cannot_be_discarded():
    accepted = assumption(
        "revenue_growth", 2.5, "percentage",
        operation_segment="Group")
    p = plan().model_copy(update={"assumptions": [accepted]})
    with pytest.raises(ValueError, match="Only a proposed analyst"):
        discard_proposed_assumption(p, accepted.assumption_id, "Dion")


def test_gemini_suggestion_still_uses_reject_not_discard():
    suggestion = assumption(
        "revenue_growth", 2.5, "percentage",
        origin=Origin.GEMINI_SUGGESTION, state=ApprovalState.PROPOSED,
        operation_segment="Group")
    p = plan().model_copy(update={"assumptions": [suggestion]})
    with pytest.raises(ValueError, match="Only a proposed analyst"):
        discard_proposed_assumption(p, suggestion.assumption_id, "Dion")
    rejected = reject_suggestion(p, suggestion.assumption_id, "Dion")
    assert rejected.assumptions[0].approval_state == ApprovalState.REJECTED


def test_discarded_proposal_no_longer_blocks_approval_but_remaining_one_does():
    first = assumption(
        "revenue_growth", 2.5, "percentage",
        origin=Origin.ANALYST_ASSUMPTION, state=ApprovalState.PROPOSED,
        operation_segment="Group")
    second = assumption(
        "retail_sales_growth", 2.5, "percentage",
        origin=Origin.ANALYST_ASSUMPTION, state=ApprovalState.PROPOSED,
        operation_segment="Group")
    p = plan().model_copy(update={"assumptions": [first, second]})
    one_left = discard_proposed_assumption(p, first.assumption_id, "Dion")
    with pytest.raises(ValueError, match="Review proposed assumptions"):
        approve_plan(one_left, "reviewer")
    none_left = discard_proposed_assumption(
        one_left, second.assumption_id, "Dion")
    approved_copy = approve_plan(none_left, "reviewer")
    assert approved_copy.status == PlanStatus.APPROVED
    assert none_left.status == PlanStatus.DRAFT


def test_txt_imported_proposal_can_be_discarded():
    from modules.analysis.forecast_txt_import import parse_forecast_txt
    current = plan()
    text = """FORECAST_PLAN
ticker=JBL.JO
case=base

ASSUMPTION
period=FY2027
operation=Group
field=revenue_growth
value=2.5
unit=percentage
currency=ZAR
confidence=0.6
analyst=Dion
rationale=Exploratory imported assumption.
"""
    preview = parse_forecast_txt(
        text, current_plan=current, current_ticker="JBL.JO",
        category="General Retail", allowed_operations={"Group"})
    imported = preview.assumptions[0]
    assert imported.origin == Origin.ANALYST_ASSUMPTION
    assert imported.approval_state == ApprovalState.PROPOSED
    draft = current.model_copy(
        update={"horizon": preview.horizon, "assumptions": [imported]})
    discarded = discard_proposed_assumption(
        draft, imported.assumption_id, "Dion")
    assert discarded.assumptions == []


def test_discard_ui_does_not_run_valuation_or_create_target(monkeypatch):
    from types import SimpleNamespace
    import components.valuation_workbench_tab as workbench
    proposed = assumption(
        "revenue_growth", 2.5, "percentage",
        origin=Origin.ANALYST_ASSUMPTION, state=ApprovalState.PROPOSED,
        operation_segment="Group")
    source = plan().model_copy(update={"assumptions": [proposed]})
    revised = discard_proposed_assumption(
        source, proposed.assumption_id, "Dion")
    calls = []
    monkeypatch.setattr(
        workbench.messagebox, "askyesno", lambda *args: True)
    monkeypatch.setattr(
        workbench, "discard_proposed_assumption", None, raising=False)
    class Table:
        def selection(self): return (str(proposed.assumption_id),)
    class Var:
        def get(self): return "Dion"
    class Status:
        def set(self,value): calls.append(("status",value))
    fake = SimpleNamespace(
        plan=source, assumption_table=Table(),
        fields={"analyst": Var()}, pending=[], status=Status(),
        _render=lambda: calls.append(("render",None)),
        async_run_bg=lambda *args, **kwargs: calls.append(("valuation",None)),
    )
    fake._stage_plan=lambda proposed: (
        setattr(fake,'plan',proposed), setattr(fake,'pending',[proposed]),
        fake._render())
    # The handler imports the model function locally; invoke normally.
    workbench.ValuationWorkbenchTab.discard_selected(fake)
    assert fake.plan.assumptions == []
    assert fake.plan.status == PlanStatus.DRAFT
    assert fake.plan.legacy_target == source.legacy_target
    assert not any(name == "valuation" for name, _ in calls)



