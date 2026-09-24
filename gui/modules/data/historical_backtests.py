"""Persistence and database resolvers for isolated Historical Backtests."""
from __future__ import annotations
from datetime import date,datetime,timezone
from decimal import Decimal
from uuid import UUID,uuid4,uuid5,NAMESPACE_URL
import json
from core.db.engine import DBEngine
from modules.data.report_versions import json_text
from modules.analysis.historical_backtest import (HistoricalBacktest,HistoricalEvidence,
    BacktestStatus,resolve_evidence_as_of,resolve_latest_market_as_of,
    backtest_input_hash,canonical_hash,lock_backtest,compare_forecast_actuals,valuation_performance,
    require_reveal_allowed,transition_key)
from modules.analysis.forecast_plan import ForecastPlan,PlanStatus,approve_plan,compile_plan_inputs,preview_valuation
from modules.analysis.financial_metrics import FinancialMetric

async def resolve_historical_snapshot(ticker:str,as_of_date:date,db=DBEngine):
    """Resolve only dated evidence/market rows; never reads stock_analysis.current_report_id."""
    metric_rows=await db.fetch("""SELECT f.metric,d.report_id
      FROM financial_metrics f JOIN deepresearch_versions d ON d.report_id=f.report_id
      WHERE d.ticker=$1""",ticker)
    raw_metrics=[]
    for row in metric_rows:
        raw=json.loads(row['metric']) if isinstance(row['metric'],str) else dict(row['metric'])
        if raw.get('assumption_type') not in {'historical_actual','formal_guidance','management_target','python_calculation'}:
            continue
        if raw.get('name')=='target_price':
            continue
        raw['report_id']=str(row['report_id']); raw_metrics.append(raw)
    eligible,excluded=resolve_evidence_as_of(raw_metrics,as_of_date)
    from pathlib import Path
    from modules.analysis.historical_packages import discover_packages
    package_root=Path(__file__).resolve().parents[2]/'results_history'
    packages=discover_packages(package_root,ticker,as_of_date)
    package_observations=[]
    for package in packages:
        sources=package['validation']['sources']
        by_id={x['source_id']:x for x in sources}
        for source in sources:
            source_row={**source,'id':source['source_id'],'kind':source['document_role']}
            included,_excluded=resolve_evidence_as_of([source_row],as_of_date)
            eligible.extend(included);excluded.extend(_excluded)
        from modules.analysis.results_package import observations_to_metrics
        package_id=uuid5(NAMESPACE_URL,package['folder'])
        manifest=package['validation']['manifest']
        typed=observations_to_metrics(ticker,package_id,package['results_package'],
            manifest.period_end,datetime.combine(as_of_date,datetime.min.time(),tzinfo=timezone.utc))
        for metric in typed:
            raw=metric.model_dump(mode='json')
            raw['available_date']=raw.get('source_date')
            included,_excluded=resolve_evidence_as_of([raw],as_of_date)
            eligible.extend(included);excluded.extend(_excluded);package_observations.extend(included)
    sens_rows=await db.fetch("""SELECT sens_id,publication_datetime,source_document_id,content
      FROM sens WHERE ticker=$1 AND publication_datetime::date <= $2
        AND (content ILIKE '%results%' OR content ILIKE '%financial statements%')
      ORDER BY publication_datetime""",ticker,as_of_date)
    sens_raw=[{'id':f"sens:{r['sens_id']}",'source_id':f"sens:{r['sens_id']}",
      'source_document_id':str(r['source_document_id']) if r['source_document_id'] else None,
      'kind':'results_sens','available_date':r['publication_datetime'].date(),
      'published_at':r['publication_datetime'].date(),'content':r['content']} for r in sens_rows]
    sens_eligible,sens_excluded=resolve_evidence_as_of(sens_raw,as_of_date)
    eligible.extend(sens_eligible);excluded.extend(sens_excluded)
    price_rows=await db.fetch("""SELECT observation_id AS id,ticker,trade_date,
      COALESCE(raw_close,close_price) AS close_price,source,source_document_id,
      COALESCE(currency,'ZAR') AS currency,COALESCE(price_unit,'cents_per_share') AS unit,
      COALESCE(price_basis,'raw_close') AS price_basis,provider_symbol
      FROM price_observations WHERE ticker=$1 AND trade_date <= $2
      ORDER BY trade_date DESC,observed_at DESC LIMIT 1""",ticker,as_of_date)
    market_raw=[{'id':str(r['id']),'kind':'share_price','instrument':ticker,
      'trade_date':r['trade_date'],'value':r['close_price'],'currency':r['currency'],'unit':r['unit'],
      'source':r['source'] or 'unknown','price_basis':r['price_basis'],'provider_symbol':r['provider_symbol'],
      'source_document_id':str(r['source_document_id']) if r['source_document_id'] else None} for r in price_rows]
    market=resolve_latest_market_as_of(market_raw,as_of_date)
    available_periods=sorted({x.period_end for x in eligible if x.period_end})
    period_end=available_periods[-1] if available_periods else None
    reports=sorted({x.report_id for x in eligible if x.report_id},key=str)
    backtest=HistoricalBacktest(ticker=ticker,as_of_date=as_of_date,
      reporting_period_end=period_end,evidence_snapshot=eligible,market_snapshot=market,
      source_report_ids=reports,created_by='analyst',metadata={
        'excluded_evidence':[x.model_dump(mode='json') for x in excluded],
        'resolver':'historical_backtest_v1','historical_packages':[p['folder'] for p in packages],
        'current_report_pointer_used':False,
        'current_forecast_plans_used':False,'learning_points_used':False})
    backtest=backtest.model_copy(update={'input_hash':backtest_input_hash(backtest)})
    return backtest

