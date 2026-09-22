import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from scripts import generate_deepresearch_from_results as generator
from modules.analysis.valuation_audit import HISTORICAL_CONTEXT
from modules.data import report_versions


def test_generation_prompt_revalidation_and_python_only_target():
    template = Path(generator.GUI_ROOT / "prompts/commodity_prompt.txt").read_text(encoding="utf-8")
    prompt = generator._build_llm_prompt(template, ticker="JBL.JO", price=45, payload="Source", previous_report="Old report")
    assert HISTORICAL_CONTEXT in prompt
    assert "ASSUMPTION_AUDIT_JSON_BEGIN" in prompt
    assert "HEPS = [(Spot Price - AISC) * Production * (1 - Tax Rate)] / Shares" not in prompt
    assert "Python alone calculates valuation and target prices" in prompt
    assert "LATEST CLOSE PRICE (ZAR): 0.45" in prompt


@pytest.mark.parametrize("provider_fails", [False, True])
def test_generation_retains_exact_inputs_before_query_and_raw_response(monkeypatch, tmp_path, provider_fails):
    from modules.analysis import selector, engine
    from modules.data import research
    from scripts_standalone.results_scraper import watchlist
    from core.db.engine import DBEngine
    root = tmp_path / "gui"
    (root / "results/TEST").mkdir(parents=True)
    (root / "prompts").mkdir()
    source = root / "results/TEST/20260914.txt"
    source.write_text("Exact source data", encoding="utf-8")
    (root / "prompts/commodity_prompt.txt").write_text("Generate report", encoding="utf-8")
    monkeypatch.setattr(generator, "GUI_ROOT", root)
    monkeypatch.setattr(report_versions, "ARCHIVE_ROOT", tmp_path / "evidence")
    monkeypatch.setattr(watchlist, "resolve_tickers_to_process", AsyncMock(return_value=["TEST.JO"]))
    monkeypatch.setattr(generator, "_fetch_latest_close_price", AsyncMock(return_value={"value": 45, "source_date": "2026-09-18"}))
    monkeypatch.setattr(generator, "_fetch_category_name", AsyncMock(return_value="commodity"))
    monkeypatch.setattr(generator, "_fetch_last_results_date", AsyncMock(return_value=None))
    monkeypatch.setattr(report_versions, "get_previous_report", AsyncMock(return_value={"deepresearch": "Old report", "current_report_id": None}))
    monkeypatch.setattr(report_versions, "fetch_audit_sources", AsyncMock(return_value=[]))
    monkeypatch.setattr(DBEngine, "fetch", AsyncMock(return_value=[]))
    monkeypatch.setattr(report_versions, "register_generation", AsyncMock())
    published = []
    async def finish(archive, result, **kwargs):
        archive.save_result(result)
        published.append((result, kwargs))
    monkeypatch.setattr(report_versions, "finish_generation", finish)
    monkeypatch.setattr(engine, "generate_master_research", AsyncMock(return_value="Summary"))
    monkeypatch.setattr(research, "save_research_data", AsyncMock())
    from modules.data import valuation_results
    monkeypatch.setattr(valuation_results, "save_valuation_result", AsyncMock())
    monkeypatch.setattr(generator.asyncio, "sleep", AsyncMock())
    report = "Research findings. " * 150
    async def query(task, prompt, **kwargs):
        manifests = list((tmp_path / "evidence").rglob("inputs.json"))
        assert len(manifests) == 1  # Already durable before inference.
        manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
        assert manifest["prompt"] == prompt
        assert manifest["previous_report"] == "Old report"
        assert manifest["share_price"]["source_date"] == "2026-09-18"
        assert Path(manifest["sources"][0]["archive_path"]).read_text() == "Exact source data"
        if provider_fails:
            raise RuntimeError("Simulated inference failure")
        return SimpleNamespace(text=report, usage_metadata=None, model_dump=lambda **kw: {"text": report, "extra": "raw field"})
    monkeypatch.setattr(selector, "managed_query_ai", query)
    asyncio.run(generator.run(ticker="TEST.JO", limit=None, dry_run=False, max_chars=200000))
    assert source.exists()
    assert len(published) == 1
    result, options = published[0]
    if provider_fails:
        assert result["status"] == "failed"
        assert not options.get("publish")
    else:
        assert result["raw_response"]["extra"] == "raw field"
        assert options["publish"]
        assert result["valuation_preflight"]["status"] == "FAIL"
        assert result["valuation_preflight"]["target_reconciliation"] in {"unresolved", "carried_forward"}
        assert options["report_content"].startswith(report)
        assert result["deterministic_valuation"]["status"] == "NOT_CALCULABLE"
        assert "Deterministic target price: NOT_CALCULABLE" in options["report_content"]


