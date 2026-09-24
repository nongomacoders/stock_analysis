import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from datetime import date,datetime,timezone
from decimal import Decimal
from uuid import uuid4
import pytest
from modules.analysis.historical_backtest import (
 Availability,BacktestStatus,HistoricalBacktest,resolve_evidence_as_of,
 resolve_latest_market_as_of,select_historical_share_count,backtest_input_hash,
 lock_backtest,require_reveal_allowed,compare_forecast_actuals,
 valuation_performance,transition_key)
from modules.analysis.forecast_plan import ForecastPlan,PlanStatus

RID=uuid4()
def approved_plan():
 return ForecastPlan(ticker='TRU.JO',created_by='Dion',source_report_version_id=RID,
   status=PlanStatus.APPROVED,approval_status='approved',approved_by='Dion',approved_at=datetime.now(timezone.utc))

def test_as_of_cutoff_excludes_later_and_unknown_sens_afs():
 rows=[
  {'id':'sens-old','kind':'results_sens','source_date':'2022-08-30'},
  {'id':'afs-later','kind':'annual_financial_statements','source_date':'2022-09-02'},
  {'id':'afs-unknown','kind':'annual_financial_statements','source_date':None}]
 included,excluded=resolve_evidence_as_of(rows,date(2022,9,1))
 assert [x.evidence_id for x in included]==['sens-old']
 assert {x.availability for x in excluded}=={Availability.UNAVAILABLE,Availability.UNCERTAIN}

def test_later_market_data_excluded_and_latest_prior_with_lag_selected():
 rows=[{'id':'p1','kind':'share_price','ticker':'TRU.JO','trade_date':'2022-08-30','value':'5000','source':'yf'},
       {'id':'p2','kind':'share_price','ticker':'TRU.JO','trade_date':'2022-09-01','value':'5100','source':'yf'},
       {'id':'future','kind':'share_price','ticker':'TRU.JO','trade_date':'2022-09-02','value':'9999','source':'yf'}]
 got=resolve_latest_market_as_of(rows,date(2022,9,1))
 assert len(got)==1 and got[0].snapshot_id=='p2' and got[0].lag_days==0

def test_historical_share_count_uses_available_semantic_priority_not_current():
 rows=[{'metric_id':'old-issued','name':'issued_shares_current','source_date':'2022-08-30','value':'400','period_end':'2022-06-30'},
       {'metric_id':'old-diluted','name':'weighted_average_diluted_shares','source_date':'2022-08-30','value':'390','period_end':'2022-06-30'},
       {'metric_id':'today','name':'forecast_diluted_shares','source_date':'2026-08-30','value':'300'}]
 included,_=resolve_evidence_as_of(rows,date(2022,9,1))
 selected=select_historical_share_count(included)
 assert selected.evidence_id=='old-diluted'

def test_historical_wacc_inputs_obey_same_cutoff():
 rows=[{'metric_id':'rf-old','name':'risk_free_rate','source_date':'2022-09-01','value':'10'},
       {'metric_id':'rf-new','name':'risk_free_rate','source_date':'2023-09-01','value':'12'}]
 included,_=resolve_evidence_as_of(rows,date(2022,9,1))
 assert [x.evidence_id for x in included]==['rf-old']

def test_input_hash_reproducible_and_sensitive_to_cutoff_plan_and_evidence():
 bt=HistoricalBacktest(ticker='TRU.JO',as_of_date=date(2022,9,1),created_by='Dion')
 plan=approved_plan(); one=backtest_input_hash(bt,plan,'1.1');two=backtest_input_hash(bt,plan,'1.1')
 assert one==two
 assert one!=backtest_input_hash(bt.model_copy(update={'as_of_date':date(2022,9,2)}),plan,'1.1')

def test_lock_is_copy_on_write_and_requires_approved_historical_plan():
 bt=HistoricalBacktest(ticker='TRU.JO',as_of_date=date(2022,9,1),created_by='Dion')
 locked=lock_backtest(bt,approved_plan(),'1.1')
 assert bt.status==BacktestStatus.DRAFT and locked.status==BacktestStatus.LOCKED
 assert locked.locked_at and locked.input_hash
 draft=approved_plan().model_copy(update={'status':PlanStatus.DRAFT})
 with pytest.raises(ValueError,match='approved'):lock_backtest(bt,draft,'1.1')