async def insert_backtest(backtest:HistoricalBacktest,db=DBEngine):
    result=await db.execute("""INSERT INTO historical_backtests
      (backtest_id,ticker,as_of_date,reporting_period_label,reporting_period_end,status,
       evidence_snapshot,market_snapshot,evidence_ids,market_snapshot_ids,source_report_ids,
       created_by,created_at,locked_at,input_hash,metadata)
      VALUES($1,$2,$3,$4,$5,$6,$7::jsonb,$8::jsonb,$9,$10,$11,$12,$13,$14,$15,$16::jsonb)
      ON CONFLICT(ticker,as_of_date,input_hash) DO NOTHING""",
      backtest.backtest_id,backtest.ticker,backtest.as_of_date,backtest.reporting_period_label,
      backtest.reporting_period_end,backtest.status.value,
      json_text([x.model_dump(mode='json') for x in backtest.evidence_snapshot]),
      json_text([x.model_dump(mode='json') for x in backtest.market_snapshot]),
      [x.evidence_id for x in backtest.evidence_snapshot],[x.snapshot_id for x in backtest.market_snapshot],
      backtest.source_report_ids,backtest.created_by,backtest.created_at,backtest.locked_at,
      backtest.input_hash,json_text(backtest.metadata))
    rows=await db.fetch("SELECT * FROM historical_backtests WHERE ticker=$1 AND as_of_date=$2 AND input_hash=$3",backtest.ticker,backtest.as_of_date,backtest.input_hash)
    return dict(rows[0]) if rows else None

async def save_historical_plan(backtest_id:UUID,plan:ForecastPlan,created_by:str,db=DBEngine):
    if plan.status!=PlanStatus.DRAFT:raise ValueError('Only a historical draft may be inserted')
    version=await db.fetch("SELECT COALESCE(MAX(plan_version),0)+1 AS version FROM historical_backtest_plans WHERE backtest_id=$1",backtest_id)
    number=version[0]['version']; ident=uuid4(); digest=canonical_hash({'backtest_id':backtest_id,'plan':plan.model_dump(mode='json'),'engine_version':plan.valuation_engine_version})
    await db.execute("""INSERT INTO historical_backtest_plans
      (historical_plan_id,backtest_id,plan_version,status,forecast_plan_snapshot,input_hash,created_by)
      VALUES($1,$2,$3,'draft',$4::jsonb,$5,$6)""",ident,backtest_id,number,plan.model_dump_json(),digest,created_by)
    return ident,number

