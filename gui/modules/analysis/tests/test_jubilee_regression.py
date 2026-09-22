import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from modules.analysis.valuation_audit import audit_report, extract_share_disclosures


def test_actual_jubilee_report_provenance_is_not_invented():
    fixture = json.loads((Path(__file__).parent / "fixtures/jubilee_legacy.json").read_text(encoding="utf-8"))
    result = audit_report(fixture["report"], share_disclosures=extract_share_disclosures(fixture["audit_only_sources"]))
    values = {x["assumption"]: x for x in result["assumptions"]}
    assert values["target_price"]["value"] == "ZAR 1.70"
    assert values["target_price"]["classification"] == "previous_report"
    assert values["target_price"]["python_calculated"] is False
    assert values["production"]["value"] == "12,000 tonnes copper"
    assert values["production"]["classification"] == "unresolved"
    assert values["production_cost"]["classification"] == "unresolved"
    assert values["shares"]["newer_share_disclosure"]["value"] == "3381330240"
    assert values["shares"]["newer_share_disclosure"]["source"] == "sens:4955"
    for key in ("wacc", "growth", "exit_multiple"):
        assert values[key]["classification"] == "unresolved"
        assert values[key]["source"] is None
    codes = {(w["assumption"], w["code"]) for w in result["warnings"]}
    assert ("shares", "stale_share_count") in codes
    assert ("wacc", "wacc_unsupported") in codes
    assert ("growth", "unsupported_parameter") in codes
    assert ("exit_multiple", "unsupported_parameter") in codes
