"""Regression contract for the supplied Truworths FY2026 SENS."""
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import json
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from modules.analysis.financial_metrics import (AssumptionType, FinancialMetric, ShareCountType,
    SourceType, Unit)
from modules.analysis.historical_metrics import extract_retail_historical_metrics
from modules.analysis.metric_extraction import parse_numeric_value, structure_report_metrics
from modules.analysis.metric_validation import validate_metrics
from modules.analysis.report_contract import guard_report, valid_headline_metric
from modules.analysis.valuation_audit import audit_report, extract_share_disclosures
from modules.data.report_versions import EvidenceArchive, source_date_from_text
from scripts import generate_deepresearch_from_results as generator

FIXTURE = Path(__file__).parent / "fixtures" / "truworths_fy2026_sens.txt"
REPORT_ID = uuid4()


def source():
    return {"source_id": "file:0", "name": FIXTURE.name, "text": FIXTURE.read_text(encoding="utf-8"),
            "source_date": "2026-08-27", "observed_at": "2026-09-22T16:27:51+00:00",
            "supplied_to_model": True}


def test_deterministic_numeric_normalization_contract():
    cases = {"400 551 604": "400551604", "31 279 039": "31279039",
             "R196 million": "196000000", "R4.2 billion": "4200000000",
             "R949 million": "949000000", "732.2 cents": "732.2",
             "51.3%": "51.3", "7.5x": "7.5"}
    for raw, expected in cases.items():
        assert parse_numeric_value(raw)[0] == Decimal(expected)


def test_source_publication_date_is_not_file_or_report_date(tmp_path):
    text = source()["text"]
    assert source_date_from_text(text) == "2026-08-27"
    copied = tmp_path / "20260922_saved.txt"
    copied.write_text(text, encoding="utf-8")
    archive = EvidenceArchive("TRU.JO", root=tmp_path / "evidence",
        generated_at=datetime(2026, 9, 22, 16, 27, 51, tzinfo=timezone.utc))
    item = archive.snapshot_sources([copied])[0]
    assert item["source_date"] == "2026-08-27"
    assert item["observed_at"].startswith("2026-09-22")


def tru_audit():
    audit_json = [
      {"assumption":"net_debt_cash","value":"R196 million","raw_value":"R196 million","unit":"ZAR","unit_code":"ZAR","currency":"ZAR","period_start":"2025-06-30","period_end":"2026-06-28","source":"file:0","source_date":"2026-09-22","classification":"historical_actual","source_type":"company_disclosure","confidence":"high","evidence_quote":"Net cash*                                                                                                                   R196 million"},
      {"assumption":"growth","value":"2%","unit":"%","unit_code":"percentage","source":"previous_report","source_date":None,"classification":"previous_report","source_type":"previous_report","confidence":"low","evidence_quote":None},
      {"assumption":"exit_multiple","value":"7.5x","unit":"x","unit_code":"multiple","source":"previous_report","source_date":None,"classification":"previous_report","source_type":"previous_report","confidence":"low","evidence_quote":None},
      {"assumption":"target_price","value":"R55","unit":"ZAR","unit_code":"ZAR","source":"previous_report","source_date":None,"classification":"previous_report","source_type":"previous_report","confidence":"low","evidence_quote":None}
    ]
    report = "ASSUMPTION_AUDIT_JSON_BEGIN\n" + json.dumps(audit_json) + "\nASSUMPTION_AUDIT_JSON_END"
    return audit_report(report, sources=[source()], previous_report="Report target price: R55",
                        share_disclosures=extract_share_disclosures([source()]))


def test_evidence_dates_point_in_time_shares_and_treasury():
    audit = tru_audit()
    by_basis = {x.get("share_count_type"): x for x in audit["assumptions"] if x.get("share_count_type")}
    assert by_basis["issued_shares_current"]["value"] == "400551604"
    assert by_basis["issued_shares_current"]["effective_date"] == "2026-08-27"
    assert by_basis["issued_shares_current"].get("period_start") is None
    assert by_basis["treasury_shares"]["value"] == "31279039"
    assert by_basis["external_shares_ex_treasury"]["value"] == "369272565"
    assert by_basis["external_shares_ex_treasury"]["evidence_verified"]
    assert not any(w["code"] == "missing_source" and w.get("assumption") == "shares"
                   for w in audit["warnings"])
    net_cash = next(x for x in audit["assumptions"] if x["assumption"] == "net_debt_cash")
    assert net_cash["classification"] == "historical_actual" and net_cash["evidence_verified"]
    assert net_cash["source_date"] == "2026-08-27"
    assert net_cash["period_start"] is None and net_cash["period_end"] == "2026-06-28"
    assert net_cash["effective_date"] == "2026-06-28"


def test_typed_metrics_preserve_normalization_dates_and_confidence():
    audit = tru_audit()
    for item in audit["assumptions"]:
        item["report_date"] = "2026-09-22"
    metrics, warnings = structure_report_metrics("TRU.JO", REPORT_ID, audit)
    issued = next(m for m in metrics if m.share_count_type == ShareCountType.ISSUED_SHARES_CURRENT)
    treasury = next(m for m in metrics if m.share_count_type == ShareCountType.TREASURY_SHARES)
    cash = next(m for m in metrics if m.name == "net_debt_cash")
    assert issued.value == Decimal("400551604") and treasury.value == Decimal("31279039")
    assert cash.value == Decimal("196000000") and cash.unit == Unit.ZAR
    assert cash.source_date == date(2026,8,27) and cash.report_date == date(2026,9,22)
    assert cash.period_start is None and cash.period_end == date(2026,6,28)
    assert cash.confidence == Decimal("1.0")
    assert "UNKNOWN_CONFIDENCE" not in {w["code"] for w in warnings}


