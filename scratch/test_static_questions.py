import sys
import json
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gui"))
from modules.analysis.financial_concept_dictionary import build_default_canonical_concepts
from modules.analysis.gold_release_hashes import (
    GOLD001_RELEASE_ID,
    GOLD001_RELEASE_HASH,
    GOLD001_SOURCE_HASH,
    GOLD001_LABEL_HASH,
)

# Load concepts
base_concepts = build_default_canonical_concepts()
concept_criteria = {}
for cid, c in sorted(base_concepts.items()):
    concept_criteria[cid] = c.description or c.name

# Add other concepts present in gold review
extra_gold_concepts = {
    "weighted_average_shares": "Weighted average number of ordinary shares in issue during the period.",
    "issued_shares": "Total number of issued ordinary shares at the reporting or announcement date.",
    "total_assets": "Total recognized statutory assets on the balance sheet.",
    "unknown": "The text does not refer to any specific canonical financial concept, or represents general commentary."
}
for cid, desc in extra_gold_concepts.items():
    if cid not in concept_criteria:
        concept_criteria[cid] = desc

print(f"Total concept choices: {len(concept_criteria)}")

# Build static questions
STATIC_QUESTIONS = {
    "concept": {
        "type": "choice",
        "instructions": "Identify the primary financial concept or metric referred to in the target sentence.",
        "criteria": concept_criteria
    },
    "scope": {
        "type": "choice",
        "instructions": "Operational scope of the financial metric.",
        "criteria": {
            "unspecified": "Scope is unspecified or implied by general context.",
            "group_consolidated": "Group consolidated operations.",
            "total_operations": "Total operations (continuing and discontinued combined).",
            "continuing_operations": "Continuing operations only.",
            "discontinued_operations": "Discontinued operations only.",
            "segment": "Specific operating division, subsidiary, or regional segment."
        }
    },
    "dilution": {
        "type": "choice",
        "instructions": "Per-share dilution basis.",
        "criteria": {
            "unspecified": "Not a per-share metric or dilution is unspecified.",
            "basic": "Basic (undiluted) per share metric.",
            "diluted": "Diluted per share metric."
        }
    },
    "tax_basis": {
        "type": "choice",
        "instructions": "Dividend withholding tax basis.",
        "criteria": {
            "unspecified": "Not a dividend metric or tax basis is unspecified.",
            "gross": "Gross of dividend withholding tax.",
            "net": "Net of dividend withholding tax."
        }
    },
    "capex_basis": {
        "type": "choice",
        "instructions": "Capital expenditure measurement basis.",
        "criteria": {
            "unspecified": "Not a capex metric or capex basis is unspecified.",
            "cash_payments": "Cash payments for capital expenditure.",
            "accounting_additions": "Accounting additions to property, plant and equipment / intangibles."
        }
    },
    "lease_inclusion": {
        "type": "choice",
        "instructions": "Inclusion of IFRS 16 lease liabilities in debt/cash metrics.",
        "criteria": {
            "unspecified": "Not a debt/cash metric or lease inclusion is unspecified.",
            "inc_leases": "Including lease liabilities (IFRS 16 basis).",
            "ex_leases": "Excluding lease liabilities."
        }
    },
    "basis_evidence": {
        "type": "choice",
        "instructions": "Disclosed evidentiary basis for debt or presentation classification.",
        "criteria": {
            "unspecified": "Standard context or unspecified.",
            "balance_sheet_presentation_separate": "Explicit separate balance sheet presentation.",
            "explicit_note_wording": "Explicit statement in accounting notes.",
            "reconciled_source_formula": "Derived from explicit reconciled source formula.",
            "deterministic_parser_section": "Disclosed in specific standardized parser section."
        }
    },
    "margin_denominator": {
        "type": "choice",
        "instructions": "Denominator used for margin or percentage calculation.",
        "criteria": {
            "unspecified": "Not a margin metric or denominator is unspecified.",
            "accounting_revenue": "Statutory accounting revenue from contracts with customers.",
            "merchandise_sales": "Sale of merchandise / merchandise sales.",
            "turnover": "Turnover."
        }
    },
    "attribution": {
        "type": "choice",
        "instructions": "Earnings profit attribution.",
        "criteria": {
            "unspecified": "Not an earnings metric or attribution is unspecified.",
            "parent_equity_holders": "Attributable to equity holders of parent.",
            "total_group": "Total group earnings before non-controlling interest attribution.",
            "non_controlling_interest": "Attributable to non-controlling interest.",
            "headline_attributable": "Headline earnings attributable to ordinary shareholders."
        }
    },
    "alias_role": {
        "type": "choice",
        "instructions": "Syntactic function and extraction role of the wording.",
        "criteria": {
            "DIRECT_VALUE_LABEL": "Adjacent value represents canonical metric level directly.",
            "CHANGE_STATEMENT": "Identifies concept, but adjacent number is rate of change or delta.",
            "GUIDANCE_STATEMENT": "Forecast, range, or outlook wording rather than historical actual.",
            "CONCEPT_MENTION_ONLY": "Discursive or narrative mention unsafe for direct numeric extraction."
        }
    },
    "value_pattern": {
        "type": "choice",
        "instructions": "Syntactic structure of adjacent numeric figures.",
        "criteria": {
            "DIRECT_LEVEL": "Direct level figure (e.g. profit was R120m).",
            "CHANGE_RATE_ONLY": "Change rate or percentage only (e.g. revenue grew 10%).",
            "CHANGE_RATE_TO_LEVEL": "Change rate and final level (e.g. grew 10% to R120m).",
            "FROM_TO_LEVEL": "From a starting level to an ending level.",
            "RANGE": "Value range (e.g. between 150c and 160c).",
            "UNKNOWN": "Complex narrative or unstructured statement without clear level syntax."
        }
    },
    "valuation_eligibility": {
        "type": "choice",
        "instructions": "Downstream admissibility for valuation model intake.",
        "criteria": {
            "ELIGIBLE": "Directly eligible for valuation intake.",
            "ELIGIBLE_WITH_QUALIFIER": "Eligible for valuation intake with explicit qualifiers.",
            "REQUIRES_SCOPE": "Requires explicit operating scope verification before intake.",
            "REQUIRES_BASIS": "Requires explicit reporting basis verification before intake.",
            "REQUIRES_PERIOD": "Requires explicit period verification before intake.",
            "REQUIRES_SOURCE_SECTION": "Requires verification against primary statement section.",
            "INFORMATIONAL_ONLY": "Informational mention only, prohibited from valuation input.",
            "PROHIBITED": "Strictly prohibited from valuation intake."
        }
    },
    "should_abstain": {
        "type": "choice",
        "instructions": "Whether the automated classifier should abstain from classification.",
        "criteria": {
            "true": "Abstain: statement is narrative mention only, ambiguous, or lacks definitive financial figures.",
            "false": "Classify: statement contains concrete, extractable financial metric information."
        }
    }
}

