"""Persistent ingestion scheduler. Completion and retries live in PostgreSQL."""
import asyncio
from datetime import datetime, time as dt_time, timedelta
import logging
from time import monotonic
from core.db.engine import DBEngine
from modules.data.ingestion_runs import run_claimed
from modules.market_agent.sens import run_sens_check, run_sens_analysis_check
from modules.market_agent.prices import run_price_update
from modules.market_agent.fundamentals import run_fundamentals_check
from modules.market_agent.commodity_fx import run_market_data_update

logger=logging.getLogger(__name__)
RUN_START=dt_time(7,0)
RUN_END=dt_time(22,30)

def quarter_hour_key(now: datetime) -> str:
    return f"all:{now.hour:02d}{(now.minute//15)*15:02d}"

def worker_for(job: str):
    return {
        "price_update": lambda run: run_price_update(ingestion_run_id=run["id"]),
        "manual_price_update": lambda run: run_price_update(ingestion_run_id=run["id"]),
        "manual_price_repair": lambda run: run_price_update(repair=True,ingestion_run_id=run["id"]),
        "price_gap_repair": lambda run: run_price_update(repair=True,ingestion_run_id=run["id"]),
        "sens_collection": lambda run: run_sens_check(ingestion_run_id=run["id"]),
        "market_data": lambda run: run_market_data_update(ingestion_run_id=run["id"]),
        "fundamentals": lambda run: run_fundamentals_check(ingestion_run_id=run["id"]),
    }[job]

async def retry_due_jobs(now: datetime):
    rows=await DBEngine.fetch("""SELECT * FROM (
        SELECT DISTINCT ON (source,job_type,entity_key,business_date)
        source,job_type,entity_key,business_date,status,next_retry_at,started_at
        FROM ingestion_runs WHERE job_type!='sens_analysis'
        ORDER BY source,job_type,entity_key,business_date,attempt_no DESC
        ) latest WHERE (status IN ('retry_scheduled','partial') AND next_retry_at<=$1)
          OR (status='running' AND started_at<=$1-interval '45 minutes')
        ORDER BY business_date,job_type LIMIT 50""",now)
    if rows:
        logger.info("Market agent: %d ingestion retries are due", len(rows))
    for row in rows:
        if (row["next_retry_at"] and row["next_retry_at"]<=now) or row["status"]=="running":
            try:
                await run_claimed(row["source"],row["job_type"],row["entity_key"],
                                  row["business_date"],worker_for(row["job_type"]),now=now)
            except Exception:
                logger.exception("Retry claim failed job=%s entity=%s",row["job_type"],row["entity_key"])

async def run_due_jobs(now: datetime | None = None):
    now=now or datetime.now().astimezone()
    if now.weekday()>4 or not RUN_START<=now.time().replace(tzinfo=None)<=RUN_END:
        logger.info("Market agent: outside weekday collection hours (07:00-22:30); no jobs due")
        return
    today=now.date()
    slot=quarter_hour_key(now)
    logger.info("Market agent: starting collection cycle for %s, slot %s",today,slot)
    # Collect announcements before slow whole-universe price and retry jobs.
    logger.info("Market agent: checking Moneyweb SENS announcements")
    try:
        result=await run_claimed("moneyweb_sens","sens_collection",slot,today,
                                 lambda run: run_sens_check(ingestion_run_id=run["id"]),now=now)
        logger.info("Market agent: SENS collection %s",_result_summary(result))
    except Exception:
        logger.exception("Could not claim or finish SENS collection slot=%s",slot)
    logger.info("Market agent: checking due ingestion retries")
    await retry_due_jobs(now)
    logger.info("Market agent: retry check complete")
    jobs=(
        ("yfinance","price_update",slot,lambda run: run_price_update(ingestion_run_id=run["id"])),
        ("TradingEconomics","market_data","all",lambda run: run_market_data_update(ingestion_run_id=run["id"])),
        ("sharedata","fundamentals","all",lambda run: run_fundamentals_check(ingestion_run_id=run["id"])),
        ("yfinance","price_gap_repair","all",lambda run: run_price_update(repair=True,ingestion_run_id=run["id"])),
    )
    for source,job,entity,worker in jobs:
        logger.info("Market agent: starting %s (%s)",job,source)
        started=monotonic()
        try:
            result=await run_claimed(source,job,entity,today,worker,now=now)
            logger.info("Market agent: %s %s (%.1fs)",job,_result_summary(result),monotonic()-started)
        except Exception:
            logger.exception("Could not claim or finish source=%s job=%s entity=%s",source,job,entity)
    logger.info("Market agent: checking SENS announcements awaiting Gemini analysis")
    started=monotonic()
    try:
        result=await run_sens_analysis_check()
        logger.info("Market agent: SENS analysis %s (%.1fs)",_result_summary(result),monotonic()-started)
    except Exception:
        logger.exception("SENS downstream analysis check failed")

def _result_summary(result):
    if result is None:
        return "already complete, running elsewhere, or not yet due"
    return (f"finished: {result.status}; fetched={result.records_fetched}; "
            f"written={result.records_written}; error={result.error_code or 'none'}")

async def run_market_agent():
    logger.info("Market Agent Scheduler Started")
    await DBEngine.get_pool()
    try:
        ready=await DBEngine.fetch("SELECT to_regclass('public.ingestion_runs') AS table_name")
        if not ready or ready[0]["table_name"] is None:
            logger.error("Ingestion provenance migration is not installed; market agent will not start collectors")
            return
        cycle=0
        while True:
            cycle+=1
            started=monotonic()
            logger.info("Market agent cycle %d started",cycle)
            await run_due_jobs()
            now=datetime.now().astimezone()
            delay=900 if now.weekday()<=4 and RUN_START<=now.time().replace(tzinfo=None)<=RUN_END else 600
            logger.info("Market agent cycle %d complete in %.1fs; next check at %s",
                        cycle,monotonic()-started,(now+timedelta(seconds=delay)).strftime("%Y-%m-%d %H:%M:%S %Z"))
            await asyncio.sleep(delay)
    except asyncio.CancelledError:
        logger.info("Market Agent stopping")
    except Exception:
        logger.exception("Critical market-agent error")
    finally:
        await DBEngine.close()

if __name__=="__main__":
    asyncio.run(run_market_agent())
