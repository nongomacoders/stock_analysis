"""Run Pan African Resources HY2026 Mining Cross-Sector Validation with Gemini 3.8 Flash Mode A.
Produces durable audit artifact:
gui/results_history/PAN/HY2026/afs_experiments/gemini_38_mode_a_audit.json
"""
import asyncio
import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

from modules.analysis.afs_pipeline.gemini_semantic_engine import (
    MODE_A_SCHEMA,
    PROMPT_VERSION_MODE_A,
)
from modules.analysis.afs_pipeline.pipeline import run_afs_evidence_pipeline

PDF_PATH = r"C:\Users\Dion\Desktop\Projects\stock_analysis\gui\results_history\PAN\HY2026\PAN_HY2026.pdf"
DURABLE_DIR = r"C:\Users\Dion\Desktop\Projects\stock_analysis\gui\results_history\PAN\HY2026\afs_experiments"
os.makedirs(DURABLE_DIR, exist_ok=True)
DURABLE_ARTIFACT_PATH = os.path.join(DURABLE_DIR, "gemini_38_mode_a_audit.json")


def compute_file_sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


# Ground-truth mining operational and financial facts for PAN HY2026 (for post-extraction scoring only)
KNOWN_MINING_FACTS = [
    {
        "fact_name": "gold_production",
        "display_name": "Gold Produced (oz)",
        "expected_value": Decimal("128296"),
        "expected_page": 4,
        "keywords": ["gold_produced", "production"],
        "unit": "oz",
    },
    {
        "fact_name": "gold_sold",
        "display_name": "Gold Sold (oz)",
        "expected_value": Decimal("127296"),
        "expected_page": 4,
        "keywords": ["gold_sold", "sales_volumes"],
        "unit": "oz",
    },
    {
        "fact_name": "realised_gold_price",
        "display_name": "Average Realised Gold Price (US$/oz)",
        "expected_value": Decimal("3812"),
        "expected_page": 4,
        "keywords": ["realised_commodity_price", "gold_price"],
        "unit": "US$/oz",
    },
    {
        "fact_name": "aisc_unit_cost",
        "display_name": "All-in Sustaining Costs (US$/oz)",
        "expected_value": Decimal("1874"),
        "expected_page": 4,
        "keywords": ["aisc_unit_cost", "unit_cost"],
        "unit": "US$/oz",
    },
    {
        "fact_name": "cash_costs",
        "display_name": "Cash Costs (US$/oz)",
        "expected_value": Decimal("1574"),
        "expected_page": 4,
        "keywords": ["cash_costs", "unit_cost"],
        "unit": "US$/oz",
    },
    {
        "fact_name": "revenue",
        "display_name": "Revenue (US$m)",
        "expected_value": Decimal("487.1"),
        "expected_page": 4,
        "keywords": ["revenue", "accounting_revenue"],
        "unit": "US$m",
    },
    {
        "fact_name": "adjusted_ebitda",
        "display_name": "Adjusted EBITDA (US$m)",
        "expected_value": Decimal("245.2"),
        "expected_page": 4,
        "keywords": ["adjusted_ebitda", "ebitda"],
        "unit": "US$m",
    },
    {
        "fact_name": "attributable_earnings",
        "display_name": "Attributable Earnings (US$m)",
        "expected_value": Decimal("148.0"),
        "expected_page": 4,
        "keywords": ["attributable_earnings", "profit_for_period"],
        "unit": "US$m",
    },
    {
        "fact_name": "headline_earnings",
        "display_name": "Headline Earnings (US$m)",
        "expected_value": Decimal("148.8"),
        "expected_page": 4,
        "keywords": ["headline_earnings"],
        "unit": "US$m",
    },
    {
        "fact_name": "operating_cash_flow",
        "display_name": "Operating Cash Flow (US$m)",
        "expected_value": Decimal("259.5"),
        "expected_page": 4,
        "keywords": ["operating_cash_flow", "cash_generated_from_operations"],
        "unit": "US$m",
    },
    {
        "fact_name": "net_debt",
        "display_name": "Net Debt (US$m)",
        "expected_value": Decimal("46.2"),
        "expected_page": 4,
        "keywords": ["net_debt", "reported_net_debt"],
        "unit": "US$m",
    },
    {
        "fact_name": "total_capex",
        "display_name": "Total Capital Expenditure (US$m)",
        "expected_value": Decimal("66.1"),
        "expected_page": 4,
        "keywords": ["total_capex", "cash_capex"],
        "unit": "US$m",
    },
    {
        "fact_name": "sustaining_capex",
        "display_name": "Sustaining Capital Expenditure (US$m)",
        "expected_value": Decimal("9.6"),
        "expected_page": 4,
        "keywords": ["sustaining_capex", "capex_maintenance"],
        "unit": "US$m",
    },
    {
        "fact_name": "wans_shares",
        "display_name": "WANOS Shares in Issue (million)",
        "expected_value": Decimal("2027.3"),
        "expected_page": 4,
        "keywords": ["weighted_average_basic_shares", "issued_shares"],
        "unit": "million",
    },
    {
        "fact_name": "underground_recovered_grade",
        "display_name": "Underground Recovered Grade (g/t)",
        "expected_value": Decimal("6.90"),
        "expected_page": 40,
        "keywords": ["recovered_grade", "head_grade"],
        "unit": "g/t",
    },
    {
        "fact_name": "underground_recovery",
        "display_name": "Underground Recovery (%)",
        "expected_value": Decimal("97"),
        "expected_page": 40,
        "keywords": ["recovery", "plant_recovery"],
        "unit": "%",
    },
    {
        "fact_name": "tonnes_processed_milled",
        "display_name": "Total Tonnes Milled & Processed (tonnes)",
        "expected_value": Decimal("13591354"),
        "expected_page": 40,
        "keywords": ["throughput", "plant_throughput"],
        "unit": "tonnes",
    },
]


