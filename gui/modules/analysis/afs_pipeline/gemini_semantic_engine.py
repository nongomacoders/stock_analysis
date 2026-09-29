"""Experimental Gemini-First Semantic Extraction Engine for AFS Pipeline.

Supports:
- Feature flag: AFS_SEMANTIC_ENGINE ("kev" or "gemini")
- Two Gemini extraction modes:
  1. MODE A: Candidate Adjudication (Candidate-level semantic classification)
  2. MODE B: Paragraph Fact Extraction (Block-level fact extraction matched to Python candidates)
- Python evidence validation:
  - Verbatim token match in supplied context
  - Matching back to deterministic NumericCandidate
  - Verbatim quote match
  - Valid canonical concept enum
  - Strict temporal period preservation (comparative cannot become current)
  - Gemini strictly prohibited from altering or inventing numbers
- Material Category Routing:
  - Guaranteed submission across all mandatory financial categories
- Deterministic Derived Metrics:
  - Python-owned calculations (trading margin, cash capex, net cash, total leases, external shares)
  - Component evidence IDs and formulas preserved
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from modules.analysis.selector import managed_query_ai, TASK_MAP
from .document_extraction import ExtractedDocument, ExtractedParagraph
from .evidence_package import ContextEvidencePackage
from .numeric_candidates import NumericCandidate
from .reconciliation import HistoricalActualCandidate

logger = logging.getLogger(__name__)

# Feature flag & supported engines
AFS_SEMANTIC_ENGINE = os.getenv("AFS_SEMANTIC_ENGINE", "kev")
SUPPORTED_SEMANTIC_ENGINES = ["kev", "gemini"]
SUPPORTED_GEMINI_MODES = ["mode_a", "mode_b"]

PROMPT_VERSION_MODE_A = "afs_gemini_mode_a_v1"
PROMPT_VERSION_MODE_B = "afs_gemini_mode_b_v1"

# Cost per token for gemini-3.6-flash (standard rates)
COST_PER_INPUT_TOKEN = 0.075 / 1_000_000.0
COST_PER_OUTPUT_TOKEN = 0.30 / 1_000_000.0

# Canonical financial concepts permitted for AFS extraction
CANONICAL_CONCEPTS_ALLOWED = {
    # Revenue & Income
    "accounting_revenue",
    "sale_of_merchandise",
    "retail_sales",
    "turnover",
    "gross_profit",
    "trading_profit",
    "operating_profit",
    "profit_before_finance_costs_and_tax",
    "profit_before_tax",
    "profit_for_period",
    "headline_earnings",
    "attributable_earnings",
    # Balance Sheet Assets
    "cash_and_cash_equivalents",
    "money_market_funds",
    "trade_and_other_receivables",
    "inventories",
    "property_plant_equipment",
    "intangible_assets",
    "goodwill",
    "total_assets",
    # Balance Sheet Liabilities & Equity
    "interest_bearing_borrowings",
    "bank_overdraft",
    "lease_liabilities",
    "lease_liabilities_current",
    "lease_liabilities_noncurrent",
    "issued_shares",
    "issued_shares_current",
    "treasury_shares",
    "external_shares_ex_treasury",
    "total_equity",
    # Cash Flow & Capex
    "operating_cash_flow",
    "cash_generated_from_operations",
    "working_capital_movement",
    "working_capital_cash_flow",
    "cash_capex",
    "total_capex",
    "capex_expansion",
    "capex_maintenance",
    "intangible_additions",
    "depreciation_amortisation_expense",
    "depreciation_amortisation_cashflow_addback",
    "depreciation_and_amortisation",
    # Margins & Rates & Per-Share
    "trading_margin",
    "operating_margin",
    "gross_margin",
    "effective_tax_rate",
    "statutory_tax_rate",
    "tax_expense",
    "eps",
    "heps",
    "diluted_eps",
    "diluted_heps",
    "weighted_average_basic_shares",
    "weighted_average_diluted_shares",
    "reported_net_cash",
    "reported_net_debt",
    # Mining / Resource specific
    "production",
    "sales_volumes",
    "realised_commodity_price",
    "aisc_unit_cost",
    "aic_unit_cost",
    "cash_costs",
    "head_grade",
    "recovered_grade",
    "plant_recovery",
    "recovery",
    "plant_throughput",
    "throughput",
    "guidance",
    "hedging",
    "unit_cost",
    "gold_produced",
    "gold_sold",
    "gold_price",
    "ebitda",
    "adjusted_ebitda",
    "sustaining_capex",
    "net_debt",
    "unknown",
}


@dataclass
class GeminiExecutionMetrics:
    call_count: int = 0
    prompt_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    total_latency_ms: float = 0.0
    estimated_cost_usd: float = 0.0
    model_name: str = "gemini-3.8-flash"
    model_version: str = "gemini-3.8-flash"
    temperature: float = 0.0

    def record_call(
        self,
        prompt_tokens: int,
        output_tokens: int,
        latency_ms: float,
        model_version: Optional[str] = None,
    ):
        self.call_count += 1
        self.prompt_tokens += prompt_tokens
        self.output_tokens += output_tokens
        self.total_tokens += prompt_tokens + output_tokens
        self.total_latency_ms += latency_ms
        if model_version:
            self.model_version = model_version
        self.estimated_cost_usd += (
            prompt_tokens * COST_PER_INPUT_TOKEN + output_tokens * COST_PER_OUTPUT_TOKEN
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "call_count": self.call_count,
            "requested_model": self.model_name,
            "returned_model_version": self.model_version,
            "temperature": self.temperature,
            "prompt_tokens": self.prompt_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "total_latency_ms": round(self.total_latency_ms, 2),
            "estimated_cost_usd": round(self.estimated_cost_usd, 6),
            "model_name": self.model_name,
        }


@dataclass(frozen=True)
class DerivedFinancialMetric:
    metric_name: str
    display_name: str
    value: Decimal
    formula: str
    component_evidence_ids: List[str]
    component_descriptions: List[str]
    source_pages: List[int]
    provenance_quote: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "display_name": self.display_name,
            "value": str(self.value),
            "formula": self.formula,
            "component_evidence_ids": self.component_evidence_ids,
            "component_descriptions": self.component_descriptions,
            "source_pages": self.source_pages,
            "provenance_quote": self.provenance_quote,
        }


# ==============================================================================
# Material Category Routing
# ==============================================================================

MANDATORY_CATEGORIES_RETAIL = [
    "revenue",
    "sale_of_merchandise",
    "trading_profit",
    "margins",
    "tax",
    "capex",
    "working_capital",
    "borrowings_debt",
    "leases",
    "shares",
    "depreciation_amortisation",
]

MANDATORY_CATEGORIES_MINING = [
    "production",
    "realised_commodity_price",
    "aisc_unit_cost",
    "head_grade",
    "recovery",
    "throughput",
    "guidance",
    "hedging",
]


def select_candidates_by_material_categories(
    packages: Sequence[ContextEvidencePackage],
    is_mining: bool = False,
    max_per_category: int = 10,
) -> List[ContextEvidencePackage]:
    """Select candidate packages guaranteeing coverage across all mandatory categories.
    
    Guarantees every mandatory category receives its top candidates without
    premature global ranking truncation.
    """
    selected: List[ContextEvidencePackage] = []
    seen_ids: Set[str] = set()

    # 1. Guaranteed primary statement / salient candidates
    for pkg in packages:
        is_primary = False
        if pkg.page_number in (18, 19, 20, 21):
            is_primary = True
        else:
            sh = (pkg.section_heading or "").lower()
            ts = pkg.target_sentence.lower()
            tp = (pkg.target_paragraph or "").lower()[:150]
            for term in [
                "statement of comprehensive income",
                "statement of profit or loss",
                "statement of financial position",
                "statement of cash flows",
                "statement of changes in equity",
                "condensed consolidated statement",
                "salient features",
                "summary of salient",
            ]:
                if term in sh or term in ts or term in tp:
                    is_primary = True
                    break
        if is_primary and pkg.temporal_role == "CURRENT_PERIOD":
            if pkg.evidence_id not in seen_ids:
                selected.append(pkg)
                seen_ids.add(pkg.evidence_id)

    # 2. Key note keywords mapping
    category_patterns = {
        "revenue": ["note 26", "revenue", "sale of merchandise", "merchandise"],
        "sale_of_merchandise": ["note 26", "merchandise sales", "sale of merchandise"],
        "trading_profit": ["trading profit", "trading margin", "operating profit", "profit before finance"],
        "margins": ["note 35", "segment", "margin"],
        "tax": ["note 29", "tax", "taxation", "effective tax", "tax rate"],
        "capex": ["note 17", "note 33", "capital expenditure", "additions", "expansion", "maintenance", "sustaining"],
        "working_capital": ["note 33", "working capital", "inventories", "receivables"],
        "borrowings_debt": ["note 16", "borrowings", "debt", "facility", "credit", "net debt"],
        "leases": ["note 20", "lease liabilities", "lease liability", "ifrs 16"],
        "shares": ["note 13", "note 14", "note 31", "share capital", "treasury shares", "weighted average"],
        "depreciation_amortisation": ["note 27", "note 33", "depreciation", "amortisation"],
    }

    if is_mining:
        category_patterns.update({
            "production": ["production", "tonnes", "ounces", "mined", "milled", "gold produced", "pgm", "oz"],
            "sales_volumes": ["sales", "sold", "gold sold", "ounces sold", "tonnes sold"],
            "realised_commodity_price": ["realised price", "average price", "commodity", "gold price", "price received", "average gold price"],
            "aisc_unit_cost": ["aisc", "all-in sustaining", "cost per tonne", "cash cost", "cost per ounce", "unit cost", "all-in costs", "aic"],
            "head_grade": ["grade", "g/t", "head grade", "recovered grade"],
            "recovery": ["recovery", "plant recovery", "overall recovery"],
            "throughput": ["throughput", "milled", "processed", "treated", "tonnes milled", "tonnes processed"],
            "guidance": ["guidance", "target", "forecast", "outlook"],
            "hedging": ["hedge", "hedging", "derivative", "forward contract", "collar", "gold loan"],
        })

    # For each category, select best candidates
    for cat, patterns in category_patterns.items():
        cat_matches = []
        for pkg in packages:
            if pkg.evidence_id in seen_ids:
                continue
            nh = (pkg.note_heading or "").lower()
            sh = (pkg.section_heading or "").lower()
            dl = (pkg.detected_label or "").lower()
            ts = pkg.target_sentence.lower()

            match_score = 0
            # Specific category boosts
            if cat == "tax":
                if "effective" in dl and "tax" in dl:
                    match_score += 50
                elif "effective" in ts and "tax" in ts:
                    match_score += 40
                elif "tax rate" in dl or "tax rate" in ts:
                    match_score += 30
            elif cat == "shares":
                if "weighted average" in dl or "weighted average" in ts:
                    match_score += 45
                elif "treasury" in dl or "treasury" in ts:
                    match_score += 40
            elif cat == "capex":
                if "capital expenditure" in dl or "capital expenditure" in ts:
                    match_score += 40
                elif "additions" in dl or "additions" in ts:
                    match_score += 30
            elif cat == "leases":
                if "lease liabilities" in dl or "lease liabilities" in ts:
                    match_score += 40
            elif cat == "trading_profit":
                if "trading profit" in dl or "trading profit" in ts:
                    match_score += 40
            elif cat == "sale_of_merchandise":
                if "sale of merchandise" in dl or "sale of merchandise" in ts:
                    match_score += 40
            elif is_mining:
                if cat == "aisc_unit_cost" and any(k in dl or k in ts for k in ["aisc", "all-in sustaining", "cost per ounce", "cash cost"]):
                    match_score += 50
                elif cat == "production" and any(k in dl or k in ts for k in ["gold produced", "ounces produced", "production"]):
                    match_score += 45
                elif cat == "sales_volumes" and any(k in dl or k in ts for k in ["gold sold", "ounces sold"]):
                    match_score += 45
                elif cat == "head_grade" and any(k in dl or k in ts for k in ["grade", "g/t"]):
                    match_score += 40
                elif cat == "realised_commodity_price" and any(k in dl or k in ts for k in ["realised", "gold price", "price received"]):
                    match_score += 45
                elif cat == "recovery" and any(k in dl or k in ts for k in ["recovery", "recovered grade"]):
                    match_score += 40
                elif cat == "throughput" and any(k in dl or k in ts for k in ["milled", "processed", "tonnes"]):
                    match_score += 40
                elif cat == "hedging" and any(k in dl or k in ts for k in ["hedge", "hedging", "gold loan", "derivative"]):
                    match_score += 40

            for pat in patterns:
                if pat in nh:
                    match_score += 15
                if pat in dl:
                    match_score += 10
                if pat in ts:
                    match_score += 5
                if pat in sh:
                    match_score += 3

            if match_score > 0 and pkg.temporal_role != "COMPARATIVE_PERIOD":
                cat_matches.append((match_score, pkg))

        cat_matches.sort(key=lambda x: x[0], reverse=True)
        for _, pkg in cat_matches[:max_per_category]:
            if pkg.evidence_id not in seen_ids:
                selected.append(pkg)
                seen_ids.add(pkg.evidence_id)

    return selected


def select_paragraphs_by_material_categories(
    extracted_doc: ExtractedDocument,
    is_mining: bool = False,
) -> List[ExtractedParagraph]:
    """Select financially relevant paragraph/table blocks covering all mandatory categories."""
    selected: List[ExtractedParagraph] = []
    seen_ids: Set[str] = set()

    # 1. Primary financial statement paragraphs (pages 18, 19, 20, 21)
    for p in extracted_doc.paragraphs_by_id.values():
        if p.page_number in (18, 19, 20, 21):
            if any(char.isdigit() for char in p.text) and len(p.text.split()) >= 6:
                if p.paragraph_id not in seen_ids:
                    selected.append(p)
                    seen_ids.add(p.paragraph_id)

    # 2. Key note targets by note number and keywords
    note_targets = [
        # Retail notes
        ("11", "trade and other receivables"),
        ("12", "cash and cash equivalents"),
        ("13", "share capital"),
        ("14", "treasury shares"),
        ("16", "interest-bearing borrowings"),
        ("17", "property, plant and equipment"),
        ("20.1", "lease liabilities"),
        ("26", "revenue"),
        ("27.2", "depreciation and amortisation"),
        ("29.2", "taxation"),
        ("31.1", "earnings per share"),
        ("31.2", "diluted earnings per share"),
        ("33.1", "depreciation and amortisation addback"),
        ("33.2", "working capital"),
        ("33.3", "net cash"),
        ("33.5", "additions"),
        ("33.6", "additions to intangible assets"),
        ("35", "segment reporting"),
    ]

    for p in extracted_doc.paragraphs_by_id.values():
        if p.paragraph_id in seen_ids:
            continue
        p_text_lower = p.text.lower()
        # Check note target matches
        for note_num, keyword in note_targets:
            if (f"note {note_num}" in p_text_lower or f"note {note_num.split('.')[0]}" in p_text_lower) and keyword in p_text_lower:
                if any(char.isdigit() for char in p.text) and len(p.text.split()) >= 8:
                    selected.append(p)
                    seen_ids.add(p.paragraph_id)
                    break

    return selected


# ==============================================================================
# MODE A: Candidate Adjudication
# ==============================================================================

MODE_A_SCHEMA = {
    "type": "object",
    "properties": {
        "candidate_raw_token": {
            "type": "string",
            "description": "Must match the candidate raw numeric token verbatim.",
        },
        "canonical_concept": {
            "type": "string",
            "description": "Exact canonical financial concept from the permitted list or 'unknown'.",
        },
        "temporal_classification": {
            "type": "string",
            "enum": ["historical_actual", "comparative_period", "guidance", "target", "change_only", "unknown"],
        },
        "scope": {
            "type": "string",
            "enum": ["group_consolidated", "total_operations", "continuing_operations", "discontinued_operations", "segment", "company_standalone", "unspecified"],
        },
        "dilution_basis": {
            "type": "string",
            "enum": ["basic", "diluted", "unspecified"],
        },
        "tax_basis": {
            "type": "string",
            "enum": ["gross", "net", "unspecified"],
        },
        "capex_basis": {
            "type": "string",
            "enum": ["cash_payments", "accounting_additions", "unspecified"],
        },
        "lease_inclusion": {
            "type": "string",
            "enum": ["inc_leases", "ex_leases", "unspecified"],
        },
        "margin_denominator": {
            "type": "string",
            "enum": ["accounting_revenue", "merchandise_sales", "turnover", "unspecified"],
        },
        "attribution": {
            "type": "string",
            "enum": ["parent_equity_holders", "total_group", "non_controlling_interest", "headline_attributable", "unspecified"],
        },
        "alias_role": {
            "type": "string",
            "enum": ["DIRECT_VALUE_LABEL", "ROW_HEADER", "COLUMN_HEADER", "NOTE_REFERENCE", "TOTAL_LINE", "SUBTOTAL_LINE", "UNSPECIFIED"],
        },
        "value_pattern": {
            "type": "string",
            "enum": ["DIRECT_LEVEL", "CHANGE_AMOUNT", "RATIO_PERCENT", "COUNT_SHARES", "UNSPECIFIED"],
        },
        "should_abstain": {
            "type": "boolean",
            "description": "True if evidence is insufficient or ambiguous to assign a canonical concept.",
        },
        "supporting_quote": {
            "type": "string",
            "description": "Exact verbatim substring from the supplied text supporting this classification.",
        },
        "reasoning": {
            "type": "string",
            "description": "Brief factual explanation.",
        },
    },
    "required": [
        "candidate_raw_token",
        "canonical_concept",
        "temporal_classification",
        "scope",
        "dilution_basis",
        "tax_basis",
        "capex_basis",
        "lease_inclusion",
        "margin_denominator",
        "attribution",
        "should_abstain",
        "supporting_quote",
    ],
}


def build_mode_a_prompt(package: ContextEvidencePackage) -> str:
    """Build candidate-level semantic classification prompt."""
    prompt = f"""You are a skeptical financial accounting semantic adjudicator analyzing an extract from an Annual Financial Statements (AFS) document.