def test_reveal_actuals_only_after_lock():
 bt=HistoricalBacktest(ticker='TRU.JO',as_of_date=date(2022,9,1),created_by='Dion')
 with pytest.raises(ValueError,match='locked'):require_reveal_allowed(bt)
 require_reveal_allowed(lock_backtest(bt,approved_plan(),'1.1'))

def test_forecast_errors_use_percentage_and_basis_points_without_invention():
 forecast=[{'assumption_id':'a','field':'revenue','value':'100','unit':'ZAR','operation_segment':'Group'},
           {'assumption_id':'b','field':'trading_margin','value':'12','unit':'percentage','operation_segment':'Group'},
           {'assumption_id':'c','field':'fcff','value':'5','unit':'ZAR','operation_segment':'Group'}]
 actual=[{'metric_id':'m1','name':'revenue','value':'110','unit':'ZAR','operation_segment':'Group'},
         {'metric_id':'m2','name':'trading_margin','value':'13','unit':'percentage','operation_segment':'Group'}]
 got=compare_forecast_actuals(forecast,actual)
 assert got[0]['error_pct']=='10.0'
 assert got[1]['error_bps']=='100'
 assert all(x['field']!='fcff' for x in got)

def test_valuation_performance_keeps_price_return_separate_from_total_return():
 got=valuation_performance('60','50',{'12m':'55'})
 assert got['implied_upside_downside_pct']=='20.0'
 assert got['price_returns']['12m']=='10.0'
 assert got['return_basis']=='price_return_excluding_dividends'

def test_transition_key_deduplicates_same_reporting_transition():
 assert transition_key('TRU.JO','FY2025','FY2026')==transition_key('TRU.JO','FY2025','FY2026')
 assert transition_key('TRU.JO','FY2024','FY2025')!=transition_key('TRU.JO','FY2025','FY2026')

def test_current_live_objects_are_not_mutated_or_included():
 live=approved_plan(); dump=live.model_dump()
 bt=HistoricalBacktest(ticker='TRU.JO',as_of_date=date(2022,9,1),created_by='Dion',metadata={
   'current_report_pointer_used':False,'current_forecast_plans_used':False,'learning_points_used':False})
 lock_backtest(bt,live,'1.1')
 assert live.model_dump()==dump
 assert not any(bt.metadata.values())


def test_database_resolver_never_queries_current_pointers_plans_or_learning(tmp_path,monkeypatch):
 import asyncio
 import modules.data.historical_backtests as storage
 class Db:
  def __init__(self):self.queries=[]
  async def fetch(self,sql,*args):self.queries.append(sql);return []
 db=Db()
 monkeypatch.setattr('modules.analysis.historical_packages.discover_packages',lambda *args:[])
 bt=asyncio.run(storage.resolve_historical_snapshot('TRU.JO',date(2022,9,1),db=db))
 sql=' '.join(db.queries).lower()
 assert 'stock_analysis' not in sql and 'forecast_plans' not in sql and 'learning' not in sql
 assert bt.metadata['current_report_pointer_used'] is False


def test_unknown_availability_cannot_be_rescued_by_old_period_end():
 included,excluded=resolve_evidence_as_of([
  {'metric_id':'old-period','name':'revenue','period_end':'2021-06-30','source_date':None}],date(2022,9,1))
 assert not included and excluded[0].availability==Availability.UNCERTAIN


def test_exact_equivalent_backtest_hash_supports_idempotent_reuse():
 bt=HistoricalBacktest(ticker='TRU.JO',as_of_date=date(2022,9,1),created_by='Dion')
 plan=approved_plan()
 assert backtest_input_hash(bt,plan,'1.1',['a'])==backtest_input_hash(bt,plan,'1.1',['a'])
 assert backtest_input_hash(bt,plan,'1.1',['a'])!=backtest_input_hash(bt,plan,'1.1',['b'])
