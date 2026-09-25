"""Structured SENS + annual-financial-statements results packages."""
from __future__ import annotations
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import UUID
from .financial_metrics import (AssumptionType, FinancialMetric, ShareCountType, SourceType, Unit, normalize_metric)
from modules.analysis.afs_parser import (
    ANNUAL_FINANCIAL_STATEMENTS, RESULTS_SENS, PARSER_VERSION,
    STATEMENT_MAP, CENTS, SHARES, parse_afs, _obs, _line_pair
)
from modules.analysis.sens_parser import parse_sens

DETAILED_RESULTS_PACKAGE = "DETAILED_RESULTS_PACKAGE"
HEADLINE_RESULTS_ONLY = "HEADLINE_RESULTS_ONLY"

def _decimal(raw):
    raw = str(raw).strip(); negative = raw.startswith("(") and raw.endswith(")")
    raw = raw.strip("()").replace(",", "").replace(" ", "")
    try: value = Decimal(raw)
    except InvalidOperation: return None
    return -value if negative else value

def _period(text):
    m = re.search(r"(?:52\s+weeks\s+(?:to|ended)|period\s+ended)\s+(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})", text, re.I)
    return datetime.strptime(" ".join(m.groups()), "%d %B %Y").date() if m else None

def classify_document(source):
    text = (source.get("text") or "")[:120000].lower(); suffix = Path(source.get("name") or "").suffix.lower()
    if ("produced by the jse sens department" in text or "jse sens" in text) and ("results" in text or "financial statements" in text):
        return RESULTS_SENS
    if suffix == ".pdf" and "annual financial statements" in text and (
        ("statement of financial position" in text or "statements of financial position" in text) or
        ("statement of comprehensive income" in text or "statements of comprehensive income" in text)
    ):
        return ANNUAL_FINANCIAL_STATEMENTS
    return "other"

def classify_path(path):
    path = Path(path)
    return classify_document({'name': path.name, 'text': read_document_text(path)})

def read_document_text(path: Path) -> str:
    path = Path(path)
    try:
        if path.suffix.lower() == '.txt': return path.read_text(encoding='utf-8', errors='ignore')
        if path.suffix.lower() == '.pdf':
            try:
                from pypdf import PdfReader
            except ImportError:
                from PyPDF2 import PdfReader
            return '\n'.join((page.extract_text() or '') for page in PdfReader(str(path)).pages[:25])
    except Exception: return ''
    return ''

def select_live_sources(sources, requested_period=None):
    inspected = []
    for source in sources:
        item = dict(source); item['document_role'] = classify_document(item); item['reporting_period'] = _period(item.get('text') or '')
        inspected.append(item)
    target = requested_period
    if isinstance(target, str): target = date.fromisoformat(target)
    recognized = [x for x in inspected if x['document_role'] in {RESULTS_SENS, ANNUAL_FINANCIAL_STATEMENTS}]
    if target is None:
        sens_periods = [x['reporting_period'] for x in recognized if x['document_role'] == RESULTS_SENS and x['reporting_period']]
        periods = sens_periods or [x['reporting_period'] for x in recognized if x['reporting_period']]
        target = max(periods) if periods else None
    selected = []; ignored = []
    for item in inspected:
        reason = None
        if item['document_role'] not in {RESULTS_SENS, ANNUAL_FINANCIAL_STATEMENTS}: reason = 'unsupported document role'
        elif item['reporting_period'] is None: reason = 'reporting period unresolved'
        elif target is None: reason = 'package reporting period unresolved'
        elif item['reporting_period'] != target: reason = f"reporting period {item['reporting_period']} does not match requested {target}"
        if reason: ignored.append({'source': item, 'reason': reason})
        else: selected.append(item)
    roles = {x['document_role'] for x in selected}
    warnings = [f"Ignored {x['source'].get('name')}: {x['reason']}" for x in ignored]
    if target and RESULTS_SENS not in roles: warnings.append(f'No results SENS found for {target}')
    if target and ANNUAL_FINANCIAL_STATEMENTS not in roles: warnings.append(f'No annual financial statements found for {target}')
    return {'target_period': target, 'selected': selected, 'ignored': ignored, 'warnings': warnings}

def select_live_result_paths(paths, requested_period=None):
    sources = [{'name': Path(x).name, 'path': Path(x), 'text': read_document_text(Path(x))} for x in paths]
    result = select_live_sources(sources, requested_period)
    result['selected_paths'] = [x['path'] for x in result['selected']]
    return result

def classify_package(sources):
    roles = {s.get("document_role") or classify_document(s) for s in sources}
    if RESULTS_SENS in roles and ANNUAL_FINANCIAL_STATEMENTS in roles: return DETAILED_RESULTS_PACKAGE
    return HEADLINE_RESULTS_ONLY

def annotate_sources(sources):
    for source in sources:
        source["document_role"] = classify_document(source); source["parser_version"] = PARSER_VERSION
        source["reporting_period"] = str(_period(source.get("text") or "") or "") or None
    return classify_package(sources)

