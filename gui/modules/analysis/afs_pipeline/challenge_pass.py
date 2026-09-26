"""Stage 11: Whole-Document Skeptical Challenge Pass (Second Gemini Pass).

Acts as a skeptical research reviewer questioning omissions, management spin,
downplayed risks, caveats in notes, margin pressures, working-capital drains,
and covenants.
Produces structured findings with severity (INFO, WATCH, MATERIAL, BLOCKING)
for analyst review. Does not mutate structured metrics.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from modules.analysis.selector import managed_query_ai
from .document_extraction import ExtractedDocument
from .reconciliation import HistoricalActualCandidate, ReconciliationReport

logger = logging.getLogger(__name__)

CHALLENGE_PROMPT_VERSION = "afs_skeptical_challenge_v1"


@dataclass(frozen=True)
class ChallengeFinding:
    finding_type: str  # ADVERSE_TREND, HIDDEN_CAVEAT, COVENANT_RISK, BOTTLENECK, PROVISION, CONCENTRATION, POLICY_CHANGE, OMISSION
    title: str
    description: str
    severity: str  # INFO, WATCH, MATERIAL, BLOCKING
    source_page: Optional[int]
    source_section: Optional[str]
    evidence_quote_or_span: str
    already_in_model: bool
    affected_metric_or_assumption: str
    recommended_analyst_review: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ChallengeReport:
    findings: List[ChallengeFinding]
    raw_prompt: str
    raw_response: str
    model_name: str
    prompt_version: str
    chunk_count: int = 1
    page_coverage: List[int] = field(default_factory=list)
    failed_chunks: int = 0
    retry_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "findings": [f.to_dict() for f in self.findings],
            "model_name": self.model_name,
            "prompt_version": self.prompt_version,
            "chunk_count": self.chunk_count,
            "page_coverage_range": [min(self.page_coverage), max(self.page_coverage)] if self.page_coverage else [],
            "total_pages_covered": len(self.page_coverage),
            "failed_chunks": self.failed_chunks,
            "retry_count": self.retry_count,
        }


CHALLENGE_SCHEMA_JSON = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "finding_type": {
                        "type": "string",
                        "enum": [
                            "ADVERSE_TREND",
                            "HIDDEN_CAVEAT",
                            "COVENANT_RISK",
                            "BOTTLENECK",
                            "PROVISION",
                            "CONCENTRATION",
                            "POLICY_CHANGE",
                            "OMISSION",
                            "OPERATIONAL_RISK",
                        ],
                    },
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "severity": {
                        "type": "string",
                        "enum": ["INFO", "WATCH", "MATERIAL", "BLOCKING"],
                    },
                    "source_page": {"type": ["integer", "null"]},
                    "source_section": {"type": ["string", "null"]},
                    "evidence_quote_or_span": {"type": "string"},
                    "already_in_model": {"type": "boolean"},
                    "affected_metric_or_assumption": {"type": "string"},
                    "recommended_analyst_review": {"type": "string"},
                },
                "required": [
                    "finding_type",
                    "title",
                    "description",
                    "severity",
                    "evidence_quote_or_span",
                    "already_in_model",
                    "affected_metric_or_assumption",
                    "recommended_analyst_review",
                ],
            },
        }
    },
    "required": ["findings"],
}


def build_challenge_prompt(
    ticker: str,
    financial_period: str,
    doc_summary_text: str,
    structured_candidates: List[HistoricalActualCandidate],
    chunk_info: Optional[str] = None,
) -> str:
    """Build skeptical reviewer prompt for Gemini whole-document analysis."""
    # Build candidate summary
    cands_summary = []
    for c in structured_candidates:
        cands_summary.append(
            f"- {c.concept}: {c.value} {c.unit or ''} (p.{c.source_page}, scope={c.scope}, status={c.final_status})"
        )
    metrics_str = "\n".join(cands_summary[:50]) if cands_summary else "No structured candidates in this section."

    chunk_ctx = f"\n[CORPUS CHUNK INFO: {chunk_info}]\n" if chunk_info else ""

    prompt = f"""You are a skeptical equity research analyst reviewing the Annual Financial Statements (AFS) for {ticker} ({financial_period}).
{chunk_ctx}
YOUR TASK:
Act as a skeptical research reviewer. Your job is NOT to calculate a fair value or re-extract standard numbers.
Instead, question the document and identify material risks, caveats, downplayed operational problems, and adverse trends that might be overlooked or omitted from structured metrics.

Specifically examine:
1. What material information in the AFS is NOT represented in the structured historical package?
2. What does management emphasize positively in headline text while detailed notes or secondary statements contain caveats?
3. What materially negative facts are mentioned briefly, indirectly, or buried in notes (e.g. margin pressure, cost inflation, inventory aging, bad debt write-offs, capex overruns, covenant thresholds, contingent liabilities)?
4. What facts would challenge an optimistic future forecast?

STRUCTURED CANDIDATES CURRENTLY CAPTURED BY PYTHON:
\"\"\"
{metrics_str}
\"\"\"

AFS TEXT EXTRACTS COVERED IN THIS SECTION:
\"\"\"
{doc_summary_text}
\"\"\"

