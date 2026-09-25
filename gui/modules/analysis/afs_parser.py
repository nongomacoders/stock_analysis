"""AFS document parser extracting structured accounting observations."""
from __future__ import annotations
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

PARSER_VERSION = "results-package-1.0"
RESULTS_SENS = "results_sens"
ANNUAL_FINANCIAL_STATEMENTS = "annual_financial_statements"

CENTS = {"eps", "diluted_eps", "heps", "diluted_heps", "nav_per_share"}
SHARES = {
    "issued_shares_current", "treasury_shares", "external_shares_ex_treasury",
    "weighted_average_basic_shares", "weighted_average_diluted_shares"
}

STATEMENT_MAP = {
    r"GROUP STATEMENTS? OF FINANCIAL POSITION": ("balance_sheet", {
        "Property, plant and equipment": "property_plant_equipment",
        r"Right\s*-of-use assets": "right_of_use_assets",
        "Intangible assets": "intangible_assets",
        "Goodwill": "goodwill",
        "Inventories": "inventory",
        "Trade and other receivables": "trade_and_other_receivables",
        "Cash and cash equivalents": "cash_and_cash_equivalents",
        "Total assets": "total_assets",
        "Total equity": "total_equity",
        "Trade and other payables": "trade_and_other_payables",
        r"Interest\s*-bearing borrowings": "borrowings",
        "Bank overdraft": "bank_overdraft",
        "Total liabilities": "total_liabilities",
    }),
    r"GROUP STATEMENTS? OF COMPREHENSIVE INCOME": ("income_statement", {
        "Revenue": "revenue",
        "Sale of merchandise": "sale_of_merchandise",
        "Cost of sales": "cost_of_sales",
        "Gross profit": "gross_profit",
        "Other income": "other_income",
        "Trading expenses": "operating_expenses",
        "Depreciation and amortisation": "depreciation_and_amortisation",
        "Trading profit": "trading_profit",
        "Interest income": "finance_income",
        "Profit before finance costs and tax": "profit_before_finance_costs_and_tax",
        "Finance costs": "finance_costs",
        "Profit before tax": "profit_before_tax",
        "Tax expense": "tax",
        "Profit for the period": "profit_for_period",
        r"Equity holders of the [Cc]ompany": "attributable_earnings",
        r"Basic earnings per share\s*\(cents\)": "eps",
        r"Diluted basic earnings per share\s*\(cents\)": "diluted_eps",
    }),
    r"GROUP STATEMENTS? OF CASH FLOWS": ("cash_flow_statement", {
        "Working capital movements": "working_capital_movement",
        "Cash generated from operations": "cash_generated_from_operations",
        "Tax paid": "tax_paid",
        "Dividends paid": "dividends_paid",
        "Net cash from operating activities": "operating_cash_flow",
        "Acquisition of plant and equipment to expand operations": "capex_expansion",
        "Acquisition of plant and equipment to maintain operations": "capex_maintenance",
        "Acquisition of computer software": "intangible_additions",
        "Net cash used in investing activities": "investing_cash_flow",
        "Lease liability payments": "lease_payments",
        "Net cash used in financing activities": "financing_cash_flow",
    })
}

def _decimal(raw: str | None) -> Decimal | None:
    if raw is None: return None
    s = str(raw).strip(); negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace(",", "").replace(" ", "")
    try: val = Decimal(s); return -val if negative else val
    except InvalidOperation: return None

def _line_pair(text: str, label: str) -> tuple[str | None, str | None, str | None]:
    pattern = rf"(?im)^\s*{label}\s+(?:\d+(?:\.\d+)?(?:,\s*\d+)?\s+)?(\(?[\d,]+(?:\.\d+)?\)?)\s+(\(?[\d,]+(?:\.\d+)?\)?)\s*$"
    m = re.search(pattern, text)
    return (m.group(1), m.group(2), m.group(0).strip()) if m else (None, None, None)

