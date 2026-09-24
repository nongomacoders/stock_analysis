"""Deterministic Historical Backtest contracts and leakage controls."""
from __future__ import annotations
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4
import json
from pydantic import BaseModel, Field, model_validator

class Availability(str,Enum):
    AVAILABLE='available_at_time'
    UNAVAILABLE='not_available_at_time'
    UNCERTAIN='uncertain'

class BacktestStatus(str,Enum):
    DRAFT='draft'; LOCKED='locked'; COMPLETED='completed'; FAILED='failed'

class HistoricalEvidence(BaseModel):
    evidence_id:str
    kind:str
    available_date:date|None=None
    period_end:date|None=None
    source_id:str|None=None
    report_id:UUID|None=None
    payload:dict[str,Any]=Field(default_factory=dict)
    availability:Availability=Availability.UNCERTAIN
    reason:str|None=None

class HistoricalMarketObservation(BaseModel):
    snapshot_id:str
    kind:str
    instrument:str
    observation_date:date
    value:Decimal
    currency:str|None=None
    unit:str|None=None
    source:str
    source_id:str|None=None
    lag_days:int=Field(ge=0)

class HistoricalBacktest(BaseModel):
    backtest_id:UUID=Field(default_factory=uuid4)
    ticker:str
    as_of_date:date
    reporting_period_label:str|None=None
    reporting_period_end:date|None=None
    status:BacktestStatus=BacktestStatus.DRAFT
    evidence_snapshot:list[HistoricalEvidence]=Field(default_factory=list)
    market_snapshot:list[HistoricalMarketObservation]=Field(default_factory=list)
    source_report_ids:list[UUID]=Field(default_factory=list)
    created_by:str
    created_at:datetime=Field(default_factory=lambda:datetime.now(timezone.utc))
    locked_at:datetime|None=None
    input_hash:str=''
    metadata:dict[str,Any]=Field(default_factory=dict)
    @model_validator(mode='after')
    def locked_is_frozen(self):
        if self.status in {BacktestStatus.LOCKED,BacktestStatus.COMPLETED} and not self.locked_at:
            raise ValueError('Locked historical backtest requires locked_at')
        return self

SHARE_PRIORITY=('forecast_diluted_shares','weighted_average_diluted_shares',
                'external_shares_ex_treasury','issued_shares_current',
                'weighted_average_basic_shares')

def _iso(value):
    if isinstance(value,date): return value
    if not value:return None
    try:return date.fromisoformat(str(value)[:10])
    except ValueError:return None

def evidence_availability(item,as_of_date:date):
    available=_iso(item.get('available_date') or item.get('source_date') or item.get('published_at'))
    if available is None:return Availability.UNCERTAIN,'Availability date unknown'
    if available>as_of_date:return Availability.UNAVAILABLE,f'Available {available} after cutoff {as_of_date}'
    return Availability.AVAILABLE,None

def resolve_evidence_as_of(items:list[dict],as_of_date:date):
    """Fail closed: unknown and later evidence are retained in audit output but excluded."""
    eligible=[]; excluded=[]
    for raw in items:
        state,reason=evidence_availability(raw,as_of_date)
        item=HistoricalEvidence(
            evidence_id=str(raw.get('metric_id') or raw.get('source_document_id') or raw.get('source_id') or raw.get('id')),
            kind=str(raw.get('kind') or raw.get('document_role') or raw.get('name') or 'evidence'),
            available_date=_iso(raw.get('available_date') or raw.get('source_date') or raw.get('published_at')),
            period_end=_iso(raw.get('period_end')),source_id=raw.get('source_id'),
            report_id=raw.get('report_id'),payload=dict(raw),availability=state,reason=reason)
        (eligible if state==Availability.AVAILABLE else excluded).append(item)
    return eligible,excluded

def resolve_latest_market_as_of(items:list[dict],as_of_date:date):
    """Select the latest observation <= cutoff for each kind/instrument; never use future rows."""
    selected={}
    for row in items:
        observed=_iso(row.get('observation_date') or row.get('trade_date') or row.get('source_timestamp') or row.get('as_of_ts'))
        if observed is None or observed>as_of_date:continue
        key=(str(row.get('kind') or 'price'),str(row.get('instrument') or row.get('ticker') or row.get('symbol') or ''))
        prior=selected.get(key)
        if prior is None or observed>prior[0]:selected[key]=(observed,row)
    out=[]
    for (kind,instrument),(observed,row) in sorted(selected.items()):
        value=row.get('value',row.get('close_price',row.get('close')))
        if value is None:continue
        out.append(HistoricalMarketObservation(snapshot_id=str(row.get('observation_id') or row.get('id') or f'{kind}:{instrument}:{observed}'),kind=kind,instrument=instrument,observation_date=observed,value=Decimal(str(value)),currency=row.get('currency'),unit=row.get('unit'),source=str(row.get('source') or 'unknown'),source_id=str(row.get('source_document_id') or '') or None,lag_days=(as_of_date-observed).days))
    return out

