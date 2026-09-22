import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from modules.analysis.valuation_audit import (
    audit_report, extract_share_disclosures, HISTORICAL_CONTEXT,
)
from modules.analysis.prompts import build_research_prompt


def response(items):
    return "ASSUMPTION_AUDIT_JSON_BEGIN\n" + json.dumps(items) + "\nASSUMPTION_AUDIT_JSON_END"


def entry(**overrides):
    item = dict(assumption="production", value="12000", unit="tonnes", source="file:0",
                source_date="2026-09-14", classification="formal_guidance",
                evidence_quote="Production guidance is 12000 tonnes.")
    item.update(overrides)
    return item


def codes(audit):
    return {w["code"] for w in audit["warnings"]}


def test_verified_quote_and_invented_source():
    source = dict(source_id="file:0", text="Production guidance is 12000 tonnes.",
                  source_date="2026-09-14", supplied_to_model=True)
    audit = audit_report(response([entry()]), sources=[source])
    assert audit["assumptions"][0]["classification"] == "formal_guidance"
    assert audit["assumptions"][0]["evidence_verified"]
    for changed in (entry(source="invented"), entry(value="15000"), entry(evidence_quote="Not in the source")):
        audit = audit_report(response([changed]), sources=[source])
        assert audit["assumptions"][0]["classification"] == "unresolved"
        assert "unverified_source" in codes(audit)


def test_audit_only_evidence_cannot_be_claimed_as_generation_input():
    source = dict(source_id="file:0", text="Production guidance is 12000 tonnes.", supplied_to_model=False)
    assert audit_report(response([entry()]), sources=[source])["assumptions"][0]["classification"] == "unresolved"


def test_missing_fields_and_invalid_classification_do_not_block():
    result = audit_report(response([dict(assumption="production", value=12000)]))
    assert {"missing_unit", "missing_source", "missing_source_date", "production_unclassified", "invalid_classification"} <= codes(result)
    assert result["blocking"] is False


def test_previous_report_and_python_claims():
    result = audit_report(response([
        entry(source="previous_report", classification="historical_actual"),
        entry(assumption="target_price", value="1.70", classification="python_calculation"),
        entry(assumption="wacc", value="12", unit="%", classification="model_assumption"),
    ]))
    assert {"previous_report_only", "unverified_python_calculation", "target_not_reproducible", "wacc_unsupported"} <= codes(result)
    assert result["assumptions"][1]["python_calculated"] is False


def test_malformed_audit_preserves_report_values():
    report = "Annualized Units Produced: 12,000 tonnes copper\nASSUMPTION_AUDIT_JSON_BEGIN nope ASSUMPTION_AUDIT_JSON_END"
    result = audit_report(report)
    assert result["assumptions"][0]["value"] == "12,000 tonnes copper"
    assert result["assumptions"][0]["classification"] == "unresolved"
    assert "malformed_audit" in codes(result)


def test_newer_shares_and_denominator_basis_warning():
    source = dict(source_id="sens:1", source_date="2026-08-11", text=
                  "The Company's total issued share capital, after the issue of the Shares, will be 3 381 330 240 ordinary shares.")
    disclosures = extract_share_disclosures([source])
    assert disclosures[0]["value"] == "3381330240"
    result = audit_report("Weighted Average Shares in Issue: 3,146,295,996", share_disclosures=disclosures)
    assert "stale_share_count" in codes(result)
    assert "weighted averages may differ legitimately" in result["warnings"][-1]["message"]
    result = audit_report("Shares in Issue: 3,381,330,240", share_disclosures=disclosures)
    assert "stale_share_count" not in codes(result)


def test_no_fabricated_old_report_origin():
    result = audit_report("Annualized Units Produced: 12,000 tonnes", previous_report="Annualized Units Produced: 12,000 tonnes")
    assert result["assumptions"][0]["classification"] == "unresolved"


def test_multiple_assets_preserved():
    result = audit_report(response([entry(value="1"), entry(value="2")]))
    assert len(result["assumptions"]) == 2


def test_historical_context_is_not_truth():
    prompt = build_research_prompt("Old report")
    assert "baseline truth" not in prompt.lower()
    assert HISTORICAL_CONTEXT in prompt


def test_audit_cannot_hide_a_different_report_target():
    report = "Report target price: ZAR 1.70\n" + response([entry(assumption="target_price", value="0.45")])
    result = audit_report(report)
    assert "report_audit_mismatch" in codes(result)
    assert any(x["value"] == "ZAR 1.70" for x in result["assumptions"])


def test_unknown_wacc_inputs_are_missing():
    result = audit_report(response([entry(assumption="wacc", value=12, unit="%", supporting_inputs="unknown", source="unknown", source_date="unknown")]))
    assert {"wacc_unsupported", "missing_source", "missing_source_date"} <= codes(result)


def test_actual_market_average_is_a_registered_calculation():
    source = dict(source_id="market:commodity:0", text="", source_date="2026-09-18", supplied_to_model=True,
                  python_calculation={"value": "6.21", "allowed_units": ["lb", "USD/lb"]})
    item = entry(assumption="commodity_price", value="6.21", unit="USD/lb", source=source["source_id"], classification="python_calculation")
    result = audit_report(response([item]), sources=[source])
    assert result["assumptions"][0]["classification"] == "python_calculation"
    assert result["assumptions"][0]["evidence_verified"]
    assert "unverified_python_calculation" not in codes(result)
