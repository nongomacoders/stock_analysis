"""Run an explicit source-linked plan; store results separately from Gemini reports."""
import argparse
import asyncio
import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from modules.analysis.financial_metrics import FinancialMetric
from modules.analysis.valuation_preflight import ValuationInputCandidate
from modules.analysis.valuation.engine import ValuationPlan, run_valuation


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--plan", type=Path, required=True, help="Explicit case and calculation schedule JSON")
    p.add_argument("--inputs", type=Path, required=True, help="JSON with metrics and candidates arrays")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--legacy-target", type=Decimal)
    p.add_argument("--persist", action="store_true", help="Append to deterministic_valuations; PASS targets alone receive published_at")
    args = p.parse_args()
    plan = ValuationPlan.model_validate_json(args.plan.read_text(encoding="utf-8"))
    source = json.loads(args.inputs.read_text(encoding="utf-8"))
    metrics = [FinancialMetric.model_validate(row) for row in source["metrics"]]
    candidates = [ValuationInputCandidate.model_validate(row) for row in source["candidates"]]
    result = run_valuation(ticker=plan.ticker, report_version_id=plan.report_version_id,
        candidates=candidates, metrics=metrics, plan=plan,
        legacy_gemini_target=args.legacy_target,
        legacy_target_derivation="historical_context" if args.legacy_target is not None else None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")
    if args.persist:
        from modules.data.valuation_results import save_valuation_result
        asyncio.run(save_valuation_result(result))
    print(f"{plan.ticker}: {result.status.value}; deterministic target {result.target_price or 'unavailable'}")


if __name__ == "__main__":
    main()
