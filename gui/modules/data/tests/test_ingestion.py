"""Ingestion regressions. Optional DB tests always roll back their migration/data."""
import asyncio
import os
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from modules.market_agent.prices import request_for_ticker, missing_provider_dates, repair_candidates
from modules.market_agent.agent import quarter_hour_key
from modules.data.parse_utils import parse_period_label
from modules.data.ingestion_evidence import (content_hash,parse_sharedata_document,
    ingest_sharedata_tables,reparse_sharedata_document,register_sharedata_parser)
from modules.data.ingestion_runs import (IngestionResult,claim_run,finish_run,run_claimed,
    classify_error)

def table(nav=1000,heps=500):
    return f"""<table id='fin_S'><tr><th>Metric</th><th>Jun 2026Final (12m)25 Aug 2026</th></tr>
    <tr><td>12 Month HEPS</td><td>{heps}</td></tr>
    <tr><td>Net Asset Value Per Share (ZARc)</td><td>{nav}</td></tr></table>"""

def ratios(value=1.2):
    return f"""<table id='fin_R'><tr><th>Metric</th><th>Jun 2026Final (12m)25 Aug 2026</th></tr>
    <tr><td>Quick Ratio</td><td>{value}</td></tr></table>"""

def test_per_ticker_watermarks_and_conservative_gap_calendar():
    today=date(2026,9,22)
    assert request_for_ticker(None,today)=={"period":"5y"}
    assert request_for_ticker(date(2026,9,21),today)["start"]==date(2026,9,21)
    # Ticker A being current does not advance ticker B's watermark.
    assert request_for_ticker(date(2026,9,10),today)["start"]==date(2026,9,10)
    assert request_for_ticker(date(2026,9,15),today,repair=True)["start"]==date(2026,8,18)
    # Provider dates are the calendar: a weekend/holiday absent from provider is not a gap.
    stored={date(2026,9,18),date(2026,9,22)}
    provider=stored|{date(2026,9,21)}
    assert missing_provider_dates(stored,provider)==[date(2026,9,21)]
    assert date(2026,9,19) not in missing_provider_dates(stored,provider)
    assert date(2026,9,24) not in missing_provider_dates(stored,provider)  # SA holiday absent from provider
    assert len(repair_candidates({date(2026,9,18):(1,1,1,1,1)},
        [{"trade_date":date(2026,9,18),"open_price":1,"high_price":1,
          "low_price":1,"close_price":2,"volume":1}]))==1
    assert quarter_hour_key(datetime(2026,9,22,7,29))=="all:0715"

def test_sens_collection_precedes_slow_market_jobs(monkeypatch):
    import modules.market_agent.agent as agent
    events=[]
    async def claim(source, job, entity, day, worker, **kwargs):
        events.append(job)
    async def retries(now):
        events.append("retries")
    async def analysis():
        events.append("analysis")
    monkeypatch.setattr(agent,"run_claimed",claim)
    monkeypatch.setattr(agent,"retry_due_jobs",retries)
    monkeypatch.setattr(agent,"run_sens_analysis_check",analysis)
    asyncio.run(agent.run_due_jobs(datetime(2026,9,22,10,0,tzinfo=timezone.utc)))
    assert events[0:3]==["sens_collection","retries","price_update"]
    assert events[-1]=="analysis"

def test_parser_month_end_hash_and_malformed_content():
    assert parse_period_label("Jun 2026Final (12m)25 Aug 2026")==date(2026,6,30)
    assert content_hash(table())==content_hash(table())
    parsed=parse_sharedata_document("fin_S",table())
    assert {(p["metric"],p["value"]) for p in parsed}=={("heps_12m_zarc",500),("nav_ps_zarc",1000)}
    with pytest.raises(ValueError): parse_sharedata_document("fin_S","<table></table>")

def test_retry_classification():
    assert classify_error(TimeoutError())[0]=="transient_network"
    assert classify_error(ValueError("bad parser"))==("validation_failure",False)
    assert IngestionResult.failure("source_no_data","empty").retryable

class Pool:
    def __init__(self,conn): self.conn=conn
    def acquire(self): return Acquire(self.conn)
class Acquire:
    def __init__(self,conn): self.conn=conn
    async def __aenter__(self): return self.conn
    async def __aexit__(self,*args): pass
class Adapter:
    def __init__(self,conn): self.conn=conn
    async def get_pool(self): return Pool(self.conn)
    async def fetch(self,q,*args): return await self.conn.fetch(q,*args)
    async def execute(self,q,*args): return await self.conn.execute(q,*args)

