"""Staged Gemini 3.8 Flash Mode A regression runner (kill-safe, resumable).

Stages (each a bounded foreground invocation):
  prep     : deterministic extract + Mode A package selection -> work/packages.json
  modea    : adjudicate slice [start, start+count) -> work/modea_slice_<start>.json
  assemble : merge slices, reconcile, challenge, score, write versioned v2 audit

Targets: --target pan | tru. No production default switch. No benchmark writes.
Reference facts are used for POST-extraction scoring only (never injected).
"""
import argparse
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

from modules.analysis.afs_pipeline.archive import archive_afs_pdf
from modules.analysis.afs_pipeline.challenge_pass import run_whole_document_challenge
from modules.analysis.afs_pipeline.checklist import evaluate_checklist
from modules.analysis.afs_pipeline.document_extraction import extract_document
from modules.analysis.afs_pipeline.evidence_package import (
    ContextEvidencePackage,
    build_evidence_package,
)
from modules.analysis.afs_pipeline.gemini_semantic_engine import (
    MODE_A_SCHEMA,
    PROMPT_VERSION_MODE_A,
    compute_deterministic_derived_metrics,
    execute_gemini_mode_a,
    select_candidates_by_material_categories,
)
from modules.analysis.afs_pipeline.numeric_candidates import extract_numeric_candidates_from_sentence
from modules.analysis.afs_pipeline.pipeline import AFSPipelineResult, StageRuntimeMetrics
from modules.analysis.afs_pipeline.reconciliation import (
    HistoricalActualCandidate,
    reconcile_candidates_direct,
)

REPO = r"C:\Users\Dion\Desktop\Projects\stock_analysis"

TARGETS = {
    "pan": {
        "pdf": r"C:\Users\Dion\Desktop\Projects\stock_analysis\gui\results_history\PAN\HY2026\PAN_HY2026.pdf",
        "work": r"C:\Users\Dion\Desktop\Projects\stock_analysis\gui\results_history\PAN\HY2026\afs_experiments\v3_work",
        "artifact": r"C:\Users\Dion\Desktop\Projects\stock_analysis\gui\results_history\PAN\HY2026\afs_experiments\gemini_38_mode_a_audit_v3.json",
        "v1": r"C:\Users\Dion\Desktop\Projects\stock_analysis\gui\results_history\PAN\HY2026\afs_experiments\gemini_38_mode_a_audit.json",
        "ticker": "PAN", "company": "Pan African Resources PLC",
        "period": "HY2026", "publication": "2026-02-18T07:00:00+00:00",
        "is_mining": True,
        "expected_sha256": "4c13ee4a02b4c91ff6fa0d21b4c5446576069b2d31ac90d06d4c16911d4d82d0",
        "identity": "PAN-HY2026-MODEA-V3",
    },
    "tru": {
        "pdf": r"C:\Users\Dion\Desktop\Projects\stock_analysis\gui\results_history\TRU\FY2025\TRU_FY2025_AFS.pdf",
        "work": r"C:\Users\Dion\Desktop\Projects\stock_analysis\gui\results_history\TRU\FY2025\afs_experiments\v3_work",
        "artifact": r"C:\Users\Dion\Desktop\Projects\stock_analysis\gui\results_history\TRU\FY2025\afs_experiments\gemini_38_mode_a_audit_v3.json",
        "v1": r"C:\Users\Dion\Desktop\Projects\stock_analysis\gui\results_history\TRU\FY2025\afs_experiments\gemini_38_mode_a_audit.json",
        "ticker": "TRU", "company": "Truworths International Ltd",
        "period": "FY2025", "publication": "2025-08-28T07:00:00+00:00",
        "is_mining": False,
        "expected_sha256": "7e2389d735bba8bebec4f967ac2ae2ad58f0d1c87f5d9f35e98a52bc88cffa01",
        "identity": "TRU-FY2025-MODEA-V3",
    },
}


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def git_info():
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO,
                            capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--short"], cwd=REPO,
                           capture_output=True, text=True).stdout.strip().splitlines()
    return commit, dirty


def dec_or_none(v):
    return Decimal(v) if v is not None else None


def rebuild_package(d) -> ContextEvidencePackage:
    return ContextEvidencePackage(
        evidence_id=d["evidence_id"], document_id=d["document_id"], ticker=d["ticker"],
        financial_period=d["financial_period"], page_number=d["page_number"],
        paragraph_id=d["paragraph_id"], section_heading=d["section_heading"],
        note_heading=d["note_heading"], previous_paragraph=d["previous_paragraph"],
        target_paragraph=d["target_paragraph"], next_paragraph=d["next_paragraph"],
        target_sentence=d["target_sentence"], candidate_id=d["candidate_id"],
        candidate_numeric_token=d["candidate_numeric_token"],
        deterministic_normalized_value=dec_or_none(d["deterministic_normalized_value"]),
        currency=d["currency"], unit=d["unit"], scale=d["scale"],
        detected_label=d["detected_label"], numeric_role=d["numeric_role"],
        value_pattern=d["value_pattern"], note_reference=d["note_reference"],
        temporal_role=d["temporal_role"],
    )