def test_scale_validation_blocks_misnormalized_values_and_unit_confusion():
    bad = FinancialMetric(ticker="X.JO", name="issued_shares_current", value=400,
        unit=Unit.SHARES, share_count_type=ShareCountType.ISSUED_SHARES_CURRENT,
        raw_value="400 551 604 shares", source_type=SourceType.COMPANY_DISCLOSURE,
        assumption_type=AssumptionType.HISTORICAL_ACTUAL)
    cents = FinancialMetric(ticker="X.JO", name="earnings_per_share", value=Decimal("732.2"),
        unit=Unit.ZAR, raw_value="732.2 cents")
    warnings = validate_metrics([bad, cents])
    assert {w["code"] for w in warnings} >= {"RAW_SCALE_MISMATCH", "CENTS_AS_ZAR_WITHOUT_CONVERSION"}
    assert all(w.get("severity") == "ERROR" for w in warnings if w["code"] in {"RAW_SCALE_MISMATCH", "CENTS_AS_ZAR_WITHOUT_CONVERSION"})


def test_python_historical_ratios_do_not_become_forward_assumptions():
    metrics = extract_retail_historical_metrics("TRU.JO", REPORT_ID, [source()],
        price_zar="42.40", report_date=date(2026,9,22),
        observed_at=datetime(2026,9,22,tzinfo=timezone.utc))
    values = {m.name: m for m in metrics}
    assert values["historical_payout_ratio"].value.quantize(Decimal("0.1")) == Decimal("64.7")
    assert values["historical_pe_heps"].value.quantize(Decimal("0.01")) == Decimal("5.79")
    assert values["historical_pe_diluted_heps"].value.quantize(Decimal("0.01")) == Decimal("5.84")
    assert values["trailing_dividend_yield"].value.quantize(Decimal("0.1")) == Decimal("11.2")
    assert values["price_to_nav"].value.quantize(Decimal("0.01")) == Decimal("1.49")
    assert all(m.assumption_type == AssumptionType.PYTHON_CALCULATION for m in metrics)
    assert all(m.intended_use == "PYTHON_DERIVED_HISTORICAL_METRIC" for m in metrics)
    assert not any(m.name in {"growth", "exit_multiple", "sustainable_payout_ratio"} for m in metrics)


def test_sector_prompt_routing_and_generic_fallback():
    prompts = generator.GUI_ROOT / "prompts"
    assert generator._select_prompt_file(prompts, "General Retail").name == "clothing_food_furniture_prompt.txt"
    assert generator._select_prompt_file(prompts, "Banks").name == "banks_prompt.txt"
    assert generator._select_prompt_file(prompts, "Mining").name == "commodity_prompt.txt"
    assert generator._select_prompt_file(prompts, "REIT").name == "REITS_prompt.txt"
    assert generator._select_prompt_file(prompts, "Telecom").name == "telecoms_prompt.txt"
    assert generator._select_prompt_file(prompts, "Investment Holding").name == "holding_company_prompt.txt"
    assert generator._select_prompt_file(prompts, "Unmapped Future Sector").name == "generic_equity_prompt.txt"


def test_report_guardrails_isolate_legacy_and_reject_unsupported_language():
    report = """# Report
Key Metric: 25.5%
## Key assumptions
- Growth: 2%
- Target P/E: 7.5x
## Discussion
Inventory absorbed cash and port disruptions affected performance.
The share is attractive and undemanding.
"""
    cleaned, warnings = guard_report(report, valuation_status="NOT_CALCULABLE", audit=tru_audit())
    assert "Key Metric: 25.5%" not in cleaned
    assert "## Key assumptions" not in cleaned
    assert "ANALYST_INFERENCE (not established by supplied source)" in cleaned
    assert "attractive" not in cleaned.lower() and "undemanding" not in cleaned.lower()
    assert "Legacy valuation context - unverified / not approved" in cleaned
    assert "target_price: R55" in cleaned
    assert {w["code"] for w in warnings} >= {"UNLABELED_HEADLINE_METRIC", "UNSUPPORTED_CAUSAL_NARRATIVE", "VALUATION_LANGUAGE_WITHOUT_TARGET", "LEGACY_ASSUMPTION_ISOLATED"}
    assert not valid_headline_metric("Key Metric: 25.5%")
    assert valid_headline_metric("Key Metric: metric_name=gross_margin | value=51.3 | unit=% | period=FY2026 | source=file:0")


def test_previous_report_values_are_never_current_evidence():
    audit = tru_audit()
    for name, value in (("growth", "2%"), ("exit_multiple", "7.5x"), ("target_price", "R55")):
        item = next(x for x in audit["assumptions"] if x["assumption"] == name and x.get("value") == value)
        assert item["classification"] == "previous_report"
        assert not item["evidence_verified"]
    assert "inventory absorbing cash" not in source()["text"].lower()
    assert "delayed customer collections" not in source()["text"].lower()



def test_guard_report_replaces_model_report_date():
    cleaned, warnings = guard_report(
        "Report Date: 23 May 2024\n\nInvestment Thesis\nText",
        valuation_status="NOT_CALCULABLE",
        audit={"assumptions": []},
        report_date="2026-09-23",
    )
    assert "Report Date: 2026-09-23" in cleaned
    assert "23 May 2024" not in cleaned
    assert any(item["code"] == "REPORT_DATE_CORRECTED" for item in warnings)


def test_guard_report_adds_missing_report_date():
    cleaned, warnings = guard_report(
        "Investment Thesis\nText",
        valuation_status="NOT_CALCULABLE",
        audit={"assumptions": []},
        report_date="2026-09-23",
    )
    assert cleaned.startswith("Report Date: 2026-09-23")
    assert any(item["code"] == "REPORT_DATE_ADDED" for item in warnings)
