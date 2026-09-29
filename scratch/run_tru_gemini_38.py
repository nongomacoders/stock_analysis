"""Run TRU FY2025 AFS Pipeline with Gemini 3.8 Flash Mode A and produce durable audit artifact.
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

from core.config import DB_CONFIG
from modules.analysis.afs_pipeline.gemini_semantic_engine import (
    MODE_A_SCHEMA,
    PROMPT_VERSION_MODE_A,
)
from modules.analysis.afs_pipeline.pipeline import run_afs_evidence_pipeline
from modules.analysis.afs_pipeline.reference_loader import load_frozen_reference_facts
from modules.analysis.afs_pipeline.reference_validation import (
    ValidationStatus,
    validate_pipeline_against_frozen_references,
)

PDF_PATH = r"C:\Users\Dion\Desktop\Projects\stock_analysis\gui\results_history\TRU\FY2025\TRU_FY2025_AFS.pdf"
DURABLE_DIR = r"C:\Users\Dion\Desktop\Projects\stock_analysis\gui\results_history\TRU\FY2025\afs_experiments"
os.makedirs(DURABLE_DIR, exist_ok=True)
DURABLE_ARTIFACT_PATH = os.path.join(DURABLE_DIR, "gemini_38_mode_a_audit.json")


def compute_file_sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


async def main():
    logger.info("=== STARTING TRU FY2025 GEMINI 3.8 FLASH VALIDATION RUN ===")
    git_commit_hash = "282b74ee00b5f98cfb3d9cb56cbf96e0224591de"
    afs_sha256 = compute_file_sha256(PDF_PATH)
    logger.info("AFS SHA-256: %s", afs_sha256)

    # 1. Load Frozen Reference Truth (18 facts)
    logger.info("Loading frozen reference facts for TRU FY2025...")
    ref_facts = load_frozen_reference_facts("TRU", "FY2025")
    logger.info("Loaded frozen reference truth.")

    # 2. Run Gemini Mode A with Gemini 3.8 Flash
    logger.info("Executing Gemini 3.8 Flash Mode A pipeline...")
    t0 = time.perf_counter()
    pipeline_result = await run_afs_evidence_pipeline(
        pdf_path=PDF_PATH,
        ticker="TRU",
        company="Truworths International Ltd",
        financial_period="FY2025",
        publication_datetime="2025-08-28T07:00:00+00:00",
        run_gemini_passes=True,
        semantic_engine="gemini",
        gemini_mode="mode_a",
        is_mining=False,
    )
    total_runtime_s = time.perf_counter() - t0
    logger.info("Pipeline completed in %.2fs.", total_runtime_s)

    # 3. Validate against 18 reference facts
    val_results = validate_pipeline_against_frozen_references(pipeline_result, ref_facts)
    correct_count = sum(1 for v in val_results if v.status == ValidationStatus.CORRECT)
    missed_count = sum(1 for v in val_results if v.status == ValidationStatus.MISSED)
    incorrect_count = sum(1 for v in val_results if v.status == ValidationStatus.INCORRECT)
    ambiguous_count = sum(1 for v in val_results if v.status == ValidationStatus.AMBIGUOUS)
    conflicting_count = sum(1 for v in val_results if v.status == ValidationStatus.CONFLICTING)

    logger.info("=== VALIDATION RESULTS ===")
    logger.info("Correct: %d / %d", correct_count, len(val_results))
    logger.info("Missed: %d", missed_count)
    logger.info("Incorrect: %d", incorrect_count)
    logger.info("Ambiguous: %d", ambiguous_count)
    logger.info("Conflicting: %d", conflicting_count)

    for v in val_results:
        logger.info("  [%s] %s: expected=%s, extracted=%s (Note: %s, p.%s, ev: %s)",
                    v.status.value, v.fact_name, v.expected_value, v.extracted_value,
                    v.note_reference, v.page_number, v.evidence_id)

    # 4. Calculate review burden breakdown
    rec_report = pipeline_result.reconciliation_report
    unresolved_mandatory = getattr(rec_report, "unresolved_mandatory_categories", [])
    
    # Categories defined as mandatory for retail
    all_mandatory = [
        "revenue", "sales", "profit", "margins", "tax", "capex",
        "working_capital", "cash", "debt", "leases", "shares", "depreciation_amortisation"
    ]
    resolved_mandatory = [cat for cat in all_mandatory if cat not in unresolved_mandatory]
    
    auto_review_queue_count = len(rec_report.review_candidates)
    manual_review_required_count = auto_review_queue_count + missed_count + len(unresolved_mandatory)

    review_burden = {
        "resolved_mandatory_categories": resolved_mandatory,
        "unresolved_mandatory_categories": unresolved_mandatory,
        "automatic_review_queue_count": auto_review_queue_count,
        "missed_reference_facts": missed_count,
        "manual_review_required_count": manual_review_required_count,
    }

    # 5. Schema and Prompt Hashes
    schema_str = json.dumps(MODE_A_SCHEMA, sort_keys=True)
    schema_sha256 = hashlib.sha256(schema_str.encode("utf-8")).hexdigest()
    prompt_hash = hashlib.sha256(PROMPT_VERSION_MODE_A.encode("utf-8")).hexdigest()

    # 6. Assemble Durable Audit Artifact
    audit_artifact = {
        "metadata": {
            "title": "TRU FY2025 Gemini 3.8 Flash Mode A AFS Extraction Audit",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "git_commit": git_commit_hash,
            "afs_sha256": afs_sha256,
            "document": "TRU_FY2025_AFS.pdf",
            "ticker": "TRU",
            "period": "FY2025",
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
            "incorrect_facts_count": incorrect_count,
            "ambiguous_facts_count": ambiguous_count,
            "conflicting_facts_count": conflicting_count,
            "accuracy_pct": round((correct_count / len(val_results)) * 100, 2),
            "validations": [v.to_dict() for v in val_results],
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
            "findings_count": len(pipeline_result.challenge_report.findings),
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
    logger.info("=== FINISHED TRU FY2025 RUN ===")


if __name__ == "__main__":
    asyncio.run(main())
