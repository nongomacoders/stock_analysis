"""Run TRU FY2025 Gemini 3.8 Flash Mode A REGRESSION (v2).

Experiment identity: TRU-FY2025-MODEA-V2.
- Shared reconciliation logic changed since v1; this is the retail gate.
- Writes a NEW versioned artifact; never overwrites the frozen v1 TRU audit.
- Expected: 18/18 CORRECT. Below that: STOP, report, no recommendation.
"""
import asyncio
import hashlib
import json
import logging
import os
import subprocess
import time
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

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

REPO = r"C:\Users\Dion\Desktop\Projects\stock_analysis"
PDF_PATH = r"C:\Users\Dion\Desktop\Projects\stock_analysis\gui\results_history\TRU\FY2025\TRU_FY2025_AFS.pdf"
DURABLE_DIR = r"C:\Users\Dion\Desktop\Projects\stock_analysis\gui\results_history\TRU\FY2025\afs_experiments"
os.makedirs(DURABLE_DIR, exist_ok=True)
DURABLE_ARTIFACT_PATH = os.path.join(DURABLE_DIR, "gemini_38_mode_a_audit_v2.json")
V1_ARTIFACT_PATH = os.path.join(DURABLE_DIR, "gemini_38_mode_a_audit.json")

assert os.path.abspath(DURABLE_ARTIFACT_PATH) != os.path.abspath(V1_ARTIFACT_PATH)
assert os.path.exists(V1_ARTIFACT_PATH), "frozen v1 TRU audit must exist"


def compute_file_sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


async def main():
    logger.info("=== TRU-FY2025-MODEA-V2 REGRESSION START ===")
    git_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--short"], cwd=REPO, capture_output=True, text=True
    ).stdout.strip().splitlines()
    afs_sha256 = compute_file_sha256(PDF_PATH)
    logger.info("git commit: %s (dirty files: %d)", git_commit, len(dirty))
    logger.info("TRU AFS SHA-256: %s", afs_sha256)

    ref_facts = load_frozen_reference_facts("TRU", "FY2025")
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

    val_results = validate_pipeline_against_frozen_references(pipeline_result, ref_facts)
    counts = {}
    for v in val_results:
        counts[v.status.value] = counts.get(v.status.value, 0) + 1
    total = len(val_results)
    assert sum(counts.values()) == total, "validation equation violated"
    logger.info("Validation: %s", counts)
    for v in val_results:
        logger.info("  [%s] %s: expected=%s extracted=%s (p.%s)",
                    v.status.value, v.fact_name, v.expected_value,
                    v.extracted_value, v.page_number)

    rec_report = pipeline_result.reconciliation_report
    unresolved_mandatory = getattr(rec_report, "unresolved_mandatory_categories", [])
    schema_str = json.dumps(MODE_A_SCHEMA, sort_keys=True)
    audit_artifact = {
        "metadata": {
            "experiment_identity": "TRU-FY2025-MODEA-V2",
            "title": "TRU FY2025 Gemini 3.8 Flash Mode A Regression (v2) Audit",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "git_commit": git_commit,
            "git_dirty_files": dirty,
            "afs_sha256": afs_sha256,
            "document": "TRU_FY2025_AFS.pdf",
            "ticker": "TRU",
            "period": "FY2025",
            "experimental_engine": "gemini",
            "gemini_mode": "mode_a",
            "production_default_unchanged": "kev",
            "requested_model": "gemini-3.8-flash",
            "returned_model_version": pipeline_result.gemini_metrics.get("returned_model_version") if pipeline_result.gemini_metrics else "gemini-3.8-flash",
            "temperature": 0.0,
            "challenge_temperature": 0.2,
            "prompt_version": PROMPT_VERSION_MODE_A,
            "prompt_hash": hashlib.sha256(PROMPT_VERSION_MODE_A.encode("utf-8")).hexdigest(),
            "schema_sha256": hashlib.sha256(schema_str.encode("utf-8")).hexdigest(),
            "supersedes": "gemini_38_mode_a_audit.json (frozen v1, preserved)",
        },
        "scoring_results": {
            "total_reference_facts": total,
            "status_counts": counts,
            "accuracy_pct": round((counts.get("CORRECT", 0) / total) * 100, 2),
            "validations": [v.to_dict() for v in val_results],
        },
        "review_burden": {
            "unresolved_mandatory_categories": unresolved_mandatory,
            "automatic_review_queue_count": len(rec_report.review_candidates),
            "conflicting_evidence_count": len(rec_report.conflicting_candidates),
        },
        "token_usage_and_costs": {
            "gemini_mode_a_metrics": pipeline_result.gemini_metrics,
            "challenge_metrics": {
                "requested_model": pipeline_result.challenge_report.model_name,
                "returned_model_version": getattr(pipeline_result.challenge_report, "model_version", "gemini-3.8-flash"),
                "temperature": getattr(pipeline_result.challenge_report, "temperature", 0.2),
                "prompt_tokens": getattr(pipeline_result.challenge_report, "prompt_tokens", 0),
                "output_tokens": getattr(pipeline_result.challenge_report, "output_tokens", 0),
                "chunk_count": getattr(pipeline_result.challenge_report, "chunk_count", 0),
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
            "findings": rec_report.reconciliation_findings,
            "unresolved_mandatory_categories": unresolved_mandatory,
        },
        "challenge_summary": {
            "findings_count": len(pipeline_result.challenge_report.findings),
            "findings": [f.to_dict() for f in pipeline_result.challenge_report.findings],
        },
        "requests_and_responses": pipeline_result.gemini_audit_logs or [],
    }
    raw_json = json.dumps(audit_artifact, indent=2, default=str)
    audit_artifact["metadata"]["artifact_sha256"] = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()
    with open(DURABLE_ARTIFACT_PATH, "w", encoding="utf-8") as f:
        f.write(json.dumps(audit_artifact, indent=2, default=str))
    logger.info("V2 TRU audit written (v1 preserved): %s", DURABLE_ARTIFACT_PATH)
    logger.info("=== TRU-FY2025-MODEA-V2 FINISHED ===")


if __name__ == "__main__":
    asyncio.run(main())
