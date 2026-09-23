"""Immutable raw documents and atomic source-observation projections."""
from __future__ import annotations
from datetime import date, datetime, timezone
from decimal import Decimal
from datetime import timedelta
from dateutil.relativedelta import relativedelta
from hashlib import sha256
from uuid import UUID, uuid4
import json
from core.db.engine import DBEngine
from modules.data.parsers import parse_multi_year_share_statistics, parse_multi_year_ratios

SHAREDATA_PARSER_VERSION = "sharedata_fundamentals_v2"
MONEYWEB_PARSER_VERSION = "moneyweb_sens_v1"
TE_COMMODITY_PARSER_VERSION = "tradingeconomics_commodity_v2"
TE_FX_PARSER_VERSION = "tradingeconomics_fx_v2"
YFINANCE_PARSER_VERSION = "yfinance_ohlcv_v1"
FUNDAMENTAL_UNITS = {"heps_12m_zarc":"ZARc/share","dividend_12m_zarc":"ZARc/share",
    "cash_gen_ps_zarc":"ZARc/share","nav_ps_zarc":"ZARc/share","quick_ratio":"ratio"}

def content_hash(content: str) -> str:
    return sha256(content.encode("utf-8")).hexdigest()

async def archive_document(conn, *, source: str, entity_key: str, document_type: str,
                           raw_content: str, parser_version: str, source_url: str | None = None,
                           source_date: date | None = None, effective_date: date | None = None,
                           ingestion_run_id: UUID | None = None, content_type: str = "text/html",
                           metadata: dict | None = None, fetched_at: datetime | None = None) -> UUID:
    """Reuse identical content; a changed body receives a new immutable document ID."""
    digest = content_hash(raw_content)
    ident = uuid4()
    await conn.execute("""INSERT INTO source_documents
        (id,source,entity_key,document_type,source_url,fetched_at,source_date,effective_date,
         content_hash,content_type,raw_content,ingestion_run_id,parser_version,metadata_json)
        VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14::jsonb)
        ON CONFLICT(source,entity_key,document_type,content_hash) DO NOTHING""",
        ident,source,entity_key,document_type,source_url,fetched_at or datetime.now(timezone.utc),
        source_date,effective_date,digest,content_type,raw_content,ingestion_run_id,
        parser_version,json.dumps(metadata or {},sort_keys=True))
    return await conn.fetchval("""SELECT id FROM source_documents WHERE source=$1 AND entity_key=$2
        AND document_type=$3 AND content_hash=$4""",source,entity_key,document_type,digest)

def parse_sharedata_document(document_type: str, html: str) -> list[dict]:
    if document_type == "fin_S":
        periods = parse_multi_year_share_statistics(html)
    elif document_type == "fin_R":
        periods = parse_multi_year_ratios(html)
    else:
        raise ValueError(f"Unsupported ShareData table: {document_type}")
    if not periods:
        raise ValueError(f"No financial periods parsed from {document_type}")
    observations=[]
    for p in periods:
        for metric in FUNDAMENTAL_UNITS:
            if metric not in p or p[metric] is None:
                continue
            value=Decimal(str(p[metric]))
            if not value.is_finite():
                raise ValueError(f"Non-finite {metric}")
            label=p.get("results_period_label") or ""
            months=12 if "(12m)" in label.lower() else 6 if "(6m)" in label.lower() else None
            period_start=(p["results_period_end"]-relativedelta(months=months)+timedelta(days=1)) if months else None
            observations.append({"metric":metric,"value":value,"unit":FUNDAMENTAL_UNITS[metric],
                "period_start":period_start,"period_end":p["results_period_end"],"period_label":p.get("results_period_label"),
                "release_date":p.get("results_release_date"),
                "raw_value":p.get("raw_values",{}).get(metric,str(p[metric]))})
    if not observations and document_type == "fin_S":
        raise ValueError(f"No supported financial metrics parsed from {document_type}")
    return observations

# A reparse version must be backed by registered parser code, not just a new label.
SHAREDATA_PARSERS = {SHAREDATA_PARSER_VERSION: parse_sharedata_document}

def register_sharedata_parser(version: str, parser):
    if not version or version in SHAREDATA_PARSERS:
        raise ValueError("Parser version must be new and nonempty")
    SHAREDATA_PARSERS[version] = parser

