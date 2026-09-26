"""Stage 2: Document Extraction.

Extracts embedded text preserving page numbers, text blocks, paragraphs,
sentences, section headings, and note headings with full provenance.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from pypdf import PdfReader
except ImportError:
    from PyPDF2 import PdfReader


@dataclass
class ExtractedSentence:
    sentence_id: str
    paragraph_id: str
    page_number: int
    text: str
    sentence_index: int


@dataclass
class ExtractedParagraph:
    paragraph_id: str
    page_number: int
    paragraph_index: int
    text: str
    section_heading: Optional[str]
    note_heading: Optional[str]
    sentences: List[ExtractedSentence] = field(default_factory=list)


@dataclass
class ExtractedPage:
    page_number: int
    raw_text: str
    section_heading: Optional[str]
    paragraphs: List[ExtractedParagraph] = field(default_factory=list)


@dataclass
class ExtractedDocument:
    document_id: str
    page_count: int
    pages: List[ExtractedPage]
    paragraphs_by_id: Dict[str, ExtractedParagraph] = field(default_factory=dict)
    sentences_by_id: Dict[str, ExtractedSentence] = field(default_factory=dict)
    total_pdf_pages: int = 0
    pages_with_embedded_text: int = 0
    pages_no_usable_text: int = 0
    pages_failed: int = 0
    pages_requiring_ocr: int = 0

    def get_context_window(
        self, paragraph_id: str
    ) -> Tuple[Optional[str], str, Optional[str]]:
        """Return (previous_paragraph_text, target_paragraph_text, next_paragraph_text)."""
        target = self.paragraphs_by_id.get(paragraph_id)
        if not target:
            return None, "", None

        page = next((p for p in self.pages if p.page_number == target.page_number), None)
        if not page:
            return None, target.text, None

        idx = target.paragraph_index
        prev_p = page.paragraphs[idx - 1].text if idx > 0 else None
        next_p = page.paragraphs[idx + 1].text if idx < len(page.paragraphs) - 1 else None

        # Cross-page fallback if at boundary
        if prev_p is None and target.page_number > 1:
            prev_page = next((p for p in self.pages if p.page_number == target.page_number - 1), None)
            if prev_page and prev_page.paragraphs:
                prev_p = prev_page.paragraphs[-1].text

        if next_p is None and target.page_number < self.page_count:
            next_page = next((p for p in self.pages if p.page_number == target.page_number + 1), None)
            if next_page and next_page.paragraphs:
                next_p = next_page.paragraphs[0].text

        return prev_p, target.text, next_p


STATEMENT_HEADING_PATTERNS = [
    (r"GROUP STATEMENTS? OF FINANCIAL POSITION", "Statements of Financial Position"),
    (r"GROUP STATEMENTS? OF COMPREHENSIVE INCOME", "Statements of Comprehensive Income"),
    (r"GROUP STATEMENTS? OF CASH FLOWS", "Statements of Cash Flows"),
    (r"GROUP STATEMENTS? OF CHANGES IN EQUITY", "Statements of Changes in Equity"),
    (r"NOTES TO THE GROUP ANNUAL FINANCIAL STATEMENTS", "Notes to the AFS"),
    (r"INDEPENDENT AUDITOR'?S REPORT", "Auditor's Report"),
    (r"REPORT OF THE DIRECTORS", "Directors' Report"),
    (r"CHIEF EXECUTIVE OFFICER'?S REPORT", "CEO Report"),
    (r"CHIEF FINANCIAL OFFICER'?S REPORT", "CFO Report"),
    (r"SEGMENT REPORT", "Segment Report"),
]

NOTE_HEADING_PATTERN = re.compile(
    r"(?im)^\s*(?:NOTE\s+)?(\d{1,2}(?:\.\d{1,2})?)\s+([A-Z0-9\s,\-–/()]{4,60})\s*$"
)


def _detect_section_heading(text: str, current_section: Optional[str]) -> Optional[str]:
    for pattern, heading in STATEMENT_HEADING_PATTERNS:
        if re.search(pattern, text, re.I):
            return heading
    return current_section


def _detect_note_heading(line: str) -> Optional[str]:
    m = NOTE_HEADING_PATTERN.match(line.strip())
    if m:
        num = m.group(1).strip()
        title = m.group(2).strip()
        # Avoid false positives on common table headers like "52 WEEKS"
        if not re.search(r"\b(?:WEEKS|MONTHS|JUNE|DECEMBER|20\d\d)\b", title, re.I):
            return f"Note {num}: {title}"
    return None


def _split_into_sentences(text: str) -> List[str]:
    """Split text into sentences or table rows preserving numeric structures and abbreviations."""
    clean = text.strip()
    if not clean:
        return []
    lines = clean.splitlines()
    sentences: List[str] = []
    for line in lines:
        l_str = line.strip()
        if not l_str:
            continue
        # If line looks like a table row (has digits or compact row structure), preserve as distinct line
        if re.search(r"\d", l_str) or len(l_str) < 70:
            sentences.append(l_str)
        else:
            # Narrative paragraph line: split on sentence boundaries
            parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9(\"R])", l_str)
            for p in parts:
                if p.strip():
                    sentences.append(p.strip())
    return sentences if sentences else [clean]


def extract_document(
    pdf_path: Path | str,
    document_id: str,
    max_pages: Optional[int] = None,
) -> ExtractedDocument:
    """Extract embedded text from PDF into structured pages, paragraphs, and sentences."""
    reader = PdfReader(str(pdf_path))
    total_pages = len(reader.pages)
    limit = min(total_pages, max_pages) if max_pages else total_pages

    extracted_pages: List[ExtractedPage] = []
    paragraphs_by_id: Dict[str, ExtractedParagraph] = {}
    sentences_by_id: Dict[str, ExtractedSentence] = {}

    current_section = None
    pages_with_embedded_text = 0
    pages_no_usable_text = 0
    pages_failed = 0

    for page_idx in range(limit):
        page_no = page_idx + 1
        page_obj = reader.pages[page_idx]
        try:
            raw_text = page_obj.extract_text() or ""
        except Exception:
            raw_text = ""

        current_section = _detect_section_heading(raw_text, current_section)

        # Split raw text into blocks / paragraphs
        # Normalize double newlines and carriage returns
        normalized_text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
        raw_blocks = re.split(r"\n\s*\n+", normalized_text)

        page_paragraphs: List[ExtractedParagraph] = []
        current_note = None

        p_idx = 0
        for block in raw_blocks:
            clean_block = block.strip()
            if not clean_block:
                continue

            # Check if any line in block introduces a note heading
            for line in clean_block.split("\n"):
                detected_note = _detect_note_heading(line)
                if detected_note:
                    current_note = detected_note

            p_id = f"doc_{document_id}_p{page_no}_{p_idx}"
            sentences = _split_into_sentences(clean_block)
            ext_sentences: List[ExtractedSentence] = []

            for s_idx, s_text in enumerate(sentences):
                s_id = f"{p_id}_s{s_idx}"
                s_obj = ExtractedSentence(
                    sentence_id=s_id,
                    paragraph_id=p_id,
                    page_number=page_no,
                    text=s_text,
                    sentence_index=s_idx,
                )
                ext_sentences.append(s_obj)
                sentences_by_id[s_id] = s_obj

            p_obj = ExtractedParagraph(
                paragraph_id=p_id,
                page_number=page_no,
                paragraph_index=p_idx,
                text=clean_block,
                section_heading=current_section,
                note_heading=current_note,
                sentences=ext_sentences,
            )
            page_paragraphs.append(p_obj)
            paragraphs_by_id[p_id] = p_obj
            p_idx += 1

        extracted_pages.append(
            ExtractedPage(
                page_number=page_no,
                raw_text=raw_text,
                section_heading=current_section,
                paragraphs=page_paragraphs,
            )
        )

        if not raw_text.strip():
            pages_no_usable_text += 1
        else:
            pages_with_embedded_text += 1

    return ExtractedDocument(
        document_id=document_id,
        page_count=len(extracted_pages),
        pages=extracted_pages,
        paragraphs_by_id=paragraphs_by_id,
        sentences_by_id=sentences_by_id,
        total_pdf_pages=total_pages,
        pages_with_embedded_text=pages_with_embedded_text,
        pages_no_usable_text=pages_no_usable_text,
        pages_failed=pages_failed,
        pages_requiring_ocr=pages_no_usable_text,
    )