async def with_rollback(callback):
    from core.db.engine import DBEngine
    pool=await DBEngine.get_pool()
    try:
        async with pool.acquire() as conn:
            outer=conn.transaction();await outer.start()
            try:
                sql=(Path(__file__).resolve().parents[3]/'core/db/migrations/add_ingestion_provenance.sql').read_text(encoding='utf-8-sig')
                await conn.execute(sql)
                dismissal_sql=(Path(__file__).resolve().parents[3]/'core/db/migrations/add_sens_action_dismissals.sql').read_text(encoding='utf-8')
                await conn.execute(dismissal_sql)
                result=await callback(Adapter(conn))
            finally:
                await outer.rollback()
        return result
    finally:
        await DBEngine.close()

@pytest.mark.skipif(os.getenv("RUN_DB_INGESTION_TESTS")!="1",reason="requires local PostgreSQL; all changes roll back")
def test_persistent_restart_retry_duplicate_claim_and_success():
    async def scenario(db):
        start=datetime(2026,9,22,7,0,tzinfo=timezone.utc)
        r=await claim_run("test","daily","entity",start.date(),now=start,db=db)
        assert r["attempt_no"]==1
        assert await claim_run("test","daily","entity",start.date(),now=start,db=db) is None
        await finish_run(r,IngestionResult.failure("transient_network","temporary"),now=start,db=db)
        assert await claim_run("test","daily","entity",start.date(),now=start+timedelta(minutes=14),db=db) is None
        second=await claim_run("test","daily","entity",start.date(),now=start+timedelta(minutes=15),db=db)
        assert second["attempt_no"]==2
        await finish_run(second,IngestionResult.success(1,1),now=start+timedelta(minutes=15),db=db)
        assert await claim_run("test","daily","entity",start.date(),now=start+timedelta(hours=2),db=db) is None
        statuses=await db.fetch("SELECT status FROM ingestion_runs WHERE source='test' ORDER BY attempt_no")
        assert [x["status"] for x in statuses]==["retry_scheduled","success"]
    asyncio.run(with_rollback(scenario))

@pytest.mark.skipif(os.getenv("RUN_DB_INGESTION_TESTS")!="1",reason="requires local PostgreSQL; all changes roll back")
def test_sharedata_duplicate_correction_reparse_and_atomic_failure():
    async def scenario(db):
        ticker='NED.JO'
        period=date(2099,6,30)
        future=lambda html: html.replace('2026','2099')
        original=[{"fin_S":future(table()),"fin_R":future(ratios())}]
        fetched,written=await ingest_sharedata_tables(ticker,original,db=db)
        assert (fetched,written)==(3,3)
        _,written=await ingest_sharedata_tables(ticker,original,db=db)
        assert written==0
        _,written=await ingest_sharedata_tables(ticker,[{"fin_S":future(table(nav=1050)),"fin_R":future(ratios(1.3))}],db=db)
        assert written==3
        rows=await db.fetch("SELECT nav_ps_zarc,quick_ratio,heps_12m_zarc FROM raw_stock_valuations WHERE ticker=$1 AND results_period_end=$2",ticker,period)
        assert len(rows)==1 and rows[0]["nav_ps_zarc"]==1050 and rows[0]["quick_ratio"]==Decimal("1.3")
        observations=await db.fetch("SELECT metric,count(*) n FROM fundamental_observations WHERE ticker=$1 GROUP BY metric",ticker)
        assert {x["metric"]:x["n"] for x in observations}=={"heps_12m_zarc":2,"nav_ps_zarc":2,"quick_ratio":2}
        revisions=await db.fetch("SELECT metric,normalized_value,value_changed FROM fundamental_revision_history WHERE ticker=$1",ticker)
        assert any(x["metric"]=="nav_ps_zarc" and x["normalized_value"]==1050 and x["value_changed"] for x in revisions)
        assert not any(x["metric"]=="heps_12m_zarc" and x["value_changed"] for x in revisions)
        canonical=await db.fetch("SELECT metric,normalized_value FROM canonical_fundamental_observations WHERE ticker=$1",ticker)
        assert {x["metric"]:x["normalized_value"] for x in canonical}["nav_ps_zarc"]==1050
        doc=await db.fetch("SELECT id FROM source_documents WHERE source='sharedata' AND entity_key=$1 AND document_type='fin_S:final' ORDER BY fetched_at LIMIT 1",ticker)
        with pytest.raises(ValueError):
            await reparse_sharedata_document(doc[0]["id"],parser_version="unregistered_v3",db=db)
        register_sharedata_parser("test_sharedata_v3",parse_sharedata_document)
        assert await reparse_sharedata_document(doc[0]["id"],parser_version="test_sharedata_v3",db=db)==2
        before=await db.fetch("SELECT count(*) n FROM source_documents WHERE entity_key=$1",ticker)
        with pytest.raises(ValueError):
            await ingest_sharedata_tables(ticker,[{"fin_S":future(table(nav=1200)),"fin_R":"<table></table>"}],db=db)
        after=await db.fetch("SELECT count(*) n FROM source_documents WHERE entity_key=$1",ticker)
        assert after[0]["n"]==before[0]["n"]+2
        unchanged=await db.fetch("SELECT nav_ps_zarc FROM raw_stock_valuations WHERE ticker=$1 AND results_period_end=$2",ticker,period)
        assert unchanged[0]["nav_ps_zarc"]==1050
    asyncio.run(with_rollback(scenario))