def _minimal_backtest(backtest_id):
    return HistoricalBacktest(backtest_id=backtest_id,ticker='snapshot',as_of_date=date.min,created_by='system')

async def approve_historical_plan(backtest_id:UUID,historical_plan_id:UUID,reviewer:str,db=DBEngine):
    rows=await db.fetch("SELECT forecast_plan_snapshot,status FROM historical_backtest_plans WHERE historical_plan_id=$1 AND backtest_id=$2",historical_plan_id,backtest_id)
    if not rows or rows[0]['status']!='draft':raise ValueError('Historical draft plan not found')
    raw=rows[0]['forecast_plan_snapshot']; plan=ForecastPlan.model_validate(json.loads(raw) if isinstance(raw,str) else raw)
    approved=approve_plan(plan,reviewer)
    await db.execute("""UPDATE historical_backtest_plans SET status='approved',forecast_plan_snapshot=$3::jsonb,
      approved_by=$4,approved_at=$5 WHERE historical_plan_id=$1 AND backtest_id=$2 AND status='draft'""",
      historical_plan_id,backtest_id,approved.model_dump_json(),reviewer,approved.approved_at)
    return approved

async def lock_and_run_backtest(backtest_id:UUID,historical_plan_id:UUID,db=DBEngine):
    rows=await db.fetch("""SELECT b.*,p.forecast_plan_snapshot,p.status plan_status
      FROM historical_backtests b JOIN historical_backtest_plans p ON p.backtest_id=b.backtest_id
      WHERE b.backtest_id=$1 AND p.historical_plan_id=$2""",backtest_id,historical_plan_id)
    if not rows:raise ValueError('Historical backtest/plan not found')
    row=rows[0]
    if row['status']!='draft' or row['plan_status']!='approved':raise ValueError('Approved historical plan on a draft backtest required')
    evidence_raw=json.loads(row['evidence_snapshot']) if isinstance(row['evidence_snapshot'],str) else row['evidence_snapshot']
    market_raw=json.loads(row['market_snapshot']) if isinstance(row['market_snapshot'],str) else row['market_snapshot']
    bt=HistoricalBacktest(backtest_id=row['backtest_id'],ticker=row['ticker'],as_of_date=row['as_of_date'],reporting_period_label=row['reporting_period_label'],reporting_period_end=row['reporting_period_end'],status=row['status'],evidence_snapshot=evidence_raw,market_snapshot=market_raw,source_report_ids=row['source_report_ids'],created_by=row['created_by'],created_at=row['created_at'],input_hash=row['input_hash'],metadata=row['metadata'])
    plan_raw=row['forecast_plan_snapshot']; plan=ForecastPlan.model_validate(json.loads(plan_raw) if isinstance(plan_raw,str) else plan_raw)
    metrics=[FinancialMetric.model_validate(x.payload) for x in bt.evidence_snapshot if x.kind!='results_sens' and x.payload.get('metric_id')]
    compiled,candidates=compile_plan_inputs(plan,metrics)
    from modules.analysis.dcf_execution import require_calculable_dcf,add_execution_warnings
    result=require_calculable_dcf(add_execution_warnings(preview_valuation(plan,compiled,candidates)))
    locked=lock_backtest(bt,plan,plan.valuation_engine_version,result.input_ids)
    digest=backtest_input_hash(locked,plan,plan.valuation_engine_version,result.input_ids)
    existing=await db.fetch("""SELECT historical_result_id,valuation_result FROM historical_backtest_results
      WHERE backtest_id=$1 AND historical_plan_id=$2 AND valuation_engine_version=$3 AND input_hash=$4""",backtest_id,historical_plan_id,plan.valuation_engine_version,digest)
    if existing:return dict(existing[0]),True
    price=next((x for x in locked.market_snapshot if x.kind=='share_price'),None)
    market_price_zar=(price.value/Decimal(100)) if price else None
    implied=(result.target_price-market_price_zar)/market_price_zar*100 if market_price_zar and result.target_price is not None else None
    rid=uuid4()
    pool=await db.get_pool()
    async with pool.acquire() as conn:
      async with conn.transaction():
       await conn.execute("UPDATE historical_backtests SET status='locked',locked_at=$2,input_hash=$3 WHERE backtest_id=$1 AND status='draft'",backtest_id,locked.locked_at,digest)
       await conn.execute("""INSERT INTO historical_backtest_results
        (historical_result_id,backtest_id,historical_plan_id,valuation_engine_version,input_hash,
         valuation_result,historical_share_price,implied_upside_downside,warnings)
        VALUES($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb,$8,$9::jsonb)""",rid,backtest_id,historical_plan_id,plan.valuation_engine_version,digest,result.model_dump_json(),json_text(price.model_dump(mode='json')) if price else None,implied,json_text(result.warnings))
    return {'historical_result_id':rid,'valuation_result':result.model_dump(mode='json')},False