def _obs(source: dict, role: str, name: str, value: Decimal | None, unit: str, period_end, page: int | None, section: str, raw_label: str, raw_value: str | None, *, segment: str | None = None, scale: str | None = None, effective_date = None, notes: str | None = None) -> dict:
    normalized = value; raw_unit = unit
    if value is not None and scale == "billions":
        normalized = value * Decimal(1000000000); raw_unit = f"{unit}_billion" if unit != "percentage" else unit
    elif value is not None and scale == "millions":
        normalized = value * Decimal(1000000); raw_unit = f"{unit}_million" if unit != "percentage" else unit
    elif value is not None and scale == "thousands":
        normalized = value * Decimal(1000); raw_unit = "thousands"
    return {
        "name": name, "raw_label": raw_label, "raw_value": raw_value, "raw_unit": raw_unit,
        "value": str(value) if value is not None else None,
        "normalized_value": str(normalized) if normalized is not None else None,
        "unit": unit, "currency": "ZAR" if unit == "ZAR" else None,
        "period_end": str(period_end) if period_end else None,
        "effective_date": str(effective_date) if effective_date else (str(period_end) if period_end else None),
        "source_id": source["source_id"], "source_document_id": source["source_id"],
        "document_role": role, "source_path": source.get("archive_path") or source.get("original_path"),
        "source_hash": source.get("sha256"), "source_date": source.get("source_date"),
        "page_number": page, "statement_section": section, "parser_version": PARSER_VERSION,
        "operation_segment": segment, "assumption_type": "historical_actual",
        "evidence_verified": value is not None, "notes": notes
    }

