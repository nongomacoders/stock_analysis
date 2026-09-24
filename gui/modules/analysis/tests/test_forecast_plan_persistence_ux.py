import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

sys.path.insert(0,str(Path(__file__).resolve().parents[3]))

from modules.analysis.forecast_plan import ForecastPlan, PlanStatus, approve_plan, new_version
from modules.data.forecast_plans import approve_saved_plan
from components.valuation_workbench_tab import (
    ValuationWorkbenchTab, approval_confirmation, forecast_plan_header,
    save_confirmation,
)


def make_plan(version=1):
    return ForecastPlan(ticker='TRU.JO',created_by='Dion',plan_version=version,
                        source_report_version_id=uuid4())


class FakeDb:
    def __init__(self,plan,execute_result='UPDATE 1'):
        self.plan=plan
        self.execute_result=execute_result
        self.calls=[]
    async def fetch(self,sql,*args):
        self.calls.append(('fetch',sql,args))
        return [{'plan':self.plan.model_dump_json()}]
    async def execute(self,sql,*args):
        self.calls.append(('execute',sql,args))
        return self.execute_result


class Var:
    def __init__(self,value=''): self.value=value
    def get(self): return self.value
    def set(self,value): self.value=value


def test_approval_uses_same_persisted_version_and_identifier():
    draft=make_plan(27)
    approved=approve_plan(draft,'Dion')
    assert approved.plan_version==27
    assert approved.forecast_plan_id==draft.forecast_plan_id
    assert approved.status==PlanStatus.APPROVED


def test_atomic_approval_updates_existing_row_without_insert():
    draft=make_plan(27)
    db=FakeDb(draft)
    approved=asyncio.run(approve_saved_plan(draft.forecast_plan_id,'Dion',db=db))
    assert approved.plan_version==27
    assert approved.forecast_plan_id==draft.forecast_plan_id
    assert len([c for c in db.calls if c[0]=='execute'])==1
    sql=db.calls[-1][1]
    assert 'UPDATE forecast_plans' in sql
    assert 'INSERT' not in sql
    assert json.loads(db.calls[-1][2][-1])['status']=='approved'


def test_approval_lost_race_is_reported():
    draft=make_plan(27)
    db=FakeDb(draft,execute_result='UPDATE 0')
    try:
        asyncio.run(approve_saved_plan(draft.forecast_plan_id,'Dion',db=db))
    except ValueError as exc:
        assert 'did not update' in str(exc)
    else:
        raise AssertionError('Expected failed conditional update')


def test_unsaved_edits_coalesce_into_one_next_version():
    source=make_plan(25)
    first=new_version(source,changed_by='Dion',notes='first')
    fake=SimpleNamespace(plan=source,pending=[],_render=lambda:None)
    ValuationWorkbenchTab._stage_plan(fake,first)
    second=new_version(fake.plan,changed_by='Dion',notes='second')
    ValuationWorkbenchTab._stage_plan(fake,second)
    assert len(fake.pending)==1
    assert fake.plan.plan_version==26
    assert fake.plan.forecast_plan_id==first.forecast_plan_id
    assert fake.plan.previous_plan_id==source.forecast_plan_id
    assert fake.plan.notes=='second'


def test_header_and_confirmation_include_audit_identity_and_dirty_state():
    draft=make_plan(27)
    assert forecast_plan_header('TRU.JO',draft,True).endswith('UNSAVED CHANGES')
    assert forecast_plan_header('TRU.JO',draft,False).endswith('SAVED')
    saved=save_confirmation(draft)
    assert 'v27 saved successfully' in saved
    assert str(draft.forecast_plan_id) in saved
    assert 'Status: draft' in saved
    approved=approve_plan(draft,'Dion')
    message=approval_confirmation(approved)
    assert 'v27 approved successfully' in message
    assert str(approved.forecast_plan_id) in message
    assert approved.approved_at.isoformat() in message


def test_apply_loaded_selects_exact_persisted_plan_and_clears_dirty_state():
    other=make_plan(28)
    saved=make_plan(27)
    fake=SimpleNamespace(
        status=Var(),ticker='TRU.JO',pending=[saved],plan=None,plans=[],
        evidence=[],history=[],category=None,_render=lambda:None)
    data=([other,saved],[],[],None,'General Retail')
    ValuationWorkbenchTab._apply_loaded(fake,data,saved.forecast_plan_id)
    assert fake.plan.forecast_plan_id==saved.forecast_plan_id
    assert fake.plan.plan_version==27
    assert fake.pending==[]
    assert fake.category=='General Retail'