def test_gemini_fallback_trace_keeps_actual_model_and_temperature(monkeypatch):
    from modules.analysis import gemini_vertex_llm as llm
    attempts = []
    async def generate(**kwargs):
        attempts.append(kwargs)
        if len(attempts) == 1:
            raise RuntimeError("404 model not found")
        return SimpleNamespace(text="report", model_version="resolved-version")
    monkeypatch.setattr(llm.genai, "Client", lambda **kw: SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate))))
    trace = {}
    asyncio.run(llm.query_ai("exact prompt", model="requested-model", request_trace=trace))
    assert trace["model"] == "gemini-3.1-pro-preview"
    assert trace["response_model_version"] == "resolved-version"
    assert [a["status"] for a in trace["attempts"]] == ["failed", "succeeded"]
    assert all(a["config"].temperature == 0.7 for a in attempts)


def test_pdf_inline_bytes_and_raw_response(monkeypatch, tmp_path):
    from google import genai
    captured = []
    response = SimpleNamespace(text="PDF report", usage_metadata=None, model_version="pdf-version",
                               model_dump=lambda **kw: {"candidates": [{"text": "PDF report"}], "extra": "raw"})
    def generate(**kwargs):
        captured.append(kwargs)
        return response
    monkeypatch.setattr(genai, "Client", lambda **kw: SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
    pdf = tmp_path / "immutable.pdf"
    pdf.write_bytes(b"%PDF-1.4 exact bytes")
    trace = {}
    result = generator._query_ai_with_pdfs(prompt="exact PDF prompt", pdf_paths=[pdf], display_name_prefix="id", request_trace=trace)
    assert captured[0]["contents"][1].inline_data.data == pdf.read_bytes()
    assert captured[0]["config"].temperature == 0.2
    assert result["raw_response"]["extra"] == "raw"
    assert trace["response_model_version"] == "pdf-version"


def test_legacy_inspection_uses_original_report_date(monkeypatch):
    from datetime import datetime, date, timezone
    from scripts import inspect_valuation_audit as inspection
    from core.db.engine import DBEngine
    row = dict(inputs={"original_report_date": "2026-09-18"}, response=None,
               report_content="Report target price: ZAR 1.70", status="legacy",
               generated_at=datetime(2026, 9, 17, 22, tzinfo=timezone.utc))
    monkeypatch.setattr(DBEngine, "fetch", AsyncMock(return_value=[row]))
    sources = AsyncMock(return_value=[])
    monkeypatch.setattr(inspection, "fetch_audit_sources", sources)
    result = asyncio.run(inspection.inspect("JBL.JO", "legacy-id"))
    assert result["report_date"] == date(2026, 9, 18)
    assert sources.call_args.kwargs["until"].date() == date(2026, 9, 18)


def test_all_sector_templates_remove_gemini_target_requests():
    for template in (generator.GUI_ROOT / "prompts").glob("*_prompt.txt"):
        prompt = generator._build_llm_prompt(template.read_text(encoding="utf-8"),
                                              ticker="TEST.JO", price=100, payload="Current source")
        assert "<Your calculated 12-month target>" not in prompt, template.name
        assert "<Target Price>" not in prompt, template.name
        assert "HEPS = [(Spot Price - AISC)" not in prompt, template.name
        assert "Python alone calculates valuation and target prices" in prompt
