"""Pytest fixtures for historical backtest tests."""
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
import pytest
try:
    from pypdf import PdfReader
except ImportError:
    from PyPDF2 import PdfReader
from modules.analysis.results_package import (
    build_results_package, observations_to_metrics, ANNUAL_FINANCIAL_STATEMENTS, RESULTS_SENS
)
from modules.analysis.historical_backtest import (
    HistoricalBacktest, HistoricalEvidence, HistoricalMarketObservation, Availability
)

PACKAGE_DIR = Path(__file__).resolve().parents[3] / "results_history" / "TRU" / "FY2025"

@pytest.fixture(scope="session")
def cached_tru_backtest():
    sens_p, afs_p = PACKAGE_DIR / "TRU_FY2025_SENS.txt", PACKAGE_DIR / "TRU_FY2025_AFS.pdf"
    afs_text = "\n".join(p.extract_text() or "" for p in PdfReader(afs_p).pages)
    sources = [
        {"source_id": "hist:sens", "name": sens_p.name, "text": sens_p.read_text(encoding="utf-8", errors="ignore"),
         "source_date": "2025-08-28", "available_date": "2025-08-28", "original_path": str(sens_p),
         "archive_path": str(sens_p), "sha256": "607f150f", "document_role": RESULTS_SENS, "active": True},
        {"source_id": "hist:afs", "name": afs_p.name, "text": afs_text,
         "source_date": "2025-08-28", "available_date": "2025-08-28", "original_path": str(afs_p),
         "archive_path": str(afs_p), "sha256": "7e2389d7", "document_role": ANNUAL_FINANCIAL_STATEMENTS, "active": True}
    ]
    pkg = build_results_package(sources)
    metrics = observations_to_metrics("TRU.JO", uuid4(), pkg, date(2025, 6, 29), datetime(2025, 8, 31, tzinfo=timezone.utc))
    ev = [HistoricalEvidence(evidence_id=str(m.metric_id), kind=m.name, available_date=date(2025, 8, 28), period_end=date(2025, 6, 29), source_id=m.source_id, payload=m.model_dump(mode="json"), availability=Availability.AVAILABLE) for m in metrics]
    mkt = [HistoricalMarketObservation(snapshot_id="m1", kind="share_price", instrument="TRU.JO", observation_date=date(2025, 8, 29), value=Decimal("6022.0"), currency="ZAR", unit="cents_per_share", source="test", price_basis="raw_close", lag_days=2)]
    return HistoricalBacktest(ticker="TRU.JO", as_of_date=date(2025, 8, 31), reporting_period_label="FY2025", reporting_period_end=date(2025, 6, 29), evidence_snapshot=ev, market_snapshot=mkt, created_by="analyst")