def score_mining_extraction(candidates, doc) -> list:
    """Score extracted candidates against known mining facts post-extraction."""
    validation_results = []
    
    for kf in KNOWN_MINING_FACTS:
        target_val = kf["expected_value"]
        kw_list = kf["keywords"]
        matched_cand = None
        
        for c in candidates:
            c_concept = (c.concept or "").lower()
            c_label = f"{c.raw_token} {c.qualifiers.get('concept', '')} {c.qualifiers.get('nearby_label', '')}".lower()
            
            # Check concept match
            concept_match = any(kw in c_concept for kw in kw_list) or any(kw in c_label for kw in kw_list)
            if not concept_match:
                continue
            
            # Check value match with scaling tolerance
            if c.value is not None:
                for scale in [Decimal(1), Decimal("0.001"), Decimal(1000), Decimal(1_000_000)]:
                    scaled_val = c.value * scale
                    if abs(scaled_val - target_val) <= Decimal("0.05") or (target_val != 0 and abs((scaled_val - target_val) / target_val) < Decimal("0.01")):
                        matched_cand = c
                        break
            if matched_cand:
                break
                
        if matched_cand:
            p_obj = doc.paragraphs_by_id.get(matched_cand.source_paragraph_id) if doc else None
            quote = p_obj.text[:140].replace("\n", " ").strip() if p_obj else matched_cand.raw_token
            validation_results.append({
                "fact_name": kf["fact_name"],
                "display_name": kf["display_name"],
                "expected_value": str(target_val),
                "extracted_value": str(matched_cand.value),
                "status": "CORRECT",
                "page_number": matched_cand.source_page,
                "evidence_id": matched_cand.evidence_id,
                "provenance_quote": quote,
                "explanation": f"Matched {kf['fact_name']} from page {matched_cand.source_page}.",
            })
        else:
            validation_results.append({
                "fact_name": kf["fact_name"],
                "display_name": kf["display_name"],
                "expected_value": str(target_val),
                "extracted_value": None,
                "status": "MISSED",
                "page_number": kf["expected_page"],
                "evidence_id": None,
                "provenance_quote": None,
                "explanation": f"Fact {kf['fact_name']} not matched in active verified candidates.",
            })
            
    return validation_results


