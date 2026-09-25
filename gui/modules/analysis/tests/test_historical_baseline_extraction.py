"""Tests for FY2025 historical baseline extraction, provenance, and readiness gating."""
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
import pytest
from modules.analysis.results_package import (
    build_results_package, observations_to_metrics, ANNUAL_FINANCIAL_STATEMENTS, RESULTS_SENS
)
from modules.analysis.historical_backtest import (
    HistoricalBacktest, HistoricalEvidence, HistoricalMarketObservation, Availability,
    resolve_evidence_as_of, select_historical_share_count
)
from modules.analysis.historical_readiness import (
    evaluate_historical_baseline, assert_historical_baseline_ready, ReadinessStatus
)

PACKAGE_DIR = Path(__file__).resolve().parents[3] / "results_history" / "TRU" / "FY2025"

def _load_fy2025_sources():
    sens_p, afs_p = PACKAGE_DIR / "TRU_FY2025_SENS.txt", PACKAGE_DIR / "TRU_FY2025_AFS.pdf"
    try:
        from pypdf import PdfReader
    except ImportError:
        from PyPDF2 import PdfReader
    afs_text = "\n".join(p.extract_text() or "" for p in PdfReader(afs_p).pages)
    return [
        {"source_id": "hist:sens", "name": sens_p.name, "text": sens_p.read_text(encoding="utf-8", errors="ignore"),
         "source_date": "2025-08-28", "available_date": "2025-08-28", "original_path": str(sens_p),
         "archive_path": str(sens_p), "sha256": "607f150f", "document_role": RESULTS_SENS, "active": True},
        {"source_id": "hist:afs", "name": afs_p.name, "text": afs_text,
         "source_date": "2025-08-28", "available_date": "2025-08-28", "original_path": str(afs_p),
         "archive_path": str(afs_p), "sha256": "7e2389d7", "document_role": ANNUAL_FINANCIAL_STATEMENTS, "active": True}
    ]

def test_fy2025_sens_scale_normalization_and_afs_precedence():
    sources = _load_fy2025_sources()
    pkg = build_results_package(sources)
    sens_merch = next(x for x in pkg["observations"] if x["name"] == "sale_of_merchandise" and x["document_role"] == RESULTS_SENS)
    assert sens_merch["raw_value"] == "21.3" and sens_merch["raw_unit"] == "ZAR_billion"
    assert Decimal(sens_merch["normalized_value"]) == Decimal("21300000000") and sens_merch["unit"] == "ZAR"
    afs_merch = next(x for x in pkg["observations"] if x["name"] == "sale_of_merchandise" and x["document_role"] == ANNUAL_FINANCIAL_STATEMENTS)
    assert Decimal(afs_merch["normalized_value"]) == Decimal("21323000000")
    metrics = observations_to_metrics("TRU.JO", uuid4(), pkg, date(2025, 6, 29), datetime(2025, 8, 31, tzinfo=timezone.utc))
    ev = [HistoricalEvidence(evidence_id=str(m.metric_id), kind=m.name, available_date=date(2025, 8, 28), period_end=date(2025, 6, 29), source_id=m.source_id, payload=m.model_dump(mode="json"), availability=Availability.AVAILABLE) for m in metrics]
    bt = HistoricalBacktest(ticker="TRU.JO", as_of_date=date(2025, 8, 31), evidence_snapshot=ev, created_by="analyst")
    res = evaluate_historical_baseline(bt)
    assert res.concept_statuses["sale_of_merchandise"].normalized_value == Decimal("21323000000")

def test_depreciation_accounting_sign_vs_economic_magnitude():
    sources = _load_fy2025_sources()
    pkg = build_results_package(sources)
    d_obs = next(x for x in pkg["observations"] if x["name"] == "depreciation_and_amortisation")
    assert "-" in str(d_obs["normalized_value"]) or "(" in str(d_obs["raw_value"])
    metrics = observations_to_metrics("TRU.JO", uuid4(), pkg, date(2025, 6, 29), datetime(2025, 8, 31, tzinfo=timezone.utc))
    d_met = next(m for m in metrics if m.name == "depreciation_and_amortisation")
    assert d_met.value < 0 and d_met.normalized_value == Decimal("1500000000")