def reconcile_observations(observations):
    groups = {}; results = []
    for item in observations:
        identity_date = item.get("effective_date") if item["name"] in {"issued_shares_current", "treasury_shares", "external_shares_ex_treasury", "period_end_external_shares", "announcement_date_external_shares"} else item.get("period_end")
        groups.setdefault((item["name"], item.get("operation_segment"), identity_date, item.get("unit")), []).append(item)
    for key, items in groups.items():
        roles = {x["document_role"] for x in items}; values = {x["normalized_value"] for x in items}
        if len(roles) > 1:
            status = "CONFIRMED_BY_MULTIPLE_SOURCES" if len(values) == 1 else "SOURCE_CONFLICT"
        else: status = "SINGLE_SOURCE"
        name = key[0]
        preferred = RESULTS_SENS if name in {"issued_shares_current", "treasury_shares", "annual_dividend_per_share"} else (ANNUAL_FINANCIAL_STATEMENTS if ANNUAL_FINANCIAL_STATEMENTS in roles else next(iter(roles)))
        results.append({
            "metric_name": name, "operation_segment": key[1], "period_end": key[2], "unit": key[3],
            "status": status, "preferred_role": preferred,
            "observations": [{"source_id": x["source_id"], "role": x["document_role"], "value": x["normalized_value"], "raw_value": x["raw_value"], "page": x["page_number"]} for x in items]
        })
    return results

def build_results_package(sources):
    depth = annotate_sources(sources); observations = []; warnings = []
    for source in sources:
        if source["document_role"] == RESULTS_SENS: observations.extend(parse_sens(source))
        elif source["document_role"] == ANNUAL_FINANCIAL_STATEMENTS:
            found, issues = parse_afs(source); observations.extend(found); warnings.extend(issues)
    return {"evidence_depth": depth, "parser_version": PARSER_VERSION, "observations": observations, "reconciliations": reconcile_observations(observations), "warnings": warnings}

def observations_to_metrics(ticker, report_id, package, report_date, observed_at):
    metrics = []
    for item in package["observations"]:
        if item["normalized_value"] is None: continue
        unit = {"ZAR": Unit.ZAR, "ZAR_cents": Unit.ZAR_CENTS, "shares": Unit.SHARES, "percentage": Unit.PERCENTAGE}.get(item["unit"])
        if unit is None: continue
        share_type = ShareCountType(item["name"]) if item["name"] in {x.value for x in ShareCountType} else None
        metric = FinancialMetric(
            ticker=ticker, report_id=UUID(str(report_id)), name=item["name"], value=Decimal(item["normalized_value"]),
            currency=item["currency"], unit=unit, period_end=date.fromisoformat(item["period_end"]) if item["period_end"] else None,
            effective_date=date.fromisoformat(item["effective_date"]) if item["effective_date"] else None,
            source_date=date.fromisoformat(str(item["source_date"])[:10]) if item["source_date"] else None,
            observed_at=observed_at, report_date=report_date, source=item["source_id"], source_id=item["source_id"],
            source_type=SourceType.COMPANY_DISCLOSURE, assumption_type=AssumptionType.HISTORICAL_ACTUAL,
            operation_segment=item["operation_segment"], share_count_type=share_type, raw_value=item["raw_value"],
            raw_unit=item.get("raw_unit") or item.get("unit"), normalized_value=Decimal(item["normalized_value"]), normalized_unit=unit,
            evidence_quote=item["notes"], evidence_verified=True, intended_use="historical_baseline",
            notes=f"{item['document_role']} | page {item['page_number'] or 'n/a'} | {item['statement_section']}",
            source_page=item["page_number"], source_section=item["statement_section"], raw_label=item["raw_label"],
            parser_version=item["parser_version"], document_role=item["document_role"]
        )
        metrics.append(normalize_metric(metric))
    return metrics

def render_package_for_prompt(package):
    lines = [f"[STRUCTURED RESULTS PACKAGE]\nEvidence depth: {package['evidence_depth']}\nParser version: {package['parser_version']}", "Use these Python-extracted observations as the accounting baseline. Preserve distinct concepts and do not invent unresolved values."]
    for item in package["observations"]:
        lines.append(f"- {item['name']} | value={item['normalized_value']} {item['unit']} | period={item['period_end']} | segment={item['operation_segment'] or 'Group'} | role={item['document_role']} | source={item['source_id']} | page={item['page_number'] or 'n/a'} | section={item['statement_section']}")
    lines.append("\n[RECONCILIATION]")
    for item in package["reconciliations"]:
        lines.append(f"- {item['metric_name']} | {item['status']} | preferred={item['preferred_role']} | observations={json_compact(item['observations'])}")
    if package["warnings"]: lines.append("\n[PARSER WARNINGS]\n- " + "\n- ".join(package["warnings"]))
    lines.append("\nDo not discuss a specific working-capital cause unless the structured AFS observations support it. Do not create forward assumptions or a target price.\n[END STRUCTURED RESULTS PACKAGE]")
    return "\n".join(lines)

def json_compact(value):
    import json
    return json.dumps(value, separators=(",", ":"), default=str)