@pytest.mark.skipif(os.getenv("RUN_DB_INGESTION_TESTS")!="1",reason="requires local PostgreSQL; all changes roll back")
def test_sens_persists_before_ai_failure_and_reanalysis_is_append_only(monkeypatch):
    import modules.market_agent.sens as sens
    import modules.analysis.engine as ai_engine
    stamp=datetime.now(timezone.utc).replace(microsecond=0)
    body="Synthetic SENS " + uuid4().hex
    list_html=("<div class='sens-row'><a title='Visit Click a company for this listing'>NED</a>"
        f"<time datetime='{stamp.isoformat()}'></time>"
        "<a title='Go to SENS announcement' href='/synthetic'></a></div>")
    class Response:
        text=list_html
        def raise_for_status(self): pass
    monkeypatch.setattr(sens.requests,"get",lambda *a,**k: Response())
    monkeypatch.setattr(sens,"_fetch_page",lambda url:("<html><div id='sens-content'>"+body+"</div></html>",body))
    async def failed(*a,**kw): raise RuntimeError("Gemini unavailable")
    monkeypatch.setattr(ai_engine,"analyze_new_sens",failed)
    async def scenario(db):
        first=await sens.run_sens_check(db=db)
        second=await sens.run_sens_check(db=db)
        assert first.records_written==1 and second.records_written==0
        rows=await db.fetch("SELECT sens_id,source_document_id FROM sens WHERE content=$1",body)
        assert len(rows)==1 and rows[0]["source_document_id"] is not None
        sid=rows[0]["sens_id"]
        outcome=await sens.run_sens_analysis_check(sens_id=sid,db=db)
        assert outcome.status=="failed"
        assert (await db.fetch("SELECT count(*) n FROM sens WHERE sens_id=$1",sid))[0]["n"]==1
        assert (await db.fetch("SELECT count(*) n FROM sens_analyses WHERE sens_announcement_id=$1 AND status='failed'",sid))[0]["n"]==1
        await db.execute("UPDATE ingestion_runs SET next_retry_at=now()-interval '1 minute' WHERE job_type='sens_analysis' AND entity_key=$1",str(sid))
        async def succeeded(*a,**kw): return "Significance: Low. Synthetic analysis."
        monkeypatch.setattr(ai_engine,"analyze_new_sens",succeeded)
        outcome=await sens.run_sens_analysis_check(sens_id=sid,db=db)
        assert outcome.status=="success"
        assert (await db.fetch("SELECT count(*) n FROM sens_analyses WHERE sens_announcement_id=$1",sid))[0]["n"]==2
        assert (await db.fetch("SELECT count(*) n FROM sens WHERE sens_id=$1",sid))[0]["n"]==1
        monkeypatch.setattr(sens,"_fetch_page",lambda url:("<html>malformed</html>",None))
        bad=await sens.run_sens_check(db=db)
        assert bad.status=="failed"
        assert (await db.fetch("SELECT count(*) n FROM sens WHERE sens_id=$1",sid))[0]["n"]==1
        docs=await db.fetch("SELECT count(*) n FROM source_documents WHERE source='moneyweb_sens' AND entity_key LIKE $1", "NED.JO:%")
        assert docs[0]["n"]==2
    asyncio.run(with_rollback(scenario))