def rebuild_candidate(d) -> HistoricalActualCandidate:
    return HistoricalActualCandidate(
        candidate_id=d["candidate_id"], evidence_id=d["evidence_id"],
        concept=d["concept"], value=dec_or_none(d["value"]),
        raw_token=d["raw_token"], unit=d["unit"], currency=d["currency"],
        period=d["period"], scope=d["scope"], qualifiers=d["qualifiers"],
        source_page=d["source_page"], source_paragraph_id=d["source_paragraph_id"],
        extraction_method=d["extraction_method"], kev_result=d["kev_result"],
        gemini_result=d["gemini_result"], safety_status=d["safety_status"],
        final_status=d["final_status"], reconciliation_notes=d["reconciliation_notes"],
    )


def cmd_prep(cfg):
    os.makedirs(cfg["work"], exist_ok=True)
    commit, dirty = git_info()
    digest = sha256_file(cfg["pdf"])
    logger.info("source sha256: %s", digest)
    if digest != cfg["expected_sha256"]:
        raise SystemExit(f"SOURCE HASH MISMATCH for {cfg['ticker']}; aborting.")
    archived = archive_afs_pdf(
        pdf_path=cfg["pdf"], ticker=cfg["ticker"], company=cfg["company"],
        financial_period=cfg["period"], publication_datetime=cfg["publication"],
        source_url=None, db_conn=None,
    )
    doc = extract_document(cfg["pdf"], archived.document_id, max_pages=None)
    allc = []
    for s in doc.sentences_by_id.values():
        allc.extend(extract_numeric_candidates_from_sentence(
            s.sentence_id, s.paragraph_id, s.page_number, s.text))
    pkgs = [build_evidence_package(c, doc, ticker=cfg["ticker"],
                                   financial_period=cfg["period"]) for c in allc]
    selected = select_candidates_by_material_categories(pkgs, is_mining=cfg["is_mining"])
    manifest = {
        "identity": cfg["identity"], "git_commit": commit, "git_dirty_files": dirty,
        "afs_sha256": digest, "document_id": archived.document_id,
        "ticker": cfg["ticker"], "period": cfg["period"],
        "page_count": doc.page_count, "numeric_candidates": len(allc),
        "mode_a_selected": len(selected),
        "experimental_engine": "gemini", "gemini_mode": "mode_a",
        "requested_model": "gemini-3.8-flash", "temperature": 0.0,
        "challenge_temperature": 0.2, "production_default_unchanged": "kev",
    }
    json.dump(manifest, open(os.path.join(cfg["work"], "manifest.json"), "w"), indent=2)
    json.dump([p.to_dict() for p in selected],
              open(os.path.join(cfg["work"], "packages.json"), "w"), indent=2)
    json.dump({"archived_doc": archived.to_dict()},
              open(os.path.join(cfg["work"], "archive.json"), "w"), indent=2, default=str)
    logger.info("prep done: %d pages, %d candidates, %d mode-A selected",
                doc.page_count, len(allc), len(selected))
    print(f"TOTAL_SELECTED={len(selected)}")


async def cmd_modea(cfg, start: int, count: int, overwrite: bool):
    pkgs = [rebuild_package(d) for d in
            json.load(open(os.path.join(cfg["work"], "packages.json")))]
    total = len(pkgs)
    if start >= total:
        print(f"SLICE_EMPTY total={total} start={start}");
        return
    out_path = os.path.join(cfg["work"], f"modea_slice_{start}.json")
    if os.path.exists(out_path) and not overwrite:
        print(f"SLICE_EXISTS {out_path}; use --overwrite to redo");
        return
    sl = pkgs[start:start + count]
    logger.info("adjudicating slice [%d, %d) of %d", start, start + len(sl), total)
    t0 = time.perf_counter()
    prelims, metrics, audit_logs = await execute_gemini_mode_a(
        packages=sl, ticker=cfg["ticker"], financial_period=cfg["period"])
    dt = time.perf_counter() - t0
    json.dump({"start": start, "count": len(sl),
               "metrics": metrics.to_dict(), "audit_logs": audit_logs,
               "prelims": [c.to_dict() for c in prelims]},
              open(out_path, "w"), indent=2, default=str)
    logger.info("slice done in %.1fs: %d prelims, %d calls", dt, len(prelims),
                metrics.to_dict().get("call_count"))
    print(f"SLICE_DONE start={start} prelims={len(prelims)} seconds={dt:.1f} "
          f"remaining={total - (start + len(sl))}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True, choices=list(TARGETS))
    ap.add_argument("stage", choices=["prep", "modea", "assemble"])
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--count", type=int, default=40)
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()
    cfg = TARGETS[args.target]
    assert os.path.abspath(cfg["artifact"]) != os.path.abspath(cfg["v1"])
    assert os.path.exists(cfg["v1"]), "frozen v1 audit must exist"
    if args.stage == "prep":
        cmd_prep(cfg)
    elif args.stage == "modea":
        asyncio.run(cmd_modea(cfg, args.start, args.count, args.overwrite))
    elif args.stage == "assemble":
        from assemble_v2 import cmd_assemble
        cmd_assemble(cfg)


if __name__ == "__main__":
    main()