IMPORTANT RULES:
1. YOU MUST NOT RECALCULATE, GUESS, OR ALTER THE CANDIDATE NUMBER.
2. DO NOT INFER FROM USUAL ACCOUNTING CONVENTION. Use ONLY explicit factual evidence in the supplied text.
3. If the supplied evidence does not explicitly establish a qualifier, return 'unspecified'.
4. If evidence is ambiguous, missing, or insufficient to classify, set 'should_abstain': true.
5. Your supporting_quote MUST be an exact verbatim substring from the supplied text.
6. Output STRICT valid JSON matching the requested schema. No surrounding markdown formatting, no commentary.

CONTEXT:
Document ID: {package.document_id}
Ticker: {package.ticker}
Financial Period: {package.financial_period}
Page: {package.page_number}
Section Heading: {package.section_heading or 'N/A'}
Note Heading: {package.note_heading or 'N/A'}

PREVIOUS PARAGRAPH:
\"\"\"{package.previous_paragraph or 'None'}\"\"\"

TARGET PARAGRAPH:
\"\"\"{package.target_paragraph}\"\"\"

NEXT PARAGRAPH:
\"\"\"{package.next_paragraph or 'None'}\"\"\"

TARGET SENTENCE:
\"\"\"{package.target_sentence}\"\"\"

