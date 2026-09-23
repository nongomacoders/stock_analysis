"""Durable, concurrency-safe ingestion claims and bounded retries."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4
import logging
from core.db.engine import DBEngine

logger = logging.getLogger(__name__)
RETRY_MINUTES = (15, 30, 60)
MAX_ATTEMPTS = 4

@dataclass(frozen=True)
class IngestionResult:
    status: str
    records_fetched: int = 0
    records_written: int = 0
    warnings: tuple[str, ...] = ()
    retryable: bool = False
    error_code: str | None = None
    error_message: str | None = None

    @classmethod
    def success(cls, fetched=0, written=0):
        return cls("success", fetched, written)

    @classmethod
    def failure(cls, code, message, *, retryable=True, fetched=0, written=0):
        return cls("failed", fetched, written, retryable=retryable, error_code=code, error_message=str(message)[:1000])

def classify_error(exc: Exception) -> tuple[str, bool]:
    name = type(exc).__name__.lower()
    if any(s in name for s in ("timeout", "connection", "client", "network")):
        return "transient_network", True
    if any(s in name for s in ("postgres", "database", "asyncpg")):
        return "database_failure", True
    if isinstance(exc, ValueError):
        return "validation_failure", False
    return "worker_failure", True

async def claim_run(source: str, job_type: str, entity_key: str, business_date: date,
                    *, scheduled_for: datetime | None = None, worker_id: str = "market_agent",
                    now: datetime | None = None, db=DBEngine) -> dict | None:
    now = now or datetime.now(timezone.utc)
    scheduled_for = scheduled_for or now
    key = f"{source}:{job_type}:{entity_key}:{business_date}"
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            locked = await conn.fetchval("SELECT pg_try_advisory_xact_lock(hashtextextended($1,0))", key)
            if not locked:
                return None
            prior = await conn.fetchrow("""SELECT * FROM ingestion_runs
                WHERE source=$1 AND job_type=$2 AND entity_key=$3 AND business_date=$4
                ORDER BY attempt_no DESC LIMIT 1 FOR UPDATE""", source, job_type, entity_key, business_date)
            if prior:
                if prior["status"] in ("success", "skipped", "failed"):
                    return None
                if prior["status"] == "running":
                    if prior["started_at"] > now - timedelta(minutes=45):
                        return None
                    await conn.execute("""UPDATE ingestion_runs SET status='retry_scheduled',
                        error_code='stale_worker',error_message='Worker lease expired',next_retry_at=$2,
                        finished_at=$2,updated_at=$2 WHERE id=$1""",prior["id"],now)
                elif prior["next_retry_at"] and prior["next_retry_at"] > now:
                    return None
                attempt = prior["attempt_no"]+1
            else:
                attempt = 1
            if attempt > MAX_ATTEMPTS:
                return None
            ident = uuid4()
            row = await conn.fetchrow("""INSERT INTO ingestion_runs
                (id,source,job_type,entity_key,business_date,scheduled_for,started_at,status,attempt_no,worker_id)
                VALUES($1,$2,$3,$4,$5,$6,$7,'running',$8,$9) RETURNING *""",
                ident,source,job_type,entity_key,business_date,scheduled_for,now,attempt,worker_id)
            logger.info("ingestion claimed run=%s source=%s job=%s entity=%s attempt=%s",ident,source,job_type,entity_key,attempt)
            return dict(row)

async def finish_run(run: dict, result: IngestionResult, *, now: datetime | None = None, db=DBEngine) -> str:
    now = now or datetime.now(timezone.utc)
    status = result.status
    next_retry = None
    if status != "success" and status != "skipped":
        if result.retryable and run["attempt_no"] < MAX_ATTEMPTS:
            next_retry = now + timedelta(minutes=RETRY_MINUTES[run["attempt_no"]-1])
            status = "partial" if result.records_written else "retry_scheduled"
        else:
            status = "failed"
    if status not in {"success","partial","failed","retry_scheduled","skipped"}:
        raise ValueError("Unknown ingestion result status")
    await db.execute("""UPDATE ingestion_runs SET finished_at=$2,status=$3,records_fetched=$4,
        records_written=$5,error_code=$6,error_message=$7,next_retry_at=$8,updated_at=$2
        WHERE id=$1 AND status='running'""",run["id"],now,status,result.records_fetched,
        result.records_written,result.error_code,result.error_message,next_retry)
    logger.info("ingestion finished run=%s source=%s job=%s entity=%s attempt=%s fetched=%s written=%s status=%s retry=%s error=%s",
        run["id"],run["source"],run["job_type"],run["entity_key"],run["attempt_no"],
        result.records_fetched,result.records_written,status,next_retry,result.error_code)
    return status

async def run_claimed(source: str, job_type: str, entity_key: str, business_date: date, worker,
                      *, db=DBEngine, now: datetime | None = None) -> IngestionResult | None:
    run = await claim_run(source,job_type,entity_key,business_date,db=db,now=now)
    if run is None:
        return None
    try:
        result = await worker(run)
        if not isinstance(result, IngestionResult):
            raise ValueError("Worker must return IngestionResult")
    except Exception as exc:
        code,retryable=classify_error(exc)
        logger.exception("ingestion worker failed run=%s",run["id"])
        result=IngestionResult.failure(code,str(exc),retryable=retryable)
    await finish_run(run,result,db=db,now=now)
    return result
