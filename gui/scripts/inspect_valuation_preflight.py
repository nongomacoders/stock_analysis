"""Read-only Jubilee legacy preflight example; no report or valuation publication."""
import argparse
import json
import re
import sys
from pathlib import Path
from decimal import Decimal

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from modules.analysis.financial_metrics import FinancialMetric
from modules.analysis.metric_extraction import structure_report_metrics
from modules.analysis.valuation_preflight import candidate, render_preflight, run_preflight

ROOT = Path(__file__).resolve().parents[2]


def inspect_jubilee(audit_path: Path, comparison_path: Path) -> dict:
    prior = json.loads(audit_path.read_text(encoding="utf-8"))
    if prior.get("ticker") != "JBL.JO":
        raise ValueError("This source-specific inspection expects the Jubilee audit")
    legacy, extraction_warnings = structure_report_metrics(prior["ticker"], prior["report_id"], prior["audit"])
    by_name = {m.name: m for m in legacy}
    comparison = [FinancialMetric.model_validate(x) for x in json.loads(comparison_path.read_text(encoding="utf-8"))]
    report_id = prior["report_id"]
    selections = [
        candidate(comparison[0], report_id, "production_volume", "base", "Roan FY2027 formal guidance midpoint; source-grounded comparator"),
        candidate(comparison[1], report_id, "mining_throughput", "bull", "Molefe ROM management target, not metal production"),
        candidate(comparison[2], report_id, "production_volume", "informational", "Molefe indicated contained metal, separate from ROM"),
        candidate(comparison[3], report_id, "production_volume", "informational", "FY2026 combined pre-refining actual"),
        candidate(comparison[4], report_id, "saleable_volume", "informational", "FY2026 saleable cathode actual"),
        candidate(by_name["production_unresolved"], report_id, "production_volume", "base", "Legacy report 12,000t assumption"),
        candidate(by_name["commodity_price"], report_id, "commodity_price", "base", "Legacy report commodity assumption"),
        candidate(by_name["production_cost_per_tonne"], report_id, "aisc", "base", "Legacy report called $5,950/t AISC; definition unverified"),
        candidate(comparison[5], report_id, "current_issued_shares", "base", "Older issued-share comparison; report share basis remains unverified"),
        candidate(comparison[6], report_id, "current_issued_shares", "base", "Newer issued-share disclosure"),
        candidate(by_name["share_count_unresolved"], report_id, "current_issued_shares", "base", "Legacy report share basis unresolved"),
        candidate(comparison[7], report_id, "production_cost", "informational", "H1 FY2025 company cost reference, not verified as legacy AISC"),
        candidate(comparison[8], report_id, "production_cost", "informational", "H1 FY2026 newer company cost reference"),
        candidate(by_name["wacc"], report_id, "wacc", "base", "Legacy unsupported WACC"),
        candidate(by_name["growth"], report_id, "production_growth", "base", "Legacy ambiguous 5% growth"),
        candidate(by_name["exit_multiple"], report_id, "exit_multiple", "base", "Legacy unsupported 6x multiple"),
    ]
    target = next(x for x in prior["audit"]["assumptions"] if x["assumption"] == "target_price")
    current = re.search(r"(?im)^-?Current price:\s*ZAR\s*([0-9.]+)", prior["report"])
    if not current:
        raise ValueError("Current share price not visible in the retained Jubilee report")
    result = run_preflight(prior["ticker"], report_id, selections, legacy + comparison,
                           current_price=Decimal(current.group(1)), target_price=Decimal("1.70"),
                           target_assumption=target)
    result["inspection_only"] = True
    result["comparison_data_note"] = ("Comparison metrics are source-grounded regression data, not retroactively "
                                      "claimed as inputs supplied to the legacy Gemini generation.")
    result["legacy_extraction_warnings"] = extraction_warnings
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", type=Path, default=ROOT / "tmp/jubilee_phase1_audit.json")
    parser.add_argument("--comparison", type=Path, default=ROOT / "gui/modules/analysis/tests/fixtures/jubilee_phase2_metrics.json")
    parser.add_argument("--output", type=Path, default=ROOT / "tmp/jubilee_phase3_preflight.json")
    args = parser.parse_args()
    result = inspect_jubilee(args.audit, args.comparison)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    args.output.with_suffix(".txt").write_text(render_preflight(result) + "\n", encoding="utf-8")
    print(f"{result['ticker']}: {result['status']}; {len(result['ineligible_inputs'])} ineligible base candidates; "
          f"target {result['target_reconciliation']}; output {args.output}")


if __name__ == "__main__":
    main()
