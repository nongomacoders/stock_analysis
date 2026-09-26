"""Stage 7 & 8: Targeted Gemini Adjudication and Evidence Verification.

Reuses the existing Gemini Vertex AI integration (via selector.managed_query_ai)
to adjudicate unresolved accounting qualifiers on high-risk candidates.
Enforces strict JSON schema, verifies supporting quotes exist in context,
and strictly prohibits Gemini from altering numbers or creating new metrics.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from modules.analysis.selector import managed_query_ai
from .evidence_package import ContextEvidencePackage
from .kev_classifier import KevSemanticResult
from .safety_policy import SafetyPolicyEvaluation

logger = logging.getLogger(__name__)

ADJUDICATION_PROMPT_VERSION = "afs_adjudication_v1"

ADJUDICATION_SCHEMA_JSON = {
    "type": "object",
    "properties": {
        "candidate_number_verified": {
            "type": "string",
            "description": "Must match the candidate number token provided in the prompt exactly.",
        },
        "canonical_concept": {
            "type": "string",
            "description": "Exact canonical financial concept (e.g. revenue, heps, eps, trading_profit, total_capex, etc.) or 'unknown'.",
        },
        "temporal_classification": {
            "type": "string",
            "enum": ["historical_actual", "comparative_period", "guidance", "target", "change_only", "unknown"],
        },
        "scope": {
            "type": "string",
            "enum": ["group_consolidated", "total_operations", "continuing_operations", "discontinued_operations", "segment", "unspecified"],
        },
        "dilution": {
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
        "profit_attribution": {
            "type": "string",
            "enum": ["parent_equity_holders", "total_group", "non_controlling_interest", "headline_attributable", "unspecified"],
        },
        "is_safe_for_historical_intake": {
            "type": "boolean",
            "description": "True only if the number represents a concrete historical actual level supported by explicit text.",
        },
        "supporting_quote": {
            "type": "string",
            "description": "Exact verbatim substring from the supplied text supporting this adjudication.",
        },
        "reasoning": {
            "type": "string",
            "description": "Brief explanation of factual evidence.",
        },
    },
    "required": [
        "candidate_number_verified",
        "canonical_concept",
        "temporal_classification",
        "scope",
        "dilution",
        "tax_basis",
        "capex_basis",
        "lease_inclusion",
        "margin_denominator",
        "profit_attribution",
        "is_safe_for_historical_intake",
        "supporting_quote",
    ],
}


@dataclass(frozen=True)
class GeminiAdjudicationResult:
    evidence_id: str
    is_valid: bool
    status: str  # ADJUDICATED, ABSTAINED, REJECTED, PARSE_ERROR
    canonical_concept: Optional[str]
    temporal_classification: Optional[str]
    scope: Optional[str]
    dilution: Optional[str]
    tax_basis: Optional[str]
    capex_basis: Optional[str]
    lease_inclusion: Optional[str]
    margin_denominator: Optional[str]
    profit_attribution: Optional[str]
    is_safe_for_historical_intake: bool
    supporting_quote: Optional[str]
    reasoning: Optional[str]
    verification_errors: List[str]
    raw_prompt: str
    raw_response: str
    prompt_version: str
    model_name: str
    timestamp: datetime

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d


def build_adjudication_prompt(
    package: ContextEvidencePackage,
    kev: KevSemanticResult,
    safety: SafetyPolicyEvaluation,
) -> str:
    """Build strict, zero-inference adjudication prompt for Gemini."""
    prompt = f"""You are a skeptical financial accounting adjudicator analyzing an extract from an Annual Financial Statements (AFS) document.

IMPORTANT RULES:
1. YOU MUST NOT RECALCULATE, GUESS, OR ALTER THE CANDIDATE NUMBER.
2. DO NOT INFER FROM USUAL ACCOUNTING CONVENTION. Use ONLY explicit factual evidence in the supplied text.
3. If the supplied evidence does not explicitly establish a qualifier, return 'unspecified'.
4. If the figure is guidance, outlook, change-only, or lacks concrete textual backing, set 'is_safe_for_historical_intake': false.
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

KEV PRELIMINARY CLASSIFICATION:
- Concept: {kev.concept}
- Scope: {kev.scope}
- Dilution: {kev.dilution}
- Capex Basis: {kev.capex_basis}
- Lease Inclusion: {kev.lease_inclusion}
- Margin Denominator: {kev.margin_denominator}

UNRESOLVED QUESTIONS REQUIRING YOUR ADJUDICATION:
{json.dumps(safety.unresolved_questions, indent=2)}