CANDIDATE NUMBER DETAILS (OWNED BY PYTHON):
- Raw Token: "{package.candidate_numeric_token}"
- Deterministic Normalized Value: {package.deterministic_normalized_value}
- Unit: {package.unit or 'unspecified'}
- Currency: {package.currency or 'unspecified'}
- Detected Label: "{package.detected_label or 'N/A'}"
- Syntactic Role: {package.numeric_role}
- Note Reference: {package.note_reference or 'N/A'}
- Deterministic Temporal Role: {package.temporal_role or 'unspecified'}

ALLOWED CANONICAL CONCEPTS:
{sorted(list(CANONICAL_CONCEPTS_ALLOWED))}

JSON SCHEMA TO RETURN:
{json.dumps(MODE_A_SCHEMA, indent=2)}
"""
    return prompt


def verify_mode_a_response(
    package: ContextEvidencePackage,
    parsed: Dict[str, Any],
) -> Tuple[bool, List[str]]:
    """Python verification checks on Gemini Mode A output."""
    errors = []

    # 1. Candidate raw token match
    raw_tok = parsed.get("candidate_raw_token", "").strip()
    if re.sub(r"\s+", "", raw_tok) != re.sub(r"\s+", "", package.candidate_numeric_token):
        errors.append(
            f"Candidate token mismatch: Gemini reported '{raw_tok}', expected '{package.candidate_numeric_token}'"
        )

    # 2. Verbatim quote match
    quote = parsed.get("supporting_quote", "").strip()
    if not quote:
        errors.append("Supporting quote is missing or empty")
    else:
        full_context = f"{package.previous_paragraph or ''}\n{package.target_paragraph}\n{package.next_paragraph or ''}"
        norm_context = re.sub(r"\s+", " ", full_context).lower()
        norm_quote = re.sub(r"\s+", " ", quote).lower()
        if norm_quote not in norm_context:
            errors.append(f"Supporting quote does not exist verbatim in supplied context: '{quote[:60]}...'")

    # 3. Canonical concept allowed
    concept = parsed.get("canonical_concept")
    if concept and concept not in CANONICAL_CONCEPTS_ALLOWED:
        errors.append(f"Canonical concept '{concept}' not recognized in allowed taxonomy")

    # 4. Temporal rule: deterministic comparative column cannot become historical actual
    if package.temporal_role == "COMPARATIVE_PERIOD":
        if parsed.get("temporal_classification") == "historical_actual":
            errors.append("Comparative period candidate cannot be classified as current historical_actual")

    # 4b. Change-only rule: deterministic Movement/change% column (or change-role
    # token) cannot become a historical actual level.
    if package.temporal_role == "CHANGE_RATE" or package.numeric_role in ("CHANGE_AMOUNT", "CHANGE_RATE"):
        if parsed.get("temporal_classification") == "historical_actual":
            errors.append("Change-only candidate cannot be classified as current historical_actual")

    # 5. Enum validation
    for field_name, schema in MODE_A_SCHEMA["properties"].items():
        if "enum" in schema:
            val = parsed.get(field_name)
            if val is not None and val not in schema["enum"]:
                errors.append(f"Invalid enum value '{val}' for field '{field_name}'. Allowed: {schema['enum']}")

    is_valid = len(errors) == 0
    return is_valid, errors


# ==============================================================================
# MODE B: Paragraph Fact Extraction
# ==============================================================================

MODE_B_SCHEMA = {
    "type": "object",
    "properties": {
        "block_id": {"type": "string"},
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "raw_token": {
                        "type": "string",
                        "description": "The exact numeric token as it appears VERBATIM in the text. DO NOT calculate, round, or alter it.",
                    },
                    "canonical_concept": {
                        "type": "string",
                        "description": "Exact canonical financial concept from the permitted list or 'unknown'.",
                    },
                    "temporal_classification": {
                        "type": "string",
                        "enum": ["historical_actual", "comparative_period", "guidance", "target", "change_only", "unknown"],
                    },
                    "period": {
                        "type": "string",
                        "description": "Financial period for this number (e.g. FY2025, FY2024, etc.).",
                    },
                    "scope": {
                        "type": "string",
                        "enum": ["group_consolidated", "total_operations", "continuing_operations", "discontinued_operations", "segment", "company_standalone", "unspecified"],
                    },
                    "dilution_basis": {
                        "type": "string",
                        "enum": ["basic", "diluted", "unspecified"],
                    },
                    "tax_basis": {
                        "type": "string",
                        "enum": ["gross", "net", "unspecified"],
                    },
                    "capex_basis": {
                        "type": "string",
                        "enum": ["cash_payments", "accounting_additions", "unspecified"],
                    },
                    "lease_inclusion": {
                        "type": "string",
                        "enum": ["inc_leases", "ex_leases", "unspecified"],
                    },
                    "margin_denominator": {
                        "type": "string",
                        "enum": ["accounting_revenue", "merchandise_sales", "turnover", "unspecified"],
                    },
                    "attribution": {
                        "type": "string",
                        "enum": ["parent_equity_holders", "total_group", "non_controlling_interest", "headline_attributable", "unspecified"],
                    },
                    "evidence_quote": {
                        "type": "string",
                        "description": "Verbatim excerpt from the block containing this fact.",
                    },
                    "confidence_status": {
                        "type": "string",
                        "enum": ["VERIFIED", "REQUIRES_REVIEW"],
                    },
                },
                "required": [
                    "raw_token",
                    "canonical_concept",
                    "temporal_classification",
                    "period",
                    "scope",
                    "evidence_quote",
                ],
            },
        },
    },
    "required": ["block_id", "facts"],
}


def build_mode_b_prompt(
    paragraph: ExtractedParagraph,
    ticker: str,
    financial_period: str,
    section_heading: Optional[str] = None,
    note_heading: Optional[str] = None,
) -> str:
    """Build paragraph/table block fact extraction prompt."""
    prompt = f"""You are a skeptical financial accounting extraction engine analyzing a text block from an Annual Financial Statements (AFS) document.

