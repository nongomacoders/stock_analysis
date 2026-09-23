"""Conservative provenance checks, deliberately not a valuation engine.

Model citations are claims. Literal excerpt checks establish traceability only,
not the accounting correctness of the selected fact or its classification.
"""
import json
import re
from decimal import Decimal, InvalidOperation

CLASSIFICATIONS = {
    "historical_actual", "formal_guidance", "management_target", "external_consensus",
    "model_assumption", "previous_report", "python_calculation", "unresolved",
}
ASSUMPTIONS = ("production", "commodity_price", "production_cost", "shares", "tax",
               "wacc", "growth", "terminal_growth", "exit_multiple", "net_debt_cash", "target_price", "treasury_shares")
HISTORICAL_CONTEXT = (
    "Previous reports are historical context only.\n"
    "Do not retain a material numerical assumption solely because it appeared in a previous report.\n"
    "Every material numerical assumption must be revalidated against current evidence."
)
AUDIT_INSTRUCTIONS = """
ASSUMPTION AUDIT (additional required section; keep the existing valuation methods):
Append a JSON array between ASSUMPTION_AUDIT_JSON_BEGIN and ASSUMPTION_AUDIT_JSON_END.
Include every applicable assumption, using multiple entries for different assets/scenarios:
production, commodity_price, production_cost (cash cost/AISC), shares, treasury_shares, tax, wacc,
growth, terminal_growth, exit_multiple, net_debt_cash, target_price (historical target only; never calculate a new target).
Each entry must contain: assumption, value, unit, source, source_date, classification,
evidence_quote, supporting_inputs, calculation. Use null for unknown fields.
Also include unit_code, currency, period_start, period_end, source_type,
confidence, operation_segment, commodity, production_stage, annualised,
effective_date/as_of_date for point-in-time metrics,
share_count_type, price_type, cost_definition, raw_value, raw_unit, intended_use when applicable. Use null
when evidence cannot establish a field. source_type must be one of:
company_disclosure, market_data, external_consensus, previous_report,
model, python, manual, unresolved. production_stage must be one of:
ore_mined, rom_feed, processed_ore, concentrate, contained_metal,
refined_product, saleable_product, sales_volume, capacity. share_count_type
must be one of: issued_shares_current, treasury_shares, external_shares_ex_treasury,
weighted_average_basic_shares, weighted_average_diluted_shares, forecast_diluted_shares. Use controlled
unit_code values, including tonnes_rom_per_month, tonnes_contained_metal,
tonnes_refined_product, tonnes_saleable_product, USD_per_lb,
USD_per_tonne, ZAR, ZAR_cents, shares, percentage, multiple.
For commodity prices, price_type must be current_spot, historical_average,
analyst_forecast, or long_term_normalized, or null if unknown.
For cost metrics, cost_definition must be production_cost, cash_cost, aisc,
or operating_cost, or null when the source does not establish it. Never
rename production cost as AISC without evidence.
Do not invent a controlled value to make the schema complete. Do not infer a copper production stage
from ROM feed, capacity or contained-metal figures. Keep historical weighted
shares separate from current issued, treasury and forecast diluted shares.
For net cash use null period_start and a point-in-time reporting date.
For shares stated as at announcement date, use that date as effective_date.
Confidence must be low, medium, high or null. Do not present previous-report
growth, payout or multiples as current assumptions. If working-capital drivers
or segment volumes are absent, state that they cannot be determined.
source must be a supplied Source ID or exact filename, or previous_report.
source_date must be YYYY-MM-DD when known. Distinguish current issued shares from
weighted-average shares in a share_basis field. Cite a verbatim evidence_quote.
classification must be exactly one of: historical_actual, formal_guidance,
management_target, external_consensus, model_assumption, previous_report,
python_calculation, unresolved.
If provenance cannot be established, use unresolved; never invent a source/date.
If choosing an unsupported valuation parameter yourself, explicitly label it
model_assumption. Repeating an old number is not revalidation. Distinguish production
guidance from management targets and capacity. State WACC supporting inputs and
the target calculation where actually available; do not fabricate missing workings.
Do not label your arithmetic python_calculation: Python has not calculated a target.
This audit adds disclosure; it does not prescribe a new DCF or SOTP model.
"""