@pytest.mark.skipif(os.getenv("RUN_DB_INGESTION_TESTS")!="1",reason="requires local PostgreSQL; all changes roll back")
def test_deleted_sens_alert_stays_dismissed_after_analysis(monkeypatch):
    import modules.data.research as research
    import modules.market_agent.sens as sens
    import modules.analysis.engine as ai_engine
    from hashlib import sha256
    body="Synthetic dismissal " + uuid4().hex + " " + ("details " * 40)
    ticker="NED.JO"
    async def fake_analysis(*args,**kwargs):
        return "Significance: Low. Synthetic analysis."
    monkeypatch.setattr(ai_engine,"analyze_new_sens",fake_analysis)
    async def scenario(db):
        monkeypatch.setattr(research,"DBEngine",db)
        monkeypatch.setattr(ai_engine,"DBEngine",db)
        sid=await db.conn.fetchval("""INSERT INTO sens(ticker,publication_datetime,content)
            VALUES($1,now(),$2) RETURNING sens_id""",ticker,body)
        log_id=await db.conn.fetchval("""INSERT INTO action_log
            (ticker,trigger_type,trigger_content,ai_analysis,significance)
            VALUES($1,'SENS',$2,'old analysis','Low') RETURNING log_id""",ticker,body[:203])
        await research.delete_action_log(log_id)
        digest=sha256(body.encode()).hexdigest()
        assert await db.conn.fetchval("SELECT dismissed_at IS NOT NULL FROM action_log WHERE log_id=$1",log_id)
        assert await db.conn.fetchval("""SELECT count(*) FROM sens_action_dismissals
            WHERE ticker=$1 AND content_hash=$2""",ticker,digest)==1
        await ai_engine._save_log(ticker,"SENS",body[:203],"new analysis",source_content=body)
        result=await sens.run_sens_analysis_check(sens_id=sid,db=db)
        assert result.status=="success"
        assert await db.conn.fetchval("""SELECT count(*) FROM action_log
            WHERE ticker=$1 AND trigger_type='SENS' AND sens_content_hash=$2
              AND dismissed_at IS NULL""",ticker,digest)==0
        assert await db.conn.fetchval("SELECT count(*) FROM sens_analyses WHERE sens_announcement_id=$1",sid)==1
        assert await research.get_action_logs(ticker)==[dict(x) for x in await db.fetch("""SELECT log_id,log_timestamp,trigger_type,trigger_content,ai_analysis,is_read
            FROM action_log WHERE ticker=$1 AND dismissed_at IS NULL
            ORDER BY is_read ASC,log_timestamp DESC LIMIT 50""",ticker)]
    asyncio.run(with_rollback(scenario))

@pytest.mark.skipif(os.getenv("RUN_DB_INGESTION_TESTS")!="1",reason="requires local PostgreSQL; all changes roll back")
def test_market_observation_same_timestamp_dedup_and_correction():
    from modules.data.ingestion_evidence import ingest_tradingeconomics_row
    async def scenario(db):
        symbol="XTEST"+uuid4().hex[:6]
        stamp=datetime(2026,9,22,12,0)
        row={"symbol":symbol,"commodity":"Synthetic copper","price":6.2,"unit":"USD/lb",
             "currency":"USD","as_of_ts":stamp,"url":"https://example.invalid/synthetic",
             "quality":"spot","notes":"Synthetic"}
        html="<html>synthetic market page</html>"
        assert await ingest_tradingeconomics_row("commodity",row,html,db=db)
        assert not await ingest_tradingeconomics_row("commodity",row,html,db=db)
        corrected={**row,"price":6.3}
        assert await ingest_tradingeconomics_row("commodity",corrected,html+" corrected",db=db)
        obs=await db.fetch("SELECT value FROM market_observations WHERE instrument=$1 ORDER BY observed_at",symbol)
        assert len(obs)==2 and {x["value"] for x in obs}=={Decimal("6.2"),Decimal("6.3")}
        projected=await db.fetch("SELECT price FROM commodity_prices WHERE symbol=$1",symbol)
        assert len(projected)==1 and projected[0]["price"]==Decimal("6.3")
    asyncio.run(with_rollback(scenario))


@pytest.mark.skipif(os.getenv("RUN_DB_INGESTION_TESTS")!="1",reason="requires local PostgreSQL; all changes roll back")
def test_price_gap_repair_is_ticker_scoped_and_corrections_are_immutable():
    from modules.market_agent.prices import _persist_rows
    async def scenario(db):
        ticker='NED.JO'
        def row(day,close):
            return {"ticker":ticker,"trade_date":day,"open_price":Decimal(100),
                "high_price":Decimal(110),"low_price":Decimal(90),
                "close_price":Decimal(close),"volume":100}
        a,b,c=(date(2099,9,15),date(2099,9,16),date(2099,9,17))
        assert await _persist_rows(ticker,[row(a,100),row(c,102)],db=db)==2
        assert await _persist_rows(ticker,[row(a,100),row(b,101),row(c,102)],repair=True,db=db)==1
        assert await _persist_rows(ticker,[row(c,103)],db=db)==1
        assert await _persist_rows(ticker,[row(c,103)],db=db)==0
        obs=await db.fetch("SELECT close_price FROM price_observations WHERE ticker=$1 AND trade_date=$2",ticker,c)
        assert {x["close_price"] for x in obs}=={Decimal(102),Decimal(103)}
        current=await db.fetch("SELECT trade_date,close_price FROM daily_stock_data WHERE ticker=$1 AND trade_date BETWEEN $2 AND $3 ORDER BY trade_date",ticker,a,c)
        assert [x["trade_date"] for x in current]==[a,b,c]
        assert current[-1]["close_price"]==Decimal(103)
    asyncio.run(with_rollback(scenario))


