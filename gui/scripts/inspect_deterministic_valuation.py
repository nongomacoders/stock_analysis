"""Source-bounded, read-only Jubilee Phase 4 valuation inspection."""
import argparse
import asyncio
import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from modules.analysis.financial_metrics import FinancialMetric
from modules.analysis.metric_extraction import structure_report_metrics
from modules.analysis.valuation_preflight import candidate
from modules.analysis.valuation import run_valuation
from modules.analysis.valuation.engine import render_valuation_result

ROOT = Path(__file__).resolve().parents[2]
MISSING = [
    "Roan: no source-backed saleable-output/recovery and realization bridge for the FY2027 contained-copper guidance",
    "Forecast: no complete year-by-year revenue, operating/corporate cost, sustaining/growth capex and working-capital schedule",
    "Discounting: no eligible currency-consistent WACC components or documented permitted override",
    "Terminal value: no supported long-term growth or EBITDA/exit-multiple basis",
    "SOTP: Roan, Molefe and Project G lack complete distinct attributable asset values and risk/timing schedules",
    "LWP consideration: $35m staged and $30m accelerated alternatives lack final payment dates and completion/counterparty probabilities",
    "South African disposal: deferred instalments require an updated outstanding balance, payment schedule and probability after $25m cash received",
    "Equity bridge: no verified valuation-date cash, debt, leases, minorities and central adjustments",
    "Commodity/FX: no eligible long-term price/realization and matching forecast currency treatment",
]


def inspect() -> dict:
    old = json.loads((ROOT / "tmp/jubilee_phase1_audit.json").read_text(encoding="utf-8"))
    fixture = json.loads((ROOT / "gui/modules/analysis/tests/fixtures/jubilee_phase2_metrics.json").read_text(encoding="utf-8"))
    sources = [FinancialMetric.model_validate(x) for x in fixture]
    legacy, _ = structure_report_metrics("JBL.JO", old["report_id"], old["audit"])
    report_id = old["report_id"]
    eligible = [
        candidate(sources[0], report_id, "production_volume", "base", "Roan FY2027 formal guidance midpoint"),
        candidate(sources[6], report_id, "current_issued_shares", "base", "Newer issued shares; dilution warning"),
    ]
    result = run_valuation(ticker="JBL.JO", report_version_id=report_id,
        candidates=eligible, metrics=legacy + sources, valuation_date=date(2026, 9, 18),
        legacy_gemini_target=Decimal("1.70"), legacy_target_derivation="carried_forward",
        missing_input_reasons=MISSING)
    schedule = [
        {"boundary": "Roan", "available": "FY2027 2,850?3,150t contained copper formal guidance",
         "source": "sens:5513", "missing": "saleable conversion, realization, forecast cost/capex and FCF", "value": None},
        {"boundary": "Molefe", "available": "10,000t/month ROM management target; ~1,740tpa contained copper indication",
         "source": "sens:5513", "missing": "sourced saleable ramp, capex, operating cost and risked NPV", "value": None},
        {"boundary": "Project G", "available": "Development and trial activity described",
         "source": "sens:5513", "missing": "resource-backed production, development timing/capex and project economics", "value": None},
        {"boundary": "Large Waste Project", "available": "$35m staged or $30m accelerated conditional sale",
         "source": "sens:5513", "missing": "final payment dates, probabilities and selected settlement structure", "value": None},
        {"boundary": "South African disposal receivable", "available": "$25m cash instalments received by February 2026",
         "source": "sens:1701", "missing": "verified remaining amount, exact future dates and probability", "value": None},
        {"boundary": "Cash/debt", "available": None, "source": None,
         "missing": "current consolidated cash, debt and lease position", "value": None},
        {"boundary": "Corporate/central", "available": None, "source": None,
         "missing": "forecast central cost, liabilities and equity adjustments", "value": None},
    ]
    payload = result.model_dump(mode="json")
    payload["jubilee_input_schedule"] = {
        "eligible": [{"name": "Roan FY2027 contained-copper guidance midpoint", "value": "3000",
                      "unit": "tonnes_contained_metal", "source": "sens:5513", "metric_id": str(sources[0].metric_id)},
                     {"name": "current issued shares", "value": "3381330240", "unit": "shares",
                      "source": "sens:4955", "metric_id": str(sources[6].metric_id)}],
        "excluded": [
            {"name": "legacy 12,000t copper", "reason": "unresolved stage and provenance"},
            {"name": "legacy $5,950/t AISC", "reason": "source, period and cost definition unresolved"},
            {"name": "3,146,295,996 shares", "reason": "stale or basis unresolved versus newer issued count"},
            {"name": "legacy 12% WACC", "reason": "components/derivation unavailable"},
            {"name": "legacy 5% growth", "reason": "economic meaning and support unavailable"},
            {"name": "legacy 6x exit multiple", "reason": "terminal metric/basis unavailable"},
        ],
        "historical_reference": [{"name": "FY2026 pre-refining copper", "value": "3739", "unit": "tonnes_contained_metal"},
                                 {"name": "FY2026 cathode", "value": "2120", "unit": "tonnes_saleable_product"},
                                 {"name": "H1 FY2026 copper production cost", "value": "8062", "unit": "USD_per_tonne",
                                  "period_end": "2025-12-31", "note": "production cost, not AISC"}],
    }
    payload["jubilee_sotp_components"] = schedule
    payload["sensitivity"] = {"status": "NOT_CALCULABLE", "reason": "No calculable base DCF or SOTP"}
    payload["inspection_only"] = True
    payload["comparison_data_note"] = "Curated company-disclosure comparisons were not supplied to the legacy Gemini generation."
    return payload


async def persist(payload: dict):
    from modules.data.valuation_results import save_valuation_result
    from modules.analysis.valuation.models import ValuationResult
    result = ValuationResult.model_validate({k: v for k, v in payload.items() if k in ValuationResult.model_fields})
    await save_valuation_result(result)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,default=ROOT/"tmp/jubilee_phase4_valuation.json")
    parser.add_argument("--persist",action="store_true",help="Append NOT_CALCULABLE valuation to deterministic history")
    args=parser.parse_args()
    payload=inspect()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(payload,indent=2)+"\n",encoding="utf-8")
    from modules.analysis.valuation.models import ValuationResult
    result=ValuationResult.model_validate({k: v for k,v in payload.items() if k in ValuationResult.model_fields})
    lines=[render_valuation_result(result),"", "JUBILEE COMPONENT AVAILABILITY"]
    for component in payload["jubilee_sotp_components"]:
        lines.append(f"{component['boundary']}: NOT_CALCULABLE ? {component['missing']}")
    args.output.with_suffix(".txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    if args.persist:
        asyncio.run(persist(payload))
    print(f"JBL.JO: {result.status.value}; no deterministic target; {args.output}")


if __name__=="__main__":main()
