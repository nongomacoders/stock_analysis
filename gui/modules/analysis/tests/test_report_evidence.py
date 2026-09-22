import asyncio
import pytest
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from modules.data.report_versions import EvidenceArchive, raw_response, source_date_from_name
from modules.analysis.market_context import fetch_market_averages, format_market_context
from core.db.engine import DBEngine


def test_archive_preserves_input_bytes_and_response(tmp_path):
    source = tmp_path / "news_20260914_update.txt"
    source.write_bytes(b"Financial evidence\r\n12,000 tonnes")
    archive = EvidenceArchive("JBL.JO", root=tmp_path / "archive")
    sources = archive.snapshot_sources([source])
    inputs = archive.save_inputs({"prompt": "Exact prompt", "sources": sources, "previous_report": "Old report"})
    archive.save_result({"raw_response": {"candidates": [{"text": "Original response"}]}})
    source.write_text("Changed staging file")
    stored = json.loads((archive.path / "inputs.json").read_text(encoding="utf-8"))
    assert stored == inputs
    assert Path(sources[0]["archive_path"]).read_bytes() == b"Financial evidence\r\n12,000 tonnes"
    assert sources[0]["source_date"] == "2026-09-14"
    assert (archive.path / "prompt.txt").read_text() == "Exact prompt"
    assert json.loads((archive.path / "result.json").read_text())["raw_response"]["candidates"]
    newer = EvidenceArchive("JBL.JO", root=tmp_path / "archive")
    assert newer.report_id != archive.report_id
    assert (archive.path / "inputs.json").exists()


def test_missing_source_date_is_not_filesystem_mtime():
    assert source_date_from_name("arbitrary.pdf") is None
    assert source_date_from_name("20260231.pdf") is None


def test_full_sdk_response_is_retained():
    class Response:
        def model_dump(self, mode):
            assert mode == "json"
            return {"candidates": ["text"], "usage_metadata": {"tokens": 10}, "model_version": "actual-version"}
    assert raw_response(Response())["model_version"] == "actual-version"


def test_market_context_preserves_metadata_and_precision(monkeypatch):
    calls = []
    async def fetch(query, *args):
        calls.append((query, args))
        common = dict(samples=114, observation_ids=[1, 2], sources=["TradingEconomics"],
                      observation_start=None, observation_end=None)
        if "commodity_prices" in query:
            return [dict(common, commodity="Copper", currency="USD", unit="USD/lb", value=6.2108026)]
        return [dict(common, pair="USDZAR", value=16.4059491)]
    monkeypatch.setattr(DBEngine, "fetch", fetch)
    until = datetime(2026, 9, 18, tzinfo=timezone.utc)
    commodities, fx = asyncio.run(fetch_market_averages(date(2026, 3, 31), until=until))
    text = format_market_context(commodities, fx)
    assert "Value: 6.21\nCurrency: USD\nUnit: lb" in text
    assert "Value: 16.4059\nCurrency: ZAR\nUnit: ZAR per USD" in text
    assert "Price type: historical average" in text
    assert "2026-03-31 to 2026-09-18" in text
    assert commodities[0]["observation_ids"] == [1, 2]
    assert "GROUP BY commodity, currency, unit" in calls[0][0]
    assert calls[0][1][1] == until


def test_generation_inputs_are_write_once(tmp_path):
    archive = EvidenceArchive("TEST.JO", root=tmp_path)
    archive.save_inputs({"prompt": "original"})
    with pytest.raises(ValueError, match="cannot be overwritten"):
        archive.save_inputs({"prompt": "changed"})
    assert json.loads((archive.path / "inputs.json").read_text())["prompt"] == "original"
