from datetime import date
from decimal import Decimal
import asyncio
import pandas as pd
import pytest
from modules.data.historical_prices import HistoricalPriceRow,classify_existing,compare_overlap,download_preview,parse_download,provider_symbol
from modules.analysis.historical_backtest import resolve_latest_market_as_of

def frame(close=5000,adjusted=4900):
    return pd.DataFrame({'Open':[4950],'High':[5050],'Low':[4900],'Close':[close],'Adj Close':[adjusted],'Volume':[100]},index=pd.to_datetime(['2025-08-29']))

def test_tru_mapping_and_raw_adjusted_distinct():
    assert provider_symbol('tru.jo')=='TRU.JO'
    p=parse_download(frame(),ticker='TRU.JO',start=date(2025,8,1),end=date(2025,8,31),currency='ZAc')
    assert p.rows[0].raw_close==Decimal('5000') and p.rows[0].adjusted_close==Decimal('4900')
    assert p.currency=='ZAR' and p.adjusted_available

def test_download_requests_unadjusted_data():
    calls={}
    def download(symbol,**kwargs):calls.update(symbol=symbol,**kwargs);return frame()
    class Ticker:
        def __init__(self,symbol):self.fast_info={'currency':'ZAc'}
    p=asyncio.run(download_preview('TRU.JO',date(2025,8,1),date(2025,8,31),download,Ticker))
    assert calls['symbol']=='TRU.JO' and calls['auto_adjust'] is False and calls['actions'] is False
    assert p.settings['end_exclusive']=='2025-09-01'

@pytest.mark.parametrize('currency',['USD',None])
def test_currency_ambiguity_fails_closed(currency):
    with pytest.raises(ValueError,match='currency/unit'):
        parse_download(frame(),ticker='TRU.JO',start=date(2025,8,1),end=date(2025,8,31),currency=currency)

@pytest.mark.parametrize('close',[0,-1,None])
def test_bad_raw_close_rejected(close):
    with pytest.raises(ValueError,match='raw Close'):
        parse_download(frame(close=close),ticker='TRU.JO',start=date(2025,8,1),end=date(2025,8,31),currency='ZAc')

def test_empty_rejected():
    with pytest.raises(ValueError,match='no historical'):
        parse_download(pd.DataFrame(),ticker='TRU.JO',start=date(2025,8,1),end=date(2025,8,31),currency='ZAc')

def test_idempotency_and_revisions():
    row=HistoricalPriceRow(date(2025,8,29),Decimal('5000'),Decimal('4900'))
    assert classify_existing(None,row)=='insert'
    assert classify_existing({'raw_close':Decimal('5000'),'adjusted_close':Decimal('4900')},row)=='reuse'
    assert classify_existing({'raw_close':Decimal('5000'),'adjusted_close':Decimal('4800')},row)=='adjusted_revision'
    assert classify_existing({'raw_close':Decimal('5100'),'adjusted_close':Decimal('4900')},row)=='raw_close_conflict'

def test_overlap_detects_100x_mismatch():
    result=compare_overlap({date(2025,1,1):Decimal('5000')},{date(2025,1,1):Decimal('50')})
    assert result['suspected_unit_mismatch'] and result['maximum_difference']==Decimal('4950')

def test_weekend_fallback_no_future_leakage_and_basis():
    rows=[{'id':'fri','kind':'share_price','ticker':'TRU.JO','trade_date':date(2025,8,29),'value':5000,'source':'yfinance','price_basis':'raw_close','provider_symbol':'TRU.JO'},{'id':'mon','kind':'share_price','ticker':'TRU.JO','trade_date':date(2025,9,1),'value':5100,'source':'yfinance','price_basis':'raw_close'}]
    out=resolve_latest_market_as_of(rows,date(2025,8,31))
    assert len(out)==1 and out[0].snapshot_id=='fri' and out[0].lag_days==2 and out[0].price_basis=='raw_close'

def test_duplicate_dates_rejected():
    with pytest.raises(ValueError,match='Duplicate'):
        parse_download(pd.concat([frame(),frame()]),ticker='TRU.JO',start=date(2025,8,1),end=date(2025,8,31),currency='ZAc')