# Fallback for existing reports / models that omit the requested JSON. These are
# labels, not Jubilee constants; extraction never manufactures a source.
LABELS = {
    "production": r"Annuali[sz]ed Units Produced",
    "commodity_price": r"Commodity assumptions",
    "production_cost": r"(?:All-in Sustaining Cost\s*\(AISC\)|AISC|Cash cost|Production cost)",
    "shares": r"(?:Weighted Average Shares in Issue|Shares in Issue|Shares outstanding)",
    "tax": r"Effective Tax Rate",
    "wacc": r"(?:Discount rate\s*\(WACC\)|WACC)",
    "growth": r"Growth rate",
    "terminal_growth": r"Terminal [Gg]rowth(?: [Rr]ate)?",
    "exit_multiple": r"Exit multiple",
    "net_debt_cash": r"Net (?:debt|cash)(?:/cash)?",
    "target_price": r"(?:Report target price|12-month target price)",
}


def _normal(text):
    return " ".join(str(text or "").split()).casefold()


def _number(value):
    match = re.search(r"[-+]?\d[\d, ]*(?:\.\d+)?", str(value or ""))
    if not match:
        return None
    try:
        number = Decimal(match.group().replace(",", "").replace(" ", ""))
        tail = str(value)[match.end():].strip().lower()
        if re.match(r"(?:bn|billion)\b", tail):
            number *= 10**9
        elif re.match(r"(?:m|million)\b", tail):
            number *= 10**6
        elif re.match(r"(?:k|thousand)\b", tail):
            number *= 10**3
        return number
    except InvalidOperation:
        return None


def _unit(value, key):
    text = str(value)
    currency = "USD" if re.search(r"US\$|USD", text, re.I) else "ZAR" if re.search(r"ZAR|R\s*\d", text) else None
    if key == "shares":
        return "shares"
    if "%" in text:
        return "%"
    if re.search(r"\d\s*x\b", text):
        return "x"
    if re.search(r"tonne|\bton|/t\b", text, re.I):
        return f"{currency}/tonne" if currency else "tonnes"
    return currency


def extract_legacy_assumptions(report):
    entries = []
    # Never treat numbers in the audit appendix as independently reported facts.
    body = report.split("ASSUMPTION_AUDIT_JSON_BEGIN")[0].split("ASSUMPTION AUDIT — APPLICATION")[0]
    for key, label in LABELS.items():
        match = re.search(rf"(?im)^\s*[-#*]*\s*{label}\s*:\s*([^\n]+)", body)
        if not match:
            continue
        value = match.group(1).strip()
        if key == "target_price":
            value = re.split(r"Implied upside", value, flags=re.I)[0].strip()
        item = dict(assumption=key, value=value, unit=_unit(value, key), source=None,
                    source_date=None, classification="unresolved", evidence_quote=None,
                    supporting_inputs=None, calculation=None)
        # An explicit statement of carry-forward is evidence of carry-forward,
        # even when the actual preceding report has already been lost.
        if key == "target_price" and re.search(r"target price (?:maintained|unchanged|retained)", body, re.I):
            item.update(classification="previous_report", source="previous_report",
                        note="Carry-forward explicitly stated in report; original derivation unavailable.")
        entries.append(item)
    return entries


def extract_share_disclosures(sources):
    disclosures = []
    pattern = re.compile(
        r"(?:total issued (?:share )?capital|total (?:number of )?shares in issue)"
        r"[^.;]{0,100}?(\d{1,3}(?:[ ,]\d{3}){2,}|\d{7,})\s*(?:ordinary\s+)?shares", re.I)
    for source in sources:
        for match in pattern.finditer(source.get("text") or ""):
            disclosures.append({"value": str(_number(match.group(1))),
                                "source": source["source_id"], "source_date": source.get("source_date"),
                                "evidence_quote": match.group(0), "share_basis": "issued",
                                "supplied_to_model": source.get("supplied_to_model", False)})
    return disclosures


