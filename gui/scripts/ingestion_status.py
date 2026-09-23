"""Read-only status of durable ingestion jobs."""
import argparse
import asyncio
import json
import sys
from datetime import date
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.db.engine import DBEngine

async def inspect(day: date, failed_only: bool, limit: int):
    rows=await DBEngine.fetch("""SELECT * FROM (
        SELECT DISTINCT ON (source,job_type,entity_key,business_date)
          id,source,job_type,entity_key,business_date,attempt_no,status,
          records_fetched,records_written,error_code,error_message,next_retry_at
        FROM ingestion_runs WHERE business_date=$1
        ORDER BY source,job_type,entity_key,business_date,attempt_no DESC
        ) latest WHERE ($2::boolean=false OR status IN ('failed','partial','retry_scheduled'))
        ORDER BY status,source,job_type,entity_key LIMIT $3""",day,failed_only,limit)
    return [dict(row) for row in rows]

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--date',type=date.fromisoformat,default=date.today())
    parser.add_argument('--failed-only',action='store_true')
    parser.add_argument('--limit',type=int,default=500)
    args=parser.parse_args()
    async def main():
        try: print(json.dumps(await inspect(args.date,args.failed_only,args.limit),default=str,indent=2))
        finally: await DBEngine.close()
    asyncio.run(main())
