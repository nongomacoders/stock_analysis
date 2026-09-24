"""Controlled, provenance-backed yfinance historical price imports."""
from __future__ import annotations
import asyncio,json
from dataclasses import dataclass,field
from datetime import date,datetime,timedelta,timezone
from decimal import Decimal
from hashlib import sha256
from uuid import uuid4
import pandas as pd
import yfinance as yf
from core.db.engine import DBEngine
from modules.data.ingestion_evidence import archive_document

PROVIDER='yfinance'; PRICE_UNIT='cents_per_share'

def provider_symbol(ticker:str)->str:
    """Reuse the current Yahoo convention: application JSE tickers retain .JO."""
    value=ticker.strip().upper()
    if not value: raise ValueError('Ticker is required')
    return value

@dataclass(frozen=True)
class HistoricalPriceRow:
    trade_date:date; raw_close:Decimal; adjusted_close:Decimal|None
    open_price:Decimal|None=None; high_price:Decimal|None=None; low_price:Decimal|None=None
    volume:int=0

@dataclass
class HistoricalPricePreview:
    ticker:str; provider_symbol:str; start:date; end:date; retrieved_at:datetime
    currency:str; rows:list[HistoricalPriceRow]; adjusted_available:bool
    provider_currency:str='ZAc'
    settings:dict=field(default_factory=lambda:{'auto_adjust':False,'actions':False,'progress':False})
    warnings:list[str]=field(default_factory=list)

def _decimal(value):
    if value is None or pd.isna(value): return None
    return Decimal(str(value))

def parse_download(data,*,ticker,start,end,currency,retrieved_at=None):
    symbol=provider_symbol(ticker)
    if currency not in {'ZAc','ZAR'} or not symbol.endswith('.JO'):
        raise ValueError(f'Unresolved price currency/unit for {symbol}: {currency or "unknown"}')
    if data is None or data.empty: raise ValueError('yfinance returned no historical prices')
    if isinstance(data.columns,pd.MultiIndex):
        level=next((i for i in range(data.columns.nlevels) if symbol in data.columns.get_level_values(i)),None)
        if level is None: raise ValueError(f'yfinance response omitted expected symbol {symbol}')
        data=data.xs(symbol,axis=1,level=level)
    rows=[]; seen=set()
    for stamp,item in data.sort_index().iterrows():
        day=stamp.date() if hasattr(stamp,'date') else stamp
        if day in seen: raise ValueError(f'Duplicate provider date: {day}')
        seen.add(day)
        if day<start or day>end or day>date.today(): raise ValueError(f'Out-of-range provider date: {day}')
        raw=_decimal(item.get('Close'))
        if raw is None or raw<=0: raise ValueError(f'Invalid raw Close for {day}')
        adjusted=_decimal(item.get('Adj Close'))
        if adjusted is not None and adjusted<=0: raise ValueError(f'Invalid adjusted close for {day}')
        rows.append(HistoricalPriceRow(day,raw,adjusted,_decimal(item.get('Open')),
          _decimal(item.get('High')),_decimal(item.get('Low')),int(item.get('Volume') or 0)))
    if not rows: raise ValueError('yfinance returned no usable raw Close rows')
    return HistoricalPricePreview(ticker,symbol,start,end,retrieved_at or datetime.now(timezone.utc),
      'ZAR',rows,any(x.adjusted_close is not None for x in rows),provider_currency=currency)

async def download_preview(ticker,start,end,download=None,ticker_factory=None):
    if start>end or end>date.today(): raise ValueError('Invalid historical import range')
    symbol=provider_symbol(ticker); ticker_factory=ticker_factory or yf.Ticker
    info=await asyncio.to_thread(lambda:ticker_factory(symbol).fast_info)
    currency=dict(info).get('currency') if info is not None else None
    download=download or yf.download
    settings={'start':start,'end':end+timedelta(days=1),'auto_adjust':False,'actions':False,'progress':False}
    data=await asyncio.to_thread(download,symbol,**settings)
    preview=parse_download(data,ticker=ticker,start=start,end=end,currency=currency)
    preview.settings['end_exclusive']=str(end+timedelta(days=1))
    return preview

def _body(preview,row):
    return json.dumps({'provider':PROVIDER,'provider_symbol':preview.provider_symbol,
      'trade_date':str(row.trade_date),'raw_close':str(row.raw_close),
      'adjusted_close':str(row.adjusted_close) if row.adjusted_close is not None else None,
      'currency':preview.currency,'provider_currency':preview.provider_currency,'provider_price_unit':'JSE cents per share',
      'stored_price_unit':PRICE_UNIT,'settings':preview.settings},sort_keys=True)