def select_historical_share_count(evidence:list[HistoricalEvidence]):
    eligible=[x for x in evidence if x.availability==Availability.AVAILABLE and x.kind in SHARE_PRIORITY]
    for name in SHARE_PRIORITY:
        matches=[x for x in eligible if x.kind==name]
        if matches:return max(matches,key=lambda x:(x.available_date or date.min,x.period_end or date.min))
    return None

def canonical_hash(value):
    def default(x):
        if isinstance(x,(date,datetime,UUID,Decimal,Enum)):return str(x.value if isinstance(x,Enum) else x)
        raise TypeError(type(x).__name__)
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),default=default).encode()).hexdigest()

def backtest_input_hash(backtest:HistoricalBacktest,forecast_plan=None,engine_version=None,mapped_input_ids=()):
    return canonical_hash({'ticker':backtest.ticker,'as_of_date':backtest.as_of_date,
      'evidence_ids':sorted(x.evidence_id for x in backtest.evidence_snapshot if x.availability==Availability.AVAILABLE),
      'market_ids':sorted(x.snapshot_id for x in backtest.market_snapshot),
      'forecast_plan':forecast_plan.model_dump(mode='json') if hasattr(forecast_plan,'model_dump') else forecast_plan,
      'engine_version':engine_version,'mapped_input_ids':sorted(map(str,mapped_input_ids))})

def lock_backtest(backtest:HistoricalBacktest,forecast_plan,engine_version,mapped_input_ids=()):
    if backtest.status!=BacktestStatus.DRAFT:raise ValueError('Only a draft backtest can be locked')
    if getattr(forecast_plan,'status',None).value!='approved':raise ValueError('Historical ForecastPlan must be approved before lock')
    digest=backtest_input_hash(backtest,forecast_plan,engine_version,mapped_input_ids)
    return backtest.model_copy(update={'status':BacktestStatus.LOCKED,'locked_at':datetime.now(timezone.utc),'input_hash':digest})

def require_reveal_allowed(backtest:HistoricalBacktest):
    if backtest.status not in {BacktestStatus.LOCKED,BacktestStatus.COMPLETED}:
        raise ValueError('Reveal next-period actuals requires a locked historical plan and valuation')

def _decimal(value):
    try:return Decimal(str(value)) if value is not None else None
    except InvalidOperation:return None

def compare_forecast_actuals(forecasts:list[dict],actuals:list[dict]):
    actual_by={(x.get('name'),x.get('operation_segment')):x for x in actuals}
    out=[]
    for f in forecasts:
        a=actual_by.get((f.get('field') or f.get('name'),f.get('operation_segment')))
        fv=_decimal(f.get('value')); av=_decimal(a.get('value') if a else None)
        if a is None or fv is None or av is None:continue
        unit=f.get('unit') or a.get('unit'); delta=av-fv
        row={'field':f.get('field') or f.get('name'),'operation_segment':f.get('operation_segment'),'forecast':str(fv),'actual':str(av),'unit':unit,'forecast_id':str(f.get('assumption_id') or ''),'actual_id':str(a.get('metric_id') or '')}
        if unit=='percentage':row['error_bps']=str(delta*100)
        elif fv!=0:row['error_pct']=str(delta/abs(fv)*100)
        out.append(row)
    return out

def valuation_performance(fair_value,market_price,subsequent_prices:dict[str,Any]|None=None):
    fair=_decimal(fair_value); market=_decimal(market_price)
    result={'historical_fair_value':str(fair) if fair is not None else None,'historical_market_price':str(market) if market is not None else None,'price_returns':{}}
    if fair is not None and market not in (None,Decimal(0)):result['implied_upside_downside_pct']=str((fair-market)/market*100)
    for horizon,value in (subsequent_prices or {}).items():
        later=_decimal(value)
        if later is not None and market not in (None,Decimal(0)):result['price_returns'][horizon]=str((later-market)/market*100)
    result['return_basis']='price_return_excluding_dividends'
    return result

def transition_key(ticker,from_period,to_period):return f'{ticker}:{from_period}->{to_period}'
