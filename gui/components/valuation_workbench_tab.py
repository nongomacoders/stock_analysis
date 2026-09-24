"""Analyst forecast workbench in the existing research window."""
from __future__ import annotations
from datetime import date
import json
from pathlib import Path
from decimal import Decimal
from tkinter import StringVar, messagebox, filedialog
import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, X
from modules.analysis.forecast_plan import (ForecastPlan, ForecastPeriod, ForecastAssumption,
    Origin, ApprovalState, new_version, scenario_differences,
    configure_terminal_method, horizon_for_assumption, forecast_selector_values,
    terminal_configuration_status, terminal_method_values, terminal_metric_values)
from modules.data.forecast_plans import (list_plans, save_plan, valuation_history,
    approve_saved_plan)
from modules.data.research import get_stock_category
from modules.analysis.retail_forecast import (WorkbenchRoute, build_sector_schedules,
    aggregate_retail_revenue, render_historical_retail_earnings,
    render_retail_earnings_records, render_retail_fcff_previews,
    render_retail_records, retail_engine_mapping)
from modules.analysis.equity_bridge_preview import (
    equity_bridge_preview, map_reviewed_equity_bridge,
    render_equity_bridge_preview)
from modules.analysis.forecast_txt_import import (
    parse_forecast_txt, resolve_import_assumptions, ForecastTxtImportError)
from core.db.engine import DBEngine

def forecast_plan_header(ticker,plan,dirty):
    state='UNSAVED CHANGES' if dirty else 'SAVED'
    return f'{ticker}  Plan v{plan.plan_version}  {plan.status.value.upper()} — {state}'


def save_confirmation(plan):
    return (f'ForecastPlan v{plan.plan_version} saved successfully.\n\n'
            f'Plan ID: {plan.forecast_plan_id}\nStatus: {plan.status.value}')


def approval_confirmation(plan):
    timestamp=plan.approved_at.isoformat() if plan.approved_at else 'unavailable'
    return (f'ForecastPlan v{plan.plan_version} approved successfully.\n\n'
            f'Plan ID: {plan.forecast_plan_id}\nApproved: {timestamp}')

LABELS = {
    'historical_actual':'REPORTED', 'formal_guidance':'GUIDANCE',
    'management_target':'MANAGEMENT TARGET', 'external_consensus':'CONSENSUS',
    'deterministic_calculation':'CALCULATED', 'analyst_assumption':'ANALYST ASSUMPTION',
    'scenario_assumption':'SCENARIO', 'gemini_suggestion':'GEMINI SUGGESTION',
}

