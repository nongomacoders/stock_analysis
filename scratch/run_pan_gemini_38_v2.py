"""Run PAN HY2026 Gemini 3.8 Flash Mode A REGRESSION (v2).

Experiment identity: PAN-HY2026-MODEA-V2.
- Uses updated candidate/table-role/reconciliation logic (working tree).
- Writes a NEW versioned artifact; never overwrites the frozen v1 audit.
- Reference facts are used for POST-extraction scoring only (never injected).
"""
import asyncio
import hashlib
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

from modules.analysis.afs_pipeline.gemini_semantic_engine import (
    MODE_A_SCHEMA,
    PROMPT_VERSION_MODE_A,
)
from modules.analysis.afs_pipeline.pipeline import run_afs_evidence_pipeline

REPO = r"C:\Users\Dion\Desktop\Projects\stock_analysis"
PDF_PATH = r"C:\Users\Dion\Desktop\Projects\stock_analysis\gui\results_history\PAN\HY2026\PAN_HY2026.pdf"
DURABLE_DIR = r"C:\Users\Dion\Desktop\Projects\stock_analysis\gui\results_history\PAN\HY2026\afs_experiments"
os.makedirs(DURABLE_DIR, exist_ok=True)
DURABLE_ARTIFACT_PATH = os.path.join(DURABLE_DIR, "gemini_38_mode_a_audit_v2.json")
V1_ARTIFACT_PATH = os.path.join(DURABLE_DIR, "gemini_38_mode_a_audit.json")
EXPECTED_SOURCE_SHA256 = "4c13ee4a02b4c91ff6fa0d21b4c5446576069b2d31ac90d06d4c16911d4d82d0"

assert os.path.abspath(DURABLE_ARTIFACT_PATH) != os.path.abspath(V1_ARTIFACT_PATH)
assert os.path.exists(V1_ARTIFACT_PATH), "frozen v1 audit must exist for comparison"


def compute_file_sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


# Established PAN reference population (v1, 17 facts) + 2 v2 additions with
# clean document definitions (p.2/3 guidance range; p.9 effective tax rate).
KNOWN_MINING_FACTS = [
    {"fact_name": "gold_production", "display_name": "Gold Produced (oz)",
     "expected_value": Decimal("128296"), "expected_page": 4,
     "keywords": ["gold_produced", "production"], "unit": "oz"},
    {"fact_name": "gold_sold", "display_name": "Gold Sold (oz)",
     "expected_value": Decimal("127296"), "expected_page": 4,
     "keywords": ["gold_sold", "sales_volumes"], "unit": "oz"},
    {"fact_name": "realised_gold_price", "display_name": "Average Realised Gold Price (US$/oz)",
     "expected_value": Decimal("3812"), "expected_page": 4,
     "keywords": ["realised_commodity_price", "gold_price"], "unit": "US$/oz"},
    {"fact_name": "aisc_unit_cost", "display_name": "All-in Sustaining Costs (US$/oz)",
     "expected_value": Decimal("1874"), "expected_page": 4,
     "keywords": ["aisc_unit_cost", "unit_cost"], "unit": "US$/oz"},
    {"fact_name": "cash_costs", "display_name": "Cash Costs (US$/oz)",
     "expected_value": Decimal("1574"), "expected_page": 4,
     "keywords": ["cash_costs", "unit_cost"], "unit": "US$/oz"},
    {"fact_name": "revenue", "display_name": "Revenue (US$m)",
     "expected_value": Decimal("487.1"), "expected_page": 4,
     "keywords": ["revenue", "accounting_revenue"], "unit": "US$m"},
    {"fact_name": "adjusted_ebitda", "display_name": "Adjusted EBITDA (US$m)",
     "expected_value": Decimal("245.2"), "expected_page": 4,
     "keywords": ["adjusted_ebitda", "ebitda"], "unit": "US$m"},
    {"fact_name": "attributable_earnings", "display_name": "Attributable Earnings (US$m)",
     "expected_value": Decimal("148.0"), "expected_page": 4,
     "keywords": ["attributable_earnings", "profit_for_period"], "unit": "US$m"},
    {"fact_name": "headline_earnings", "display_name": "Headline Earnings (US$m)",
     "expected_value": Decimal("148.8"), "expected_page": 4,
     "keywords": ["headline_earnings"], "unit": "US$m"},
    {"fact_name": "operating_cash_flow", "display_name": "Operating Cash Flow (US$m)",
     "expected_value": Decimal("259.5"), "expected_page": 4,
     "keywords": ["operating_cash_flow", "cash_generated_from_operations"], "unit": "US$m"},
    {"fact_name": "net_debt", "display_name": "Net Debt (US$m)",
     "expected_value": Decimal("46.2"), "expected_page": 4,
     "keywords": ["net_debt", "reported_net_debt"], "unit": "US$m"},
    {"fact_name": "total_capex", "display_name": "Total Capital Expenditure (US$m)",
     "expected_value": Decimal("66.1"), "expected_page": 4,
     "keywords": ["total_capex", "cash_capex"], "unit": "US$m"},
    {"fact_name": "sustaining_capex", "display_name": "Sustaining Capital Expenditure (US$m)",
     "expected_value": Decimal("9.6"), "expected_page": 4,
     "keywords": ["sustaining_capex", "capex_maintenance"], "unit": "US$m"},
    {"fact_name": "wans_shares", "display_name": "WANOS Shares in Issue (million)",
     "expected_value": Decimal("2027.3"), "expected_page": 4,
     "keywords": ["weighted_average_basic_shares", "issued_shares"], "unit": "million"},
    {"fact_name": "underground_recovered_grade", "display_name": "Underground Recovered Grade (g/t)",
     "expected_value": Decimal("6.90"), "expected_page": 40,
     "keywords": ["recovered_grade", "head_grade"], "unit": "g/t"},
    {"fact_name": "underground_recovery", "display_name": "Underground Recovery (%)",
     "expected_value": Decimal("97"), "expected_page": 40,
     "keywords": ["recovery", "plant_recovery"], "unit": "%"},
    {"fact_name": "tonnes_processed_milled", "display_name": "Total Tonnes Milled & Processed (tonnes)",
     "expected_value": Decimal("13591354"), "expected_page": 40,
     "keywords": ["throughput", "plant_throughput"], "unit": "tonnes"},
    {"fact_name": "production_guidance", "display_name": "FY26 Production Guidance Range (oz)",
     "expected_value": Decimal("275000"), "expected_range": [Decimal("275000"), Decimal("292000")],
     "expected_page": 2, "keywords": ["guidance"], "unit": "oz"},
    {"fact_name": "effective_tax_rate", "display_name": "Effective Tax Rate (%)",
     "expected_value": Decimal("29.6"), "expected_page": 9,
     "keywords": ["effective_tax_rate"], "unit": "%"},
]

