import sys
import json
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gui"))
from modules.analysis.financial_concept_dictionary import build_default_canonical_concepts

base_concepts = build_default_canonical_concepts()
concept_criteria = {}
for cid, c in sorted(base_concepts.items()):
    concept_criteria[cid] = c.name

extra_gold_concepts = {
    "weighted_average_shares": "Weighted average ordinary shares in issue",
    "issued_shares": "Total issued ordinary shares",
    "total_assets": "Total statutory balance sheet assets",
    "unknown": "General commentary or not a canonical financial concept"
}
for cid, desc in extra_gold_concepts.items():
    if cid not in concept_criteria:
        concept_criteria[cid] = desc

STATIC_QUESTIONS = {
    "concept": {
        "type": "choice",
        "instructions": "Identify the financial concept referred to in the sentence.",
        "criteria": concept_criteria
    },
    "scope": {
        "type": "choice",
        "instructions": "Operating scope.",
        "criteria": {
            "unspecified": "Unspecified scope",
            "group_consolidated": "Group consolidated operations",
            "total_operations": "Total operations (continuing and discontinued)",
            "continuing_operations": "Continuing operations only",
            "discontinued_operations": "Discontinued operations only",
            "segment": "Specific operating segment"
        }
    },
    "dilution": {
        "type": "choice",
        "instructions": "Dilution basis.",
        "criteria": {
            "unspecified": "Unspecified or not per-share",
            "basic": "Basic undiluted metric",
            "diluted": "Diluted per-share metric"
        }
    },
    "tax_basis": {
        "type": "choice",
        "instructions": "Dividend tax basis.",
        "criteria": {
            "unspecified": "Unspecified or not a dividend",
            "gross": "Gross of dividend withholding tax",
            "net": "Net of dividend withholding tax"
        }
    },
    "capex_basis": {
        "type": "choice",
        "instructions": "Capex measurement basis.",
        "criteria": {
            "unspecified": "Unspecified or not capex",
            "cash_payments": "Cash payments for capex",
            "accounting_additions": "Accounting additions to assets"
        }
    },
    "lease_inclusion": {
        "type": "choice",
        "instructions": "Lease liabilities inclusion.",
        "criteria": {
            "unspecified": "Unspecified or not debt/cash",
            "inc_leases": "Including lease liabilities (IFRS 16)",
            "ex_leases": "Excluding lease liabilities"
        }
    },
    "basis_evidence": {
        "type": "choice",
        "instructions": "Evidentiary presentation basis.",
        "criteria": {
            "unspecified": "Unspecified or standard context",
            "balance_sheet_presentation_separate": "Separate balance sheet presentation",
            "explicit_note_wording": "Explicit note disclosure",
            "reconciled_source_formula": "Reconciled source formula",
            "deterministic_parser_section": "Standardized parser section"
        }
    },
    "margin_denominator": {
        "type": "choice",
        "instructions": "Margin denominator basis.",
        "criteria": {
            "unspecified": "Unspecified or not a margin",
            "accounting_revenue": "Statutory accounting revenue",
            "merchandise_sales": "Sale of merchandise",
            "turnover": "Turnover"
        }
    },
    "attribution": {
        "type": "choice",
        "instructions": "Earnings profit attribution.",
        "criteria": {
            "unspecified": "Unspecified or not earnings",
            "parent_equity_holders": "Attributable to equity holders of parent",
            "total_group": "Total group earnings",
            "non_controlling_interest": "Attributable to non-controlling interest",
            "headline_attributable": "Headline earnings attributable to ordinary shareholders"
        }
    },
    "alias_role": {
        "type": "choice",
        "instructions": "Syntactic function of the wording.",
        "criteria": {
            "DIRECT_VALUE_LABEL": "Direct value label for canonical metric",
            "CHANGE_STATEMENT": "Change statement or rate delta",
            "GUIDANCE_STATEMENT": "Guidance, forecast, or outlook wording",
            "CONCEPT_MENTION_ONLY": "Discursive mention without extractable number"
        }
    },
    "value_pattern": {
        "type": "choice",
        "instructions": "Structure of adjacent numbers.",
        "criteria": {
            "DIRECT_LEVEL": "Direct level figure",
            "CHANGE_RATE_ONLY": "Change rate or percentage only",
            "CHANGE_RATE_TO_LEVEL": "Change rate and level reached",
            "FROM_TO_LEVEL": "From a starting level to an ending level",
            "RANGE": "Value range",
            "UNKNOWN": "Complex or unstructured syntax"
        }
    },
    "valuation_eligibility": {
        "type": "choice",
        "instructions": "Admissibility for valuation intake.",
        "criteria": {
            "ELIGIBLE": "Directly eligible for valuation intake",
            "ELIGIBLE_WITH_QUALIFIER": "Eligible with qualifier confirmation",
            "REQUIRES_SCOPE": "Requires scope verification",
            "REQUIRES_BASIS": "Requires basis verification",
            "REQUIRES_PERIOD": "Requires period verification",
            "REQUIRES_SOURCE_SECTION": "Requires source section verification",
            "INFORMATIONAL_ONLY": "Informational mention only",
            "PROHIBITED": "Prohibited from valuation intake"
        }
    },
    "should_abstain": {
        "type": "choice",
        "instructions": "Whether to abstain from classification.",
        "criteria": {
            "true": "Abstain: mention only, ambiguous, or lacks definitive figures",
            "false": "Classify: concrete extractable financial metric information"
        }
    }
}

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
print(f"Input tokens: {res_json['usage']['input_tokens']}, Output tokens: {res_json['usage']['output_tokens']}")
for q, a in res_json["answers"].items():
    print(f"  {q:22s} -> {a['choice']} (conf: {a.get('confidence')})")
