"""Analyst forecast workbench in the existing research window."""
from __future__ import annotations
from datetime import date
import json
from pathlib import Path
from decimal import Decimal
from tkinter import StringVar, messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, X
from modules.analysis.forecast_plan import (ForecastPlan, ForecastPeriod, ForecastAssumption,
    Origin, ApprovalState, new_version, approve_plan, forecast_operating_schedule, scenario_differences)
from modules.data.forecast_plans import list_plans, save_plan, valuation_history
from core.db.engine import DBEngine

LABELS = {
    'historical_actual':'REPORTED', 'formal_guidance':'GUIDANCE',
    'management_target':'MANAGEMENT TARGET', 'external_consensus':'CONSENSUS',
    'deterministic_calculation':'CALCULATED', 'analyst_assumption':'ANALYST ASSUMPTION',
    'scenario_assumption':'SCENARIO', 'gemini_suggestion':'GEMINI SUGGESTION',
}

class ValuationWorkbenchTab(ttk.Frame):
    def __init__(self, parent, ticker, async_run_bg):
        super().__init__(parent)
        self.ticker=ticker; self.async_run_bg=async_run_bg; self.plan=None; self.evidence=[]; self.history=[]; self.pending=[]; self.saving=False
        self.fields={}
        self._widgets()
        self.refresh()

    def update_ticker(self,ticker):
        self.ticker=ticker; self.plan=None; self.pending=[]; self.refresh()

    def _widgets(self):
        bar=ttk.Frame(self); bar.pack(fill=X,padx=8,pady=5)
        self.title_var=StringVar(value='Forecast workbench')
        ttk.Label(bar,textvariable=self.title_var,font=('Helvetica',13,'bold')).pack(side='left')
        ttk.Button(bar,text='Refresh',command=self.refresh).pack(side='right')
        ttk.Button(bar,text='Approve plan',command=self.approve).pack(side='right',padx=5)
        ttk.Button(bar,text='Save new version',command=self.save).pack(side='right',padx=5)
        self.book=ttk.Notebook(self); self.book.pack(fill=BOTH,expand=True,padx=8,pady=4)
        self.views={}
        for name in ('Evidence','Forecast','Scenarios','WACC','DCF','SOTP','Sensitivity','Reconciliation','Audit','Legacy / History'):
            frame=ttk.Frame(self.book); self.book.add(frame,text=name)
            if name == 'Forecast': self._forecast_form(frame)
            else:
                if name == 'Sensitivity':
                    controls=ttk.Frame(frame); controls.pack(fill=X)
                    self.compare_from=StringVar(); self.compare_to=StringVar()
                    ttk.Label(controls,text='Base plan version').pack(side='left')
                    ttk.Entry(controls,textvariable=self.compare_from,width=7).pack(side='left')
                    ttk.Label(controls,text='Changed approved version').pack(side='left')
                    ttk.Entry(controls,textvariable=self.compare_to,width=7).pack(side='left')
                    ttk.Button(controls,text='Calculate impact',command=self.compare_versions).pack(side='left')
                box=ttk.Text(frame,wrap='word',height=20); box.pack(fill=BOTH,expand=True)
                self.views[name]=box
        mapping=ttk.Frame(self.book); self.book.add(mapping,text='Engine Mapping')
        ttk.Label(mapping,text='Advanced: explicit ValuationPlan JSON. References must be source metric IDs or accepted assumption IDs.').pack(fill=X)
        self.mapping_text=ttk.Text(mapping,wrap='none'); self.mapping_text.pack(fill=BOTH,expand=True)
        ttk.Button(mapping,text='Apply mapping as new version',command=self.apply_mapping).pack()
        ttk.Button(mapping,text='Run approved plan as draft valuation',command=self.run_plan).pack()
        publication=ttk.Frame(self.book); self.book.add(publication,text='Publication')
        ttk.Label(publication,text='Valuation ID for separate target approval and publication').pack(fill=X)
        self.valuation_id_var=StringVar(); ttk.Entry(publication,textvariable=self.valuation_id_var,width=48).pack(fill=X)
        ttk.Button(publication,text='Approve valuation',command=self.approve_valuation_action).pack(pady=5)
        ttk.Button(publication,text='Publish approved valuation',command=self.publish_valuation_action).pack(pady=5)
        ttk.Label(publication,text='Only a calculable, plan-linked valuation can be approved. Publishing is a second explicit action.').pack(fill=X)
        self.status=StringVar(value='Loading...')
        ttk.Label(self,textvariable=self.status).pack(fill=X,padx=8,pady=3)

    def _forecast_form(self,frame):
        top=ttk.Frame(frame); top.pack(fill=X,padx=5,pady=4)
        schema=[('FY label','period_label'),('Start YYYY-MM-DD','period_start'),('End YYYY-MM-DD','period_end'),
                ('Operation','operation'),('Case','case'),('Field','field'),('Value','value'),
                ('Unit','unit'),('Currency','currency'),('Rationale','rationale'),('Analyst','analyst'),
                ('Commodity','commodity'),('Price type','price_type'),('Project start YYYY-MM-DD','effective_date'),
                ('Cost definition','cost_definition'),('Confidence 0-1','confidence'),('FX pair','fx_pair')]
        for i,(label,key) in enumerate(schema):
            var=StringVar(); self.fields[key]=var
            ttk.Label(top,text=label).grid(row=i//3*2,column=i%3,sticky='w',padx=4)
            ttk.Entry(top,textvariable=var,width=23).grid(row=i//3*2+1,column=i%3,sticky='ew',padx=4)
        ttk.Button(top,text='Add financial period',command=self.add_period).grid(row=16,column=0,pady=5)
        ttk.Button(top,text='Add proposed assumption',command=self.add_assumption).grid(row=16,column=1,pady=5)
        ttk.Button(top,text='Accept selected',command=self.accept_selected).grid(row=16,column=2,pady=5)
        ttk.Button(top,text='Reject selected',command=self.reject_selected).grid(row=17,column=2,pady=5)
        ttk.Button(top,text='Record Gemini suggestion',command=self.add_suggestion).grid(row=17,column=1,pady=5)
        self.assumption_table=ttk.Treeview(frame,columns=('period','case','operation','field','value','unit','origin','approval'),show='headings',height=10)
        for col in ('period','case','operation','field','value','unit','origin','approval'):
            self.assumption_table.heading(col,text=col.upper()); self.assumption_table.column(col,width=105)
        self.assumption_table.pack(fill=BOTH,expand=True,padx=5,pady=5)
        self.forecast_detail=ttk.Text(frame,height=6,wrap='word'); self.forecast_detail.pack(fill=X,padx=5)

    async def _load(self):
        plans=await list_plans(self.ticker)
        rows=await DBEngine.fetch('''SELECT f.metric FROM financial_metrics f
          JOIN stock_analysis s ON s.current_report_id=f.report_id
          WHERE s.ticker=$1 ORDER BY f.metric->>'name' ''',self.ticker)
        hist=await valuation_history(self.ticker)
        report=await DBEngine.fetch('SELECT current_report_id FROM stock_analysis WHERE ticker=$1',self.ticker)
        evidence=[json.loads(r['metric']) if isinstance(r['metric'],str) else r['metric'] for r in rows]
        report_id=report[0]['current_report_id'] if report else None
        if not evidence and self.ticker == 'JBL.JO' and report_id:
            snapshot=Path(__file__).resolve().parents[1]/'data/valuation_workbench_jubilee_evidence.json'
            evidence=json.loads(snapshot.read_text(encoding='utf-8'))
            for metric in evidence:
                metric['report_id']=str(report_id)
        return plans,evidence,hist,report_id

    def refresh(self):
        self.status.set('Loading evidence and plan history...')
        self.async_run_bg(self._load(),callback=self._loaded)

    def _loaded(self,data):
        if data is None:
            self.status.set('Workbench data unavailable. Check Phase 5 migration and database connection.'); return
        plans,self.evidence,self.history,report_id=data
        self.plan=plans[0] if plans else (ForecastPlan(ticker=self.ticker,created_by='analyst',source_report_version_id=report_id,legacy_target=next((Decimal(h['legacy_target']) for h in self.history if h['legacy_target']),None))
             if report_id else None)
        self.plans=plans
        self.pending=[] if plans or self.plan is None else [self.plan]
        self._render()

    def _text(self,name,content):
        box=self.views[name]; box.configure(state='normal'); box.delete('1.0','end'); box.insert('end',content); box.configure(state='disabled')

    def _render(self):
        p=self.plan
        if p is None:
            self.status.set('No deep-research report version available.'); return
        self.title_var.set(f'{self.ticker}  Plan v{p.plan_version}  {p.status.value.upper()}')
        self.status.set('No analyst assumptions are automatically filled. Save edits as a new version; approve separately.')
        evidence=[]
        for m in self.evidence:
            origin=m.get('assumption_type','unresolved')
            label=LABELS.get(origin,'UNRESOLVED')
            value=m.get('value') if m.get('value') is not None else f"{m.get('value_low')}â€“{m.get('value_high')}"
            evidence.append(f"[{label}] {m.get('operation_segment') or 'Company'} | {m.get('name')} = {value} {m.get('unit') or 'UNIT MISSING'} | {m.get('source') or 'SOURCE MISSING'} | {m.get('source_date') or 'DATE MISSING'}")
        self._text('Evidence','\n'.join(evidence) or 'No source-backed metrics in current report.')
        self.assumption_table.delete(*self.assumption_table.get_children())
        for a in p.assumptions:
            self.assumption_table.insert('', 'end', iid=str(a.assumption_id), values=(a.period_label or '',a.case,a.operation_segment or '',a.field,
                str(a.value) if a.value is not None else '',a.unit or '',LABELS[a.origin.value],a.approval_state.value))
        periods='\n'.join(f'{x.label}: {x.start} to {x.end}' for x in p.horizon) or 'No fiscal periods entered.'
        self.forecast_detail.delete('1.0','end'); self.forecast_detail.insert('end',periods+'\n\nDerived production appears only when every required accepted input is present.\n')
        for operation in sorted({a.operation_segment for a in p.assumptions if a.operation_segment}):
            for row in forecast_operating_schedule(p,operation):
                self.forecast_detail.insert('end',f"{operation} {row['period']}: {row['status']} {row.get('attributable_saleable_tonnes',row.get('missing'))}\n")
        self.mapping_text.delete('1.0','end'); self.mapping_text.insert('end',p.engine_plan.model_dump_json(indent=2) if p.engine_plan else '')
        self._text('Scenarios','\n'.join(str(x) for x in scenario_differences(p)) or 'No explicit bear/base/bull differences. Base does not inherit management targets.')
        wacc=[a for a in p.assumptions if a.field in {'risk_free_rate','equity_risk_premium','beta','country_risk_premium','cost_of_debt','tax_rate','debt_weight','equity_weight','wacc'}]
        from modules.analysis.forecast_plan import calculate_plan_wacc,price_fx_schedule,cost_forecast_schedule
        self.forecast_detail.insert('end','\nCost schedules: '+str({o:cost_forecast_schedule(p,o) for o in sorted({a.operation_segment for a in p.assumptions if a.operation_segment})}))
        self._text('WACC','\n'.join(f"{a.field}: {a.value} {a.unit} [{LABELS[a.origin.value]} / {a.approval_state.value}]" for a in wacc) + '\nCalculated: ' + str(calculate_plan_wacc(p)))
        self.forecast_detail.insert('end','\nCommodity price schedule: '+str(price_fx_schedule(p,'commodity_price'))+'\nFX schedule: '+str(price_fx_schedule(p,'fx_rate')))
        self._text('DCF','DCF requires an approved plan with explicit annual operating, cash-flow, WACC and terminal inputs. Missing fields remain missing.\nTerminal method: '+(p.engine_plan.cases.get('base').dcf.terminal_method.value if p.engine_plan and p.engine_plan.cases.get('base') and p.engine_plan.cases['base'].dcf else 'not selected'))
        self._text('SOTP','SOTP components must have explicit asset boundaries, ownership, probability, and source-linked values.\n'+('\n'.join(c.name for c in p.engine_plan.cases['base'].sotp.components) if p.engine_plan and p.engine_plan.cases.get('base') and p.engine_plan.cases['base'].sotp else 'No SOTP components entered.'))
        self._text('Sensitivity','Enter two saved approved plan versions and calculate the target-price change. Missing inputs remain NOT_CALCULABLE. No Gemini estimate is used.')
        self._text('Reconciliation','Deterministic target: NOT_CALCULABLE until complete approved inputs pass preflight and the engine.\nNo legacy target is used in equity-to-share reconciliation.')
        self._text('Audit',f'Plan ID: {p.forecast_plan_id}\nSource report: {p.source_report_version_id}\nEngine: {p.valuation_engine_version}\nApproval: {p.approval_status}\nUnaccepted assumptions: '+str(sum(a.approval_state!=ApprovalState.ACCEPTED for a in p.assumptions)))
        from modules.analysis.forecast_plan import plan_changes
        plan_by_version={x.plan_version:x for x in self.plans}
        hist='\n'.join(f"{h['generated_at']} | Plan v{h['plan_version'] or 'none'} | {h['status']} | {h['publication_state']} | target {h['target_price'] or 'NOT_CALCULABLE'} | engine {h['valuation_engine_version']} | changes {plan_changes(plan_by_version[h['plan_version']],plan_by_version.get(h['plan_version']-1)) if h['plan_version'] in plan_by_version else 'unknown'}" for h in self.history)
        self._text('Legacy / History',f'Legacy Gemini target: {p.legacy_target or "see historical report"} (historical, unreconciled)\nDeterministic history:\n'+(hist or 'No valuations saved.'))

    def add_period(self):
        if not self.plan: return
        try:
            period=ForecastPeriod(label=self.fields['period_label'].get(),start=date.fromisoformat(self.fields['period_start'].get()),end=date.fromisoformat(self.fields['period_end'].get()))
            self.plan=new_version(self.plan,changed_by=self.fields['analyst'].get() or 'analyst',horizon=sorted([*self.plan.horizon,period],key=lambda p:p.start))
            self.pending.append(self.plan); self._render()
        except Exception as e: messagebox.showerror('Invalid period',str(e))

    def add_assumption(self):
        if not self.plan: return
        try:
            a=ForecastAssumption(field=self.fields['field'].get(),value=Decimal(self.fields['value'].get()) if self.fields['value'].get() else None,
              unit=self.fields['unit'].get(),currency=self.fields['currency'].get() or None,
              period_label=self.fields['period_label'].get() or None,operation_segment=self.fields['operation'].get() or None,
              case=self.fields['case'].get() or 'base',origin=Origin.ANALYST_ASSUMPTION,
              rationale=self.fields['rationale'].get(),created_by=self.fields['analyst'].get() or 'analyst',
              commodity=self.fields['commodity'].get() or None,price_type=self.fields['price_type'].get() or None,
              cost_definition=self.fields['cost_definition'].get() or None,fx_pair=self.fields['fx_pair'].get() or None,
              confidence=Decimal(self.fields['confidence'].get()) if self.fields['confidence'].get() else None,
              effective_date=date.fromisoformat(self.fields['effective_date'].get()) if self.fields['effective_date'].get() else None)
            self.plan=new_version(self.plan,changed_by=a.created_by,assumptions=[*self.plan.assumptions,a]); self.pending.append(self.plan); self._render()
        except Exception as e: messagebox.showerror('Invalid assumption',str(e))

    def accept_selected(self):
        if not self.plan: return
        selected=self.assumption_table.selection()
        if len(selected)!=1: return
        from uuid import UUID
        from modules.analysis.forecast_plan import accept_suggestion,accept_assumption
        ident=UUID(selected[0]); original=next(a for a in self.plan.assumptions if a.assumption_id==ident)
        analyst=self.fields['analyst'].get() or 'analyst'
        try:
            if original.origin==Origin.GEMINI_SUGGESTION:
                self.plan=accept_suggestion(self.plan,ident,analyst=analyst,
                    value=Decimal(self.fields['value'].get()) if self.fields['value'].get() else None,
                    rationale=self.fields['rationale'].get() or None)
            else:
                self.plan=accept_assumption(self.plan,ident,analyst)
            self.pending.append(self.plan); self._render()
        except Exception as e: messagebox.showerror('Cannot accept',str(e))

    async def _save_pending(self):
        count=0
        while self.pending:
            item=self.pending[0]
            await save_plan(item)
            self.pending.pop(0); count+=1
        return count

    def save(self):
        if not self.plan or self.saving: return
        self.saving=True
        def done(count):
            self.saving=False
            self.status.set(f'Saved {count} plan version(s)' if count is not None else 'Plan save failed; retry')
            if self.pending: self.save()
        self.async_run_bg(self._save_pending(),callback=done)

    def approve(self):
        if not self.plan: return
        try:
            self.plan=approve_plan(self.plan,self.fields['analyst'].get() or 'analyst')
            self.pending.append(self.plan); self._render(); self.save()
        except Exception as e: messagebox.showerror('Cannot approve plan',str(e))

    def reject_selected(self):
        if not self.plan: return
        from uuid import UUID
        from modules.analysis.forecast_plan import reject_suggestion
        selected=self.assumption_table.selection()
        if len(selected)!=1: return
        try:
            self.plan=reject_suggestion(self.plan,UUID(selected[0]),self.fields['analyst'].get() or 'analyst')
            self.pending.append(self.plan); self._render()
        except Exception as e: messagebox.showerror('Cannot reject',str(e))

    def apply_mapping(self):
        if not self.plan: return
        from modules.analysis.valuation.engine import ValuationPlan
        try:
            mapping=ValuationPlan.model_validate_json(self.mapping_text.get('1.0','end'))
            self.plan=new_version(self.plan,changed_by=self.fields['analyst'].get() or 'analyst',engine_plan=mapping)
            self.pending.append(self.plan); self._render()
        except Exception as e: messagebox.showerror('Invalid engine mapping',str(e))

    async def _run_approved(self):
        from modules.analysis.financial_metrics import FinancialMetric
        from modules.analysis.forecast_plan import compile_plan_inputs,preview_valuation
        from modules.data.forecast_plans import save_plan_valuation
        evidence=[FinancialMetric.model_validate(x) for x in self.evidence]
        metrics,candidates=compile_plan_inputs(self.plan,evidence)
        result=preview_valuation(self.plan,metrics,candidates)
        await save_plan_valuation(self.plan,result)
        return result

    def run_plan(self):
        if not self.plan: return
        if self.pending:
            messagebox.showerror('Save first','Save all plan versions before running the engine.'); return
        def done(result):
            if result is None:
                self.status.set('Valuation failed; inspect application log.'); return
            self.valuation_id_var.set(str(result.valuation_id))
            self.status.set(f'Draft valuation {result.status.value}: {result.target_price or "NOT_CALCULABLE"}. Publication requires separate approval.')
            self._text('Reconciliation',str(result.reconciliation or result.warnings))
            from modules.analysis.forecast_plan import terminal_value_summary
            self._text('DCF',str(result.methods.get('DCF'))+'\nTerminal dependence: '+str(terminal_value_summary(result)))
            self._text('SOTP',str(result.methods.get('SOTP')))
        self.async_run_bg(self._run_approved(),callback=done)


    def approve_valuation_action(self):
        from uuid import UUID
        from modules.data.forecast_plans import approve_valuation
        try: ident=UUID(self.valuation_id_var.get())
        except ValueError: messagebox.showerror('Invalid ID','Enter a saved valuation ID.'); return
        reviewer=self.fields['analyst'].get() or 'analyst'
        async def work():
            await approve_valuation(ident,reviewer); return True
        self.async_run_bg(work(),callback=lambda ok: self.refresh() if ok else self.status.set('Valuation approval failed; inspect application log.'))

    def publish_valuation_action(self):
        from uuid import UUID
        from modules.data.forecast_plans import publish_valuation
        try: ident=UUID(self.valuation_id_var.get())
        except ValueError: messagebox.showerror('Invalid ID','Enter a saved valuation ID.'); return
        publisher=self.fields['analyst'].get() or 'analyst'
        async def work():
            await publish_valuation(ident,publisher); return True
        self.async_run_bg(work(),callback=lambda ok: self.refresh() if ok else self.status.set('Publication failed; inspect application log.'))


    async def _compare_versions(self,from_version,to_version):
        from modules.analysis.financial_metrics import FinancialMetric
        from modules.analysis.forecast_plan import compile_plan_inputs,deterministic_impact
        plans={p.plan_version:p for p in self.plans}
        a,b=plans[from_version],plans[to_version]
        evidence=[FinancialMetric.model_validate(x) for x in self.evidence]
        am,ac=compile_plan_inputs(a,evidence)
        bm,bc=compile_plan_inputs(b,evidence)
        return deterministic_impact(a,b,am,ac,bm,bc)

    def compare_versions(self):
        try: a=int(self.compare_from.get()); b=int(self.compare_to.get())
        except ValueError: messagebox.showerror('Versions required','Enter two saved plan version numbers.'); return
        def done(impact):
            self._text('Sensitivity',str(impact) if impact is not None else 'Impact unavailable; inspect application log and missing inputs.')
        self.async_run_bg(self._compare_versions(a,b),callback=done)

    def add_suggestion(self):
        if not self.plan: return
        from modules.analysis.forecast_plan import record_gemini_suggestion
        try:
            a=ForecastAssumption(field=self.fields['field'].get(),
                value=Decimal(self.fields['value'].get()) if self.fields['value'].get() else None,
                unit=self.fields['unit'].get() or None,currency=self.fields['currency'].get() or None,
                period_label=self.fields['period_label'].get() or None,
                operation_segment=self.fields['operation'].get() or None,case=self.fields['case'].get() or 'base',
                origin=Origin.GEMINI_SUGGESTION,approval_state=ApprovalState.PROPOSED,
                rationale=self.fields['rationale'].get(),created_by='Gemini suggestion',
                commodity=self.fields['commodity'].get() or None,price_type=self.fields['price_type'].get() or None,
                fx_pair=self.fields['fx_pair'].get() or None)
            self.plan=record_gemini_suggestion(self.plan,a)
            self.pending.append(self.plan);self._render()
        except Exception as e: messagebox.showerror('Invalid suggestion',str(e))
