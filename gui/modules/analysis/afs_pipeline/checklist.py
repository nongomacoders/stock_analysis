"""Stage 10: High-Impact Mandatory Review Checklist.

Audits coverage of all 20 high-impact financial & operational categories.
Statuses:
- VERIFIED: Concrete reconciled historical metric available.
- NOT_APPLICABLE: Category not applicable to this company/sector (e.g. AISC for pure retailers).
- REQUIRES_REVIEW: Candidate present but requires analyst confirmation of basis.
- NOT_FOUND: No candidates or disclosures found for this category in the document.

Mandatory: All 20 categories must be explicitly reported without omission.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from .reconciliation import HistoricalActualCandidate, ReconciliationReport


class ChecklistStatus(str, Enum):
    VERIFIED = "VERIFIED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"
    NOT_FOUND = "NOT_FOUND"


@dataclass(frozen=True)
class ChecklistItem:
    category: str
    display_name: str
    status: ChecklistStatus
    candidate_count: int
    primary_concept: Optional[str]
    sample_value: Optional[str]
    source_pages: List[int]
    notes: str

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


CHECKLIST_CATEGORIES = [
    ("accounting_revenue_sales_basis", "Accounting revenue / sales basis"),
    ("operating_trading_margin_basis", "Operating / trading margin basis"),
    ("production_output_volumes", "Production / output volumes"),
    ("realised_prices", "Realised commodity / merchandise prices"),
    ("unit_costs_aisc", "Unit costs / AISC"),
    ("capex_basis", "Capex basis (cash capex vs additions)"),
    ("working_capital", "Working capital movements"),
    ("debt_net_debt", "Debt / borrowings / net debt"),
    ("lease_liabilities", "Lease liabilities (IFRS 16)"),
    ("share_count", "Share count (issued, external, treasury, weighted)"),
    ("minorities", "Minorities / non-controlling interest"),
    ("tax", "Tax expense / effective rate"),
    ("guidance", "Guidance / outlook qualifications"),
    ("hedging", "Hedging & financial derivatives"),
    ("acquisitions_disposals", "Acquisitions & disposals"),
    ("impairments", "Impairments & write-downs"),
    ("provisions", "Provisions & reserves"),
    ("contingent_liabilities", "Contingent liabilities"),
    ("covenants", "Debt & borrowing covenants"),
    ("operational_constraints", "Major operational constraints / bottlenecks"),
]


from .document_extraction import ExtractedDocument
from .numeric_candidates import NumericCandidate


CATEGORY_DOCUMENT_SEARCH_RULES = {
    "accounting_revenue_sales_basis": {
        "keywords": ["sale of merchandise", "accounting revenue", "revenue", "turnover", "note 26"],
        "notes": ["Note 26"],
    },
    "operating_trading_margin_basis": {
        "keywords": ["trading profit", "operating profit", "trading margin", "operating margin", "pbit"],
        "notes": [],
    },
    "production_output_volumes": {
        "keywords": ["production", "output", "tonnes", "koz", "volume"],
        "notes": [],
    },
    "realised_prices": {
        "keywords": ["realised price", "average realised price", "usd/oz", "zar/t"],
        "notes": [],
    },
    "unit_costs_aisc": {
        "keywords": ["aisc", "all-in sustaining cost", "cash cost per", "cost per tonne"],
        "notes": [],
    },
    "capex_basis": {
        "keywords": ["capital expenditure", "additions", "capex", "note 33", "cash flows from investing", "note 2", "property, plant and equipment"],
        "notes": ["Note 2", "Note 33"],
    },
    "working_capital": {
        "keywords": ["working capital", "inventories", "trade and other receivables", "trade and other payables", "note 33.2", "note 10", "note 11", "note 21"],
        "notes": ["Note 10", "Note 11", "Note 21", "Note 33.2"],
    },
    "debt_net_debt": {
        "keywords": ["interest-bearing borrowings", "borrowings", "bank overdraft", "net debt", "net cash", "note 16", "note 12"],
        "notes": ["Note 16", "Note 12"],
    },
    "lease_liabilities": {
        "keywords": ["lease liabilities", "right-of-use", "ifrs 16", "note 20", "note 3"],
        "notes": ["Note 20", "Note 3"],
    },
    "share_count": {
        "keywords": ["share capital", "treasury shares", "weighted average number of shares", "shares in issue", "note 13", "note 14", "note 30"],
        "notes": ["Note 13", "Note 14", "Note 30"],
    },
    "minorities": {
        "keywords": ["non-controlling interest", "minority interest", "note 15"],
        "notes": ["Note 15"],
    },
    "tax": {
        "keywords": ["tax expense", "effective tax rate", "taxation", "income tax expense", "note 29", "note 9"],
        "notes": ["Note 29", "Note 9"],
    },
    "guidance": {
        "keywords": ["outlook", "guidance", "prospects", "future prospects", "trading update"],
        "notes": [],
    },
    "hedging": {
        "keywords": ["derivative financial instruments", "hedging", "forward exchange contracts", "note 6", "note 34"],
        "notes": ["Note 6", "Note 34"],
    },
    "acquisitions_disposals": {
        "keywords": ["business combinations", "acquisitions", "disposals", "subsidiaries", "note 31"],
        "notes": ["Note 31"],
    },
    "impairments": {
        "keywords": ["impairment", "write-down", "expected credit loss", "ecl", "impairment of", "note 12", "note 8", "note 11"],
        "notes": ["Note 12", "Note 8", "Note 11"],
    },
    "provisions": {
        "keywords": ["provisions", "provision for", "note 22", "note 19"],
        "notes": ["Note 22", "Note 19"],
    },
    "contingent_liabilities": {
        "keywords": ["contingent liabilities", "guarantees", "litigation", "note 32"],
        "notes": ["Note 32"],
    },
    "covenants": {
        "keywords": ["covenant", "covenants", "financial covenants", "debt covenants", "borrowing covenants", "note 16"],
        "notes": ["Note 16", "Note 34"],
    },
    "operational_constraints": {
        "keywords": ["port delays", "load shedding", "supply chain disruption", "bottleneck", "operational constraint", "infrastructure failure"],
        "notes": [],
    },
}


def evaluate_checklist(
    report: ReconciliationReport,
    extracted_doc: Optional[ExtractedDocument] = None,
    all_candidates: Optional[List[NumericCandidate]] = None,
    is_mining_or_producer: bool = False,
) -> List[ChecklistItem]:
    """Evaluate candidate evidence and active document search against the 20 mandatory categories."""
    active_candidates = report.verified_candidates + report.review_candidates

    items: List[ChecklistItem] = []

    def get_cands(keywords: List[str]) -> List[HistoricalActualCandidate]:
        matched = []
        for c in active_candidates:
            c_str = f"{c.concept} {c.raw_token} {c.qualifiers.get('concept', '')}".lower()
            if any(k in c_str for k in keywords):
                matched.append(c)
        return matched

    def search_all_candidates(keywords: List[str]) -> List[NumericCandidate]:
        if not all_candidates:
            return []
        matched = []
        for c in all_candidates:
            lbl = f"{c.nearby_label or ''} {c.sentence_text}".lower()
            if any(k in lbl for k in keywords):
                matched.append(c)
        return matched

    def search_document_text(keywords: List[str]) -> List[Tuple[int, str]]:
        if not extracted_doc:
            return []
        hits: List[Tuple[int, str]] = []
        for p in extracted_doc.pages:
            p_lower = p.raw_text.lower()
            for kw in keywords:
                if kw in p_lower:
                    # Find snippet
                    idx = p_lower.find(kw)
                    snippet = p.raw_text[max(0, idx - 40) : min(len(p.raw_text), idx + 80)].replace("\n", " ").strip()
                    hits.append((p.page_number, snippet))
                    break
        return hits

    for cat_id, display in CHECKLIST_CATEGORIES:
        matched: List[HistoricalActualCandidate] = []
        status = ChecklistStatus.NOT_FOUND
        notes = "No candidate disclosures identified."
        source_pages: List[int] = []
        sample_val: Optional[str] = None
        primary_c: Optional[str] = None

        search_rules = CATEGORY_DOCUMENT_SEARCH_RULES.get(cat_id, {})
        keywords = search_rules.get("keywords", [])
        expected_notes = search_rules.get("notes", [])

        if cat_id == "accounting_revenue_sales_basis":
            matched = get_cands(["revenue", "sale_of_merchandise", "sales", "turnover"])
        elif cat_id == "operating_trading_margin_basis":
            matched = get_cands(["margin", "trading_profit", "operating_profit", "pbit"])
        elif cat_id == "production_output_volumes":
            if not is_mining_or_producer:
                status = ChecklistStatus.NOT_APPLICABLE
                notes = "Not applicable to general merchandise retailer."
            else:
                matched = get_cands(["production", "output", "tonnes", "koz", "volume"])
        elif cat_id == "realised_prices":
            if not is_mining_or_producer:
                status = ChecklistStatus.NOT_APPLICABLE
                notes = "Not applicable to general merchandise retailer."
            else:
                matched = get_cands(["realised_price", "usd/oz", "zar/t"])
        elif cat_id == "unit_costs_aisc":
            if not is_mining_or_producer:
                status = ChecklistStatus.NOT_APPLICABLE
                notes = "Not applicable to general merchandise retailer."
            else:
                matched = get_cands(["aisc", "cash_cost", "cost_per_tonne"])
        elif cat_id == "capex_basis":
            matched = get_cands(["capex", "capital_expenditure", "additions"])
        elif cat_id == "working_capital":
            matched = get_cands(["working_capital", "receivables", "inventor", "payables"])
        elif cat_id == "debt_net_debt":
            matched = get_cands(["debt", "borrowing", "overdraft", "net_cash", "cash_and_cash_equivalents"])
        elif cat_id == "lease_liabilities":
            matched = get_cands(["lease_liabilit", "lease_payment", "right_of_use"])
        elif cat_id == "share_count":
            matched = get_cands(["shares", "share_capital", "treasury_shares"])
        elif cat_id == "minorities":
            matched = get_cands(["non_controlling", "minorities"])
        elif cat_id == "tax":
            matched = get_cands(["tax", "effective_tax_rate"])
        elif cat_id == "guidance":
            matched = [c for c in report.rejected_candidates if "guidance" in (c.kev_result or {}).get("alias_role", "").lower()]
        elif cat_id == "hedging":
            matched = get_cands(["hedge", "derivative", "forward_exchange"])
        elif cat_id == "acquisitions_disposals":
            matched = get_cands(["acquisition", "disposal", "subsidiary"])
        elif cat_id == "impairments":
            matched = get_cands(["impairment", "write_down"])
        elif cat_id == "provisions":
            matched = get_cands(["provision", "allowance"])
        elif cat_id == "contingent_liabilities":
            matched = get_cands(["contingent", "guarantee"])
        elif cat_id == "covenants":
            matched = get_cands(["covenant"])
        elif cat_id == "operational_constraints":
            matched = get_cands(["bottleneck", "constraint", "disruption"])

        # Determine status
        if status != ChecklistStatus.NOT_APPLICABLE:
            if matched:
                has_verified = any(c.final_status == "VERIFIED" for c in matched)
                if has_verified:
                    status = ChecklistStatus.VERIFIED
                    notes = f"{len(matched)} candidate occurrences verified."
                else:
                    status = ChecklistStatus.REQUIRES_REVIEW
                    notes = f"{len(matched)} candidates found, requiring analyst confirmation."
                sample_val = str(matched[0].value)
                primary_c = matched[0].concept
                source_pages = sorted(list(set(c.source_page for c in matched)))
            else:
                # Active whole-document search before declaring NOT_FOUND!
                extra_cands = search_all_candidates(keywords)
                doc_hits = search_document_text(keywords)

                if extra_cands:
                    status = ChecklistStatus.REQUIRES_REVIEW
                    cand_pgs = sorted(list(set(c.page_number for c in extra_cands)))
                    source_pages = cand_pgs
                    sample_val = str(extra_cands[0].normalized_value)
                    primary_c = extra_cands[0].nearby_label or cat_id
                    notes = f"Located {len(extra_cands)} unclassified numeric candidates across p.{cand_pgs[:5]}."
                elif doc_hits:
                    status = ChecklistStatus.REQUIRES_REVIEW
                    hit_pgs = sorted(list(set(h[0] for h in doc_hits)))
                    source_pages = hit_pgs
                    sample_val = f"Snippet: {doc_hits[0][1][:40]}..."
                    primary_c = cat_id
                    notes = f"Active search identified disclosures on p.{hit_pgs[:5]} ({', '.join(expected_notes) if expected_notes else 'sections'}). Requires qualitative review."
                else:
                    status = ChecklistStatus.NOT_FOUND
                    total_p = extracted_doc.page_count if extracted_doc else "document"
                    notes = f"Searched full {total_p} pages across notes and text; not disclosed."

        items.append(
            ChecklistItem(
                category=cat_id,
                display_name=display,
                status=status,
                candidate_count=len(matched),
                primary_concept=primary_c,
                sample_value=sample_val,
                source_pages=source_pages,
                notes=notes,
            )
        )

    return items