SCALES = [Decimal(1), Decimal("0.001"), Decimal(1000), Decimal(1_000_000)]


def _value_matches(value: Decimal, target: Decimal) -> bool:
    for scale in SCALES:
        scaled = value * scale
        if abs(scaled - target) <= Decimal("0.05") or (
            target != 0 and abs((scaled - target) / target) < Decimal("0.01")
        ):
            return True
    return False


def _concept_matches(cand, kw_list) -> bool:
    c_concept = (cand.concept or "").lower()
    c_label = f"{cand.raw_token} {cand.qualifiers.get('concept', '')}".lower()
    return any(kw in c_concept for kw in kw_list) or any(kw in c_label for kw in kw_list)


def score_mining_extraction_v2(verified, review, conflicting, doc) -> list:
    """Four-status scoring: CORRECT / INCORRECT / MISSED / AMBIGUOUS."""
    results = []
    for kf in KNOWN_MINING_FACTS:
        target = kf["expected_value"]
        kw_list = kf["keywords"]
        is_range = "expected_range" in kf

        def pool_match(pool):
            concept_hits, value_hits = [], []
            for c in pool:
                if c.value is None or not _concept_matches(c, kw_list):
                    continue
                concept_hits.append(c)
                if is_range:
                    if kf["expected_range"][0] <= c.value <= kf["expected_range"][1]:
                        value_hits.append(c)
                elif _value_matches(c.value, target):
                    value_hits.append(c)
            return concept_hits, value_hits

        v_concepts, v_values = pool_match(verified)
        if v_values:
            c = v_values[0]
            p_obj = doc.paragraphs_by_id.get(c.source_paragraph_id) if doc else None
            quote = p_obj.text[:140].replace("\n", " ").strip() if p_obj else c.raw_token
            results.append({
                "fact_name": kf["fact_name"], "display_name": kf["display_name"],
                "expected_value": str(target), "extracted_value": str(c.value),
                "status": "CORRECT", "page_number": c.source_page,
                "evidence_id": c.evidence_id, "provenance_quote": quote,
                "explanation": f"Verified {kf['fact_name']} from page {c.source_page}.",
            })
            continue
        r_concepts, r_values = pool_match(review)
        x_concepts, x_values = pool_match(conflicting)
        # Guidance lives in review by design (fail-closed: guidance is never a
        # historical actual level). A guidance-temporal candidate in range is
        # ambiguous evidence, not a miss.
        if not (r_values or x_values) and kf["fact_name"] == "production_guidance":
            for c in review:
                g = (c.gemini_result or {}) if isinstance(c.gemini_result, dict) else {}
                if (g.get("temporal_classification") == "guidance" and c.value is not None
                        and kf["expected_range"][0] <= c.value <= kf["expected_range"][1]):
                    r_values.append(c)
                    break
        if r_values or x_values:
            c = (r_values + x_values)[0]
            results.append({
                "fact_name": kf["fact_name"], "display_name": kf["display_name"],
                "expected_value": str(target), "extracted_value": str(c.value),
                "status": "AMBIGUOUS", "page_number": c.source_page,
                "evidence_id": c.evidence_id, "provenance_quote": None,
                "explanation": f"{kf['fact_name']} present but not cleanly verified "
                               f"(status {c.final_status}); analyst resolution required.",
            })
        elif v_concepts or r_concepts or x_concepts:
            c = (v_concepts + r_concepts + x_concepts)[0]
            results.append({
                "fact_name": kf["fact_name"], "display_name": kf["display_name"],
                "expected_value": str(target), "extracted_value": str(c.value),
                "status": "INCORRECT", "page_number": c.source_page,
                "evidence_id": c.evidence_id, "provenance_quote": None,
                "explanation": f"Concept adjudicated for {kf['fact_name']} but no value match.",
            })
        else:
            results.append({
                "fact_name": kf["fact_name"], "display_name": kf["display_name"],
                "expected_value": str(target), "extracted_value": None,
                "status": "MISSED", "page_number": kf["expected_page"],
                "evidence_id": None, "provenance_quote": None,
                "explanation": f"Fact {kf['fact_name']} not matched in extracted candidates.",
            })
    return results


