from datetime import datetime, timezone
from pathlib import Path
import asyncio
import sys
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from modules.analysis import sens_processor
from modules.data.report_versions import EvidenceArchive


def test_sens_processor_passes_database_record_without_staging_file(monkeypatch, tmp_path):
    run = AsyncMock(return_value=0)
    monkeypatch.setattr(sens_processor, "run_deepresearch", run)
    before = set(tmp_path.rglob("*"))
    result = asyncio.run(sens_processor.process_sens_for_deepresearch(
        "TRU.JO", "Exact persisted SENS body", sens_id=5591,
        publication_datetime=datetime(2026, 8, 27, 12, 30),
        source_document_id="11111111-1111-1111-1111-111111111111"))
    assert result is True
    assert set(tmp_path.rglob("*")) == before
    kwargs = run.await_args.kwargs
    assert "post_compare" not in kwargs
    assert kwargs["source_records"] == [{
        "source_id": "sens:5591", "name": "sens_5591.txt",
        "text": "Exact persisted SENS body", "source_date": "2026-08-27",
        "date_basis": "SENS publication", "sens_id": 5591,
        "source_document_id": "11111111-1111-1111-1111-111111111111",
        "supplied_to_model": True, "origin": "sens_database"}]


def test_database_text_is_immutably_archived(tmp_path):
    archive = EvidenceArchive("TRU.JO", root=tmp_path,
        generated_at=datetime(2026, 9, 22, tzinfo=timezone.utc))
    sources = archive.snapshot_text_records([{
        "source_id": "sens:5591", "name": "sens_5591.txt",
        "text": "Exact persisted SENS body", "source_date": "2026-08-27",
        "date_basis": "SENS publication", "sens_id": 5591,
        "source_document_id": "doc-id"}])
    item = sources[0]
    assert item["original_path"] is None
    assert item["source_id"] == "sens:5591"
    assert item["source_date"] == "2026-08-27"
    assert item["source_document_id"] == "doc-id"
    assert Path(item["archive_path"]).read_text(encoding="utf-8") == "Exact persisted SENS body"
    assert len(item["sha256"]) == 64


def test_multiple_sens_rows_are_sent_in_one_generation(monkeypatch):
    run = AsyncMock(return_value=0)
    monkeypatch.setattr(sens_processor, "run_deepresearch", run)
    selected = [
        {"sens_id": 10, "content": "First announcement",
         "publication_datetime": datetime(2026, 8, 1, 9, 0), "source_document_id": "doc-10"},
        {"sens_id": 11, "content": "Second announcement",
         "publication_datetime": datetime(2026, 9, 1, 10, 0), "source_document_id": "doc-11"},
    ]
    assert asyncio.run(sens_processor.process_sens_records_for_deepresearch("TRU.JO", selected))
    records = run.await_args.kwargs["source_records"]
    assert [x["source_id"] for x in records] == ["sens:10", "sens:11"]
    assert [x["text"] for x in records] == ["First announcement", "Second announcement"]
    assert [x["source_date"] for x in records] == ["2026-08-01", "2026-09-01"]
    assert run.await_count == 1


def test_add_selected_sens_to_folder_uses_stable_files(monkeypatch, tmp_path):
    monkeypatch.setattr(sens_processor, "RESULTS_ROOT", tmp_path)
    selected = [
        {"sens_id": 10, "content": "First headline\nFirst body",
         "publication_datetime": datetime(2026, 8, 1, 9, 0)},
        {"sens_id": 11, "content": "Second headline\nSecond body",
         "publication_datetime": datetime(2026, 9, 1, 10, 0)},
    ]
    first = asyncio.run(sens_processor.save_sens_records_to_results("TRU.JO", selected))
    second = asyncio.run(sens_processor.save_sens_records_to_results("TRU.JO", selected))
    assert first == second
    assert [p.name for p in first] == [
        "20260801_sens_10_First_headline.txt",
        "20260901_sens_11_Second_headline.txt",
    ]
    assert first[0].read_text(encoding="utf-8") == "First headline\nFirst body\n"
    assert len(list((tmp_path / "TRU").glob("*.txt"))) == 2