async def main():
    logger.info("=== STARTING PAN AFRICAN RESOURCES HY2026 CROSS-SECTOR TEST ===")
    git_commit_hash = "282b74ee00b5f98cfb3d9cb56cbf96e0224591de"
    afs_sha256 = compute_file_sha256(PDF_PATH)
    logger.info("PAN HY2026 SHA-256: %s", afs_sha256)

    # 1. Run Pipeline with is_mining=True, gemini-3.8-flash Mode A
    logger.info("Executing Gemini 3.8 Flash Mode A pipeline on PAN HY2026 (45 pages)...")
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
    logger.info("PAN HY2026 Pipeline completed in %.2fs.", total_runtime_s)

    # 2. Score against ground-truth mining operational and financial facts
    rec_report = pipeline_result.reconciliation_report
    active_cands = rec_report.verified_candidates + rec_report.review_candidates
    doc = pipeline_result.extracted_doc
    val_results = score_mining_extraction(active_cands, doc)

    correct_count = sum(1 for v in val_results if v["status"] == "CORRECT")
    missed_count = sum(1 for v in val_results if v["status"] == "MISSED")

    logger.info("=== MINING VALIDATION RESULTS ===")
    logger.info("Correct: %d / %d", correct_count, len(val_results))
    logger.info("Missed: %d", missed_count)

    for v in val_results:
        logger.info("  [%s] %s: expected=%s, extracted=%s (p.%s, ev: %s)",
                    v["status"], v["fact_name"], v["expected_value"], v["extracted_value"],
                    v["page_number"], v["evidence_id"])

    # 3. Assess Cross-Sector Coverage Requirements:
    # production, sold oz, realised price, aisc, grades, recoveries, throughput, capex, net debt, leases, shares, tax, hedging, guidance, bottlenecks, caveats
    unresolved_mandatory = getattr(rec_report, "unresolved_mandatory_categories", [])
    all_mining_mandatory = [
        "revenue", "sales", "profit", "margins", "tax", "capex",
        "working_capital", "cash", "debt", "leases", "shares", "depreciation_amortisation",
        "production", "sales_volumes", "commodity_price", "unit_cost", "grade",
        "recovery", "throughput", "guidance", "hedging"
    ]
    resolved_mandatory = [cat for cat in all_mining_mandatory if cat not in unresolved_mandatory]

    review_burden = {
        "resolved_mandatory_categories": resolved_mandatory,
        "unresolved_mandatory_categories": unresolved_mandatory,
        "automatic_review_queue_count": len(rec_report.review_candidates),
        "missed_reference_facts": missed_count,
        "manual_review_required_count": len(rec_report.review_candidates) + missed_count + len(unresolved_mandatory),
    }

    # 4. Challenge findings inspection for bottlenecks and caveats
    bottlenecks_findings = [f for f in pipeline_result.challenge_report.findings if f.finding_type in ("BOTTLENECK", "OPERATIONAL_RISK", "ADVERSE_TREND")]
    caveats_findings = [f for f in pipeline_result.challenge_report.findings if f.finding_type in ("HIDDEN_CAVEAT", "COVENANT_RISK", "PROVISION", "POLICY_CHANGE")]

    # 5. Schema and Prompt Hashes
    schema_str = json.dumps(MODE_A_SCHEMA, sort_keys=True)
    schema_sha256 = hashlib.sha256(schema_str.encode("utf-8")).hexdigest()
    prompt_hash = hashlib.sha256(PROMPT_VERSION_MODE_A.encode("utf-8")).hexdigest()

    # 6. Assemble Durable Audit Artifact
    audit_artifact = {
        "metadata": {
            "title": "Pan African Resources HY2026 Gemini 3.8 Flash Mode A Cross-Sector Extraction Audit",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "git_commit": git_commit_hash,
            "afs_sha256": afs_sha256,
            "document": "PAN_HY2026.pdf",
            "ticker": "PAN",
            "period": "HY2026",
            "is_mining": True,
            "requested_model": "gemini-3.8-flash",
            "returned_model_version": pipeline_result.gemini_metrics.get("returned_model_version") if pipeline_result.gemini_metrics else "gemini-3.8-flash",
            "temperature": 0.0,
            "prompt_version": PROMPT_VERSION_MODE_A,
            "prompt_hash": prompt_hash,
            "schema_sha256": schema_sha256,
        },
        "scoring_results": {
            "total_reference_facts": len(val_results),
            "correct_facts_count": correct_count,
            "missed_facts_count": missed_count,
            "accuracy_pct": round((correct_count / len(val_results)) * 100, 2),
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
            "findings": rec_report.reconciliation_findings,
        },
        "challenge_summary": {
            "total_findings": len(pipeline_result.challenge_report.findings),
            "operational_bottlenecks_count": len(bottlenecks_findings),
            "management_caveats_count": len(caveats_findings),
            "findings": [f.to_dict() for f in pipeline_result.challenge_report.findings],
        },
        "requests_and_responses": pipeline_result.gemini_audit_logs or [],
    }

    # Serialize without artifact hash first
    raw_json = json.dumps(audit_artifact, indent=2, default=str)
    artifact_sha256 = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()
    audit_artifact["metadata"]["artifact_sha256"] = artifact_sha256

    final_json = json.dumps(audit_artifact, indent=2, default=str)
    with open(DURABLE_ARTIFACT_PATH, "w", encoding="utf-8") as f:
        f.write(final_json)

    logger.info("Durable audit artifact written to: %s", DURABLE_ARTIFACT_PATH)
    logger.info("Artifact SHA-256: %s", artifact_sha256)
    logger.info("=== FINISHED PAN HY2026 RUN ===")


if __name__ == "__main__":
    asyncio.run(main())