JSON SCHEMA TO RETURN:
{json.dumps(ADJUDICATION_SCHEMA_JSON, indent=2)}
"""
    return prompt


def verify_gemini_adjudication(
    package: ContextEvidencePackage,
    parsed: Dict[str, Any],
) -> Tuple[bool, List[str]]:
    """Python verification checks on Gemini output."""
    errors = []

    # 1. Candidate number verification
    cand_num_check = parsed.get("candidate_number_verified", "").strip()
    if cand_num_check != package.candidate_numeric_token.strip():
        # Relax slightly for whitespace or case, but token must match
        if re.sub(r"\s+", "", cand_num_check) != re.sub(r"\s+", "", package.candidate_numeric_token):
            errors.append(
                f"Candidate token mismatch: Gemini reported '{cand_num_check}', expected '{package.candidate_numeric_token}'"
            )

    # 2. Quote verification: supporting quote must exist in supplied context
    quote = parsed.get("supporting_quote", "").strip()
    if not quote:
        errors.append("Supporting quote is missing or empty")
    else:
        full_context = f"{package.previous_paragraph or ''}\n{package.target_paragraph}\n{package.next_paragraph or ''}"
        # Normalize whitespace for matching
        norm_context = re.sub(r"\s+", " ", full_context).lower()
        norm_quote = re.sub(r"\s+", " ", quote).lower()
        if norm_quote not in norm_context:
            errors.append(f"Supporting quote does not exist verbatim in supplied context: '{quote[:60]}...'")

    # 3. Enum validation
    for field, schema in ADJUDICATION_SCHEMA_JSON["properties"].items():
        if "enum" in schema:
            val = parsed.get(field)
            if val is not None and val not in schema["enum"]:
                errors.append(f"Invalid enum value '{val}' for field '{field}'. Allowed: {schema['enum']}")

    is_valid = len(errors) == 0
    return is_valid, errors


async def adjudicate_with_gemini(
    package: ContextEvidencePackage,
    kev: KevSemanticResult,
    safety: SafetyPolicyEvaluation,
) -> GeminiAdjudicationResult:
    """Send candidate evidence package to Gemini for targeted adjudication."""
    prompt = build_adjudication_prompt(package, kev, safety)
    ts = datetime.now(timezone.utc)

    try:
        raw_res = await managed_query_ai("afs_adjudication", prompt)
        res_text = raw_res.strip() if isinstance(raw_res, str) else getattr(raw_res, "text", str(raw_res)).strip()

        # Clean JSON markdown fences if present
        clean_json = re.sub(r"^```(?:json)?\s*", "", res_text, flags=re.I)
        clean_json = re.sub(r"\s*```$", "", clean_json).strip()

        parsed = json.loads(clean_json)

        is_valid, verification_errors = verify_gemini_adjudication(package, parsed)

        status = "ADJUDICATED" if is_valid and parsed.get("is_safe_for_historical_intake") else "REJECTED"
        if not is_valid:
            status = "REJECTED"

        return GeminiAdjudicationResult(
            evidence_id=package.evidence_id,
            is_valid=is_valid,
            status=status,
            canonical_concept=parsed.get("canonical_concept"),
            temporal_classification=parsed.get("temporal_classification"),
            scope=parsed.get("scope"),
            dilution=parsed.get("dilution"),
            tax_basis=parsed.get("tax_basis"),
            capex_basis=parsed.get("capex_basis"),
            lease_inclusion=parsed.get("lease_inclusion"),
            margin_denominator=parsed.get("margin_denominator"),
            profit_attribution=parsed.get("profit_attribution"),
            is_safe_for_historical_intake=bool(parsed.get("is_safe_for_historical_intake", False)),
            supporting_quote=parsed.get("supporting_quote"),
            reasoning=parsed.get("reasoning"),
            verification_errors=verification_errors,
            raw_prompt=prompt,
            raw_response=res_text,
            prompt_version=ADJUDICATION_PROMPT_VERSION,
            model_name="gemini-3.6-flash",
            timestamp=ts,
        )

    except Exception as exc:
        logger.warning("Gemini adjudication failed for %s: %s", package.evidence_id, exc)
        return GeminiAdjudicationResult(
            evidence_id=package.evidence_id,
            is_valid=False,
            status="PARSE_ERROR",
            canonical_concept=None,
            temporal_classification=None,
            scope=None,
            dilution=None,
            tax_basis=None,
            capex_basis=None,
            lease_inclusion=None,
            margin_denominator=None,
            profit_attribution=None,
            is_safe_for_historical_intake=False,
            supporting_quote=None,
            reasoning=None,
            verification_errors=[f"Exception during adjudication: {exc}"],
            raw_prompt=prompt,
            raw_response=str(exc),
            prompt_version=ADJUDICATION_PROMPT_VERSION,
            model_name="gemini-3.6-flash",
            timestamp=ts,
        )