def classify_existing(existing,row):
    if not existing:return 'insert'
    if existing.get('raw_close')==row.raw_close and existing.get('adjusted_close')==row.adjusted_close:return 'reuse'
    if existing.get('raw_close')!=row.raw_close:return 'raw_close_conflict'
    return 'adjusted_revision'

def compare_overlap(imported,reference):
    common=sorted(imported.keys() & reference.keys())
    if not common:return {'count':0,'median_difference':None,'maximum_difference':None,'suspected_unit_mismatch':False}
    differences=sorted(abs(imported[x]-reference[x]) for x in common)
    ratios=sorted(imported[x]/reference[x] for x in common if reference[x])
    median_ratio=ratios[len(ratios)//2] if ratios else Decimal('1')
    return {'count':len(common),'median_difference':differences[len(differences)//2],
      'maximum_difference':max(differences),
      'suspected_unit_mismatch':Decimal('90')<=median_ratio<=Decimal('110') or Decimal('.009')<=median_ratio<=Decimal('.011')}

async def persist_preview(preview,db=DBEngine):
    batch=uuid4(); inserted=reused=conflicted=0; warnings=list(preview.warnings)
    pool=await db.get_pool()
    async with pool.acquire() as conn:
      async with conn.transaction():
        await conn.execute("""INSERT INTO historical_price_import_batches
          (batch_id,ticker,provider,provider_symbol,requested_start,requested_end,retrieved_at,
           library_version,settings,status,rows_fetched,warnings)
          VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,'previewed',$10,$11::jsonb)""",
          batch,preview.ticker,PROVIDER,preview.provider_symbol,preview.start,preview.end,
          preview.retrieved_at,getattr(yf,'__version__',None),json.dumps(preview.settings),
          len(preview.rows),json.dumps(warnings))
        for row in preview.rows:
          body=_body(preview,row); digest=sha256(body.encode()).hexdigest()
          existing=await conn.fetchrow("""SELECT observation_id,raw_close,adjusted_close
            FROM price_observations WHERE ticker=$1 AND source=$2 AND provider_symbol=$3
            AND trade_date=$4 ORDER BY observed_at DESC LIMIT 1""",
            preview.ticker,PROVIDER,preview.provider_symbol,row.trade_date)
          state=classify_existing(dict(existing) if existing else None,row)
          if state=='reuse':
            reused+=1; continue
          conflict=state if existing else None
          if existing:
            conflicted+=1
            if conflict=='raw_close_conflict': warnings.append(f'RAW_CLOSE_CONFLICT:{row.trade_date}')
          doc=await archive_document(conn,source=PROVIDER,entity_key=preview.ticker,
            document_type=f'historical_ohlcv:{row.trade_date}',raw_content=body,
            content_type='application/json',parser_version='yfinance_historical_v1',
            source_url=f'https://finance.yahoo.com/quote/{preview.provider_symbol}/history/',
            source_date=row.trade_date,effective_date=row.trade_date,metadata={'batch_id':str(batch)})
          result=await conn.execute("""INSERT INTO price_observations
            (observation_id,source_document_id,ticker,trade_date,source,open_price,high_price,low_price,
             close_price,volume,content_hash,provider_symbol,raw_close,adjusted_close,currency,price_unit,
             price_basis,retrieved_at,import_batch_id,provider_metadata,revision_of,conflict_status)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,'raw_close',$17,$18,$19::jsonb,$20,$21)
            ON CONFLICT(ticker,trade_date,source,content_hash) DO NOTHING""",uuid4(),doc,preview.ticker,
            row.trade_date,PROVIDER,row.open_price,row.high_price,row.low_price,row.raw_close,row.volume,digest,
            preview.provider_symbol,row.raw_close,row.adjusted_close,preview.currency,PRICE_UNIT,preview.retrieved_at,
            batch,json.dumps({'settings':preview.settings}),existing['observation_id'] if existing else None,conflict)
          inserted+=int(result.endswith('1'))
        await conn.execute("""UPDATE historical_price_import_batches SET status='completed',
          rows_inserted=$2,rows_reused=$3,rows_conflicted=$4,warnings=$5::jsonb WHERE batch_id=$1""",
          batch,inserted,reused,conflicted,json.dumps(warnings))
    return {'batch_id':batch,'fetched':len(preview.rows),'inserted':inserted,'reused':reused,
      'conflicted':conflicted,'warnings':warnings,
      'coverage':(preview.rows[0].trade_date,preview.rows[-1].trade_date)}