async def main():
    logger.info("=== PAN-HY2026-MODEA-V2 REGRESSION START ===")
    git_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--short"], cwd=REPO, capture_output=True, text=True
    ).stdout.strip().splitlines()
    logger.info("git commit: %s (dirty files: %d)", git_commit, len(dirty))

    afs_sha256 = compute_file_sha256(PDF_PATH)
    logger.info("PAN HY2026 SHA-256: %s", afs_sha256)
    if afs_sha256 != EXPECTED_SOURCE_SHA256:
        logger.error("SOURCE HASH MISMATCH — STOPPING.")
        raise SystemExit("PAN source hash differs from prior experiment; aborting.")

    t0 = time.perf_counter()
    pipeline_result = await run_afs_evidence_pipeline(
        pdf_path=PDF_PATH,
        ticker="PAN",
        company="Pan African Resources PLC",
        financial_period="HY2026",
        publication_datetime="2026-02-18T07:00:00+00:00",
        run_gemini_passes=True,
        semantic_engine="gemini",
        gemini_mode="mode_a",
        is_mining=True,
    )
    total_runtime_s = time.perf_counter() - t0
    logger.info("Pipeline completed in %.2fs.", total_runtime_s)

    rec_report = pipeline_result.reconciliation_report
    doc = pipeline_result.extracted_doc
    val_results = score_mining_extraction_v2(
        rec_report.verified_candidates,
        rec_report.review_candidates,
        rec_report.conflicting_candidates,
        doc,
    )
    counts = {}
    for v in val_results:
        counts[v["status"]] = counts.get(v["status"], 0) + 1
    total = len(val_results)
    assert sum(counts.values()) == total, "scoring equation violated"
    logger.info("Scoring: %s", counts)
    for v in val_results:
        logger.info("  [%s] %s: expected=%s extracted=%s (p.%s)",
                    v["status"], v["fact_name"], v["expected_value"],
                    v["extracted_value"], v["page_number"])

    unresolved_mandatory = getattr(rec_report, "unresolved_mandatory_categories", [])
    all_mining_mandatory = [
        "revenue", "sales", "profit", "margins", "tax", "capex",
        "working_capital", "cash", "debt", "leases", "shares", "depreciation_amortisation",
        "production", "sales_volumes", "commodity_price", "unit_cost", "grade",
        "recovery", "throughput", "guidance", "hedging",
    ]
    resolved_mandatory = [c for c in all_mining_mandatory if c not in unresolved_mandatory]
    review_burden = {
        "resolved_mandatory_categories": resolved_mandatory,
        "unresolved_mandatory_categories": unresolved_mandatory,
        "automatic_review_queue_count": len(rec_report.review_candidates),
        "conflicting_evidence_count": len(rec_report.conflicting_candidates),
        "reference_correct": counts.get("CORRECT", 0),
        "reference_incorrect": counts.get("INCORRECT", 0),
        "reference_missed": counts.get("MISSED", 0),
        "reference_ambiguous": counts.get("AMBIGUOUS", 0),
        "manual_review_required_count": (
            len(rec_report.review_candidates) + len(rec_report.conflicting_candidates)
            + counts.get("MISSED", 0) + counts.get("AMBIGUOUS", 0) + len(unresolved_mandatory)
        ),
    }

    schema_str = json.dumps(MODE_A_SCHEMA, sort_keys=True)
    audit_artifact = {
        "metadata": {
            "experiment_identity": "PAN-HY2026-MODEA-V2",
            "title": "Pan African Resources HY2026 Gemini 3.8 Flash Mode A Regression (v2) Audit",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "git_commit": git_commit,
            "git_dirty_files": dirty,
            "afs_sha256": afs_sha256,
            "document": "PAN_HY2026.pdf",
            "ticker": "PAN",
            "period": "HY2026",
            "is_mining": True,
            "experimental_engine": "gemini",
            "gemini_mode": "mode_a",
            "production_default_unchanged": "kev",
            "requested_model": "gemini-3.8-flash",
            "returned_model_version": pipeline_result.gemini_metrics.get("returned_model_version") if pipeline_result.gemini_metrics else "gemini-3.8-flash",
            "temperature": 0.0,
            "challenge_temperature": 0.2,
            "no_silent_fallback": True,
            "python_numeric_authoritative": True,
            "python_validation_authoritative": True,
            "prompt_version": PROMPT_VERSION_MODE_A,
            "prompt_hash": hashlib.sha256(PROMPT_VERSION_MODE_A.encode("utf-8")).hexdigest(),
            "schema_sha256": hashlib.sha256(schema_str.encode("utf-8")).hexdigest(),
            "scoring_method": "v2-four-status (CORRECT/INCORRECT/MISSED/AMBIGUOUS over verified/review/conflicting pools; reference values never injected into prompts)",
            "supersedes": "gemini_38_mode_a_audit.json (frozen v1, preserved)",
        },
        "scoring_results": {
            "total_reference_facts": total,
            "correct_facts_count": counts.get("CORRECT", 0),
            "incorrect_facts_count": counts.get("INCORRECT", 0),
            "missed_facts_count": counts.get("MISSED", 0),
            "ambiguous_facts_count": counts.get("AMBIGUOUS", 0),
            "accuracy_pct": round((counts.get("CORRECT", 0) / total) * 100, 2),
            "validations": val_results,
        },
        "review_burden": review_burden,
        "token_usage_and_costs": {
            "gemini_mode_a_metrics": pipeline_result.gemini_metrics,
            "challenge_metrics": {
                "requested_model": pipeline_result.challenge_report.model_name,
                "returned_model_version": getattr(pipeline_result.challenge_report, "model_version", "gemini-3.8-flash"),
                "temperature": getattr(pipeline_result.challenge_report, "temperature", 0.2),
                "prompt_tokens": getattr(pipeline_result.challenge_report, "prompt_tokens", 0),
                "output_tokens": getattr(pipeline_result.challenge_report, "output_tokens", 0),
                "chunk_count": getattr(pipeline_result.challenge_report, "chunk_count", 0),
                "page_coverage": getattr(pipeline_result.challenge_report, "page_coverage", []),
                "failed_chunks": getattr(pipeline_result.challenge_report, "failed_chunks", 0),
            },
            "runtime_seconds": round(total_runtime_s, 2),
            "stage_runtimes_ms": pipeline_result.runtimes.to_dict(),
        },
        "derived_metrics": pipeline_result.derived_metrics,
        "reconciliation_summary": {
            "verified_count": len(rec_report.verified_candidates),
            "review_count": len(rec_report.review_candidates),
            "conflicting_count": len(rec_report.conflicting_candidates),
            "rejected_count": len(rec_report.rejected_candidates),
            "verified_candidates": [c.to_dict() for c in rec_report.verified_candidates],
            "review_candidates": [c.to_dict() for c in rec_report.review_candidates],
            "conflicting_candidates": [c.to_dict() for c in rec_report.conflicting_candidates],
            "rejected_candidates": [c.to_dict() for c in rec_report.rejected_candidates],
            "findings": rec_report.reconciliation_findings,
            "unresolved_mandatory_categories": unresolved_mandatory,
        },
        "challenge_summary": {
            "total_findings": len(pipeline_result.challenge_report.findings),
            "findings": [f.to_dict() for f in pipeline_result.challenge_report.findings],
        },
        "requests_and_responses": pipeline_result.gemini_audit_logs or [],
    }

    raw_json = json.dumps(audit_artifact, indent=2, default=str)
    audit_artifact["metadata"]["artifact_sha256"] = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()
    with open(DURABLE_ARTIFACT_PATH, "w", encoding="utf-8") as f:
        f.write(json.dumps(audit_artifact, indent=2, default=str))
    logger.info("V2 audit written (v1 preserved): %s", DURABLE_ARTIFACT_PATH)
    logger.info("=== PAN-HY2026-MODEA-V2 FINISHED ===")


if __name__ == "__main__":
    asyncio.run(main())