IMPORTANT RULES:
1. YOU MAY ONLY SELECT NUMERIC TOKENS THAT LITERALLY OCCUR IN THE SUPPLIED TEXT.
2. DO NOT CALCULATE NEW VALUES. DO NOT CREATE NUMBERS. DO NOT INFER AN OMITTED VALUE.
3. raw_token MUST match the exact substring in the supplied text verbatim (including commas, negatives, decimals).
4. If a number is comparative (prior period), set temporal_classification: 'comparative_period'.
5. evidence_quote MUST be an exact verbatim substring from the supplied text.
6. Output STRICT valid JSON matching the requested schema. No surrounding markdown formatting.

CONTEXT:
Ticker: {ticker}
Financial Period: {financial_period}
Page: {paragraph.page_number}
Section Heading: {section_heading or 'N/A'}
Note Heading: {note_heading or 'N/A'}
Block ID: {paragraph.paragraph_id}

SUPPLIED TEXT BLOCK:
\"\"\"{paragraph.text}\"\"\"

ALLOWED CANONICAL CONCEPTS:
{sorted(list(CANONICAL_CONCEPTS_ALLOWED))}

JSON SCHEMA TO RETURN:
{json.dumps(MODE_B_SCHEMA, indent=2)}
"""
    return prompt


def verify_and_match_mode_b_facts(
    paragraph: ExtractedParagraph,
    deterministic_candidates: Sequence[NumericCandidate],
    parsed_json: Dict[str, Any],
    financial_period: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
    """Match Gemini Mode B facts to deterministic NumericCandidates and validate."""
    accepted_facts: List[Dict[str, Any]] = []
    rejected_facts: List[Dict[str, Any]] = []
    log_errors: List[str] = []

    facts = parsed_json.get("facts", [])
    if not isinstance(facts, list):
        return accepted_facts, rejected_facts, ["'facts' field is not a list in Gemini response"]

    # Filter deterministic candidates belonging to this paragraph
    p_cands = [c for c in deterministic_candidates if c.paragraph_id == paragraph.paragraph_id]

    norm_block_text = re.sub(r"\s+", " ", paragraph.text).lower()

    for idx, fact in enumerate(facts):
        raw_tok = str(fact.get("raw_token", "")).strip()
        quote = str(fact.get("evidence_quote", "")).strip()
        concept = fact.get("canonical_concept")
        temporal = fact.get("temporal_classification")
        period = fact.get("period", financial_period)

        fact_errors = []

        # 1. Raw token non-empty and verbatim in text
        if not raw_tok:
            fact_errors.append("Empty raw_token")
        elif raw_tok.lower() not in norm_block_text:
            fact_errors.append(f"raw_token '{raw_tok}' does not occur in block text")

        # 2. Evidence quote verbatim in text
        if not quote:
            fact_errors.append("Empty evidence_quote")
        elif quote.lower() not in norm_block_text:
            fact_errors.append(f"evidence_quote '{quote[:40]}...' not found verbatim in text")

        # 3. Canonical concept allowed
        if not concept or concept not in CANONICAL_CONCEPTS_ALLOWED:
            fact_errors.append(f"Invalid canonical concept '{concept}'")

        # 4. Deterministic candidate matching
        # Match raw_token against p_cands
        matched_cand: Optional[NumericCandidate] = None
        for c in p_cands:
            c_tok_clean = re.sub(r"[^\d\.\-]", "", c.raw_token)
            fact_tok_clean = re.sub(r"[^\d\.\-]", "", raw_tok)
            if c_tok_clean == fact_tok_clean or c.raw_token.strip() == raw_tok:
                matched_cand = c
                break

        if not matched_cand:
            fact_errors.append(
                f"raw_token '{raw_tok}' cannot be mapped to any deterministic NumericCandidate on page {paragraph.page_number}"
            )
        else:
            # Check temporal consistency
            if getattr(matched_cand, "temporal_role", None) == "COMPARATIVE_PERIOD" and temporal == "historical_actual":
                fact_errors.append("Deterministic comparative candidate cannot be classified as historical_actual")
            if (
                getattr(matched_cand, "temporal_role", None) == "CHANGE_RATE"
                or getattr(matched_cand, "numeric_role", None) in ("CHANGE_AMOUNT", "CHANGE_RATE")
            ) and temporal == "historical_actual":
                fact_errors.append("Deterministic change-only candidate cannot be classified as historical_actual")

        if fact_errors:
            rejected = dict(fact)
            rejected["rejection_reasons"] = fact_errors
            rejected_facts.append(rejected)
            log_errors.extend(fact_errors)
        else:
            accepted = dict(fact)
            accepted["matched_candidate"] = matched_cand
            accepted_facts.append(accepted)

    return accepted_facts, rejected_facts, log_errors


# ==============================================================================
# Deterministic Derived Metrics (Python-Owned)
# ==============================================================================

def compute_deterministic_derived_metrics(
    candidates: Sequence[HistoricalActualCandidate],
    period: str,
) -> Tuple[List[HistoricalActualCandidate], List[DerivedFinancialMetric]]:
    """Deterministically compute derived metrics from verified component candidates.
    
    Gemini is strictly prohibited from calculating derived metrics.
    Python owns all arithmetic derivations and preserves component evidence IDs.
    """
    derived_candidates: List[HistoricalActualCandidate] = []
    derived_metrics: List[DerivedFinancialMetric] = []

    # Map current period candidates by concept
    by_concept: Dict[str, List[HistoricalActualCandidate]] = {}
    for c in candidates:
        if c.qualifiers.get("temporal_role") != "COMPARATIVE_PERIOD":
            by_concept.setdefault(c.concept, []).append(c)

    # 1. Trading Margin = Trading Profit / Sale of Merchandise * 100
    tp_cands = by_concept.get("trading_profit", [])
    sm_cands = by_concept.get("sale_of_merchandise", [])
    if tp_cands and sm_cands:
        tp = tp_cands[0]
        sm = sm_cands[0]
        if sm.value != 0:
            calc_val = (tp.value / sm.value) * Decimal(100)
            rounded_val = calc_val.quantize(Decimal("0.0001"))
            metric = DerivedFinancialMetric(
                metric_name="trading_margin",
                display_name="Trading Margin (%)",
                value=rounded_val,
                formula="trading_profit / sale_of_merchandise * 100",
                component_evidence_ids=[tp.evidence_id, sm.evidence_id],
                component_descriptions=[
                    f"Trading Profit: {tp.value} ({tp.evidence_id})",
                    f"Sale of Merchandise: {sm.value} ({sm.evidence_id})",
                ],
                source_pages=[tp.source_page, sm.source_page],
                provenance_quote=f"Derived from Trading Profit (R{tp.value}m) / Sale of Merchandise (R{sm.value}m)",
            )
            derived_metrics.append(metric)
            derived_candidates.append(
                HistoricalActualCandidate(
                    candidate_id=f"derived_trading_margin_{period}",
                    evidence_id=f"derived_trading_margin_{period}",
                    concept="trading_margin",
                    value=rounded_val,
                    raw_token=str(rounded_val),
                    unit="%",
                    currency=None,
                    period=period,
                    scope="group_consolidated",
                    qualifiers={
                        "is_derived": True,
                        "formula": metric.formula,
                        "component_evidence_ids": metric.component_evidence_ids,
                    },
                    source_page=tp.source_page,
                    source_paragraph_id=tp.source_paragraph_id,
                    extraction_method="DETERMINISTIC_DERIVED",
                    kev_result=None,
                    gemini_result=None,
                    safety_status="ACCEPT",
                    final_status="VERIFIED",
                    reconciliation_notes=metric.provenance_quote,
                )
            )

    # 2. Cash Capex = PPE Expansion + PPE Maintenance + Intangible Additions
    # Look for cash flow capex additions
    capex_cands = (
        by_concept.get("capex_expansion", [])
        + by_concept.get("capex_maintenance", [])
        + by_concept.get("intangible_additions", [])
    )
    if capex_cands:
        # Sum absolute values of cash capex additions
        total_capex_val = sum(abs(c.value) for c in capex_cands)
        metric = DerivedFinancialMetric(
            metric_name="cash_capex",
            display_name="Cash Capex",
            value=total_capex_val,
            formula="sum(abs(capex_components))",
            component_evidence_ids=[c.evidence_id for c in capex_cands],
            component_descriptions=[f"{c.concept}: {abs(c.value)}" for c in capex_cands],
            source_pages=list({c.source_page for c in capex_cands}),
            provenance_quote="Reconciled from cash flow additions components",
        )
        derived_metrics.append(metric)
        derived_candidates.append(
            HistoricalActualCandidate(
                candidate_id=f"derived_cash_capex_{period}",
                evidence_id=f"derived_cash_capex_{period}",
                concept="cash_capex",
                value=total_capex_val,
                raw_token=str(total_capex_val),
                unit="m",
                currency="ZAR",
                period=period,
                scope="group_consolidated",
                qualifiers={
                    "is_derived": True,
                    "formula": metric.formula,
                    "component_evidence_ids": metric.component_evidence_ids,
                },
                source_page=capex_cands[0].source_page,
                source_paragraph_id=capex_cands[0].source_paragraph_id,
                extraction_method="DETERMINISTIC_DERIVED",
                kev_result=None,
                gemini_result=None,
                safety_status="ACCEPT",
                final_status="VERIFIED",
                reconciliation_notes=metric.provenance_quote,
            )
        )

    # 3. Total Lease Liabilities = Non-Current + Current
    nc_leases = by_concept.get("lease_liabilities_noncurrent", [])
    curr_leases = by_concept.get("lease_liabilities_current", [])
    if nc_leases and curr_leases:
        nc = nc_leases[0]
        cur = curr_leases[0]
        total_l = nc.value + cur.value
        metric = DerivedFinancialMetric(
            metric_name="leases",
            display_name="Total Lease Liabilities",
            value=total_l,
            formula="lease_liabilities_noncurrent + lease_liabilities_current",
            component_evidence_ids=[nc.evidence_id, cur.evidence_id],
            component_descriptions=[
                f"Non-current: {nc.value} ({nc.evidence_id})",
                f"Current: {cur.value} ({cur.evidence_id})",
            ],
            source_pages=[nc.source_page, cur.source_page],
            provenance_quote=f"Non-current ({nc.value}m) + Current ({cur.value}m) = R{total_l}m",
        )
        derived_metrics.append(metric)
        derived_candidates.append(
            HistoricalActualCandidate(
                candidate_id=f"derived_total_leases_{period}",
                evidence_id=f"derived_total_leases_{period}",
                concept="leases",
                value=total_l,
                raw_token=str(total_l),
                unit="m",
                currency="ZAR",
                period=period,
                scope="group_consolidated",
                qualifiers={
                    "is_derived": True,
                    "formula": metric.formula,
                    "component_evidence_ids": metric.component_evidence_ids,
                },
                source_page=nc.source_page,
                source_paragraph_id=nc.source_paragraph_id,
                extraction_method="DETERMINISTIC_DERIVED",
                kev_result=None,
                gemini_result=None,
                safety_status="ACCEPT",
                final_status="VERIFIED",
                reconciliation_notes=metric.provenance_quote,
            )
        )

    # 4. External Shares = Issued Shares - Treasury Shares
    issued_cands = by_concept.get("issued_shares", []) or by_concept.get("issued_shares_current", [])
    treasury_cands = by_concept.get("treasury_shares", [])
    if issued_cands and treasury_cands:
        iss = issued_cands[0]
        tr = treasury_cands[0]
        # Standardize units: if treasury is in thousands (33,138), scale up if issued is full count
        iss_val = iss.value
        tr_val = tr.value
        if iss_val > 100_000_000 and tr_val < 100_000:
            tr_val = tr_val * 1000
        ext_val = iss_val - tr_val
        metric = DerivedFinancialMetric(
            metric_name="external_shares",
            display_name="External Shares (Net of Treasury)",
            value=ext_val,
            formula="issued_shares - treasury_shares",
            component_evidence_ids=[iss.evidence_id, tr.evidence_id],
            component_descriptions=[
                f"Issued shares: {iss.value} ({iss.evidence_id})",
                f"Treasury shares: {tr.value} ({tr.evidence_id})",
            ],
            source_pages=[iss.source_page, tr.source_page],
            provenance_quote=f"Issued ({iss_val}) - Treasury ({tr_val}) = {ext_val}",
        )
        derived_metrics.append(metric)
        derived_candidates.append(
            HistoricalActualCandidate(
                candidate_id=f"derived_external_shares_{period}",
                evidence_id=f"derived_external_shares_{period}",
                concept="external_shares",
                value=ext_val,
                raw_token=str(ext_val),
                unit="shares",
                currency=None,
                period=period,
                scope="group_consolidated",
                qualifiers={
                    "is_derived": True,
                    "formula": metric.formula,
                    "component_evidence_ids": metric.component_evidence_ids,
                },
                source_page=iss.source_page,
                source_paragraph_id=iss.source_paragraph_id,
                extraction_method="DETERMINISTIC_DERIVED",
                kev_result=None,
                gemini_result=None,
                safety_status="ACCEPT",
                final_status="VERIFIED",
                reconciliation_notes=metric.provenance_quote,
            )
        )

    # 5. Reported Net Cash = Cash + Fair value money market - Borrowings - Overdraft
    cash_cands = by_concept.get("cash_and_cash_equivalents", [])
    mm_cands = by_concept.get("money_market_funds", [])
    borrow_cands = by_concept.get("interest_bearing_borrowings", [])
    overdraft_cands = by_concept.get("bank_overdraft", [])
    if cash_cands and mm_cands and borrow_cands and overdraft_cands:
        c_val = cash_cands[0].value
        mm_val = mm_cands[0].value
        b_val = borrow_cands[0].value
        od_val = overdraft_cands[0].value
        net_cash_val = c_val + mm_val - b_val - od_val
        metric = DerivedFinancialMetric(
            metric_name="reported_net_cash",
            display_name="Reported Net Cash",
            value=net_cash_val,
            formula="cash + mm_funds - borrowings - overdraft",
            component_evidence_ids=[
                cash_cands[0].evidence_id,
                mm_cands[0].evidence_id,
                borrow_cands[0].evidence_id,
                overdraft_cands[0].evidence_id,
            ],
            component_descriptions=[
                f"Cash: {c_val}",
                f"MM Funds: {mm_val}",
                f"Borrowings: {b_val}",
                f"Overdraft: {od_val}",
            ],
            source_pages=[18],
            provenance_quote=f"Cash ({c_val}m) + MM ({mm_val}m) - Borrowings ({b_val}m) - Overdraft ({od_val}m) = R{net_cash_val}m",
        )
        derived_metrics.append(metric)
        derived_candidates.append(
            HistoricalActualCandidate(
                candidate_id=f"derived_reported_net_cash_{period}",
                evidence_id=f"derived_reported_net_cash_{period}",
                concept="reported_net_cash",
                value=net_cash_val,
                raw_token=str(net_cash_val),
                unit="m",
                currency="ZAR",
                period=period,
                scope="group_consolidated",
                qualifiers={
                    "is_derived": True,
                    "formula": metric.formula,
                    "component_evidence_ids": metric.component_evidence_ids,
                },
                source_page=18,
                source_paragraph_id=cash_cands[0].source_paragraph_id,
                extraction_method="DETERMINISTIC_DERIVED",
                kev_result=None,
                gemini_result=None,
                safety_status="ACCEPT",
                final_status="VERIFIED",
                reconciliation_notes=metric.provenance_quote,
            )
        )

    return derived_candidates, derived_metrics


# ==============================================================================
# Async Execution Runners for Mode A and Mode B
# ==============================================================================

async def execute_gemini_mode_a(
    packages: Sequence[ContextEvidencePackage],
    ticker: str,
    financial_period: str,
    concurrency: int = 4,
) -> Tuple[List[HistoricalActualCandidate], GeminiExecutionMetrics, List[Dict[str, Any]]]:
    """Execute Gemini Mode A (Candidate Adjudication) across selected candidates."""
    target_model = TASK_MAP.get("afs_gemini_candidate", {}).get("m", "gemini-3.8-flash")
    target_temp = TASK_MAP.get("afs_gemini_candidate", {}).get("t", 0.0)
    metrics = GeminiExecutionMetrics(model_name=target_model, temperature=target_temp)
    candidates: List[HistoricalActualCandidate] = []
    audit_logs: List[Dict[str, Any]] = []
    semaphore = asyncio.Semaphore(concurrency)

    async def _process_candidate(pkg: ContextEvidencePackage):
        async with semaphore:
            prompt = build_mode_a_prompt(pkg)
            t0 = time.perf_counter()
            trace = {}
            try:
                raw_res = await managed_query_ai("afs_gemini_candidate", prompt, request_trace=trace)
                latency_ms = (time.perf_counter() - t0) * 1000.0

                res_text = raw_res.strip() if isinstance(raw_res, str) else getattr(raw_res, "text", str(raw_res)).strip()
                clean_json = re.sub(r"^```(?:json)?\s*", "", res_text, flags=re.I)
                clean_json = re.sub(r"\s*```$", "", clean_json).strip()
                parsed = json.loads(clean_json)

                # Record usage metadata
                usage = getattr(raw_res, "usage_metadata", None)
                p_tok = getattr(usage, "prompt_token_count", len(prompt) // 4) if usage else len(prompt) // 4
                c_tok = getattr(usage, "candidates_token_count", len(res_text) // 4) if usage else len(res_text) // 4
                returned_version = trace.get("response_model_version") or getattr(raw_res, "model_version", target_model)
                metrics.record_call(p_tok, c_tok, latency_ms, model_version=returned_version)

                is_valid, validation_errors = verify_mode_a_response(pkg, parsed)
                status = "REJECTED"
                if is_valid:
                    if parsed.get("should_abstain"):
                        status = "REJECTED"
                    else:
                        status = "VERIFIED"

                cand_period = (
                    financial_period
                    if getattr(pkg, "temporal_role", None) != "COMPARATIVE_PERIOD"
                    else f"{financial_period}_COMPARATIVE"
                )

                qualifiers = {
                    "concept": parsed.get("canonical_concept", "unknown"),
                    "scope": parsed.get("scope", "unspecified"),
                    "dilution": parsed.get("dilution_basis", "unspecified"),
                    "tax_basis": parsed.get("tax_basis", "unspecified"),
                    "capex_basis": parsed.get("capex_basis", "unspecified"),
                    "lease_inclusion": parsed.get("lease_inclusion", "unspecified"),
                    "margin_denominator": parsed.get("margin_denominator", "unspecified"),
                    "profit_attribution": parsed.get("attribution", "unspecified"),
                    "alias_role": parsed.get("alias_role", "UNSPECIFIED"),
                    "value_pattern": parsed.get("value_pattern", "UNSPECIFIED"),
                    "temporal_role": pkg.temporal_role,
                    "note_reference": pkg.note_reference,
                    "detected_label": pkg.detected_label,
                }

                cand = HistoricalActualCandidate(
                    candidate_id=pkg.candidate_id,
                    evidence_id=pkg.evidence_id,
                    concept=parsed.get("canonical_concept", "unknown"),
                    value=pkg.deterministic_normalized_value,
                    raw_token=pkg.candidate_numeric_token,
                    unit=pkg.unit,
                    currency=pkg.currency,
                    period=cand_period,
                    scope=parsed.get("scope", "unspecified"),
                    qualifiers=qualifiers,
                    source_page=pkg.page_number,
                    source_paragraph_id=pkg.paragraph_id,
                    extraction_method="GEMINI_MODE_A",
                    kev_result=None,
                    gemini_result=parsed,
                    safety_status="ACCEPT" if status == "VERIFIED" else "ABSTAIN",
                    final_status=status,
                    reconciliation_notes="; ".join(validation_errors) if validation_errors else parsed.get("reasoning"),
                )
                candidates.append(cand)
                audit_logs.append({
                    "evidence_id": pkg.evidence_id,
                    "requested_model": trace.get("model", target_model),
                    "returned_model_version": returned_version,
                    "temperature": trace.get("temperature", target_temp),
                    "prompt_tokens": p_tok,
                    "output_tokens": c_tok,
                    "latency_ms": latency_ms,
                    "prompt": prompt,
                    "response": res_text,
                    "parsed": parsed,
                    "is_valid": is_valid,
                    "validation_errors": validation_errors,
                })

            except Exception as exc:
                latency_ms = (time.perf_counter() - t0) * 1000.0
                metrics.record_call(len(prompt) // 4, 0, latency_ms)
                logger.warning("Gemini Mode A call failed for %s: %s", pkg.evidence_id, exc)
                cand = HistoricalActualCandidate(
                    candidate_id=pkg.candidate_id,
                    evidence_id=pkg.evidence_id,
                    concept="unknown",
                    value=pkg.deterministic_normalized_value,
                    raw_token=pkg.candidate_numeric_token,
                    unit=pkg.unit,
                    currency=pkg.currency,
                    period=financial_period,
                    scope="unspecified",
                    qualifiers={"temporal_role": pkg.temporal_role},
                    source_page=pkg.page_number,
                    source_paragraph_id=pkg.paragraph_id,
                    extraction_method="GEMINI_MODE_A",
                    kev_result=None,
                    gemini_result={"error": str(exc)},
                    safety_status="ABSTAIN",
                    final_status="REJECTED",
                    reconciliation_notes=f"Exception: {exc}",
                )
                candidates.append(cand)
                audit_logs.append({
                    "evidence_id": pkg.evidence_id,
                    "requested_model": target_model,
                    "returned_model_version": None,
                    "temperature": target_temp,
                    "prompt": prompt,
                    "error": str(exc),
                    "is_valid": False,
                })

    tasks = [_process_candidate(pkg) for pkg in packages]
    await asyncio.gather(*tasks)
    return candidates, metrics, audit_logs


async def execute_gemini_mode_b(
    paragraphs: Sequence[ExtractedParagraph],
    all_candidates: Sequence[NumericCandidate],
    ticker: str,
    financial_period: str,
    concurrency: int = 4,
) -> Tuple[List[HistoricalActualCandidate], GeminiExecutionMetrics, List[Dict[str, Any]]]:
    """Execute Gemini Mode B (Paragraph Fact Extraction) across selected paragraph blocks."""
    target_model = TASK_MAP.get("afs_gemini_paragraph", {}).get("m", "gemini-3.8-flash")
    target_temp = TASK_MAP.get("afs_gemini_paragraph", {}).get("t", 0.0)
    metrics = GeminiExecutionMetrics(model_name=target_model, temperature=target_temp)
    candidates: List[HistoricalActualCandidate] = []
    audit_logs: List[Dict[str, Any]] = []
    semaphore = asyncio.Semaphore(concurrency)

    async def _process_paragraph(p: ExtractedParagraph):
        async with semaphore:
            prompt = build_mode_b_prompt(
                paragraph=p,
                ticker=ticker,
                financial_period=financial_period,
            )
            t0 = time.perf_counter()
            trace = {}
            try:
                raw_res = await managed_query_ai("afs_gemini_paragraph", prompt, request_trace=trace)
                latency_ms = (time.perf_counter() - t0) * 1000.0

                res_text = raw_res.strip() if isinstance(raw_res, str) else getattr(raw_res, "text", str(raw_res)).strip()
                clean_json = re.sub(r"^```(?:json)?\s*", "", res_text, flags=re.I)
                clean_json = re.sub(r"\s*```$", "", clean_json).strip()
                parsed = json.loads(clean_json)

                # Record usage metadata
                usage = getattr(raw_res, "usage_metadata", None)
                p_tok = getattr(usage, "prompt_token_count", len(prompt) // 4) if usage else len(prompt) // 4
                c_tok = getattr(usage, "candidates_token_count", len(res_text) // 4) if usage else len(res_text) // 4
                returned_version = trace.get("response_model_version") or getattr(raw_res, "model_version", target_model)
                metrics.record_call(p_tok, c_tok, latency_ms, model_version=returned_version)

                accepted_facts, rejected_facts, log_errors = verify_and_match_mode_b_facts(
                    paragraph=p,
                    deterministic_candidates=all_candidates,
                    parsed_json=parsed,
                    financial_period=financial_period,
                )

                for fact in accepted_facts:
                    matched_c = fact["matched_candidate"]
                    cand_period = (
                        financial_period
                        if getattr(matched_c, "temporal_role", None) != "COMPARATIVE_PERIOD"
                        else f"{financial_period}_COMPARATIVE"
                    )

                    qualifiers = {
                        "concept": fact.get("canonical_concept", "unknown"),
                        "scope": fact.get("scope", "unspecified"),
                        "dilution": fact.get("dilution_basis", "unspecified"),
                        "tax_basis": fact.get("tax_basis", "unspecified"),
                        "capex_basis": fact.get("capex_basis", "unspecified"),
                        "lease_inclusion": fact.get("lease_inclusion", "unspecified"),
                        "margin_denominator": fact.get("margin_denominator", "unspecified"),
                        "profit_attribution": fact.get("attribution", "unspecified"),
                        "temporal_role": getattr(matched_c, "temporal_role", "STANDALONE"),
                        "note_reference": getattr(matched_c, "note_reference", None),
                        "detected_label": getattr(matched_c, "nearby_label", None),
                    }

                    cand = HistoricalActualCandidate(
                        candidate_id=matched_c.candidate_id,
                        evidence_id=f"ev_{matched_c.candidate_id}",
                        concept=fact.get("canonical_concept", "unknown"),
                        value=matched_c.normalized_value,
                        raw_token=fact.get("raw_token", matched_c.raw_token),
                        unit=matched_c.unit,
                        currency=matched_c.currency,
                        period=cand_period,
                        scope=fact.get("scope", "unspecified"),
                        qualifiers=qualifiers,
                        source_page=p.page_number,
                        source_paragraph_id=p.paragraph_id,
                        extraction_method="GEMINI_MODE_B",
                        kev_result=None,
                        gemini_result=fact,
                        safety_status="ACCEPT",
                        final_status="VERIFIED",
                        reconciliation_notes=fact.get("evidence_quote"),
                    )
                    candidates.append(cand)

                audit_logs.append({
                    "paragraph_id": p.paragraph_id,
                    "page_number": p.page_number,
                    "requested_model": trace.get("model", target_model),
                    "returned_model_version": returned_version,
                    "temperature": trace.get("temperature", target_temp),
                    "prompt_tokens": p_tok,
                    "output_tokens": c_tok,
                    "latency_ms": latency_ms,
                    "prompt": prompt,
                    "response": res_text,
                    "accepted_count": len(accepted_facts),
                    "rejected_count": len(rejected_facts),
                    "accepted_facts": [
                        {k: v for k, v in f.items() if k != "matched_candidate"} for f in accepted_facts
                    ],
                    "rejected_facts": rejected_facts,
                    "log_errors": log_errors,
                })

            except Exception as exc:
                latency_ms = (time.perf_counter() - t0) * 1000.0
                metrics.record_call(len(prompt) // 4, 0, latency_ms)
                logger.warning("Gemini Mode B call failed for %s: %s", p.paragraph_id, exc)
                audit_logs.append({
                    "paragraph_id": p.paragraph_id,
                    "page_number": p.page_number,
                    "requested_model": target_model,
                    "returned_model_version": None,
                    "temperature": target_temp,
                    "prompt": prompt,
                    "error": str(exc),
                })

    tasks = [_process_paragraph(p) for p in paragraphs]
    await asyncio.gather(*tasks)
    return candidates, metrics, audit_logs

