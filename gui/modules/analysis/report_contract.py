"""Publication guardrails for evidence-grounded research reports."""
from __future__ import annotations

import re

UNSUPPORTED_CAUSES = (
    r"inventory (?:absorbed|absorbing|drove|driving)",
    r"receivables? (?:absorbed|absorbing|deteriorat|increas)",
    r"delayed (?:customer )?collections?", r"strict credit criteria",
    r"negative (?:sales )?volumes?.{0,50}(?:south africa|sa).{0,50}(?:uk|united kingdom)",
    r"port disruptions?", r"(?:lower|reduced) credit[- ]loss provis",
)
VALUATION_WORDS = re.compile(r"\b(attractive|cheap|undervalued|undemanding|compelling|strong income support)\b", re.I)


def valid_headline_metric(line: str) -> bool:
    if not re.search(r"(?i)key metric", line):
        return True
    # A headline must be self-describing and traceable.
    required = (r"metric_name\s*=", r"value\s*=", r"unit\s*=", r"period\s*=", r"source\s*=")
    return all(re.search(pattern, line, re.I) for pattern in required)


def guard_report(report: str, *, valuation_status: str, audit: dict) -> tuple[str, list[dict]]:
    """Remove invalid headlines and label unsupported causal assertions."""
    original = report
    warnings = []
    lines = []
    for line in report.splitlines():
        if not valid_headline_metric(line):
            warnings.append({"code": "UNLABELED_HEADLINE_METRIC", "severity": "ERROR", "message": "Bare Key Metric omitted from publication."})
            continue
        if any(re.search(pattern, line, re.I) for pattern in UNSUPPORTED_CAUSES):
            if not re.match(r"\s*(ANALYST_INFERENCE|SCENARIO|EXTERNAL_CONTEXT)\s*:", line, re.I):
                line = "ANALYST_INFERENCE (not established by supplied source): " + line.strip()
                warnings.append({"code": "UNSUPPORTED_CAUSAL_NARRATIVE", "severity": "WARNING", "message": "Causal claim labelled as analyst inference."})
        if valuation_status == "NOT_CALCULABLE" and VALUATION_WORDS.search(line):
            warnings.append({"code": "VALUATION_LANGUAGE_WITHOUT_TARGET", "severity": "WARNING", "message": "Unsupported valuation conclusion omitted because valuation is NOT_CALCULABLE."})
            continue
        lines.append(line)
    current = "\n".join(lines)
    # Current assumptions sourced only from the previous report are rendered only in legacy context.
    legacy = [x for x in audit.get("assumptions", []) if x.get("classification") == "previous_report"]
    legacy_values = {str(x.get("value")) for x in legacy if x.get("value") is not None}
    filtered = []
    in_assumptions = False
    for line in current.splitlines():
        if re.match(r"^#{1,6}\s+Key assumptions\s*$", line, re.I):
            in_assumptions = True
            warnings.append({"code": "LEGACY_ASSUMPTION_ISOLATED", "severity": "WARNING", "message": "Unverified current Key assumptions section omitted."})
            continue
        if in_assumptions and re.match(r"^#{1,6}\s+", line):
            in_assumptions = False
        if in_assumptions:
            if any(v and v in line for v in legacy_values):
                continue
            if not line.strip():
                continue
        filtered.append(line)
    current = "\n".join(filtered).strip()
    if legacy:
        current += "\n\n## Legacy valuation context - unverified / not approved\n\n"
        current += "The following values came only from a previous report. They are excluded from current valuation inputs and require explicit ForecastPlan approval.\n"
        for item in legacy:
            current += f"\n- {item.get('assumption')}: {item.get('value')} {item.get('unit') or ''} | source=previous_report"
    if not warnings and not legacy:
        return original, warnings
    return current, warnings