def parse_afs(source: dict) -> tuple[list[dict], list[str]]:
    warnings = []; observations = []
    if source.get("extraction_error"): warnings.append(f"PDF extraction warning: {source['extraction_error']}")
    try:
        try:
            from pypdf import PdfReader
        except ImportError:
            from PyPDF2 import PdfReader
        reader = PdfReader(source["archive_path"])
    except Exception as exc: return [], [f"PDF open failed: {exc}"]
    from modules.analysis.results_package import _period
    all_text = source.get("text") or ""
    if not all_text: all_text = "\n".join(p.extract_text() or "" for p in reader.pages[:25])
    period_end = _period(all_text)
    total_capex_components = {}
    for page_no, page in enumerate(reader.pages, 1):
        try: text = page.extract_text() or ""
        except Exception as exc: warnings.append(f"Page {page_no}: {exc}"); continue
        for title_re, (section, mapping) in STATEMENT_MAP.items():
            if not re.search(title_re, text, re.I): continue
            for label, name in mapping.items():
                curr, prior, quote = _line_pair(text, label)
                if curr is None: continue
                val = _decimal(curr); unit = "ZAR_cents" if name in CENTS else "ZAR"
                scale = None if name in CENTS else "millions"
                observations.append(_obs(source, ANNUAL_FINANCIAL_STATEMENTS, name, val, unit, period_end, page_no, section, re.sub(r"\\s\*", " ", label), curr, scale=scale, notes=quote))
                if name == "revenue":
                    observations.append(_obs(source, ANNUAL_FINANCIAL_STATEMENTS, "accounting_revenue", val, unit, period_end, page_no, section, "Accounting revenue", curr, scale=scale, notes=quote))
                elif name == "depreciation_and_amortisation":
                    observations.append(_obs(source, ANNUAL_FINANCIAL_STATEMENTS, "depreciation_amortisation_expense", val, unit, period_end, page_no, section, "Depreciation and amortisation expense (Income Statement)", curr, scale=scale, notes=quote))
                elif name == "working_capital_movement":
                    observations.append(_obs(source, ANNUAL_FINANCIAL_STATEMENTS, "working_capital_cash_flow", val, unit, period_end, page_no, section, "Working capital cash flow (positive = cash inflow)", curr, scale=scale, notes=quote))
                if name in {"capex_expansion", "capex_maintenance", "intangible_additions"} and val is not None:
                    total_capex_components[name] = abs(val)
            if section == "balance_sheet":
                m_leases = re.findall(rf"(?im)^\s*Lease liabilities\s+(?:\d+(?:\.\d+)?\s+)?(\(?[\d,]+(?:\.\d+)?\)?)\s+(\(?[\d,]+(?:\.\d+)?\)?)\s*$", text)
                if len(m_leases) >= 2:
                    noncurr = _decimal(m_leases[0][0]); curr_lease = _decimal(m_leases[1][0])
                    observations.append(_obs(source, ANNUAL_FINANCIAL_STATEMENTS, "lease_liabilities_noncurrent", noncurr, "ZAR", period_end, page_no, section, "Non-current lease liabilities", m_leases[0][0], scale="millions"))
                    observations.append(_obs(source, ANNUAL_FINANCIAL_STATEMENTS, "lease_liabilities_current", curr_lease, "ZAR", period_end, page_no, section, "Current lease liabilities", m_leases[1][0], scale="millions"))
                    if noncurr is not None and curr_lease is not None:
                        observations.append(_obs(source, ANNUAL_FINANCIAL_STATEMENTS, "total_lease_liabilities", noncurr + curr_lease, "ZAR", period_end, page_no, section, "Total lease liabilities", str(noncurr + curr_lease), scale="millions"))
                m_ahfv = re.findall(rf"(?im)^\s*Assets held at fair value\s+(?:\d+(?:\.\d+)?\s+)?(\(?[\d,]+(?:\.\d+)?\)?)\s+(\(?[\d,]+(?:\.\d+)?\)?)\s*$", text)
                if len(m_ahfv) >= 2 and _decimal(m_ahfv[1][0]) is not None:
                    observations.append(_obs(source, ANNUAL_FINANCIAL_STATEMENTS, "money_market_investments", _decimal(m_ahfv[1][0]), "ZAR", period_end, page_no, section, "Current assets held at fair value (money market)", m_ahfv[1][0], scale="millions"))
        if re.search(r"\b(?:9|10)\s*INVENTORIES\b", text, re.I):
            for label, name in {"Gross inventories": "gross_inventory", "Finished goods": "finished_goods_inventory"}.items():
                curr, prior, quote = _line_pair(text, label)
                if curr: observations.append(_obs(source, ANNUAL_FINANCIAL_STATEMENTS, name, _decimal(curr), "ZAR", period_end, page_no, "note_inventories", label, curr, scale="millions", notes=quote))
        if re.search(r"\b(?:10|11)\s*TRADE AND OTHER RECEIVABLES\b", text, re.I):
            for label, name in {"Trade receivables: Active portfolio": "trade_receivables_active", r"Trade receivables: Charged\s*-off portfolio": "trade_receivables_charged_off"}.items():
                curr, prior, quote = _line_pair(text, label)
                if curr: observations.append(_obs(source, ANNUAL_FINANCIAL_STATEMENTS, name, _decimal(curr), "ZAR", period_end, page_no, "note_receivables", label, curr, scale="millions", notes=quote))
        if re.search(r"\b(?:32|33)\.1\s*Cash flow from profit before tax\b", text, re.I):
            m_da = re.search(r"(?im)^\s*Depreciation and amortisation\s+(\(?[\d,]+(?:\.\d+)?\)?)\s+(\(?[\d,]+(?:\.\d+)?\)?)\s*$", text)
            if m_da:
                curr_da = m_da.group(1)
                observations.append(_obs(source, ANNUAL_FINANCIAL_STATEMENTS, "depreciation_amortisation_cashflow_addback", _decimal(curr_da), "ZAR", period_end, page_no, "note_cashflow_reconciliation", "Depreciation and amortisation cash flow addback", curr_da, scale="millions", notes=m_da.group(0).strip()))
        if re.search(r"\b(?:32|33)\.2\s*Working capital movements\b", text, re.I):
            for label, name in {"Increase in inventories": "inventory_movement", r"\(?Increase\)?/?decrease in trade and other receivables and prepayments": "receivables_movement", r"Increase/?\(?decrease\)? in trade and other payables and provisions": "payables_movement"}.items():
                curr, prior, quote = _line_pair(text, label)
                if curr: observations.append(_obs(source, ANNUAL_FINANCIAL_STATEMENTS, name, _decimal(curr), "ZAR", period_end, page_no, "note_working_capital", label, curr, scale="millions", notes=quote))
        if "EARNINGS AND CASH FLOW PER SHARE" in text or "Diluted basic and headline earnings basis" in text:
            special = {r"Weighted average number of shares for the reporting period \(millions\)": "weighted_average_basic_shares", r"Diluted weighted average number of shares for the reporting period\s*\(millions\)": "weighted_average_diluted_shares", r"Headline earnings per share \(cents\)": "heps", r"Diluted headline earnings per share\s*\(cents\)": "diluted_heps"}
            for label, name in special.items():
                curr, prior, quote = _line_pair(text, label)
                if curr:
                    val = _decimal(curr); unit = "shares" if name in SHARES else "ZAR_cents"; scale = "millions" if unit == "shares" else None
                    observations.append(_obs(source, ANNUAL_FINANCIAL_STATEMENTS, name, val, unit, period_end, page_no, "note_per_share", label, curr, scale=scale, notes=quote))
        if "Issued and fully paid" in text and re.search(r"\b(?:12|13)\s*SHARE CAPITAL\b", text, re.I):
            m = re.search(r"Issued and fully paid\s+([\d ]+)\s+\(20\d{2}:", text)
            if m: observations.append(_obs(source, ANNUAL_FINANCIAL_STATEMENTS, "issued_shares_current", _decimal(m.group(1)), "shares", period_end, page_no, "note_share_capital", "Note 13: Issued and fully paid", m.group(1), notes=m.group(0)))
        if re.search(r"\b(?:13|14)\s*TREASURY SHARES\b", text, re.I):
            m = re.search(r"Balance at the reporting date\s+(?:\d+\s+)?([\d,]+)\s+([\d,]+)", text)
            if m: observations.append(_obs(source, ANNUAL_FINANCIAL_STATEMENTS, "treasury_shares", _decimal(m.group(1)), "shares", period_end, page_no, "note_treasury_shares", "Note 14: Treasury shares at reporting date", m.group(1), scale="thousands", notes=m.group(0)))
        if "Effective Group tax rate" in text:
            m_tax = re.search(r"Effective Group tax rate\s+([\d.]+)", text)
            if m_tax: observations.append(_obs(source, ANNUAL_FINANCIAL_STATEMENTS, "effective_tax_rate", Decimal(m_tax.group(1)), "percentage", period_end, page_no, "note_tax_expense", "Effective Group tax rate", m_tax.group(1), notes=m_tax.group(0)))
            m_stat = re.search(r"South African current tax rate\s+([\d.]+)", text)
            if m_stat: observations.append(_obs(source, ANNUAL_FINANCIAL_STATEMENTS, "statutory_tax_rate", Decimal(m_stat.group(1)), "percentage", period_end, page_no, "note_tax_expense", "South African current tax rate", m_stat.group(1), notes=m_stat.group(0)))
        if re.search(r"(?:34|35)\.1\s*Reportable segment information(?: \(continued\))?\s*(?:20\d{2})?", text, re.I):
            for label, name in {r"Total third\s*-party revenue": "segment_revenue", r"Trading margin\s*\(%\)": "segment_trading_margin"}.items():
                m_seg = re.search(rf"(?im)^\s*{label}\s+(?:\d+(?:\.\d+)?\s+)?(\(?[\d,]+(?:\.\d+)?\)?)\s+(\(?[\d,]+(?:\.\d+)?\)?)\s+(?:-|\s+|\(?[\d,]+(?:\.\d+)?\)?)\s*(\(?[\d,]+(?:\.\d+)?\)?)\s*$", text)
                if not m_seg: continue
                u = "percentage" if "margin" in name else "ZAR"; sc = None if u == "percentage" else "millions"
                for seg, raw in (("Truworths Africa", m_seg.group(1)), ("Office UK", m_seg.group(2)), ("Group", m_seg.group(3))):
                    observations.append(_obs(source, ANNUAL_FINANCIAL_STATEMENTS, name, _decimal(raw), u, period_end, page_no, "note_segment", label, raw, segment=seg, scale=sc, notes=m_seg.group(0)))
            m_tm = re.search(r"Trading margin\s*\(%\)\s+([\d.]+)\s+([\d.]+)\s+(?:-|\s+)\s*([\d.]+)", text)
            if m_tm and not any(x["name"] == "trading_margin" for x in observations):
                observations.append(_obs(source, ANNUAL_FINANCIAL_STATEMENTS, "trading_margin", Decimal(m_tm.group(3)), "percentage", period_end, page_no, "note_segment", "Trading margin Group", m_tm.group(3), notes=m_tm.group(0)))
    if total_capex_components and not any(x["name"] == "total_capex" for x in observations):
        tot = sum(total_capex_components.values())
        cf_page = next((x["page_number"] for x in observations if x["statement_section"] == "cash_flow_statement" and x["page_number"]), 21)
        observations.append(_obs(source, ANNUAL_FINANCIAL_STATEMENTS, "total_capex", tot, "ZAR", period_end, cf_page, "cash_flow_statement", "Total capex", str(tot), scale="millions", notes="Sum of capex additions"))
        observations.append(_obs(source, ANNUAL_FINANCIAL_STATEMENTS, "cash_capex", tot, "ZAR", period_end, cf_page, "cash_flow_statement", "Total cash capex (cash payments basis)", str(tot), scale="millions", notes="Cash payments basis: expansion + maintenance + software additions"))
    issued_obs = next((x for x in observations if x["name"] == "issued_shares_current"), None)
    treas_obs = next((x for x in observations if x["name"] == "treasury_shares"), None)
    if issued_obs and treas_obs and not any(x["name"] == "external_shares_ex_treasury" for x in observations):
        ext_val = Decimal(issued_obs["normalized_value"]) - Decimal(treas_obs["normalized_value"])
        notes_text = "Note 13 (Share Capital) less Note 14 (Treasury Shares) at reporting date"
        observations.append(_obs(source, ANNUAL_FINANCIAL_STATEMENTS, "external_shares_ex_treasury", ext_val, "shares", period_end, issued_obs.get("page_number"), "note_share_capital", "External shares excluding treasury", str(ext_val), notes=notes_text))
        observations.append(_obs(source, ANNUAL_FINANCIAL_STATEMENTS, "period_end_external_shares", ext_val, "shares", period_end, issued_obs.get("page_number"), "note_share_capital", "Period-end external shares excluding treasury", str(ext_val), notes=notes_text))
    if not period_end: warnings.append("Reporting period unresolved from AFS text")
    return observations, warnings
