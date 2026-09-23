"""Per-ticker Yahoo price collection with immutable corrections and targeted gap repair."""
from __future__ import annotations
import asyncio
from datetime import date, timedelta, datetime, timezone
from decimal import Decimal
import json
import logging
import pandas as pd
import yfinance as yf
from core.db.engine import DBEngine
from core.utils.math import convert_yf_price_to_cents
from modules.data.ingestion_evidence import archive_document, content_hash, YFINANCE_PARSER_VERSION
from modules.data.ingestion_runs import IngestionResult
from uuid import uuid4

logger=logging.getLogger(__name__)
SOURCE="yfinance"

def missing_provider_dates(stored: set[date], provider: set[date]) -> list[date]:
    """Provider dates are the conservative trading calendar: holidays are absent."""
    return sorted(provider-stored)

def repair_candidates(stored: dict[date, tuple], provider_rows: list[dict]) -> list[dict]:
    fields=("open_price","high_price","low_price","close_price","volume")
    return [row for row in provider_rows if row["trade_date"] not in stored
            or stored[row["trade_date"]] != tuple(row[field] for field in fields)]

def request_for_ticker(last_date: date | None, today: date, *, repair=False) -> dict:
    if last_date is None:
        return {"period":"5y"}
    if repair:
        return {"start":max(last_date-timedelta(days=35),today-timedelta(days=35)),
                "end":today+timedelta(days=1)}
    return {"start":last_date,"end":today+timedelta(days=1)}

def _rows(data, ticker: str) -> list[dict]:
    if data is None or data.empty:
        return []
    if isinstance(data.columns,pd.MultiIndex):
        level=next((i for i in range(data.columns.nlevels) if ticker in data.columns.get_level_values(i)),None)
        if level is None:
            raise ValueError(f"Yahoo response omitted {ticker}")
        data=data.xs(ticker,axis=1,level=level)
    output=[]
    for ts,row in data.iterrows():
        if pd.isna(row.get("Close")):
            continue
        day=ts.date() if hasattr(ts,"date") else ts
        output.append({"ticker":ticker,"trade_date":day,
            "provider_values":{key:(None if pd.isna(row.get(key)) else str(row.get(key)))
                               for key in ("Open","High","Low","Close","Volume")},
            "open_price":convert_yf_price_to_cents(row.get("Open")),
            "high_price":convert_yf_price_to_cents(row.get("High")),
            "low_price":convert_yf_price_to_cents(row.get("Low")),
            "close_price":convert_yf_price_to_cents(row["Close"]),
            "volume":int(row["Volume"]) if not pd.isna(row.get("Volume")) else 0})
    return output

async def _persist_rows(ticker: str, rows: list[dict], *, repair=False, ingestion_run_id=None,
                        request_params=None, db=DBEngine) -> int:
    if not rows:
        return 0
    pool=await db.get_pool()
    written=0
    async with pool.acquire() as conn:
        async with conn.transaction():
            if repair:
                existing=await conn.fetch("""SELECT trade_date,open_price,high_price,low_price,close_price,volume
                    FROM daily_stock_data WHERE ticker=$1 AND trade_date BETWEEN $2 AND $3""",
                                          ticker,rows[0]["trade_date"],rows[-1]["trade_date"])
                stored={r["trade_date"]:tuple(r[field] for field in
                    ("open_price","high_price","low_price","close_price","volume")) for r in existing}
                rows=repair_candidates(stored,rows)
            for row in rows:
                body=json.dumps({"provider_values":row.get("provider_values"),
                    "normalized_values":{key:row[key] for key in
                        ("ticker","trade_date","open_price","high_price","low_price","close_price","volume")},
                    "request_params":request_params,"auto_adjust":True,
                    "provider_price_unit":"listing currency per share",
                    "stored_price_unit":"cents per share"},sort_keys=True,default=str)
                doc=await archive_document(conn,source=SOURCE,entity_key=ticker,document_type=f"ohlcv:{row['trade_date']}",
                    raw_content=body,content_type="application/json",parser_version=YFINANCE_PARSER_VERSION,
                    source_url=f"https://finance.yahoo.com/quote/{ticker}/history/",
                    source_date=row["trade_date"],effective_date=row["trade_date"],ingestion_run_id=ingestion_run_id)
                result=await conn.execute("""INSERT INTO price_observations
                    (observation_id,source_document_id,ticker,trade_date,source,open_price,high_price,
                     low_price,close_price,volume,content_hash) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                    ON CONFLICT(ticker,trade_date,source,content_hash) DO NOTHING""",
                    uuid4(),doc,ticker,row["trade_date"],SOURCE,row["open_price"],row["high_price"],
                    row["low_price"],row["close_price"],row["volume"],content_hash(body))
                if result.endswith("1"):
                    await conn.execute("""INSERT INTO daily_stock_data
                        (ticker,trade_date,open_price,high_price,low_price,close_price,volume)
                        VALUES($1,$2,$3,$4,$5,$6,$7)
                        ON CONFLICT(ticker,trade_date) DO UPDATE SET
                        open_price=EXCLUDED.open_price,high_price=EXCLUDED.high_price,
                        low_price=EXCLUDED.low_price,close_price=EXCLUDED.close_price,volume=EXCLUDED.volume""",
                        ticker,row["trade_date"],row["open_price"],row["high_price"],
                        row["low_price"],row["close_price"],row["volume"])
                    written+=1
    return written

async def run_price_update(*, repair=False, ingestion_run_id=None, db=DBEngine) -> IngestionResult:
    if ingestion_run_id is None:
        from modules.data.ingestion_runs import run_claimed
        return await run_claimed(SOURCE,"manual_price_repair" if repair else "manual_price_update",
            "manual:"+uuid4().hex,date.today(),
            lambda run: run_price_update(repair=repair,ingestion_run_id=run["id"],db=db),db=db)
    rows=await db.fetch("""SELECT s.ticker,max(d.trade_date) AS last_date FROM stock_details s
        LEFT JOIN daily_stock_data d ON d.ticker=s.ticker WHERE s.ticker!='ZAR_CASH'
        GROUP BY s.ticker ORDER BY s.ticker""")
    fetched=written=failed=0
    today=date.today()
    for item in rows:
        ticker=item["ticker"]
        try:
            params=request_for_ticker(item["last_date"],today,repair=repair)
            data=await asyncio.to_thread(yf.download,ticker,auto_adjust=True,progress=False,**params)
            parsed=_rows(data,ticker)
            if not parsed:
                raise RuntimeError("Yahoo returned no rows")
            fetched+=len(parsed)
            written+=await _persist_rows(ticker,parsed,repair=repair,ingestion_run_id=ingestion_run_id,
                                         request_params=params,db=db)
        except Exception:
            logger.exception("price ingestion failed ticker=%s repair=%s",ticker,repair)
            failed+=1
    if failed:
        return IngestionResult.failure("price_source_or_database_failure",f"{failed} tickers failed",
            fetched=fetched,written=written)
    return IngestionResult.success(fetched,written)
