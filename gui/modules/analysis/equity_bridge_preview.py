"""Read-only EV-to-equity bridge preview for draft ForecastPlans."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from .forecast_plan import (
    ApprovalState, ForecastPlan, Origin, new_version,
)
from .valuation.engine import EquitySpec
from .valuation.models import InputRef

BRIDGE_FIELDS = (
    "net_cash", "lease_adjustments", "minorities",
    "non_operating_assets", "other_equity_adjustments",
)


def _metric(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if hasattr(raw, "model_dump"):
        return raw.model_dump(mode="json")
    return dict(raw)


def _value(item: dict) -> Decimal | None:
    raw = item.get("normalized_value")
    if raw is None:
        raw = item.get("value")
    return Decimal(str(raw)) if raw is not None else None


def _source_date(item: dict) -> str:
    return str(item.get("source_date") or item.get("effective_date") or "")


def _source_metric(evidence: list[Any], kind: str) -> tuple[dict | None, str | None]:
    candidates = []
    for raw in evidence:
        item = _metric(raw)
        verified = item.get("evidence_verified") is True
        company = item.get("source_type") == "company_disclosure"
        if not (verified and company and item.get("metric_id") and _value(item) is not None):
            continue
        if kind == "net_cash":
            quote = str(item.get("evidence_quote") or "").casefold()
            if item.get("name") == "net_cash":
                rank = 2
            elif item.get("name") == "net_debt_cash" and "net cash" in quote:
                rank = 1
            else:
                continue
        else:
            if (item.get("name") != "issued_shares_current"
                    or item.get("share_count_type") != "issued_shares_current"):
                continue
            rank = 2 if item.get("document_role") == "results_sens" else 1
        candidates.append((_source_date(item), rank, item))
    if not candidates:
        return None, None
    candidates.sort(key=lambda row: (row[0], row[1]), reverse=True)
    best = candidates[0][2]
    same_date = [row[2] for row in candidates
                 if row[0] == candidates[0][0] and _value(row[2]) != _value(best)]
    if same_date:
        return None, "conflicting source-backed values"
    return best, None


def _accepted_assumption(plan: ForecastPlan, field: str) -> tuple[Any | None, str | None]:
    matches = [
        item for item in plan.assumptions
        if item.field == field and item.case == "base"
        and item.origin in {Origin.ANALYST_ASSUMPTION, Origin.SCENARIO_ASSUMPTION}
        and item.approval_state == ApprovalState.ACCEPTED
        and item.value is not None
    ]
    if len(matches) > 1:
        return None, "multiple accepted assumptions"
    return (matches[0], None) if matches else (None, None)


def equity_bridge_preview(plan: ForecastPlan, evidence: list[Any]) -> dict:
    """Resolve inputs and report mapping state without mutating or valuing the plan."""
    case = plan.engine_plan.cases.get("base") if plan.engine_plan else None
    equity = case.equity if case else None
    rows: dict[str, dict] = {}
    missing_inputs: list[str] = []
    missing_mappings: list[str] = []
    invalid: list[str] = []

    net_cash, cash_error = _source_metric(evidence, "net_cash")
    shares, shares_error = _source_metric(evidence, "shares")
    for field, metric, error in (
        ("net_cash", net_cash, cash_error),
        ("current_issued_shares", shares, shares_error),
    ):
        if error:
            rows[field] = {"field": field, "eligibility": "INVALID/DOUBLE-COUNTED",
                           "mapping": "INVALID", "error": error}
            invalid.append(field)
        elif metric is None:
            rows[field] = {"field": field, "eligibility": "MISSING",
                           "mapping": "MISSING"}
            missing_inputs.append(field)
        else:
            rows[field] = {
                "field": field, "value": _value(metric),
                "unit": metric.get("unit") or metric.get("normalized_unit"),
                "id": str(metric["metric_id"]), "eligibility": "SOURCE-BACKED",
                "mapping": "MISSING",
            }

    for field in BRIDGE_FIELDS[1:]:
        item, error = _accepted_assumption(plan, field)
        if error:
            rows[field] = {"field": field, "eligibility": "INVALID/DOUBLE-COUNTED",
                           "mapping": "INVALID", "error": error}
            invalid.append(field)
        elif item is None:
            rows[field] = {"field": field, "eligibility": "MISSING",
                           "mapping": "MISSING"}
            missing_inputs.append(field)
        else:
            rows[field] = {
                "field": field, "value": item.value, "unit": item.unit,
                "id": str(item.assumption_id), "eligibility": "ACCEPTED",
                "mapping": "MISSING",
            }

    if equity is None:
        missing_mappings.extend([
            "net_cash", "lease_adjustments", "minorities",
            "non_operating_assets", "other_equity_adjustments",
            "current_issued_shares", "lease_treatment",
            "non_operating_asset_rationale",
        ])
        lease_treatment = None
        rationale = None
    else:
        cash_fields = {key for key in ("net_cash", "net_debt")
                       if key in equity.adjustments}
        if cash_fields != {"net_cash"}:
            invalid.append("net_cash/net_debt")
        for field in BRIDGE_FIELDS:
            row = rows[field]
            ref = equity.adjustments.get(field)
            if ref is None:
                missing_mappings.append(field)
            elif row.get("id") != str(ref.metric_id) or ref.field != field:
                row["mapping"] = "INVALID"
                invalid.append(field)
            else:
                row["mapping"] = "MAPPED"
        share_row = rows["current_issued_shares"]
        ref = equity.shares
        if (share_row.get("id") != str(ref.metric_id)
                or ref.field != "current_issued_shares"):
            share_row["mapping"] = "INVALID"
            invalid.append("current_issued_shares")
        else:
            share_row["mapping"] = "MAPPED"
        lease_treatment = equity.lease_treatment
        rationale = equity.non_operating_asset_rationale
        if lease_treatment not in {
                "lease_debt_adjustment", "leases_in_operating_cash_flows"}:
            missing_mappings.append("lease_treatment")
        if not (rationale or "").strip():
            missing_mappings.append("non_operating_asset_rationale")
        lease_value = rows["lease_adjustments"].get("value")
        if (lease_treatment == "leases_in_operating_cash_flows"
                and lease_value not in (None, Decimal(0))):
            invalid.append("lease_treatment/lease_adjustments")
        if (lease_treatment == "lease_debt_adjustment"
                and lease_value in (None, Decimal(0))):
            invalid.append("lease_treatment/lease_adjustments")

    for field, row in rows.items():
        if row.get("id") and row["mapping"] == "MISSING":
            missing_mappings.append(field)

    missing_mappings = list(dict.fromkeys(missing_mappings))
    invalid = list(dict.fromkeys(invalid))
    status = ("READY" if not missing_inputs and not missing_mappings and not invalid
              else "INVALID/DOUBLE-COUNTED" if invalid else "MISSING MAPPINGS")
    return {
        "status": status, "rows": rows,
        "lease_treatment": lease_treatment,
        "non_operating_asset_rationale": rationale,
        "missing_inputs": missing_inputs,
        "missing_mappings": missing_mappings,
        "invalid": invalid,
    }



NON_OPERATING_ASSET_RATIONALE = (
    "No separately realisable material non-operating asset was identified. "
    "Money-market funds are included in net cash, and ordinary retail "
    "working-capital assets are excluded."
)


def build_reviewed_equity_spec(
        plan: ForecastPlan, evidence: list[Any], *,
        non_operating_asset_rationale: str = NON_OPERATING_ASSET_RATIONALE
        ) -> EquitySpec:
    """Build EquitySpec only from the already reviewed bridge inputs."""
    current_case = plan.engine_plan.cases.get("base") if plan.engine_plan else None
    current = current_case.equity if current_case else None
    if current:
        if "net_debt" in current.adjustments:
            raise ValueError("net_cash/net_debt conflict: remove net_debt before mapping")
        if "receivables" in current.adjustments:
            raise ValueError(
                "Retail trade receivables cannot be added in the equity bridge")
        if current.lease_treatment not in (None, "lease_debt_adjustment"):
            raise ValueError("Existing lease treatment conflicts with lease_debt_adjustment")
    rationale = non_operating_asset_rationale.strip()
    if not rationale:
        raise ValueError("Non-operating asset rationale is required")

    preview = equity_bridge_preview(plan, evidence)
    required = (
        "net_cash", "lease_adjustments", "minorities",
        "non_operating_assets", "other_equity_adjustments",
        "current_issued_shares",
    )
    unavailable = [
        field for field in required
        if preview["rows"][field]["eligibility"] not in {"SOURCE-BACKED", "ACCEPTED"}
    ]
    if unavailable:
        raise ValueError("Reviewed equity inputs missing or invalid: " + ", ".join(unavailable))
    if preview["rows"]["net_cash"]["eligibility"] != "SOURCE-BACKED":
        raise ValueError("Net cash must be a source-backed metric")
    if preview["rows"]["current_issued_shares"]["eligibility"] != "SOURCE-BACKED":
        raise ValueError("Shares must use a source-backed current issued-share metric")
    lease_value = preview["rows"]["lease_adjustments"]["value"]
    if lease_value is None or lease_value == 0:
        raise ValueError("lease_debt_adjustment requires a non-zero lease adjustment")

    adjustments = {
        field: InputRef(
            metric_id=preview["rows"][field]["id"], field=field, case="base")
        for field in (
            "net_cash", "lease_adjustments", "minorities",
            "non_operating_assets", "other_equity_adjustments",
        )
    }
    return EquitySpec(
        adjustments=adjustments,
        shares=InputRef(
            metric_id=preview["rows"]["current_issued_shares"]["id"],
            field="current_issued_shares", case="base"),
        lease_treatment="lease_debt_adjustment",
        non_operating_asset_rationale=rationale,
    )


def map_reviewed_equity_bridge(
        plan: ForecastPlan, evidence: list[Any], *, changed_by: str,
        non_operating_asset_rationale: str = NON_OPERATING_ASSET_RATIONALE
        ) -> ForecastPlan:
    """Return a new in-memory draft with the reviewed EquitySpec; never persist or value."""
    if plan.engine_plan is None or "base" not in plan.engine_plan.cases:
        raise ValueError("Configure the base DCF engine plan before mapping the equity bridge")
    spec = build_reviewed_equity_spec(
        plan, evidence,
        non_operating_asset_rationale=non_operating_asset_rationale)
    engine = plan.engine_plan
    base = engine.cases["base"].model_copy(update={"equity": spec})
    updated_engine = engine.model_copy(
        update={"cases": {**engine.cases, "base": base}})
    return new_version(
        plan, changed_by=changed_by, engine_plan=updated_engine)

def _money(value: Decimal | None) -> str:
    if value is None:
        return "missing"
    sign = "-" if value < 0 else ""
    value = abs(value)
    if value >= Decimal("1000000000"):
        return f"{sign}R{value / Decimal('1000000000'):.3f}bn"
    if value >= Decimal("1000000"):
        return f"{sign}R{value / Decimal('1000000'):.0f}m"
    return f"{sign}R{value:,.0f}"


def render_equity_bridge_preview(preview: dict) -> str:
    rows = preview["rows"]
    labels = (
        ("net_cash", "+ Net cash"),
        ("lease_adjustments", "- Lease adjustment"),
        ("minorities", "- Minorities"),
        ("non_operating_assets", "+ Non-operating assets"),
        ("other_equity_adjustments", "+ Other equity adjustments"),
    )
    lines = ["Equity bridge", "", "Enterprise value"]
    for field, label in labels:
        row = rows[field]
        lines.append(
            f"{label:<31} {_money(row.get('value')):<13} "
            f"{row['eligibility']} | {row['mapping']}")
        lines.append(f"  ID: {row.get('id', 'missing')}")
        if row.get("error"):
            lines.append(f"  Error: {row['error']}")
    shares = rows["current_issued_shares"]
    share_value = (f"{shares['value']:,.0f}" if shares.get("value") is not None
                   else "missing")
    lines.extend([
        "",
        f"{'Shares':<31} {share_value:<13} "
        f"{shares['eligibility']} | {shares['mapping']}",
        f"  ID: {shares.get('id', 'missing')}",
        f"Lease treatment                 {preview.get('lease_treatment') or 'missing'}",
        "Non-operating asset rationale:",
        f"  {preview.get('non_operating_asset_rationale') or 'missing'}",
        "",
        f"Status: {preview['status']}",
    ])
    if preview["missing_inputs"]:
        lines.append("Missing inputs: " + ", ".join(preview["missing_inputs"]))
    if preview["missing_mappings"]:
        lines.append("Missing mappings: " + ", ".join(preview["missing_mappings"]))
    if preview["invalid"]:
        lines.append("Invalid/double-counted: " + ", ".join(preview["invalid"]))
    lines.extend([
        "",
        "Draft preview only. No valuation or target has been calculated.",
    ])
    return "\n".join(lines)