def test_fundamentals_scraper_empty_response_is_failure(monkeypatch):
    from modules.data.loader import RawFundamentalsLoader
    async def empty(ticker): return None
    loader=RawFundamentalsLoader(log_callback=lambda message:None)
    monkeypatch.setattr(loader.scraper,"scrape_tables",empty)
    result=asyncio.run(loader.run_fundamentals_update(tickers=['NED.JO']))
    assert result['failed']==1 and result['succeeded']==0
    assert result['failure_codes']==['source_no_data']

@pytest.mark.skipif(os.getenv("RUN_DB_INGESTION_TESTS")!="1",reason="requires local PostgreSQL; all changes roll back")
def test_daily_market_failure_then_persistent_retry_success(monkeypatch):
    from modules.market_agent.commodity_fx import run_market_data_update
    import scripts_standalone.commodity_scraper.runner as runner
    outcomes=iter([{'failed':1,'fetched':0,'written':0},
                   {'failed':0,'fetched':1,'written':1}])
    async def fake_run(**kwargs): return next(outcomes)
    monkeypatch.setattr(runner,'run',fake_run)
    async def scenario(db):
        start=datetime(2026,9,22,7,0,tzinfo=timezone.utc)
        entity='test:'+uuid4().hex
        first=await run_claimed('TradingEconomics','market_data',entity,start.date(),
            lambda run:run_market_data_update(ingestion_run_id=run['id']),db=db,now=start)
        assert first.status=='failed'
        assert await claim_run('TradingEconomics','market_data',entity,start.date(),
                               db=db,now=start+timedelta(minutes=10)) is None
        second=await run_claimed('TradingEconomics','market_data',entity,start.date(),
            lambda run:run_market_data_update(ingestion_run_id=run['id']),
            db=db,now=start+timedelta(minutes=15))
        assert second.status=='success'
        runs=await db.fetch("SELECT status FROM ingestion_runs WHERE source='TradingEconomics' AND entity_key=$1 ORDER BY attempt_no",entity)
        assert [x['status'] for x in runs]==['retry_scheduled','success']
    asyncio.run(with_rollback(scenario))

@pytest.mark.skipif(os.getenv("RUN_DB_INGESTION_TESTS")!="1",reason="requires local PostgreSQL; all changes roll back")
def test_permanent_validation_failure_has_no_retry():
    async def scenario(db):
        start=datetime(2026,9,22,7,0,tzinfo=timezone.utc)
        async def invalid(run): raise ValueError('malformed source content')
        result=await run_claimed('test','parser','entity',start.date(),invalid,db=db,now=start)
        assert result.error_code=='validation_failure'
        rows=await db.fetch("SELECT status,next_retry_at FROM ingestion_runs WHERE job_type='parser'")
        assert rows[0]['status']=='failed' and rows[0]['next_retry_at'] is None
    asyncio.run(with_rollback(scenario))


@pytest.mark.skipif(os.getenv("RUN_DB_INGESTION_TESTS")!="1",reason="requires local PostgreSQL; all changes roll back")
def test_malformed_tradingeconomics_page_is_archived(monkeypatch):
    import scripts_standalone.commodity_fx_scraper.tradingeconomics as te
    async def malformed(): return '<html>changed table markup</html>'
    monkeypatch.setattr(te,'_fetch_te_html',malformed)
    async def scenario(db):
        monkeypatch.setattr(te,'DBEngine',db)
        assert await te.run_tradingeconomics(symbol='HG1')==1
        rows=await db.fetch("SELECT id,raw_content FROM source_documents WHERE source='TradingEconomics' AND entity_key='HG1' AND raw_content=$1",'<html>changed table markup</html>')
        assert len(rows)==1
        assert not await db.fetch("SELECT 1 FROM market_observations WHERE source_document_id=$1",rows[0]['id'])
    asyncio.run(with_rollback(scenario))

