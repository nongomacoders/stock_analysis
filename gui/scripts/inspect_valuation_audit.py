"""Read-only audit of a stored report; does not call Gemini or publish a report.

python gui/scripts/inspect_valuation_audit.py --ticker JBL.JO --output tmp/jubilee_audit.json
"""
import argparse
import asyncio
import json
import sys
from datetime import date, datetime, time, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.db.engine import DBEngine
from modules.analysis.valuation_audit import audit_report, extract_share_disclosures, render_audit
from modules.data.report_versions import fetch_audit_sources, json_text


async def inspect(ticker, report_id=None):
    if report_id:
        rows = await DBEngine.fetch("SELECT * FROM deepresearch_versions WHERE report_id=$1::uuid AND ticker=$2", report_id, ticker)
        if not rows:
            raise ValueError("Report version not found")
        row = dict(rows[0])
        inputs = row["inputs"]
        if isinstance(inputs, str):
            inputs = json.loads(inputs)
        raw = row.get("response") or {}
        if isinstance(raw, str):
            raw = json.loads(raw)
        report = raw.get("response_text") or row["report_content"] or ""
        from modules.analysis.market_context import market_audit_sources
        sources = inputs.get("sources", []) + market_audit_sources(inputs.get("commodities_supplied"), inputs.get("fx_supplied"))
        disclosures = inputs.get("audit_only_sources", [])
        report_date = row["generated_at"]
        previous = inputs.get("previous_report")
        legacy = row["status"] in {"legacy", "manual"}
        if legacy and not disclosures:
            original_date = inputs.get("original_report_date")
            if row["status"] == "legacy" and original_date:
                # Legacy dates were date-only in the DB; timestamptz conversion
                # can land on the preceding UTC day. Preserve the original date.
                report_date = date.fromisoformat(str(original_date)[:10])
                cutoff = datetime.combine(report_date, time.max, tzinfo=timezone.utc)
            else:
                cutoff = report_date
            disclosures = await fetch_audit_sources(ticker, until=cutoff)
    else:
        rows = await DBEngine.fetch("SELECT deepresearch,deepresearch_date,to_jsonb(s)->>'current_report_id' AS current_report_id FROM stock_analysis s WHERE ticker=$1", ticker)
        if not rows or not rows[0]["deepresearch"]:
            raise ValueError("No stored report")
        if rows[0].get("current_report_id"):
            return await inspect(ticker, rows[0]["current_report_id"])
        legacy = True
        report, report_date = rows[0]["deepresearch"], rows[0]["deepresearch_date"]
        cutoff = datetime.combine(report_date, time.max, tzinfo=timezone.utc) if report_date else datetime.now(timezone.utc)
        disclosures = await fetch_audit_sources(ticker, until=cutoff)
        sources, previous = [], None
    audit = audit_report(report, sources=sources, previous_report=previous,
                         share_disclosures=extract_share_disclosures(sources + disclosures))
    return {"ticker": ticker, "report_id": report_id, "report_date": report_date,
            "inspection_only": True, "report": report, "sources": sources,
            "audit_only_sources": disclosures, "audit": audit,
            "limitations": "Legacy inspection cannot recover deleted original prompts, source attachments or earlier report versions." if legacy else None}


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--report-id")
    parser.add_argument("--list-versions", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.list_versions:
            rows = await DBEngine.fetch("""
                SELECT v.report_id,v.previous_report_id,v.generated_at,v.status,v.archive_path,
                       (v.report_id=s.current_report_id) AS is_current
                FROM deepresearch_versions v LEFT JOIN stock_analysis s ON s.ticker=v.ticker
                WHERE v.ticker=$1 ORDER BY v.generated_at DESC
            """, args.ticker)
            print(json_text([dict(r) for r in rows]))
            return
        result = await inspect(args.ticker, args.report_id)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json_text(result), encoding="utf-8")
        print(render_audit(result["audit"], result["report_id"]))
    finally:
        await DBEngine.close()


if __name__ == "__main__":
    asyncio.run(main())