async def ingest_sharedata_tables(ticker: str, table_sets: list[dict], *, ingestion_run_id: UUID | None = None,
                                  parser_version: str = SHAREDATA_PARSER_VERSION, db=DBEngine) -> tuple[int,int]:
    """Archive fetched HTML first; observations and projection then commit atomically."""
    if parser_version not in SHAREDATA_PARSERS:
        raise ValueError("Unregistered ShareData parser version")
    parse = SHAREDATA_PARSERS[parser_version]
    pool=await db.get_pool()
    documents=[]
    # Raw evidence is its own persistence boundary. A parser failure must not
    # erase the page needed to diagnose and reprocess the failure.
    async with pool.acquire() as conn:
        async with conn.transaction():
            for set_index,tables in enumerate(table_sets):
                for table_type in ("fin_S","fin_R"):
                    html=tables.get(table_type)
                    if not html:
                        continue
                    try:
                        prepared=parse(table_type,html)
                    except ValueError:
                        prepared=None
                    doc_id=await archive_document(conn,source="sharedata",entity_key=ticker,
                        document_type=f"{table_type}:{'final' if set_index==0 else 'interim'}",
                        raw_content=html,parser_version=parser_version,
                        source_url=f"https://www.sharedata.co.za/v2/Scripts/Results.aspx?c={ticker.removesuffix('.JO')}&x=JSE",
                        source_date=max((o["release_date"] for o in prepared if o["release_date"]),default=None) if prepared else None,
                        effective_date=max((o["period_end"] for o in prepared),default=None) if prepared else None,
                        ingestion_run_id=ingestion_run_id,metadata={"table":table_type,"set_index":set_index})
                    documents.append((doc_id,table_type,html,prepared))
    if not documents:
        raise ValueError("ShareData returned no supported tables")
    fetched=written=0
    async with pool.acquire() as conn:
        async with conn.transaction():
            periods=set()
            for doc_id,table_type,html,prepared in documents:
                observations=prepared if prepared is not None else parse(table_type,html)
                fetched+=len(observations)
                observed_at=await conn.fetchval("SELECT fetched_at FROM source_documents WHERE id=$1",doc_id)
                for o in observations:
                    result=await conn.execute("""INSERT INTO fundamental_observations
                        (observation_id,source_document_id,ticker,metric,raw_value,normalized_value,unit,
                         period_start,period_end,period_label,release_date,source,observed_at,parser_version)
                        VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,'sharedata',$12,$13)
                        ON CONFLICT(source_document_id,ticker,metric,period_end,parser_version) DO NOTHING""",
                        uuid4(),doc_id,ticker,o["metric"],o["raw_value"],o["value"],o["unit"],
                        o["period_start"],o["period_end"],o["period_label"],o["release_date"],observed_at,parser_version)
                    written+=int(result.endswith("1"))
                    periods.add(o["period_end"])
            for period in periods:
                await project_fundamental_period(conn,ticker,period)
    return fetched,written

