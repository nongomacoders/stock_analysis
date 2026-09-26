"""Stage 4: Context Evidence Packages.

Assembles self-contained, reproducible evidence packages for each candidate occurrence,
providing surrounding paragraph context, document provenance, and deterministic numeric values.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any, Dict, Optional

from .document_extraction import ExtractedDocument
from .numeric_candidates import NumericCandidate


@dataclass(frozen=True)
class ContextEvidencePackage:
    evidence_id: str
    document_id: str
    ticker: str
    financial_period: str
    page_number: int
    paragraph_id: str
    section_heading: Optional[str]
    note_heading: Optional[str]
    previous_paragraph: Optional[str]
    target_paragraph: str
    next_paragraph: Optional[str]
    target_sentence: str
    candidate_id: str
    candidate_numeric_token: str
    deterministic_normalized_value: Optional[Decimal]
    currency: Optional[str]
    unit: Optional[str]
    scale: Optional[str]
    detected_label: Optional[str]
    numeric_role: str
    value_pattern: str
    note_reference: Optional[str] = None
    temporal_role: str = "STANDALONE"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["deterministic_normalized_value"] = (
            str(self.deterministic_normalized_value)
            if self.deterministic_normalized_value is not None
            else None
        )
        return d


def build_evidence_package(
    candidate: NumericCandidate,
    doc: ExtractedDocument,
    ticker: str,
    financial_period: str,
) -> ContextEvidencePackage:
    """Build a reproducible context evidence package for a numeric candidate."""
    p_obj = doc.paragraphs_by_id.get(candidate.paragraph_id)
    target_p_text = p_obj.text if p_obj else candidate.sentence_text
    section_h = p_obj.section_heading if p_obj else None
    note_h = p_obj.note_heading if p_obj else None

    prev_p, _, next_p = doc.get_context_window(candidate.paragraph_id)

    ev_id = f"ev_{candidate.candidate_id}"

    return ContextEvidencePackage(
        evidence_id=ev_id,
        document_id=doc.document_id,
        ticker=ticker,
        financial_period=financial_period,
        page_number=candidate.page_number,
        paragraph_id=candidate.paragraph_id,
        section_heading=section_h,
        note_heading=note_h,
        previous_paragraph=prev_p,
        target_paragraph=target_p_text,
        next_paragraph=next_p,
        target_sentence=candidate.sentence_text,
        candidate_id=candidate.candidate_id,
        candidate_numeric_token=candidate.raw_token,
        deterministic_normalized_value=candidate.normalized_value,
        currency=candidate.currency,
        unit=candidate.unit,
        scale=candidate.scale,
        detected_label=candidate.nearby_label,
        numeric_role=candidate.numeric_role,
        value_pattern=candidate.value_pattern,
        note_reference=candidate.note_reference,
        temporal_role=candidate.temporal_role,
    )