print(f"Total questions: {len(STATIC_QUESTIONS)}")

# Test on BENCH-0001
test_payload = {
    "model": "kev-latest",
    "state": {
        "benchmark_id": "BENCH-0001",
        "ticker": "LAB.JO",
        "publication_datetime": "2025-11-14T16:40:00",
        "normalized_label": "taxation",
        "detected_numeric_tokens": "[]",
        "previous_sentence": "Previous context sentence.",
        "full_sentence": "Full text sentence with taxation context.",
        "next_sentence": "Next context sentence."
    },
    "questions": STATIC_QUESTIONS
}

req_data = json.dumps(test_payload).encode("utf-8")
req = urllib.request.Request(
    "http://127.0.0.1:8009/v1/systemone",
    data=req_data,
    headers={"Content-Type": "application/json"}
)

t0 = time.perf_counter()
with urllib.request.urlopen(req) as resp:
    res_bytes = resp.read()
t1 = time.perf_counter()

res_json = json.loads(res_bytes.decode("utf-8"))
print(f"Status 200 OK, latency: {(t1 - t0)*1000:.1f}ms, server latency: {res_json.get('latency_ms')}ms")
print("Answers returned:")
for q, a in res_json["answers"].items():
    print(f"  {q:22s} -> {a['choice']} (conf: {a.get('confidence')})")