async def project_fundamental_period(conn,ticker: str,period: date) -> None:
    rows=await conn.fetch("""SELECT c.metric,c.normalized_value,c.period_label,c.release_date,
        c.source_document_id,c.parser_version,c.observed_at FROM canonical_fundamental_observations c
        WHERE c.ticker=$1 AND c.period_end=$2""",ticker,period)
    if not rows:
        return
    by={r["metric"]:r for r in rows}
    newest=max(rows,key=lambda r:(r["release_date"] or date.min,r["observed_at"]))
    vals=[by[m]["normalized_value"] if m in by else None for m in FUNDAMENTAL_UNITS]
    # Earlier parser versions inherited today's day number for Month YYYY.
    # Reuse that month's compatibility row rather than creating a second FY row.
    legacy_id=await conn.fetchval("""SELECT id FROM raw_stock_valuations
        WHERE ticker=$1 AND date_trunc('month',results_period_end)=date_trunc('month',$2::date)
        ORDER BY (results_period_end=$2) DESC,created_at DESC LIMIT 1 FOR UPDATE""",ticker,period)
    if legacy_id is not None:
        await conn.execute("""UPDATE raw_stock_valuations SET results_period_end=$2
            WHERE id=$1 AND results_period_end<>$2 AND NOT EXISTS
                (SELECT 1 FROM raw_stock_valuations WHERE ticker=$3 AND results_period_end=$2)""",
                legacy_id,period,ticker)
    await conn.execute("""INSERT INTO raw_stock_valuations
        (ticker,results_period_end,results_period_label,results_release_date,heps_12m_zarc,
         dividend_12m_zarc,cash_gen_ps_zarc,nav_ps_zarc,quick_ratio,source,
         source_document_id,parser_version,observed_at)
        VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,'sharedata',$10,$11,$12)
        ON CONFLICT(ticker,results_period_end) DO UPDATE SET
          results_period_label=COALESCE(EXCLUDED.results_period_label,raw_stock_valuations.results_period_label),
          results_release_date=COALESCE(EXCLUDED.results_release_date,raw_stock_valuations.results_release_date),
          heps_12m_zarc=COALESCE(EXCLUDED.heps_12m_zarc,raw_stock_valuations.heps_12m_zarc),
          dividend_12m_zarc=COALESCE(EXCLUDED.dividend_12m_zarc,raw_stock_valuations.dividend_12m_zarc),
          cash_gen_ps_zarc=COALESCE(EXCLUDED.cash_gen_ps_zarc,raw_stock_valuations.cash_gen_ps_zarc),
          nav_ps_zarc=COALESCE(EXCLUDED.nav_ps_zarc,raw_stock_valuations.nav_ps_zarc),
          quick_ratio=COALESCE(EXCLUDED.quick_ratio,raw_stock_valuations.quick_ratio),
          source_document_id=EXCLUDED.source_document_id,parser_version=EXCLUDED.parser_version,
          observed_at=EXCLUDED.observed_at""",ticker,period,newest["period_label"],newest["release_date"],
        *vals,newest["source_document_id"],newest["parser_version"],newest["observed_at"])

async def reparse_sharedata_document(document_id: UUID, *, parser_version: str, db=DBEngine) -> int:
    """Reparse archived HTML into new versioned observations; never edit old rows."""
    if parser_version not in SHAREDATA_PARSERS:
        raise ValueError("Unregistered ShareData parser version")
    parse = SHAREDATA_PARSERS[parser_version]
    pool=await db.get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            doc=await conn.fetchrow("SELECT * FROM source_documents WHERE id=$1 FOR SHARE",document_id)
            if not doc or doc["source"]!="sharedata":
                raise ValueError("ShareData source document not found")
            table_type=doc["document_type"].split(":",1)[0]
            observations=parse(table_type,doc["raw_content"])
            written=0
            for o in observations:
                result=await conn.execute("""INSERT INTO fundamental_observations
                    (observation_id,source_document_id,ticker,metric,raw_value,normalized_value,unit,
                     period_start,period_end,period_label,release_date,source,observed_at,parser_version)
                    VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,'sharedata',$12,$13)
                    ON CONFLICT(source_document_id,ticker,metric,period_end,parser_version) DO NOTHING""",
                    uuid4(),document_id,doc["entity_key"],o["metric"],o["raw_value"],o["value"],o["unit"],
                    o["period_start"],o["period_end"],o["period_label"],o["release_date"],doc["fetched_at"],parser_version)
                written+=int(result.endswith("1"))
            for period in {o["period_end"] for o in observations}:
                await project_fundamental_period(conn,doc["entity_key"],period)
            return written


async def archive_market_page(kind: str, instrument: str, html: str, *, url: str,
                              ingestion_run_id: UUID | None = None, db=DBEngine) -> UUID:
    if not html:
        raise ValueError("Empty market page cannot be archived")
    pool=await db.get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            return await archive_document(conn,source="TradingEconomics",entity_key=instrument,
                document_type=f"{kind}_page",raw_content=html,source_url=url,
                parser_version=TE_COMMODITY_PARSER_VERSION if kind=="commodity" else TE_FX_PARSER_VERSION,
                ingestion_run_id=ingestion_run_id,metadata={"instrument":instrument})

