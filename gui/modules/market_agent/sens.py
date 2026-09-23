"""Moneyweb SENS collection is independent of downstream Gemini analysis."""
from __future__ import annotations
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from uuid import uuid4
import logging
from hashlib import sha256
from core.db.engine import DBEngine
from modules.data.ingestion_evidence import archive_document, MONEYWEB_PARSER_VERSION
from modules.data.ingestion_runs import IngestionResult, run_claimed

logger=logging.getLogger(__name__)
BASE_URL="https://www.moneyweb.co.za"
LIST_URL=f"{BASE_URL}/tools-and-data/moneyweb-sens/"
HEADERS={"User-Agent":"Mozilla/5.0"}

def _parse_date(elem):
    if elem.has_attr("datetime"):
        try: return datetime.fromisoformat(elem["datetime"]).replace(tzinfo=None)
        except ValueError: pass
    try: return datetime.strptime(elem.get_text(separator=" ",strip=True),"%d.%m.%y %H:%M")
    except ValueError: return None

def _fetch_page(url: str) -> tuple[str,str]:
    response=requests.get(url,headers=HEADERS,timeout=10)
    response.raise_for_status()
    html=response.text
    node=BeautifulSoup(html,"html.parser").find("div",id="sens-content")
    content=node.get_text(separator="\n",strip=True) if node is not None else None
    return html,content or None

async def run_sens_check(*, ingestion_run_id=None, db=DBEngine) -> IngestionResult:
    tickers=await db.fetch("SELECT ticker FROM stock_details WHERE ticker!='ZAR_CASH'")
    known={r["ticker"].replace(".JO","") for r in tickers}
    try:
        response=requests.get(LIST_URL,headers=HEADERS,timeout=10)
        response.raise_for_status()
        rows=BeautifulSoup(response.text,"html.parser").find_all("div",class_="sens-row")
    except Exception as exc:
        return IngestionResult.failure("transient_network",exc)
    if not rows:
        return IngestionResult.failure("source_no_data","Moneyweb SENS list has no rows")
    fetched=written=failed=0
    failures=[]
    pool=await db.get_pool()
    for row in rows:
        link=row.find("a",title="Visit Click a company for this listing")
        time=row.find("time")
        article=row.find("a",title="Go to SENS announcement")
        if not link or not time or not article:
            continue
        ticker=link.get_text(strip=True)
        if ticker not in known:
            continue
        published=_parse_date(time)
        if published is None:
            failed+=1;failures.append("validation_failure");continue
        url=article.get("href","")
        if url.startswith("/"): url=BASE_URL+url
        if not url: failed+=1;failures.append("validation_failure");continue
        try:
            html,body=_fetch_page(url)
            fetched+=1
            full_ticker=f"{ticker}.JO"
            async with pool.acquire() as conn:
                # Raw source page commits even if announcement parsing fails.
                async with conn.transaction():
                    doc=await archive_document(conn,source="moneyweb_sens",entity_key=f"{full_ticker}:{published.isoformat()}:{url}",
                        document_type="sens_article",raw_content=html,source_url=url,
                        source_date=published.date(),effective_date=published.date(),
                        parser_version=MONEYWEB_PARSER_VERSION,ingestion_run_id=ingestion_run_id)
                if not body:
                    raise ValueError("Moneyweb announcement body missing or empty")
                async with conn.transaction():
                    result=await conn.fetchrow("""INSERT INTO sens(ticker,publication_datetime,content,source_document_id)
                        VALUES($1,$2,$3,$4) ON CONFLICT DO NOTHING RETURNING sens_id""",full_ticker,published,body,doc)
                    if result:
                        written+=1
                    else:
                        await conn.execute("""UPDATE sens SET source_document_id=COALESCE(source_document_id,$4)
                            WHERE ticker=$1 AND publication_datetime=$2 AND md5(content)=md5($3)""",
                            full_ticker,published,body,doc)
        except ValueError as exc:
            logger.warning("SENS validation failed url=%s error=%s",url,exc)
            failed+=1;failures.append("validation_failure")
        except Exception:
            logger.exception("SENS collection failed url=%s",url)
            failed+=1;failures.append("transient_source_or_database_failure")
    if failed:
        code=failures[0] if len(set(failures))==1 else "mixed_failures"
        return IngestionResult.failure(code,f"{failed} announcements failed",
            retryable=code!="validation_failure",fetched=fetched,written=written)
    return IngestionResult.success(fetched,written)