def audit_report(report, *, sources=(), previous_report=None, share_disclosures=()):
    warnings = []

    def warn(code, key, message):
        warning = dict(code=code, assumption=key, message=message)
        if warning not in warnings:
            warnings.append(warning)

    match = re.search(r"ASSUMPTION_AUDIT_JSON_BEGIN\s*(.*?)\s*ASSUMPTION_AUDIT_JSON_END", report, re.S)
    declared = []
    if match:
        try:
            declared = json.loads(match.group(1).strip().removeprefix("```json").removesuffix("```").strip())
            if not isinstance(declared, list) or any(not isinstance(x, dict) for x in declared):
                raise ValueError("Audit must be an array of objects")
        except (ValueError, TypeError):
            declared = []
            warn("malformed_audit", None, "Model audit could not be parsed; report values extracted without inferred provenance.")
    else:
        warn("missing_audit", None, "No structured model audit; provenance unavailable unless independently demonstrated.")
    entries = [dict(x) for x in declared if x.get("assumption") in ASSUMPTIONS]
    legacy = extract_legacy_assumptions(report)
    keys = {x["assumption"] for x in entries}
    entries.extend(x for x in legacy if x["assumption"] not in keys)
    # Deterministically recover share-register facts omitted by Gemini.
    for source in sources:
        if not source.get("supplied_to_model"):
            continue
        body = source.get("text") or ""
        for key, pattern, basis in (
            ("shares", r"The company has\s+(\d{1,3}(?:[ ,]\d{3})+)\s+ordinary shares in issue as at the date of this announcement", "issued_shares_current"),
            ("treasury_shares", r"(\d{1,3}(?:[ ,]\d{3})+)\s+of these shares.{0,150}?held by Group subsidiaries as treasury shares", "treasury_shares"),
        ):
            if any(x["assumption"] == key for x in entries):
                continue
            found = re.search(pattern, body, re.I | re.S)
            if found:
                entries.append({"assumption": key, "value": str(_number(found.group(1))),
                    "raw_value": found.group(1), "unit": "shares", "unit_code": "shares",
                    "raw_unit": "shares", "share_count_type": basis,
                    "source": source["source_id"], "source_date": source.get("source_date"),
                    "effective_date": source.get("source_date"), "observed_at": source.get("observed_at") or source.get("fetched_at"), "classification": "historical_actual",
                    "source_type": "company_disclosure", "evidence_quote": found.group(0),
                    "intended_use": "share_count"})
    for original in legacy:
        same_key = [x for x in entries if x["assumption"] == original["assumption"]]
        if same_key and not any(_number(x.get("value")) == _number(original["value"]) for x in same_key):
            entries.append(original)
            warn("report_audit_mismatch", original["assumption"], "Audit values do not match the labelled report value; both retained for review.")
    issued = next((x for x in entries if x.get("assumption") == "shares" and x.get("share_count_type") == "issued_shares_current"), None)
    treasury = next((x for x in entries if x.get("assumption") == "treasury_shares"), None)
    if issued and treasury and _number(issued.get("value")) is not None and _number(treasury.get("value")) is not None:
        external = _number(issued["value"]) - _number(treasury["value"])
        if external >= 0 and not any(x.get("share_count_type") == "external_shares_ex_treasury" for x in entries):
            entries.append({"assumption": "shares", "value": str(external), "raw_value": str(external),
                "unit": "shares", "unit_code": "shares", "raw_unit": "shares",
                "share_count_type": "external_shares_ex_treasury", "source": "python:issued_less_treasury",
                "source_date": issued.get("source_date"), "effective_date": issued.get("effective_date") or issued.get("source_date"),
                "observed_at": issued.get("observed_at"), "classification": "python_calculation", "source_type": "python", "confidence": "high",
                "evidence_quote": f"Issued {issued.get('value')} less treasury {treasury.get('value')}",
                "supporting_inputs": [issued.get("source"), treasury.get("source")],
                "calculation": "issued_shares_current - treasury_shares", "intended_use": "historical_share_register"})
    source_map = {}
    for source in sources:
        source_map[source["source_id"]] = source
        if source.get("name"):
            source_map[source["name"]] = source
    for item in entries:
        key = item["assumption"]
        for field in ("value", "unit", "source", "source_date", "supporting_inputs", "calculation"):
            item.setdefault(field, None)
            if isinstance(item[field], str) and _normal(item[field]) in {"null", "none", "unknown", "unresolved", "n/a", ""}:
                item[field] = None
        declared_class = item.get("classification")
        item["declared_classification"] = declared_class
        if declared_class not in CLASSIFICATIONS:
            item["classification"] = "unresolved"
            warn("invalid_classification", key, "Missing or invalid assumption classification.")
        item["evidence_verified"] = False
        source = source_map.get(str(item.get("source")))
        if item.get("source") == "previous_report" or item["classification"] == "previous_report":
            item["classification"] = "previous_report"
        elif item["classification"] in {"historical_actual", "formal_guidance", "management_target", "external_consensus"}:
            quote = _normal(item.get("evidence_quote"))
            number = _number(item.get("value"))
            quote_numbers = [_number(m.group()) for m in re.finditer(
                r"\d[\d, ]*(?:\.\d+)?(?:\s*(?:thousand|million|billion|bn|m)\b)?", quote)]
            verified = (source and source.get("supplied_to_model") and quote
                        and quote in _normal(source.get("text")) and number in quote_numbers)
            if not verified:
                item["classification"] = "unresolved"
                warn("unverified_source", key, "Source/excerpt/value could not be verified against supplied evidence.")
            else:
                item["evidence_verified"] = True
                item["observed_at"] = source.get("observed_at") or source.get("fetched_at")
                item["note"] = "Literal source match; semantic classification remains model-declared."
                if not source.get("source_date") and str(item.get("source_date") or "not known") not in source.get("text", ""):
                    item["declared_source_date"] = item.get("source_date")
                    item["source_date"] = None
                if source.get("source_date") and item.get("source_date") != source["source_date"]:
                    item["declared_source_date"] = item.get("source_date")
                    item["source_date"] = source["source_date"]
                    warn("source_date_mismatch", key, "Audit source date replaced with the archived source date.")
        elif item["classification"] == "python_calculation" and item.get("share_count_type") == "external_shares_ex_treasury":
            item["evidence_verified"] = bool(item.get("supporting_inputs"))
        elif item["classification"] == "python_calculation":
            calculation = source.get("python_calculation") if source else None
            if (calculation and key == "commodity_price" and _number(item["value"]) == _number(calculation["value"])
                    and item.get("unit") in calculation["allowed_units"]):
                item["evidence_verified"] = True
                item["source_date"] = source.get("source_date")
            else:
                item["classification"] = "unresolved"
                warn("unverified_python_calculation", key, "No registered Python calculation supports this claim.")
        if key == "net_debt_cash":
            item["period_start"] = None
            item["effective_date"] = item.get("period_end")
        elif key in {"shares", "treasury_shares"}:
            item["period_start"] = None
            if item.get("evidence_verified") and re.search(r"as at (?:the )?date of this announcement|at the date of this announcement", str(item.get("evidence_quote") or ""), re.I):
                item["effective_date"] = item.get("source_date")
                item["period_end"] = None
            elif key == "treasury_shares" and item.get("evidence_verified"):
                item["effective_date"] = item.get("source_date")
                item["period_end"] = None
        if item["classification"] == "previous_report":
            warn("previous_report_only", key, "Material assumption relies on historical report context, not revalidated evidence.")
        verified_python = item["classification"] == "python_calculation" and item.get("evidence_verified")
        if ((not source and not verified_python)
                or item["classification"] in {"unresolved", "model_assumption", "previous_report"}):
            warn("missing_source", key, "No verified current external source for this assumption.")
        if not item.get("unit") or _normal(item["unit"]) in {"unknown", "unresolved", "n/a"}:
            warn("missing_unit", key, "Unit is missing or unresolved.")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(item.get("source_date") or "")):
            warn("missing_source_date", key, "Source date is missing or unresolved.")
        if key == "production" and item["classification"] == "unresolved":
            warn("production_unclassified", key, "Production is not established as actual, formal guidance, target or explicit model assumption.")
        if key == "wacc" and not item.get("supporting_inputs"):
            warn("wacc_unsupported", key, "WACC has no supporting inputs/derivation.")
        if key in {"growth", "terminal_growth", "exit_multiple"} and not item.get("supporting_inputs") and not item["evidence_verified"]:
            warn("unsupported_parameter", key, "Valuation parameter has no demonstrated supporting evidence or derivation.")
        if key == "target_price":
            # A prose formula is not an executable, independently reproducible model.
            item["python_calculated"] = False
            warn("target_not_reproducible", key, "No deterministic target calculation/valuation schedule is registered in Phase 1.")
        if key == "shares":
            known = sorted((d for d in share_disclosures if d.get("source_date")), key=lambda d: d["source_date"])
            if known:
                latest = known[-1]
                reported, disclosed = _number(item["value"]), _number(latest["value"])
                newer = not item.get("source_date") or str(latest["source_date"]) > str(item["source_date"])
                if newer and reported is not None and disclosed is not None and reported != disclosed:
                    item["newer_share_disclosure"] = latest
                    warn("stale_share_count", key,
                         f"Report uses {reported} shares; newer available issued-share disclosure {latest['source']} "
                         f"dated {latest['source_date']} states {disclosed}. Check denominator basis; historical weighted averages may differ legitimately.")
    return {"assumptions": entries, "warnings": warnings, "blocking": False,
            "method": "provenance checks only; no valuation recomputation"}


def render_audit(audit, report_id=None):
    lines = ["ASSUMPTION AUDIT — APPLICATION", f"Report ID: {report_id or 'legacy inspection'}",
             "Warnings are advisory; valuation numbers have not been recalculated."]
    for item in audit["assumptions"]:
        lines.append(f"{item['assumption']}: {item.get('value')} | unit={item.get('unit') or 'unresolved'} | "
                     f"source={item.get('source') or 'unresolved'} | date={item.get('source_date') or 'unresolved'} | "
                     f"classification={item['classification']}")
    lines.append("AUDIT WARNINGS")
    lines.extend(f"- {w['code']} ({w['assumption'] or 'report'}): {w['message']}" for w in audit["warnings"])
    return "\n".join(lines)