async def ingest_tradingeconomics_row(kind: str, row: dict, raw_html: str,
                                      *, ingestion_run_id: UUID | None = None,
                                      source_document_id: UUID | None = None, db=DBEngine) -> bool:
    """Archive page, retain immutable parsed observation, update existing market projection."""
    if kind not in {"commodity","fx"} or not raw_html:
        raise ValueError("Market kind and raw page required")
    instrument=row["symbol"] if kind=="commodity" else row["pair"]
    value=Decimal(str(row["price"] if kind=="commodity" else row["rate"]))
    if not value.is_finite() or value<=0:
        raise ValueError("Positive finite market value required")
    timestamp=row.get("as_of_ts")
    source_time_key=timestamp.isoformat() if timestamp else f"date:{date.today().isoformat()}"
    # TE's table does not state its time zone. Preserve the displayed time in
    # metadata and mark the timezone assumption; do not claim verified UTC.
    if timestamp and timestamp.tzinfo is None:
        timestamp=timestamp.replace(tzinfo=timezone.utc)
    observed_at=datetime.now(timezone.utc)
    parsed=json.dumps({"kind":kind,"instrument":instrument,"source_time_key":source_time_key,
        "value":str(value),"unit":row.get("unit"),"currency":row.get("currency")},sort_keys=True)
    digest=content_hash(parsed)
    pool=await db.get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            doc=source_document_id or await archive_document(conn,source="TradingEconomics",entity_key=instrument,
                document_type=f"{kind}_page",raw_content=raw_html,source_url=row.get("url"),
                source_date=timestamp.date() if timestamp else None,
                parser_version=TE_COMMODITY_PARSER_VERSION if kind=="commodity" else TE_FX_PARSER_VERSION,
                ingestion_run_id=ingestion_run_id,metadata={"displayed_time":source_time_key,
                    "timezone_verified":False,"instrument":instrument})
            result=await conn.execute("""INSERT INTO market_observations
                (observation_id,source_document_id,kind,instrument,source_timestamp,source_time_key,
                 observed_at,source,value,currency,unit,source_url,content_hash,parser_version)
                VALUES($1,$2,$3,$4,$5,$6,$7,'TradingEconomics',$8,$9,$10,$11,$12,$13)
                ON CONFLICT(kind,instrument,source,source_time_key,content_hash) DO NOTHING""",
                uuid4(),doc,kind,instrument,timestamp,source_time_key,observed_at,value,
                row.get("currency") if kind=="commodity" else row["pair"][3:],
                row.get("unit") if kind=="commodity" else f"{row['pair'][:3]}/{row['pair'][3:]}",
                row.get("url"),digest,TE_COMMODITY_PARSER_VERSION if kind=="commodity" else TE_FX_PARSER_VERSION)
            if not result.endswith("1"):
                return False
            if kind=="commodity":
                existing=await conn.fetchval("""SELECT id FROM commodity_prices WHERE symbol=$1
                    AND source='TradingEconomics' AND (as_of_ts IS NOT DISTINCT FROM $2)
                    ORDER BY collected_ts DESC LIMIT 1 FOR UPDATE""",instrument,timestamp)
                if existing:
                    await conn.execute("""UPDATE commodity_prices SET commodity=$2,price=$3,unit=$4,
                        currency=$5,collected_ts=$6,url=$7,quality=$8,notes=$9 WHERE id=$1""",
                        existing,row["commodity"],value,row["unit"],row["currency"],observed_at,
                        row.get("url"),row.get("quality"),row.get("notes"))
                else:
                    await conn.execute("""INSERT INTO commodity_prices
                        (symbol,commodity,price,unit,currency,as_of_ts,collected_ts,source,url,quality,notes)
                        VALUES($1,$2,$3,$4,$5,$6,$7,'TradingEconomics',$8,$9,$10)""",
                        instrument,row["commodity"],value,row["unit"],row["currency"],timestamp,
                        observed_at,row.get("url"),row.get("quality"),row.get("notes"))
            else:
                existing=await conn.fetchval("""SELECT id FROM fx_rates WHERE pair=$1
                    AND source='TradingEconomics' AND (as_of_ts IS NOT DISTINCT FROM $2)
                    ORDER BY collected_ts DESC LIMIT 1 FOR UPDATE""",instrument,timestamp)
                if existing:
                    await conn.execute("""UPDATE fx_rates SET rate=$2,collected_ts=$3,url=$4,notes=$5 WHERE id=$1""",
                        existing,value,observed_at,row.get("url"),row.get("notes"))
                else:
                    await conn.execute("""INSERT INTO fx_rates(pair,rate,as_of_ts,collected_ts,source,url,notes)
                        VALUES($1,$2,$3,$4,'TradingEconomics',$5,$6)""",
                        instrument,value,timestamp,observed_at,row.get("url"),row.get("notes"))
            return True