async def run_sens_analysis_check(*, sens_id: int | None = None, db=DBEngine) -> IngestionResult:
    rows=await db.fetch("""SELECT s.sens_id,s.ticker,s.content,s.publication_datetime
        FROM sens s WHERE s.publication_datetime >= now()-interval '30 days'
          AND ($1::integer IS NULL OR s.sens_id=$1)
          AND NOT EXISTS(SELECT 1 FROM sens_analyses a WHERE a.sens_announcement_id=s.sens_id AND a.status='success')
        ORDER BY s.publication_datetime DESC LIMIT 20""",sens_id)
    if not rows:
        return IngestionResult("skipped")
    written=failed=0
    for row in rows:
        async def analyse(run):
            from modules.analysis.engine import analyze_new_sens
            from modules.analysis.selector import TASK_MAP
            model=TASK_MAP["sens"]["m"]
            try:
                analysis=await analyze_new_sens(row["ticker"],row["content"],store_log=False)
                if not analysis:
                    raise ValueError("No analysis context or model response")
                async with (await db.get_pool()).acquire() as conn:
                    async with conn.transaction():
                        await conn.execute("""INSERT INTO sens_analyses
                            (analysis_id,sens_announcement_id,model,prompt_version,result,status)
                            VALUES($1,$2,$3,'sens_prompt_v1',$4,'success')""",uuid4(),row["sens_id"],model,analysis)
                        import re
                        match=re.search(r"Significance:\s*(Low|Medium|High)",analysis,re.I)
                        significance=match.group(1).capitalize() if match else None
                        digest=sha256(row["content"].encode("utf-8")).hexdigest()
                        dismissed=await conn.fetchval("""SELECT EXISTS(SELECT 1 FROM sens_action_dismissals
                            WHERE ticker=$1 AND content_hash=$2)""",row["ticker"],digest)
                        visible=await conn.fetchval("""SELECT EXISTS(SELECT 1 FROM action_log
                            WHERE ticker=$1 AND trigger_type='SENS' AND sens_content_hash=$2
                              AND dismissed_at IS NULL)""",row["ticker"],digest)
                        if not dismissed and not visible:
                            await conn.execute("""INSERT INTO action_log
                                (ticker,trigger_type,trigger_content,ai_analysis,significance,sens_content_hash)
                                VALUES($1,'SENS',$2,$3,$4,$5)""",
                                row["ticker"],row["content"][:203],analysis,significance,digest)
                return IngestionResult.success(1,1)
            except Exception as exc:
                try:
                    await db.execute("""INSERT INTO sens_analyses
                        (analysis_id,sens_announcement_id,model,prompt_version,status,error_message)
                        VALUES($1,$2,$3,'sens_prompt_v1','failed',$4)""",
                        uuid4(),row["sens_id"],model,str(exc)[:1000])
                except Exception: logger.exception("Could not record failed SENS analysis")
                raise
        result=await run_claimed("gemini","sens_analysis",str(row["sens_id"]),
            row["publication_datetime"].date(),analyse,db=db)
        if result is None: continue
        if result.status=="success": written+=1
        else: failed+=1
    if failed:
        return IngestionResult.failure("sens_analysis_failure",f"{failed} analyses failed",
            fetched=written+failed,written=written)
    return IngestionResult.success(written,written)