async def reveal_actuals(backtest_id:UUID,historical_result_id:UUID,actual_period_end:date,db=DBEngine):
    rows=await db.fetch("SELECT * FROM historical_backtests WHERE backtest_id=$1",backtest_id)
    if not rows:raise ValueError('Historical backtest not found')
    row=rows[0]
    bt=HistoricalBacktest(backtest_id=row['backtest_id'],ticker=row['ticker'],as_of_date=row['as_of_date'],status=row['status'],locked_at=row['locked_at'],created_by=row['created_by'])
    require_reveal_allowed(bt)
    plan_rows=await db.fetch("""SELECT p.forecast_plan_snapshot FROM historical_backtest_results r JOIN historical_backtest_plans p ON p.historical_plan_id=r.historical_plan_id WHERE r.historical_result_id=$1 AND r.backtest_id=$2""",historical_result_id,backtest_id)
    if not plan_rows:raise ValueError('Historical result not found')
    raw=plan_rows[0]['forecast_plan_snapshot']; plan=ForecastPlan.model_validate(json.loads(raw) if isinstance(raw,str) else raw)
    actual_rows=await db.fetch("""SELECT f.metric FROM financial_metrics f JOIN deepresearch_versions d ON d.report_id=f.report_id
      WHERE d.ticker=$1 AND f.metric->>'period_end'=$2""",row['ticker'],str(actual_period_end))
    actual=[json.loads(x['metric']) if isinstance(x['metric'],str) else dict(x['metric']) for x in actual_rows]
    accuracy=compare_forecast_actuals([x.model_dump(mode='json') for x in plan.assumptions if x.approval_state.value=='accepted'],actual)
    key=transition_key(row['ticker'],row['reporting_period_end'],actual_period_end)
    oid=uuid4()
    await db.execute("""INSERT INTO historical_backtest_outcomes
      (outcome_id,backtest_id,historical_result_id,transition_key,actual_period_end,actual_evidence_ids,forecast_accuracy,valuation_performance)
      VALUES($1,$2,$3,$4,$5,$6,$7::jsonb,'{}'::jsonb) ON CONFLICT(backtest_id,transition_key) DO NOTHING""",oid,backtest_id,historical_result_id,key,actual_period_end,[str(x.get('metric_id')) for x in actual if x.get('metric_id')],json_text(accuracy))
    await db.execute("UPDATE historical_backtests SET status='completed' WHERE backtest_id=$1 AND status='locked'",backtest_id)
    return accuracy

async def list_backtests(ticker:str,db=DBEngine):
    return [dict(x) for x in await db.fetch("SELECT * FROM historical_backtests WHERE ticker=$1 ORDER BY as_of_date DESC,created_at DESC",ticker)]