CRITICAL INSTRUCTIONS:
- Do NOT invent facts or rumors not present in the document.
- Quote verbatim evidence from the supplied text in 'evidence_quote_or_span'.
- Categorize severity accurately:
  * BLOCKING: Fundamental going concern, imminent covenant breach, material restatement.
  * MATERIAL: Significant margin/cash flow impact (>5% of EBITDA/profit) requiring immediate valuation adjustment.
  * WATCH: Developing headwinds, inflationary cost pressures, working capital buildup.
  * INFO: Informational accounting nuances or disclosure notes.
- Return ONLY valid JSON adhering to the specified schema.

JSON SCHEMA:
{json.dumps(CHALLENGE_SCHEMA_JSON, indent=2)}
"""
    return prompt


async def run_whole_document_challenge(
    ticker: str,
    financial_period: str,
    extracted_doc: ExtractedDocument,
    reconciliation_report: ReconciliationReport,
    chunk_size_pages: int = 35,
    max_retries_per_chunk: int = 2,
) -> ChallengeReport:
    """Execute whole-document skeptical challenge pass across all pages using chunking."""
    all_pages = extracted_doc.pages
    total_pages = len(all_pages)

    if not all_pages:
        return ChallengeReport(
            findings=[],
            raw_prompt="No pages in document",
            raw_response="Empty",
            model_name="gemini-3.8-flash",
            prompt_version=CHALLENGE_PROMPT_VERSION,
            chunk_count=0,
            page_coverage=[],
            failed_chunks=0,
            retry_count=0,
        )

    # Partition pages into sequential chunks covering 100% of pages
    page_chunks: List[List[Any]] = []
    for i in range(0, total_pages, chunk_size_pages):
        page_chunks.append(all_pages[i : i + chunk_size_pages])

    chunk_count = len(page_chunks)
    all_findings: List[ChallengeFinding] = []
    prompt_records: List[str] = []
    response_records: List[str] = []
    failed_chunks = 0
    total_retries = 0

    all_structured = reconciliation_report.verified_candidates + reconciliation_report.review_candidates

    for chunk_idx, chunk in enumerate(page_chunks):
        chunk_start_p = chunk[0].page_number
        chunk_end_p = chunk[-1].page_number
        chunk_info = f"Chunk {chunk_idx + 1}/{chunk_count} (Pages {chunk_start_p} to {chunk_end_p} of {total_pages})"

        # Assemble text for this chunk
        chunk_text_parts = []
        for p in chunk:
            head = f"--- PAGE {p.page_number} ({p.section_heading or 'General'}) ---"
            chunk_text_parts.append(f"{head}\n{p.raw_text[:2500]}")
        chunk_text = "\n\n".join(chunk_text_parts)

        # Relevant candidates for this chunk's pages
        chunk_cands = [c for c in all_structured if c.source_page in range(chunk_start_p, chunk_end_p + 1)]
        if not chunk_cands and all_structured:
            # Provide high-level context if no chunk candidates
            chunk_cands = all_structured[:10]

        prompt = build_challenge_prompt(
            ticker=ticker,
            financial_period=financial_period,
            doc_summary_text=chunk_text,
            structured_candidates=chunk_cands,
            chunk_info=chunk_info,
        )

        chunk_success = False
        res_text = ""

        for attempt in range(max_retries_per_chunk + 1):
            if attempt > 0:
                total_retries += 1
            try:
                raw_res = await managed_query_ai("afs_challenge", prompt)
                res_text = raw_res.strip() if isinstance(raw_res, str) else getattr(raw_res, "text", str(raw_res)).strip()

                clean_json = re.sub(r"^```(?:json)?\s*", "", res_text, flags=re.I)
                clean_json = re.sub(r"\s*```$", "", clean_json).strip()

                parsed = json.loads(clean_json)
                raw_findings = parsed.get("findings", [])

                for rf in raw_findings:
                    f_obj = ChallengeFinding(
                        finding_type=rf.get("finding_type", "OPERATIONAL_RISK"),
                        title=rf.get("title", "Untitled finding"),
                        description=rf.get("description", ""),
                        severity=rf.get("severity", "WATCH"),
                        source_page=rf.get("source_page") or chunk_start_p,
                        source_section=rf.get("source_section") or chunk_info,
                        evidence_quote_or_span=rf.get("evidence_quote_or_span", ""),
                        already_in_model=bool(rf.get("already_in_model", False)),
                        affected_metric_or_assumption=rf.get("affected_metric_or_assumption", "general"),
                        recommended_analyst_review=rf.get("recommended_analyst_review", "Inspect disclosure"),
                    )
                    all_findings.append(f_obj)

                prompt_records.append(f"[{chunk_info}] PROMPT:\n{prompt[:300]}...")
                response_records.append(f"[{chunk_info}] RESPONSE:\n{res_text[:300]}...")
                chunk_success = True
                break

            except Exception as exc:
                logger.warning("Gemini challenge chunk %s attempt %d failed: %s", chunk_info, attempt, exc)
                if attempt == max_retries_per_chunk:
                    failed_chunks += 1
                    response_records.append(f"[{chunk_info}] FAILED after {attempt} retries: {exc}")

    covered_pages = [p.page_number for p in all_pages]

    return ChallengeReport(
        findings=all_findings,
        raw_prompt="\n\n---\n\n".join(prompt_records),
        raw_response="\n\n---\n\n".join(response_records),
        model_name="gemini-3.8-flash",
        prompt_version=CHALLENGE_PROMPT_VERSION,
        chunk_count=chunk_count,
        page_coverage=covered_pages,
        failed_chunks=failed_chunks,
        retry_count=total_retries,
    )
