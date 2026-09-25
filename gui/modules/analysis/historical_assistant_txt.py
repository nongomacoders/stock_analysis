"""Export and mapping utilities for historical assumption proposals."""
from __future__ import annotations
from datetime import date
from decimal import Decimal
from modules.analysis.forecast_plan import ApprovalState, ForecastAssumption, Origin
from modules.analysis.historical_plan import HistoricalForecastPlan
from modules.analysis.historical_assistant import HistoricalAssumptionProposal

def export_proposals_to_txt(
    proposals: list[HistoricalAssumptionProposal],
    ticker: str,
    as_of_date: date,
    forecast_period: str = "FY2026",
    analyst_tag: str = "historical_assistant"
) -> str:
    lines = [
        "BACKTEST",
        f"ticker={ticker.strip().upper()}",
        f"as_of_date={as_of_date.isoformat()}",
        f"forecast_period={forecast_period.strip()}",
        ""
    ]
    for p in proposals:
        if not isinstance(p.proposed_value, Decimal) and not str(p.proposed_value).replace(".", "", 1).isdigit():
            continue
        lines.append("ASSUMPTION")
        lines.append(f"field={p.field}")
        lines.append(f"value={p.proposed_value}")
        lines.append(f"unit={p.unit}")
        lines.append(f"rationale={p.rationale}")
        lines.append(f"analyst={analyst_tag}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"

def proposals_to_forecast_assumptions(
    proposals: list[HistoricalAssumptionProposal],
    plan: HistoricalForecastPlan,
    state: ApprovalState = ApprovalState.PROPOSED,
    analyst_tag: str = "historical_assistant"
) -> list[ForecastAssumption]:
    assumptions: list[ForecastAssumption] = []
    for p in proposals:
        if not isinstance(p.proposed_value, Decimal):
            try: val = Decimal(str(p.proposed_value))
            except Exception: continue
        else: val = p.proposed_value
        a = ForecastAssumption(
            field=p.field,
            value=val,
            unit=p.unit,
            period_label="FY2026",
            operation_segment="Group",
            case=p.case,
            origin=Origin.ANALYST_ASSUMPTION,
            approval_state=state,
            rationale=p.rationale,
            created_by=analyst_tag,
            source_date=plan.as_of_date,
        )
        assumptions.append(a)
    return assumptions