def test_failed_save_keeps_dirty_draft_and_shows_actual_error(monkeypatch):
    draft=make_plan(27)
    shown=[]
    async def failed(): return {'ok':False,'error':'duplicate version'}
    fake=SimpleNamespace(
        plan=draft,pending=[draft],saving=False,status=Var(),
        _save_and_reload=failed,
        async_run_bg=lambda coroutine,callback: callback(asyncio.run(coroutine)))
    monkeypatch.setattr('components.valuation_workbench_tab.messagebox.showerror',
                        lambda title,message,**kw: shown.append((title,message)))
    ValuationWorkbenchTab.save(fake)
    assert fake.pending==[draft]
    assert fake.plan is draft
    assert shown==[('ForecastPlan save failed','duplicate version')]
    assert 'failed' in fake.status.value.lower()


def test_successful_save_reloads_persisted_object_and_confirms(monkeypatch):
    local=make_plan(27)
    persisted=ForecastPlan.model_validate(local.model_dump())
    data=([persisted],[],[],None,'General Retail')
    shown=[]; applied=[]
    async def succeeded(): return {'ok':True,'plan':local,'data':data}
    fake=SimpleNamespace(
        plan=local,pending=[local],saving=False,status=Var(),
        _save_and_reload=succeeded,
        _apply_loaded=lambda payload,ident: applied.append((payload,ident)),
        async_run_bg=lambda coroutine,callback: callback(asyncio.run(coroutine)))
    monkeypatch.setattr('components.valuation_workbench_tab.messagebox.showinfo',
                        lambda title,message,**kw: shown.append((title,message)))
    ValuationWorkbenchTab.save(fake)
    assert applied==[(data,local.forecast_plan_id)]
    assert shown and 'v27 saved successfully' in shown[0][1]
    assert fake.saving is False


def test_manual_refresh_remains_available():
    calls=[]
    fake=SimpleNamespace(
        status=Var(),_load=lambda: 'load-coroutine',
        _loaded=lambda data:calls.append(data),
        async_run_bg=lambda work,callback:(calls.append(work),callback('reloaded')))
    ValuationWorkbenchTab.refresh(fake)
    assert calls==['load-coroutine','reloaded']





def test_successful_approval_reloads_same_version_and_confirms(monkeypatch):
    draft=make_plan(27)
    approved=approve_plan(draft,'Dion')
    data=([approved],[],[],None,'General Retail')
    shown=[]; applied=[]
    async def succeeded(_reviewer):
        return {'ok':True,'plan':approved,'data':data}
    fake=SimpleNamespace(
        plan=draft,pending=[],saving=False,status=Var(),
        fields={'analyst':Var('Dion')},_approve_and_reload=succeeded,
        _apply_loaded=lambda payload,ident: applied.append((payload,ident)),
        async_run_bg=lambda coroutine,callback: callback(asyncio.run(coroutine)))
    monkeypatch.setattr('components.valuation_workbench_tab.messagebox.showinfo',
                        lambda title,message,**kw: shown.append((title,message)))
    ValuationWorkbenchTab.approve(fake)
    assert applied==[(data,draft.forecast_plan_id)]
    assert approved.plan_version==draft.plan_version
    assert shown and 'v27 approved successfully' in shown[0][1]
    assert fake.saving is False


def test_approved_ready_reload_enables_dcf_run_button(monkeypatch):
    import modules.analysis.dcf_execution as dcf_execution
    import components.valuation_workbench_tab as workbench
    approved=approve_plan(make_plan(27),'Dion')
    configured=[]
    class Button:
        def configure(self,**values): configured.append(values)
    monkeypatch.setattr(
        workbench,'terminal_configuration_status',
        lambda plan:{'method':'perpetuity_growth','wacc':'12.5',
                     'terminal_growth':'4.0','status':'ready','missing':[]})
    monkeypatch.setattr(
        dcf_execution,'execution_readiness',
        lambda plan,evidence:{'status':'READY','reasons':[],'preflight':{'status':'PASS'}})
    fake=SimpleNamespace(
        terminal_method_var=Var(),terminal_metric_var=Var(),
        terminal_metric_selector=Button(),run_dcf_button=Button(),
        pending=[],evidence=[],_text=lambda *args:None)
    ValuationWorkbenchTab._render_dcf_panel(fake,approved)
    assert {'state':'normal'} in configured
