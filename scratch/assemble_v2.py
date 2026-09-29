"""Assemble stage for the kill-safe Mode A regression runner (imported, not run directly)."""
import asyncio
import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

sys.path.insert(0, r"C:\Users\Dion\Desktop\Projects\stock_analysis\scratch")
from run_pan_gemini_38_v2 import KNOWN_MINING_FACTS, score_mining_extraction_v2

from modules.analysis.afs_pipeline.archive import ArchivedDocument
from modules.analysis.afs_pipeline.challenge_pass import run_whole_document_challenge
from modules.analysis.afs_pipeline.checklist import evaluate_checklist
from modules.analysis.afs_pipeline.document_extraction import extract_document
from modules.analysis.afs_pipeline.gemini_semantic_engine import (
    MODE_A_SCHEMA,
    PROMPT_VERSION_MODE_A,
    compute_deterministic_derived_metrics,
)
from modules.analysis.afs_pipeline.numeric_candidates import extract_numeric_candidates_from_sentence
from modules.analysis.afs_pipeline.pipeline import AFSPipelineResult, StageRuntimeMetrics
from modules.analysis.afs_pipeline.reconciliation import reconcile_candidates_direct

from run_modea_v2_staged import TARGETS, git_info, rebuild_candidate, sha256_file


def cmd_assemble(cfg):
    work = cfg["work"]
    manifest = json.load(open(os.path.join(work, "manifest.json")))
    pkgs_all = json.load(open(os.path.join(work, "packages.json")))
    arch = json.load(open(os.path.join(work, "archive.json")))["archived_doc"]

    # Merge slices in order
    import glob
    slice_files = sorted(glob.glob(os.path.join(work, "modea_slice_*.json")),
                         key=lambda p: int(os.path.basename(p).split("_")[-1].split(".")[0]))
    assert slice_files, "no mode-A slices found"
    prelims, audit_logs = [], []
    m_calls = m_ptok = m_otok = 0
    m_lat = 0.0
    m_cost = 0.0
    m_model = m_returned = None
    m_temp = 0.0
    for sf in slice_files:
        sd = json.load(open(sf))
        prelims.extend(rebuild_candidate(d) for d in sd["prelims"])
        audit_logs.extend(sd["audit_logs"])
        m = sd["metrics"]
        m_calls += m.get("call_count", 0)
        m_ptok += m.get("prompt_tokens", 0)
        m_otok += m.get("output_tokens", 0)
        m_lat += m.get("total_latency_ms", 0.0)
        m_cost += m.get("estimated_cost_usd", 0.0)
        m_model = m_model or m.get("requested_model")
        m_returned = m.get("returned_model_version") or m_returned
        m_temp = m.get("temperature", 0.0)
    logger.info("merged %d prelims from %d slices (%d calls)", len(prelims), len(slice_files), m_calls)
    assert len(prelims) == manifest["mode_a_selected"], \
        f"slice coverage {len(prelims)} != selected {manifest['mode_a_selected']}"

    total_candidates = manifest["numeric_candidates"]
    metrics_dict = {
        "call_count": m_calls, "requested_model": m_model,
        "returned_model_version": m_returned, "temperature": m_temp,
        "prompt_tokens": m_ptok, "output_tokens": m_otok,
        "total_tokens": m_ptok + m_otok, "total_latency_ms": round(m_lat, 2),
        "estimated_cost_usd": round(m_cost, 6), "model_name": m_model,
    }

    # Deterministic derived metrics + reconciliation
    derived_cands, derived_metric_objs = compute_deterministic_derived_metrics(
        prelims, cfg["period"])
    report = reconcile_candidates_direct(
        preliminary_candidates=prelims, period=cfg["period"],
        derived_candidates=derived_cands, is_mining=cfg["is_mining"])

    # Re-extract document (deterministic) for challenge + scoring quotes
    t0 = time.perf_counter()
    doc = extract_document(cfg["pdf"], manifest["document_id"], max_pages=None)
    allc = []
    for s in doc.sentences_by_id.values():
        allc.extend(extract_numeric_candidates_from_sentence(
            s.sentence_id, s.paragraph_id, s.page_number, s.text))

    arch_fields = {k: v for k, v in arch.items()
                   if k in ArchivedDocument.__dataclass_fields__}
    arch_fields["publication_datetime"] = datetime.fromisoformat(arch_fields["publication_datetime"])
    arch_fields["ingestion_timestamp"] = datetime.fromisoformat(arch_fields["ingestion_timestamp"])
    archived_doc = ArchivedDocument(**arch_fields)

    async def _challenge():
        return await run_whole_document_challenge(
            ticker=cfg["ticker"], financial_period=cfg["period"],
            extracted_doc=doc, reconciliation_report=report)

    challenge_report = asyncio.run(_challenge())
    runtimes = StageRuntimeMetrics()
    runtimes.total_pipeline_ms = (time.perf_counter() - t0) * 1000.0

    checklist_items = evaluate_checklist(
        report=report, extracted_doc=doc, all_candidates=allc,
        is_mining_or_producer=cfg["is_mining"])

    result = AFSPipelineResult(
        ticker=cfg["ticker"], company=cfg["company"], financial_period=cfg["period"],
        archived_doc=archived_doc, extracted_doc=doc,
        candidates_count=total_candidates, kev_classified_count=0,
        deterministic_accepted_count=len(report.verified_candidates),
        gemini_escalated_count=len(prelims),
        gemini_resolved_count=len(report.verified_candidates),
        analyst_review_count=len(report.review_candidates),
        conflicts_count=len(report.conflicting_candidates),
        reconciliation_report=report, checklist_items=checklist_items,
        challenge_report=challenge_report, runtimes=runtimes,
        semantic_engine="gemini", gemini_mode="mode_a",
        gemini_metrics=metrics_dict,
        derived_metrics=[m.to_dict() for m in derived_metric_objs],
        gemini_audit_logs=audit_logs,
    )

    # ---- scoring ----
    if cfg["ticker"] == "PAN":
        val_results = score_mining_extraction_v2(
            report.verified_candidates, report.review_candidates,
            report.conflicting_candidates, doc)
        counts = {}
        for v in val_results:
            counts[v["status"]] = counts.get(v["status"], 0) + 1
        total = len(val_results)
        assert sum(counts.values()) == total
        scoring = {
            "total_reference_facts": total,
            "correct_facts_count": counts.get("CORRECT", 0),
            "incorrect_facts_count": counts.get("INCORRECT", 0),
            "missed_facts_count": counts.get("MISSED", 0),
            "ambiguous_facts_count": counts.get("AMBIGUOUS", 0),
            "accuracy_pct": round((counts.get("CORRECT", 0) / total) * 100, 2),
            "validations": val_results,
        }
        review_burden_extra = {
            "reference_correct": counts.get("CORRECT", 0),
            "reference_incorrect": counts.get("INCORRECT", 0),
            "reference_missed": counts.get("MISSED", 0),
            "reference_ambiguous": counts.get("AMBIGUOUS", 0),
        }
    else:
        from modules.analysis.afs_pipeline.reference_loader import load_frozen_reference_facts
        from modules.analysis.afs_pipeline.reference_validation import (
            validate_pipeline_against_frozen_references,
        )
        ref_facts = load_frozen_reference_facts("TRU", "FY2025")
        val_results = validate_pipeline_against_frozen_references(result, ref_facts)
        counts = {}
        for v in val_results:
            counts[v.status.value] = counts.get(v.status.value, 0) + 1
        total = len(val_results)
        assert sum(counts.values()) == total
        scoring = {
            "total_reference_facts": total,
            "status_counts": counts,
            "accuracy_pct": round((counts.get("CORRECT", 0) / total) * 100, 2),
            "validations": [v.to_dict() for v in val_results],
        }
        review_burden_extra = {}

    unresolved_mandatory = getattr(report, "unresolved_mandatory_categories", [])
    if cfg["ticker"] == "PAN":
        all_mandatory = [
            "revenue", "sales", "profit", "margins", "tax", "capex",
            "working_capital", "cash", "debt", "leases", "shares", "depreciation_amortisation",
            "production", "sales_volumes", "commodity_price", "unit_cost", "grade",
            "recovery", "throughput", "guidance", "hedging",
        ]
    else:
        all_mandatory = [
            "revenue", "sales", "profit", "margins", "tax", "capex",
            "working_capital", "cash", "debt", "leases", "shares", "depreciation_amortisation",
        ]
    review_burden = {
        "resolved_mandatory_categories": [c for c in all_mandatory if c not in unresolved_mandatory],
        "unresolved_mandatory_categories": unresolved_mandatory,
        "automatic_review_queue_count": len(report.review_candidates),
        "conflicting_evidence_count": len(report.conflicting_candidates),
        "manual_review_required_count": (
            len(report.review_candidates) + len(report.conflicting_candidates)
            + review_burden_extra.get("reference_missed", 0)
            + review_burden_extra.get("reference_ambiguous", 0)
            + len(unresolved_mandatory)
        ),
        **review_burden_extra,
    }

    schema_str = json.dumps(MODE_A_SCHEMA, sort_keys=True)
    audit_artifact = {
        "metadata": {
            "experiment_identity": cfg["identity"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "git_commit": manifest["git_commit"],
            "git_dirty_files": manifest["git_dirty_files"],
            "afs_sha256": manifest["afs_sha256"],
            "document": os.path.basename(cfg["pdf"]),
            "ticker": cfg["ticker"], "period": cfg["period"],
            "is_mining": cfg["is_mining"],
            "experimental_engine": "gemini", "gemini_mode": "mode_a",
            "production_default_unchanged": "kev",
            "requested_model": manifest["requested_model"],
            "returned_model_version": m_returned,
            "temperature": manifest["temperature"],
            "challenge_temperature": 0.2,
            "no_silent_fallback": True,
            "python_numeric_authoritative": True,
            "python_validation_authoritative": True,
            "prompt_version": PROMPT_VERSION_MODE_A,
            "prompt_hash": hashlib.sha256(PROMPT_VERSION_MODE_A.encode("utf-8")).hexdigest(),
            "schema_sha256": hashlib.sha256(schema_str.encode("utf-8")).hexdigest(),
            "mode_a_slices": len(slice_files),
            "mode_a_selected": manifest["mode_a_selected"],
            "supersedes": os.path.basename(cfg["v1"]) + " (frozen, preserved)",
        },
        "scoring_results": scoring,
        "review_burden": review_burden,
        "token_usage_and_costs": {
            "gemini_mode_a_metrics": metrics_dict,
            "challenge_metrics": {
                "requested_model": challenge_report.model_name,
                "returned_model_version": getattr(challenge_report, "model_version", "gemini-3.8-flash"),
                "temperature": getattr(challenge_report, "temperature", 0.2),
                "prompt_tokens": getattr(challenge_report, "prompt_tokens", 0),
                "output_tokens": getattr(challenge_report, "output_tokens", 0),
                "chunk_count": getattr(challenge_report, "chunk_count", 0),
                "page_coverage": getattr(challenge_report, "page_coverage", []),
                "failed_chunks": getattr(challenge_report, "failed_chunks", 0),
            },
            "stage_runtimes_ms": runtimes.to_dict(),
        },
        "derived_metrics": result.derived_metrics,
        "reconciliation_summary": {
            "verified_count": len(report.verified_candidates),
            "review_count": len(report.review_candidates),
            "conflicting_count": len(report.conflicting_candidates),
            "rejected_count": len(report.rejected_candidates),
            "verified_candidates": [c.to_dict() for c in report.verified_candidates],
            "review_candidates": [c.to_dict() for c in report.review_candidates],
            "conflicting_candidates": [c.to_dict() for c in report.conflicting_candidates],
            "rejected_candidates": [c.to_dict() for c in report.rejected_candidates],
            "findings": report.reconciliation_findings,
            "unresolved_mandatory_categories": unresolved_mandatory,
        },
        "challenge_summary": {
            "total_findings": len(challenge_report.findings),
            "findings": [f.to_dict() for f in challenge_report.findings],
        },
        "requests_and_responses": audit_logs,
    }
    raw_json = json.dumps(audit_artifact, indent=2, default=str)
    audit_artifact["metadata"]["artifact_sha256"] = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()
    with open(cfg["artifact"], "w", encoding="utf-8") as f:
        f.write(json.dumps(audit_artifact, indent=2, default=str))
    logger.info("v2 artifact written (v1 preserved): %s", cfg["artifact"])
    print(f"ASSEMBLE_DONE verified={len(report.verified_candidates)} "
          f"review={len(report.review_candidates)} conflicting={len(report.conflicting_candidates)} "
          f"rejected={len(report.rejected_candidates)} scoring={scoring.get('accuracy_pct')}")