def test_invalid_scale_blocks_readiness():
    bad_ev = [HistoricalEvidence(evidence_id="1", kind="sale_of_merchandise", available_date=date(2025, 8, 28), period_end=date(2025, 6, 29), source_id="s1", payload={"name": "sale_of_merchandise", "value": Decimal("21.3"), "normalized_value": Decimal("21.3"), "unit": "ZAR"}, availability=Availability.AVAILABLE)]
    bt = HistoricalBacktest(ticker="TRU.JO", as_of_date=date(2025, 8, 31), evidence_snapshot=bad_ev, created_by="analyst")
    res = evaluate_historical_baseline(bt)
    assert res.concept_statuses["sale_of_merchandise"].status == ReadinessStatus.INVALID_SCALE
    assert res.ready is False

def test_historical_share_denominator_hierarchy_and_separation():
    sources = _load_fy2025_sources()
    pkg = build_results_package(sources)
    metrics = observations_to_metrics("TRU.JO", uuid4(), pkg, date(2025, 6, 29), datetime(2025, 8, 31, tzinfo=timezone.utc))
    ev = [HistoricalEvidence(evidence_id=str(m.metric_id), kind=m.name, available_date=date(2025, 8, 28), period_end=date(2025, 6, 29), source_id=m.source_id, payload=m.model_dump(mode="json"), availability=Availability.AVAILABLE) for m in metrics]
    chosen = select_historical_share_count(ev)
    assert chosen is not None and chosen.payload.get("name") == "external_shares_ex_treasury"
    assert chosen.payload.get("value") == "375360899"

def test_net_cash_and_lease_separation():
    sources = _load_fy2025_sources()
    pkg = build_results_package(sources)
    obs = {x["name"]: Decimal(x["normalized_value"]) for x in pkg["observations"]}
    net_cash = (obs["cash_and_cash_equivalents"] - Decimal("14000000") + obs["money_market_investments"]) - (obs["borrowings"] + obs["bank_overdraft"])
    assert net_cash == Decimal("720000000")
    assert obs["total_lease_liabilities"] == Decimal("3742000000")

def test_evidence_records_metric_vs_document_distinction():
    sources = _load_fy2025_sources()
    pkg = build_results_package(sources)
    metrics = observations_to_metrics("TRU.JO", uuid4(), pkg, date(2025, 6, 29), datetime(2025, 8, 31, tzinfo=timezone.utc))
    assert len(metrics) > 60 and all(m.source_id.startswith("hist:") for m in metrics)

def test_readiness_gate_passes_on_complete_baseline():
    sources = _load_fy2025_sources()
    pkg = build_results_package(sources)
    metrics = observations_to_metrics("TRU.JO", uuid4(), pkg, date(2025, 6, 29), datetime(2025, 8, 31, tzinfo=timezone.utc))
    ev = [HistoricalEvidence(evidence_id=str(m.metric_id), kind=m.name, available_date=date(2025, 8, 28), period_end=date(2025, 6, 29), source_id=m.source_id, payload=m.model_dump(mode="json"), availability=Availability.AVAILABLE) for m in metrics]
    mkt = [HistoricalMarketObservation(snapshot_id="m1", kind="share_price", instrument="TRU.JO", observation_date=date(2025, 8, 29), value=Decimal("60.22"), currency="ZAR", unit="cents_per_share", source="test", lag_days=2)]
    bt = HistoricalBacktest(ticker="TRU.JO", as_of_date=date(2025, 8, 31), evidence_snapshot=ev, market_snapshot=mkt, created_by="analyst")
    res = evaluate_historical_baseline(bt)
    assert res.ready is True and assert_historical_baseline_ready(bt).ready is True