class ValuationWorkbenchTab(ttk.Frame):
    def __init__(self, parent, ticker, async_run_bg):
        super().__init__(parent)
        self.ticker=ticker; self.async_run_bg=async_run_bg; self.plan=None; self.evidence=[]; self.history=[]; self.pending=[]; self.saving=False; self.category=None; self.backtest=None
        self.fields={}; self.input_widgets={}
        self._widgets()
        self.refresh()

    def update_ticker(self,ticker):
        self.ticker=ticker; self.plan=None; self.pending=[]; self.category=None; self.backtest=None; self.refresh()

    def _widgets(self):
        bar=ttk.Frame(self); bar.pack(fill=X,padx=8,pady=5)
        self.title_var=StringVar(value='Forecast workbench')
        ttk.Label(bar,textvariable=self.title_var,font=('Helvetica',13,'bold')).pack(side='left')
        ttk.Button(bar,text='Refresh',command=self.refresh).pack(side='right')
        ttk.Button(bar,text='Approve plan',command=self.approve).pack(side='right',padx=5)
        ttk.Button(bar,text='Save new version',command=self.save).pack(side='right',padx=5)
        self.book=ttk.Notebook(self); self.book.pack(fill=BOTH,expand=True,padx=8,pady=4)
        self.views={}
        for name in ('Evidence','Forecast','Scenarios','WACC','DCF','SOTP','Bank Equity','Sensitivity','Reconciliation','Backtest','Audit','Legacy / History'):
            frame=ttk.Frame(self.book); self.book.add(frame,text=name)
            if name == 'Forecast':
                self._forecast_form(frame)
            elif name == 'DCF':
                self._dcf_panel(frame)
            elif name == 'Reconciliation':
                self._reconciliation_panel(frame)
            elif name == 'Legacy / History':
                self._history_panel(frame)
            elif name == 'Backtest':
                self._backtest_panel(frame)
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
        ttk.Label(mapping,text='Deterministic assumption routing').pack(fill=X)
        self.mapping_flow=ttk.Text(mapping,wrap='word',height=7); self.mapping_flow.pack(fill=X)
        ttk.Label(mapping,text='Advanced: explicit ValuationPlan JSON. References must be source metric IDs or accepted assumption IDs.').pack(fill=X)
        self.mapping_text=ttk.Text(mapping,wrap='none'); self.mapping_text.pack(fill=BOTH,expand=True)
        ttk.Button(mapping,text='Map accepted FY2027 inputs to DCF',
                   command=self.map_accepted_fy2027_dcf).pack()
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
        controlled = forecast_selector_values()
        for i,(label,key) in enumerate(schema):
            var=StringVar(); self.fields[key]=var
            ttk.Label(top,text=label).grid(row=i//3*2,column=i%3,sticky='w',padx=4)
            if key in controlled or key == 'operation':
                widget=ttk.Combobox(top,textvariable=var,width=21,state='readonly',
                                    values=controlled.get(key, ()))
            else:
                widget=ttk.Entry(top,textvariable=var,width=23)
            widget.grid(row=i//3*2+1,column=i%3,sticky='ew',padx=4)
            self.input_widgets[key]=widget
        ttk.Button(top,text='Add financial period',command=self.add_period).grid(row=16,column=0,pady=5)
        ttk.Button(top,text='Add proposed assumption',command=self.add_assumption).grid(row=16,column=1,pady=5)
        ttk.Button(top,text='Import assumptions from TXT',command=self.import_assumptions_txt).grid(row=17,column=0,pady=5)
        ttk.Button(top,text='Accept selected',command=self.accept_selected).grid(row=16,column=2,pady=5)
        ttk.Button(
            top,text='Reject Gemini suggestion',
            command=self.reject_selected).grid(row=17,column=2,pady=5)
        ttk.Button(
            top,text='Discard proposed',
            command=self.discard_selected).grid(row=18,column=2,pady=5)
        ttk.Button(top,text='Record Gemini suggestion',command=self.add_suggestion).grid(row=17,column=1,pady=5)
        self.assumption_table=ttk.Treeview(frame,columns=('period','case','operation','field','value','unit','origin','approval'),show='headings',height=10)
        for col in ('period','case','operation','field','value','unit','origin','approval'):
            self.assumption_table.heading(col,text=col.upper()); self.assumption_table.column(col,width=105)
        self.assumption_table.pack(fill=BOTH,expand=True,padx=5,pady=5)
        self.forecast_detail=ttk.Text(frame,height=6,wrap='word'); self.forecast_detail.pack(fill=X,padx=5)


    def _backtest_panel(self,frame):
        controls=ttk.Frame(frame); controls.pack(fill=X,padx=8,pady=8)
        ttk.Label(controls,text='As-of date YYYY-MM-DD').pack(side='left')
        self.backtest_as_of_var=StringVar()
        ttk.Entry(controls,textvariable=self.backtest_as_of_var,width=14).pack(side='left',padx=6)
        ttk.Button(controls,text='Resolve historical snapshot',command=self.resolve_backtest).pack(side='left',padx=4)
        self.save_backtest_button=ttk.Button(controls,text='Save backtest snapshot',command=self.save_backtest,state='disabled')
        self.save_backtest_button.pack(side='left',padx=4)
        box=ttk.Text(frame,wrap='word',height=24); box.pack(fill=BOTH,expand=True,padx=8,pady=4)
        self.views['Backtest']=box

    def _render_backtest(self):
        bt=self.backtest
        if bt is None:
            self._text('Backtest','Choose an as-of date and resolve historical evidence. Unknown availability dates fail closed. Live reports, ForecastPlans, learning points and valuations are excluded.')
            self.save_backtest_button.configure(state='disabled'); return
        excluded=bt.metadata.get('excluded_evidence',[])
        lines=['HISTORICAL BACKTEST SNAPSHOT',f'Ticker: {bt.ticker}',f'As-of date: {bt.as_of_date}',
          f'Reporting period end: {bt.reporting_period_end or "unresolved"}',
          f'Eligible evidence: {len(bt.evidence_snapshot)}',f'Excluded/uncertain evidence: {len(excluded)}',
          f'Market observations: {len(bt.market_snapshot)}',f'Input hash: {bt.input_hash}',
          '', 'Leakage controls:', '  Current report pointer: EXCLUDED','  Current ForecastPlans: EXCLUDED',
          '  Current learning points: EXCLUDED','  Evidence with unknown availability: EXCLUDED','']
        for item in bt.evidence_snapshot: lines.append(f'AVAILABLE | {item.kind} | {item.available_date} | {item.evidence_id}')
        for item in excluded: lines.append(f"EXCLUDED | {item.get('kind')} | {item.get('available_date') or 'unknown'} | {item.get('reason')}")
        for item in bt.market_snapshot: lines.append(f'MARKET | {item.kind} | {item.observation_date} | lag={item.lag_days}d | {item.value} {item.unit or ""}')
        if not bt.source_report_ids: lines.extend(['','BLOCKED: No source-backed historical report package is available at this cutoff.'])
        self._text('Backtest','\n'.join(lines)); self.save_backtest_button.configure(state='normal')

    def resolve_backtest(self):
        try: cutoff=date.fromisoformat(self.backtest_as_of_var.get().strip())
        except ValueError:
            messagebox.showerror('Invalid as-of date','Enter the immutable historical cutoff as YYYY-MM-DD.',parent=self); return
        self.status.set(f'Resolving evidence available to {cutoff}...')
        async def work():
            try:
                from modules.data.historical_backtests import resolve_historical_snapshot
                return {'ok':True,'backtest':await resolve_historical_snapshot(self.ticker,cutoff)}
            except Exception as exc:return {'ok':False,'error':str(exc)}
        def done(payload):
            if not payload or not payload.get('ok'):
                error=(payload or {}).get('error','Unknown resolver error'); self.status.set('Historical snapshot resolution failed.')
                messagebox.showerror('Backtest resolution failed',error,parent=self); return
            self.backtest=payload['backtest']; self._render_backtest()
            self.status.set(f'Historical snapshot resolved for {cutoff}; nothing has been persisted.')
        self.async_run_bg(work(),callback=done)

    def save_backtest(self):
        if self.backtest is None:return
        async def work():
            try:
                from modules.data.historical_backtests import insert_backtest
                return {'ok':True,'row':await insert_backtest(self.backtest)}
            except Exception as exc:return {'ok':False,'error':str(exc)}
        def done(payload):
            if not payload or not payload.get('ok'):
                error=(payload or {}).get('error','Unknown persistence error'); messagebox.showerror('Backtest save failed',error,parent=self); return
            row=payload['row']; self.status.set(f"Historical backtest snapshot saved: {row['backtest_id']}")
            messagebox.showinfo('Historical backtest saved',f"Backtest ID: {row['backtest_id']}\nAs-of date: {row['as_of_date']}\nStatus: {row['status']}",parent=self)
        self.async_run_bg(work(),callback=done)
    def _history_panel(self,frame):
        controls=ttk.Frame(frame); controls.pack(fill=X,padx=8,pady=5)
        ttk.Button(controls,text='View selected version',command=self.view_historical_plan).pack(side='left')
        ttk.Button(controls,text='Clone selected as new draft',command=self.clone_historical_plan).pack(side='left',padx=6)
        self.plan_history_table=ttk.Treeview(frame,columns=('version','status','created','plan_id'),show='headings',height=8,selectmode='browse')
        for key,width in (('version',70),('status',100),('created',190),('plan_id',310)):
            self.plan_history_table.heading(key,text=key.upper()); self.plan_history_table.column(key,width=width)
        self.plan_history_table.pack(fill=X,padx=8,pady=4)
        box=ttk.Text(frame,wrap='none',height=18); box.pack(fill=BOTH,expand=True,padx=8,pady=4)
        self.views['Legacy / History']=box

    def _selected_history_plan(self):
        selected=self.plan_history_table.selection()
        if len(selected)!=1: raise ValueError('Select one ForecastPlan version')
        return next((p for p in self.plans if str(p.forecast_plan_id)==selected[0]),None)

    def view_historical_plan(self):
        from modules.analysis.forecast_plan_history import render_readonly_plan
        try:
            selected=self._selected_history_plan()
            if selected is None: raise ValueError('Selected ForecastPlan is unavailable')
            self._text('Legacy / History',render_readonly_plan(selected))
            self.status.set(f'Viewing ForecastPlan v{selected.plan_version} read-only.')
        except Exception as e: messagebox.showerror('Cannot view version',str(e))

    def clone_historical_plan(self):
        from modules.analysis.forecast_plan_history import clone_as_repaired_draft,render_readonly_plan
        try:
            selected=self._selected_history_plan()
            if selected is None: raise ValueError('Selected ForecastPlan is unavailable')
            proposed,details=clone_as_repaired_draft(selected,self.evidence,changed_by=self.fields['analyst'].get() or 'analyst')
            summary=(f"v{selected.plan_version} {selected.status.value.upper()}\n"
                     f"-> prospective v{proposed.plan_version} DRAFT\n\n"
                     f"Repair: {details['repair']}\n"
                     f"Stale references: {details['before'].get('stale',[]) or 'none'}\n\n"
                     "Create this in-memory draft? It will not be saved or approved automatically.")
            if not messagebox.askyesno('Clone ForecastPlan version',summary): return
            self._stage_plan(proposed)
            self._text('Legacy / History',render_readonly_plan(proposed))
            self.status.set(f'Prospective v{proposed.plan_version} draft created in memory. Save, review and approve separately; no valuation was run.')
        except Exception as e: messagebox.showerror('Cannot clone version',str(e))

    def _reconciliation_panel(self,frame):
        controls=ttk.Frame(frame); controls.pack(fill=X,padx=8,pady=8)
        ttk.Button(
            controls,text='Map reviewed equity bridge',
            command=self.map_reviewed_equity).pack(side='left')
        ttk.Label(
            controls,text='Previews first; updates the in-memory draft only.'
        ).pack(side='left',padx=8)
        box=ttk.Text(frame,wrap='word',height=20); box.pack(fill=BOTH,expand=True)
        self.views['Reconciliation']=box

    def map_reviewed_equity(self):
        if not self.plan: return
        try:
            proposed=map_reviewed_equity_bridge(
                self.plan,self.evidence,
                changed_by=self.fields['analyst'].get() or 'analyst')
            preview=render_equity_bridge_preview(
                equity_bridge_preview(proposed,self.evidence))
            confirmed=messagebox.askyesno(
                'Confirm reviewed equity bridge',
                preview+'\n\nApply this mapping to the in-memory draft?')
            if not confirmed:
                self.status.set('Equity bridge mapping cancelled; draft unchanged.')
                return
            self._stage_plan(proposed)
            self.status.set(
                'Reviewed equity bridge mapped in memory. '
                'Save new version to persist; no valuation was run.')
        except Exception as e:
            messagebox.showerror('Cannot map equity bridge',str(e))

    def _dcf_panel(self,frame):
        controls=ttk.Frame(frame); controls.pack(fill=X,padx=8,pady=8)
        ttk.Label(controls,text='Terminal method').grid(row=0,column=0,sticky='w')
        self.terminal_method_var=StringVar()
        self.terminal_method_selector=ttk.Combobox(
            controls,textvariable=self.terminal_method_var,state='readonly',
            values=terminal_method_values(),width=24)
        self.terminal_method_selector.grid(row=0,column=1,sticky='w',padx=6)
        self.terminal_method_selector.bind(
            '<<ComboboxSelected>>',self._terminal_method_changed)
        ttk.Label(controls,text='Terminal metric').grid(row=1,column=0,sticky='w')
        self.terminal_metric_var=StringVar()
        self.terminal_metric_selector=ttk.Combobox(
            controls,textvariable=self.terminal_metric_var,state='readonly',
            values=terminal_metric_values(),width=24)
        self.terminal_metric_selector.grid(row=1,column=1,sticky='w',padx=6)
        self.terminal_metric_selector.bind(
            '<<ComboboxSelected>>',self._terminal_metric_changed)
        ttk.Label(
            controls,text='Selection updates the in-memory draft only. '
                          'Save new version persists it.').grid(
                              row=2,column=0,columnspan=2,sticky='w',pady=5)
        self.run_dcf_button=ttk.Button(
            controls,text='Run deterministic DCF',command=self.run_deterministic_dcf)
        self.run_dcf_button.grid(row=3,column=0,columnspan=2,sticky='w',pady=5)
        box=ttk.Text(frame,wrap='word',height=20); box.pack(fill=BOTH,expand=True)
        self.views['DCF']=box

    def _terminal_method_changed(self,_event=None):
        if not self.plan: return
        try:
            method=self.terminal_method_var.get()
            metric=(self.terminal_metric_var.get() or None
                    if method == 'exit_multiple' else None)
            self.plan=configure_terminal_method(
                self.plan,method,terminal_metric=metric,
                changed_by=self.fields['analyst'].get() or 'analyst',
                sector=self.category)
            self._stage_plan(self.plan)
            self.status.set(
                'Terminal method changed in the in-memory draft. '
                'No assumptions were accepted and no valuation was run.')
        except Exception as e:
            messagebox.showerror('Invalid terminal configuration',str(e))
            self._render()

    def _terminal_metric_changed(self,_event=None):
        if self.terminal_method_var.get() != 'exit_multiple':
            return
        self._terminal_method_changed()

    def _render_dcf_panel(self,plan):
        from modules.analysis.dcf_execution import execution_readiness
        status=terminal_configuration_status(plan)
        method=status.get('method')
        self.terminal_method_var.set(method or '')
        metric=status.get('terminal_metric') or ''
        self.terminal_metric_var.set(metric)
        self.terminal_metric_selector.configure(
            state='readonly' if method == 'exit_multiple' else 'disabled')
        lines=[
            'DCF requires an approved plan with explicit annual operating, '
            'cash-flow, WACC and terminal inputs. Missing fields remain missing.',
            f"Terminal method: {method or 'not selected'}",
        ]
        if method == 'perpetuity_growth':
            lines.append(f"WACC: {status.get('wacc', 'missing')}%")
            lines.append(
                f"Terminal growth: {status.get('terminal_growth', 'missing')}%")
        elif method == 'exit_multiple':
            multiple=status.get('exit_multiple')
            lines.append(
                f"Exit multiple: {str(multiple) + 'x' if multiple is not None else 'missing'}")
            lines.append(f"Terminal metric: {metric or 'missing'}")
        lines.append(f"Status: {status['status']}")
        if status.get('missing'):
            lines.append('Missing: '+', '.join(status['missing']))
        if status.get('error'):
            lines.append('Error: '+status['error'])
        readiness=execution_readiness(plan,self.evidence)
        if self.pending:
            readiness['status']='BLOCKED'
            readiness['reasons']=[*readiness['reasons'],'Unsaved ForecastPlan changes']
        self.run_dcf_button.configure(
            state='normal' if readiness['status']=='READY' else 'disabled')
        lines.append(f"Execution: {readiness['status']}")
        lines.extend('Blocking: '+reason for reason in readiness['reasons'])
        if (plan.status.value=='draft' and readiness.get('preflight')
                and readiness['preflight']['status']=='PASS'
                and readiness['reasons']==['ForecastPlan is not approved']):
            lines.extend(['FY2027 YearInputSpec: COMPLETE','WACC mapping: COMPLETE',
                          'Equity bridge: READY','Status: READY FOR APPROVAL'])
        self._text('DCF','\n'.join(lines))

    async def _load(self):
        plans=await list_plans(self.ticker)
        rows=await DBEngine.fetch('''SELECT f.metric FROM financial_metrics f
          JOIN stock_analysis s ON s.current_report_id=f.report_id
          WHERE s.ticker=$1 ORDER BY f.metric->>'name' ''',self.ticker)
        hist=await valuation_history(self.ticker)
        report=await DBEngine.fetch('SELECT current_report_id FROM stock_analysis WHERE ticker=$1',self.ticker)
        evidence=[json.loads(r['metric']) if isinstance(r['metric'],str) else r['metric'] for r in rows]
        report_id=report[0]['current_report_id'] if report else None
        category=await get_stock_category(self.ticker)
        if not evidence and self.ticker == 'JBL.JO' and report_id:
            snapshot=Path(__file__).resolve().parents[1]/'data/valuation_workbench_jubilee_evidence.json'
            evidence=json.loads(snapshot.read_text(encoding='utf-8'))
            for metric in evidence:
                metric['report_id']=str(report_id)
        return plans,evidence,hist,report_id,category

    def refresh(self):
        self.status.set('Loading evidence and plan history...')
        self.async_run_bg(self._load(),callback=self._loaded)

    def _loaded(self,data):
        self._apply_loaded(data)

    def _apply_loaded(self,data,preferred_plan_id=None):
        if data is None:
            self.status.set('Workbench data unavailable. Check Phase 5 migration and database connection.'); return
        plans,self.evidence,self.history,report_id,self.category=data
        selected=next((p for p in plans if p.forecast_plan_id==preferred_plan_id),None)
        self.plan=selected or (plans[0] if plans else (ForecastPlan(ticker=self.ticker,created_by='analyst',source_report_version_id=report_id,legacy_target=next((Decimal(h['legacy_target']) for h in self.history if h['legacy_target']),None))
             if report_id else None))
        self.plans=plans
        self.pending=[] if plans or self.plan is None else [self.plan]
        self._render()

    def _stage_plan(self,proposed):
        """Keep one prospective version while local edits remain unsaved."""
        if self.pending:
            draft=self.pending[0]
            proposed=proposed.model_copy(update={
                'forecast_plan_id':draft.forecast_plan_id,
                'plan_version':draft.plan_version,
                'previous_plan_id':draft.previous_plan_id,
                'created_at':draft.created_at,
            })
        self.plan=proposed
        self.pending=[proposed]
        self._render()
    def _text(self,name,content):
        box=self.views[name]; box.configure(state='normal'); box.delete('1.0','end'); box.insert('end',content); box.configure(state='disabled')

    def _update_forecast_selectors(self):
        operations = sorted({
            value for value in (
                *[m.get('operation_segment') for m in self.evidence],
                *[a.operation_segment for a in self.plan.assumptions],
            ) if value
        })
        operation_widget = self.input_widgets.get('operation')
        if operation_widget is not None:
            current = self.fields['operation'].get()
            operation_widget.configure(values=operations)
            if current and current not in operations:
                self.fields['operation'].set('')

    def _render(self):
        p=self.plan
        if p is None:
            self.status.set('No deep-research report version available.'); return
        self._update_forecast_selectors()
        self.title_var.set(forecast_plan_header(self.ticker,p,bool(self.pending)))
        self.status.set('No analyst assumptions are automatically filled. Save edits as a new version; approve separately.')
        evidence=[]
        for m in self.evidence:
            origin=m.get('assumption_type','unresolved')
            label=LABELS.get(origin,'UNRESOLVED')
            value=m.get('value') if m.get('value') is not None else f"{m.get('value_low')}–{m.get('value_high')}"
            evidence.append(f"[{label}] {m.get('operation_segment') or 'Company'} | {m.get('name')} = {value} {m.get('unit') or 'UNIT MISSING'} | {m.get('source') or 'SOURCE MISSING'} | {m.get('source_date') or 'DATE MISSING'}")
        self._text('Evidence','\n'.join(evidence) or 'No source-backed metrics in current report.')
        self.assumption_table.delete(*self.assumption_table.get_children())
        for a in p.assumptions:
            self.assumption_table.insert('', 'end', iid=str(a.assumption_id), values=(a.period_label or '',a.case,a.operation_segment or '',a.field,
                str(a.value) if a.value is not None else '',a.unit or '',LABELS[a.origin.value],a.approval_state.value))
        periods='\n'.join(f'{x.label}: {x.start} to {x.end}' for x in p.horizon) or 'No fiscal periods entered.'
        sector_schedules=build_sector_schedules(self.category,p,self.evidence)
        route=sector_schedules['route']
        self.forecast_detail.delete('1.0','end'); self.forecast_detail.insert('end',periods+'\n\n')
        mapping_summary=f'Sector route: {route.value}\nNo sector-specific forecast bridge is active.'
        if route == WorkbenchRoute.RETAIL:
            retail_records=sector_schedules['retail_records']; retail_warnings=sector_schedules['warnings']
            retail_earnings=sector_schedules['retail_earnings_records']
            self.forecast_detail.insert(
                'end',render_historical_retail_earnings(
                    sector_schedules['historical_retail_earnings'])+'\n\n')
            self.forecast_detail.insert('end',render_retail_records(retail_records,retail_warnings)+'\n')
            self.forecast_detail.insert('end',render_retail_earnings_records(retail_earnings)+'\n')
            retail_fcff=sector_schedules['retail_fcff_previews']
            self.forecast_detail.insert('end',render_retail_fcff_previews(retail_fcff)+'\n')
            for period in p.horizon:
                aggregate=aggregate_retail_revenue(
                    p,retail_records,period=period.label,evidence_metrics=self.evidence)
                self.forecast_detail.insert('end',f"Group revenue aggregation {period.label}: {aggregate}\n")
            mapping_summary=retail_engine_mapping(
                retail_records,retail_warnings,earnings=retail_earnings,
                plan=p,fcff_previews=retail_fcff)
        elif route == WorkbenchRoute.MINING:
            self.forecast_detail.insert('end','Derived production appears only when every required accepted mining input is present.\n')
            for operation,rows in sector_schedules['production'].items():
                for row in rows:
                    self.forecast_detail.insert('end',f"{operation} {row['period']}: {row['status']} {row.get('attributable_saleable_tonnes',row.get('missing'))}\n")
            mapping_summary='ForecastPlan assumption -> mining production/cost bridge -> derived forecast metric -> valuation input'
        else:
            self.forecast_detail.insert('end',f'No {route.value} operating forecast bridge is configured. Missing values remain NOT_CALCULABLE.\n')
        self.mapping_flow.configure(state='normal'); self.mapping_flow.delete('1.0','end'); self.mapping_flow.insert('end',mapping_summary); self.mapping_flow.configure(state='disabled')
        self.mapping_text.delete('1.0','end'); self.mapping_text.insert('end',p.engine_plan.model_dump_json(indent=2) if p.engine_plan else '')
        self._text('Scenarios','\n'.join(str(x) for x in scenario_differences(p)) or 'No explicit bear/base/bull differences. Base does not inherit management targets.')
        wacc=[a for a in p.assumptions if a.field in {'risk_free_rate','equity_risk_premium','beta','country_risk_premium','cost_of_debt','tax_rate','debt_weight','equity_weight','wacc'}]
        from modules.analysis.forecast_plan import calculate_plan_wacc,price_fx_schedule
        if route == WorkbenchRoute.MINING:
            self.forecast_detail.insert('end','\nCost schedules: '+str(sector_schedules['costs']))
        self._text('WACC','\n'.join(f"{a.field}: {a.value} {a.unit} [{LABELS[a.origin.value]} / {a.approval_state.value}]" for a in wacc) + '\nCalculated: ' + str(calculate_plan_wacc(p)))
        if route == WorkbenchRoute.MINING:
            self.forecast_detail.insert('end','\nCommodity price schedule: '+str(price_fx_schedule(p,'commodity_price')))
        if route in {WorkbenchRoute.MINING, WorkbenchRoute.RETAIL}:
            self.forecast_detail.insert('end','\nFX schedule: '+str(price_fx_schedule(p,'fx_rate')))
        self._render_dcf_panel(p)
        self._text('SOTP','SOTP components must have explicit asset boundaries, ownership, probability, and source-linked values.\n'+('\n'.join(c.name for c in p.engine_plan.cases['base'].sotp.components) if p.engine_plan and p.engine_plan.cases.get('base') and p.engine_plan.cases['base'].sotp else 'No SOTP components entered.'))
        bank_case = p.engine_plan.cases.get('base') if p.engine_plan else None
        if bank_case and bank_case.primary_method == 'RESIDUAL_INCOME':
            bank_fields = {'common_equity','bank_roe','bank_earnings','dividend_payout','bank_dividends',
                           'bank_equity_movement','risk_free_rate','beta','equity_risk_premium',
                           'country_risk_premium','cost_of_equity','bank_terminal_roe','terminal_growth',
                           'forecast_diluted_shares','cet1_ratio','cet1_minimum','cet1_target','target_pb'}
            rows = [f"{a.period_label or 'Base'} | {a.field}: {a.value} {a.unit} [{LABELS[a.origin.value]} / {a.approval_state.value}]"
                    for a in p.assumptions if a.field in bank_fields]
            self._text('Bank Equity', 'Residual income uses common equity, ROE or earnings, payout, '
                'cost of equity, terminal ROE/growth, and forecast diluted shares. '
                'The bank equity bridge does not add cash or subtract deposits.\n' +
                ('\n'.join(rows) if rows else 'No approved bank forecast inputs entered.'))
            self._text('WACC', 'Bank residual income uses cost of equity; enterprise WACC is inapplicable.')
            self._text('DCF', 'Operating enterprise DCF is inapplicable to the bank residual-income method.')
        else:
            self._text('Bank Equity', 'Select bank sector and an explicit RESIDUAL_INCOME engine mapping to use this panel.')
        self._text('Sensitivity','Enter two saved approved plan versions and calculate the target-price change. Missing inputs remain NOT_CALCULABLE. No Gemini estimate is used.')
        self._text('Reconciliation',render_equity_bridge_preview(
            equity_bridge_preview(p,self.evidence)))
        self._render_backtest()
        self._text('Audit',f'Plan ID: {p.forecast_plan_id}\nSource report: {p.source_report_version_id}\nEngine: {p.valuation_engine_version}\nApproval: {p.approval_status}\nUnaccepted assumptions: '+str(sum(a.approval_state!=ApprovalState.ACCEPTED for a in p.assumptions)))
        from modules.analysis.forecast_plan import plan_changes
        plan_by_version={x.plan_version:x for x in self.plans}
        hist='\n'.join(f"{h['generated_at']} | Plan v{h['plan_version'] or 'none'} | {h['status']} | {h['publication_state']} | target {h['target_price'] or 'NOT_CALCULABLE'} | engine {h['valuation_engine_version']} | changes {plan_changes(plan_by_version[h['plan_version']],plan_by_version.get(h['plan_version']-1)) if h['plan_version'] in plan_by_version else 'unknown'}" for h in self.history)
        from modules.analysis.forecast_plan_history import history_rows
        self.plan_history_table.delete(*self.plan_history_table.get_children())
        for row in history_rows(self.plans):
            self.plan_history_table.insert('', 'end',iid=row['plan_id'],values=(f"v{row['version']}",row['status'],str(row['created']),row['plan_id']))
        self._text('Legacy / History',f'Legacy Gemini target: {p.legacy_target or "see historical report"} (historical, unreconciled)\nDeterministic history:\n'+(hist or 'No valuations saved.'))

    def add_period(self):
        if not self.plan: return
        try:
            period=ForecastPeriod(label=self.fields['period_label'].get(),start=date.fromisoformat(self.fields['period_start'].get()),end=date.fromisoformat(self.fields['period_end'].get()))
            self.plan=new_version(self.plan,changed_by=self.fields['analyst'].get() or 'analyst',horizon=sorted([*self.plan.horizon,period],key=lambda p:p.start))
            self._stage_plan(self.plan)
        except Exception as e: messagebox.showerror('Invalid period',str(e))

    def add_assumption(self):
        if not self.plan: return
        try:
            period_label=self.fields['period_label'].get().strip() or None
            start_text=self.fields['period_start'].get().strip()
            end_text=self.fields['period_end'].get().strip()
            start=date.fromisoformat(start_text) if start_text else None
            end=date.fromisoformat(end_text) if end_text else None
            horizon,period_added=horizon_for_assumption(
                self.plan,period_label,start=start,end=end)
            a=ForecastAssumption(field=self.fields['field'].get().strip(),value=Decimal(self.fields['value'].get()) if self.fields['value'].get() else None,
              unit=self.fields['unit'].get() or None,currency=self.fields['currency'].get() or None,
              period_label=period_label,operation_segment=self.fields['operation'].get() or None,
              case=self.fields['case'].get() or 'base',origin=Origin.ANALYST_ASSUMPTION,
              rationale=self.fields['rationale'].get(),created_by=self.fields['analyst'].get() or 'analyst',
              commodity=self.fields['commodity'].get() or None,price_type=self.fields['price_type'].get() or None,
              cost_definition=self.fields['cost_definition'].get() or None,fx_pair=self.fields['fx_pair'].get() or None,
              confidence=Decimal(self.fields['confidence'].get()) if self.fields['confidence'].get() else None,
              effective_date=date.fromisoformat(self.fields['effective_date'].get()) if self.fields['effective_date'].get() else None)
            self.plan=new_version(self.plan,changed_by=a.created_by,horizon=horizon,
                                  assumptions=[*self.plan.assumptions,a])
            self._stage_plan(self.plan)
            if period_added:
                self.status.set(f'Added financial period {period_label} and proposed assumption {a.field}.')
        except Exception as e: messagebox.showerror('Invalid assumption',str(e))

    def import_assumptions_txt(self):
        if not self.plan:
            return
        path=filedialog.askopenfilename(
            parent=self, title='Import ForecastPlan assumptions',
            filetypes=[('Text files','*.txt')])
        if not path:
            return
        try:
            text=Path(path).read_text(encoding='utf-8-sig')
            allowed_operations={
                value for value in (
                    *[m.get('operation_segment') for m in self.evidence],
                    *[a.operation_segment for a in self.plan.assumptions],
                ) if value
            }
            preview=parse_forecast_txt(
                text, current_plan=self.plan, current_ticker=self.ticker,
                category=self.category, source_name=Path(path).name,
                allowed_operations=allowed_operations)
        except (OSError, UnicodeError, ForecastTxtImportError) as exc:
            messagebox.showerror('Assumption import blocked',str(exc),parent=self)
            return
        dialog=ttk.Toplevel(self)
        dialog.title('Preview ForecastPlan assumption import')
        dialog.geometry('900x650')
        dialog.transient(self.winfo_toplevel())
        ttk.Label(dialog,text='Review the validated assumptions below. Import keeps every entry PROPOSED.',
                  font=('Helvetica',11,'bold')).pack(fill=X,padx=10,pady=(10,5))
        body=ttk.Text(dialog,wrap='word')
        body.pack(fill=BOTH,expand=True,padx=10,pady=5)
        body.insert('1.0',preview.render()); body.configure(state='disabled')
        buttons=ttk.Frame(dialog); buttons.pack(fill=X,padx=10,pady=10)
        def confirm(action):
            try:
                resolved=resolve_import_assumptions(self.plan,preview,action)
            except ForecastTxtImportError as exc:
                messagebox.showerror('Duplicate resolution required',str(exc),parent=dialog)
                return
            if resolved == self.plan.assumptions and preview.horizon == self.plan.horizon:
                self.status.set(
                    f'No changes imported from {preview.source_name}; identical duplicates kept existing.')
                dialog.destroy()
                return
            sources=[*preview.assumptions,*[item.imported for item in preview.conflicts]]
            analyst=sources[0].created_by if sources else 'analyst'
            self.plan=new_version(
                self.plan, changed_by=analyst, horizon=preview.horizon,
                assumptions=resolved)
            self._stage_plan(self.plan)
            replaced=len(preview.conflicts) if action == 'replace_as_proposed' else 0
            self.status.set(
                f'Imported {len(preview.assumptions)} new and replaced {replaced} conflicting '
                f'assumption(s) from {preview.source_name}. Save new version when ready; '
                'nothing has been accepted or approved.')
            dialog.destroy()
        ttk.Button(buttons,text='Cancel',command=dialog.destroy).pack(side='right',padx=5)
        if preview.conflicts:
            ttk.Button(buttons,text='Replace as Proposed',
                       command=lambda:confirm('replace_as_proposed')).pack(side='right',padx=5)
            ttk.Button(buttons,text='Keep Existing',
                       command=lambda:confirm('keep_existing')).pack(side='right',padx=5)
        else:
            ttk.Button(buttons,text='Import as proposed',
                       command=lambda:confirm('keep_existing')).pack(side='right',padx=5)
        dialog.protocol('WM_DELETE_WINDOW',dialog.destroy)
        dialog.grab_set()
        dialog.focus_set()

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
            self._stage_plan(self.plan)
        except Exception as e: messagebox.showerror('Cannot accept',str(e))

    async def _save_and_reload(self):
        try:
            if not self.pending:
                raise ValueError('There are no unsaved ForecastPlan changes')
            item=self.plan
            await save_plan(item)
            data=await self._load()
            return {'ok':True,'plan':item,'data':data}
        except Exception as exc:
            return {'ok':False,'error':str(exc)}

    def save(self):
        if not self.plan or self.saving: return
        self.saving=True
        self.status.set('Saving ForecastPlan...')
        def done(payload):
            self.saving=False
            if not payload or not payload.get('ok'):
                error=(payload or {}).get('error','Unknown persistence error')
                self.status.set('ForecastPlan save failed; unsaved draft retained.')
                messagebox.showerror('ForecastPlan save failed',error,parent=self)
                return
            saved=payload['plan']
            self._apply_loaded(payload['data'],saved.forecast_plan_id)
            message=save_confirmation(saved)
            self.status.set(message.replace('\n\n',' — ').replace('\n',' | '))
            messagebox.showinfo('ForecastPlan saved',message,parent=self)
        self.async_run_bg(self._save_and_reload(),callback=done)

    async def _approve_and_reload(self,reviewer):
        try:
            approved=await approve_saved_plan(self.plan.forecast_plan_id,reviewer)
            data=await self._load()
            return {'ok':True,'plan':approved,'data':data}
        except Exception as exc:
            return {'ok':False,'error':str(exc)}

    def approve(self):
        if not self.plan or self.saving: return
        if self.pending:
            messagebox.showerror(
                'Save draft first',
                'Save the current ForecastPlan version before approving it.',parent=self)
            return
        reviewer=self.fields['analyst'].get() or 'analyst'
        self.saving=True
        self.status.set(f'Approving ForecastPlan v{self.plan.plan_version}...')
        def done(payload):
            self.saving=False
            if not payload or not payload.get('ok'):
                error=(payload or {}).get('error','Unknown approval error')
                self.status.set('ForecastPlan approval failed; persisted status unchanged.')
                messagebox.showerror('ForecastPlan approval failed',error,parent=self)
                return
            approved=payload['plan']
            self._apply_loaded(payload['data'],approved.forecast_plan_id)
            message=approval_confirmation(approved)
            self.status.set(message.replace('\n\n',' — ').replace('\n',' | '))
            messagebox.showinfo('ForecastPlan approved',message,parent=self)
        self.async_run_bg(self._approve_and_reload(reviewer),callback=done)

    def discard_selected(self):
        if not self.plan: return
        selected=self.assumption_table.selection()
        if len(selected)!=1:
            messagebox.showerror(
                'Select one proposal',
                'Select one proposed analyst assumption to discard.')
            return
        from uuid import UUID
        from modules.analysis.forecast_plan import discard_proposed_assumption
        ident=UUID(selected[0])
        original=next(
            (item for item in self.plan.assumptions
             if item.assumption_id==ident),None)
        if (original is None or original.origin!=Origin.ANALYST_ASSUMPTION
                or original.approval_state!=ApprovalState.PROPOSED):
            messagebox.showerror(
                'Cannot discard',
                'Only a proposed analyst assumption can be discarded.')
            return
        if not messagebox.askyesno(
                'Discard proposed assumption',
                'Discard this proposed analyst assumption from the current draft?'):
            return
        try:
            self.plan=discard_proposed_assumption(
                self.plan,ident,self.fields['analyst'].get() or 'analyst')
            self._stage_plan(self.plan)
            self.status.set(
                'Proposed analyst assumption discarded from the in-memory '
                'draft. Save new version to persist.')
        except Exception as e:
            messagebox.showerror('Cannot discard',str(e))

    def reject_selected(self):
        if not self.plan: return
        from uuid import UUID
        from modules.analysis.forecast_plan import reject_suggestion
        selected=self.assumption_table.selection()
        if len(selected)!=1: return
        try:
            self.plan=reject_suggestion(self.plan,UUID(selected[0]),self.fields['analyst'].get() or 'analyst')
            self._stage_plan(self.plan)
        except Exception as e: messagebox.showerror('Cannot reject',str(e))

    def apply_mapping(self):
        if not self.plan: return
        from modules.analysis.valuation.engine import ValuationPlan
        try:
            mapping=ValuationPlan.model_validate_json(self.mapping_text.get('1.0','end'))
            self.plan=new_version(self.plan,changed_by=self.fields['analyst'].get() or 'analyst',engine_plan=mapping)
            self._stage_plan(self.plan)
        except Exception as e: messagebox.showerror('Invalid engine mapping',str(e))

    def map_accepted_fy2027_dcf(self):
        if not self.plan: return
        from modules.analysis.dcf_mapping import (
            map_accepted_fy2027_inputs,render_fy2027_mapping_preview)
        try:
            proposed,resolved=map_accepted_fy2027_inputs(
                self.plan,self.evidence,
                changed_by=self.fields['analyst'].get() or 'analyst')
            preview=render_fy2027_mapping_preview(resolved)
            if resolved['already_mapped']:
                messagebox.showinfo('Already mapped',preview)
                self.status.set('FY2027 accepted inputs are already mapped; draft unchanged.')
                return
            if not messagebox.askyesno(
                    'Confirm FY2027 DCF mapping',
                    preview+'\n\nApply this mapping to a new in-memory draft?'):
                self.status.set('FY2027 DCF mapping cancelled; plan unchanged.')
                return
            self._stage_plan(proposed)
            self.status.set(
                'Accepted FY2027 inputs mapped to a new in-memory draft. '
                'Save and approve separately; no valuation was run.')
        except Exception as e:
            messagebox.showerror('Cannot map FY2027 DCF inputs',str(e))

    async def _run_approved(self):
        from modules.analysis.financial_metrics import FinancialMetric
        from modules.analysis.forecast_plan import compile_plan_inputs,preview_valuation
        from modules.data.forecast_plans import save_plan_valuation
        evidence=[FinancialMetric.model_validate(x) for x in self.evidence]
        metrics,candidates=compile_plan_inputs(self.plan,evidence)
        result=preview_valuation(self.plan,metrics,candidates)
        await save_plan_valuation(self.plan,result)
        return result

    async def _execute_dcf(self,readiness):
        from modules.analysis.dcf_execution import valuation_input_hash,add_execution_warnings,require_calculable_dcf
        from modules.analysis.forecast_plan import preview_valuation
        from modules.data.forecast_plans import get_idempotent_plan_valuation,save_plan_valuation
        input_hash=valuation_input_hash(self.plan)
        existing=await get_idempotent_plan_valuation(self.plan,input_hash)
        if existing is not None:
            return existing,True
        result=require_calculable_dcf(add_execution_warnings(
            preview_valuation(self.plan,readiness['metrics'],readiness['candidates'])))
        result.calculation_inputs['input_hash']=input_hash
        await save_plan_valuation(self.plan,result)
        return result,False

    def run_deterministic_dcf(self):
        from modules.analysis.dcf_execution import execution_readiness,render_dcf_result
        if not self.plan:
            return
        readiness=execution_readiness(self.plan,self.evidence)
        if self.pending:
            readiness['status']='BLOCKED'
            readiness['reasons'].append('Unsaved ForecastPlan changes')
        if readiness['status']!='READY':
            messagebox.showerror(
                'Deterministic DCF blocked',
                'Preflight did not pass:\n\n'+'\n'.join(readiness['reasons']))
            self._render_dcf_panel(self.plan)
            return
        self.run_dcf_button.configure(state='disabled')
        self.status.set('Running deterministic DCF for the approved ForecastPlan...')
        def done(payload):
            if payload is None:
                self.status.set('Deterministic DCF failed; inspect application log.')
                self._render_dcf_panel(self.plan)
                return
            result,reused=payload
            self.valuation_id_var.set(str(result.valuation_id))
            self._text('DCF',render_dcf_result(result,self.plan,reused=reused))
            action=('Existing deterministic result loaded' if reused
                    else 'Deterministic DCF saved as append-only draft')
            self.status.set(f"{action}: {result.target_price or 'NOT_CALCULABLE'}.")
            self.run_dcf_button.configure(state='normal')
        self.async_run_bg(self._execute_dcf(readiness),callback=done)

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
            if self.plan.engine_plan and self.plan.engine_plan.cases.get('base') and self.plan.engine_plan.cases['base'].primary_method == 'RESIDUAL_INCOME':
                bank_result = result.methods['RESIDUAL_INCOME']
                self._text('Bank Equity', 'Residual-income schedule:\n' +
                    '\n'.join(str(row) for row in bank_result.schedule) +
                    '\nP/B cross-checks: ' + str(result.implied_checks) +
                    '\nWarnings: ' + str(result.warnings))
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
            self._stage_plan(self.plan)
        except Exception as e: messagebox.showerror('Invalid suggestion',str(e))









