from __future__ import annotations
from datetime import date, datetime
from pathlib import Path
from scripts.generate_deepresearch_from_results import run as run_deepresearch
from scripts_standalone.results_scraper.utils import sanitize_ticker

RESULTS_ROOT = Path(__file__).resolve().parents[2] / "results"


def _source_record(item: dict) -> dict:
    published = item.get("publication_datetime")
    if isinstance(published, (datetime, date)):
        source_date = published.date().isoformat() if isinstance(published, datetime) else published.isoformat()
    else:
        source_date = str(published)[:10] if published else None
    sens_id = item.get("sens_id")
    source_id = f"sens:{sens_id}" if sens_id is not None else "sens:selected"
    source_document_id = item.get("source_document_id")
    return {
        "source_id": source_id,
        "name": f"{source_id.replace(':', '_')}.txt",
        "text": str(item.get("content") or ""),
        "source_date": source_date,
        "date_basis": "SENS publication",
        "sens_id": sens_id,
        "source_document_id": str(source_document_id) if source_document_id else None,
        "supplied_to_model": True,
        "origin": "sens_database",
    }


async def save_sens_records_to_results(ticker: str, selections: list[dict]) -> list[Path]:
    """Explicitly export selected persisted SENS rows to the ticker results folder."""
    if not ticker:
        return []
    ticker_dir = RESULTS_ROOT / sanitize_ticker(ticker)
    ticker_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for index, item in enumerate(selections):
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        published = item.get("publication_datetime")
        if isinstance(published, (datetime, date)):
            date_part = (published.date() if isinstance(published, datetime) else published).strftime("%Y%m%d")
        else:
            date_part = str(published)[:10].replace("-", "") if published else "undated"
        sens_id = item.get("sens_id")
        id_part = f"sens_{sens_id}" if sens_id is not None else f"sens_selected_{index + 1}"
        headline = content.splitlines()[0][:60]
        safe_headline = "_".join("".join(c if c.isalnum() else " " for c in headline).split())
        filename = f"{date_part}_{id_part}" + (f"_{safe_headline}" if safe_headline else "") + ".txt"
        path = ticker_dir / filename
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(content + "\n", encoding="utf-8")
        temporary.replace(path)
        saved.append(path)
    return saved


async def process_sens_records_for_deepresearch(ticker: str, selections: list[dict]) -> bool:
    """Generate one report from the selected persisted SENS announcements."""
    records = [_source_record(item) for item in selections if item.get("content")]
    if not ticker or not records:
        return False
    try:
        await run_deepresearch(ticker=ticker, limit=None, dry_run=False,
                               max_chars=200_000, source_records=records)
    except Exception as exc:
        print(f"Failed to trigger deep research for {ticker}: {exc}")
        return False
    return True


async def process_sens_for_deepresearch(ticker: str, content: str, *, sens_id=None,
                                        publication_datetime=None,
                                        source_document_id=None) -> bool:
    """Backward-compatible single-announcement entry point."""
    return await process_sens_records_for_deepresearch(ticker, [{
        "content": content, "sens_id": sens_id,
        "publication_datetime": publication_datetime,
        "source_document_id": source_document_id,
    }])
