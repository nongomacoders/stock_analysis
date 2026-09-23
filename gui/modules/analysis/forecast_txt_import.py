"""Strict, atomic import of human-readable ForecastPlan assumption files."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from .forecast_plan import (
    ApprovalState, ForecastAssumption, ForecastPeriod, ForecastPlan, Origin,
    horizon_for_assumption,
)
from .retail_forecast import WorkbenchRoute, workbench_route

IMPORT_FORMAT_VERSION = "forecast-txt-1.0"

HEADER_KEYS = {"ticker", "case"}
ASSUMPTION_KEYS = {
    "period", "start", "end", "operation", "case", "field", "value", "unit",
    "currency", "confidence", "analyst", "rationale", "commodity", "price_type",
    "project_start", "cost_definition", "fx_pair",
}
MINING_FIELDS = {
    "aisc", "cash_cost", "commodity_price", "grade", "mining_cost",
    "mining_throughput", "nameplate_capacity", "payability", "processing_conversion",
    "processing_cost", "production_cost", "production_growth", "production_volume",
    "ramp_up", "reagent_energy_factor", "recovery", "refining_cost", "rom",
    "royalties", "royalty_rate", "saleable_volume", "treatment_charge",
    "treatment_cost", "utilization",
}


class ForecastTxtImportError(ValueError):
    pass


@dataclass(frozen=True)
class ForecastTxtDuplicate:
    status: str
    identity: tuple[str | None, str, str | None, str]
    existing: ForecastAssumption
    imported: ForecastAssumption
    against: str

    def render(self) -> str:
        period, case, operation, field = self.identity
        return (
            f"{self.status}: {period} / {case} / {operation} / {field} ({self.against})\n"
            f"  existing: value={self.existing.value} unit={self.existing.unit} "
            f"currency={self.existing.currency} confidence={self.existing.confidence} "
            f"analyst={self.existing.created_by} rationale={self.existing.rationale}\n"
            f"  imported: value={self.imported.value} unit={self.imported.unit} "
            f"currency={self.imported.currency} confidence={self.imported.confidence} "
            f"analyst={self.imported.created_by} rationale={self.imported.rationale}"
        )


@dataclass(frozen=True)
class ForecastTxtPreview:
    ticker: str
    default_case: str
    horizon: list[ForecastPeriod]
    assumptions: list[ForecastAssumption]
    duplicates: list[ForecastTxtDuplicate]
    source_name: str | None = None

    @property
    def conflicts(self) -> list[ForecastTxtDuplicate]:
        return [item for item in self.duplicates if item.status == "DUPLICATE_CONFLICT"]

    @property
    def identical_duplicates(self) -> list[ForecastTxtDuplicate]:
        return [item for item in self.duplicates if item.status == "DUPLICATE_IDENTICAL"]

    def render(self) -> str:
        periods = "\n".join(
            f"  {item.label}: {item.start.isoformat()} to {item.end.isoformat()}"
            for item in self.horizon
        ) or "  None"
        rows = []
        for number, item in enumerate(self.assumptions, 1):
            rows.extend([
                f"{number}. {item.period_label} | {item.case} | {item.operation_segment}",
                f"   {item.field} = {item.value} {item.unit}",
                f"   currency={item.currency or 'None'} confidence={item.confidence}",
                f"   analyst={item.created_by}",
                f"   approval={item.approval_state.value} origin={item.origin.value}",
                f"   rationale={item.rationale}",
            ])
        duplicate_rows = "\n\n".join(item.render() for item in self.duplicates) or "None"
        return (
            f"Source: {self.source_name or 'TXT input'}\n"
            f"Ticker: {self.ticker}\nDefault case: {self.default_case}\n\n"
            f"Resulting forecast periods:\n{periods}\n\n"
            f"New assumptions to add ({len(self.assumptions)}):\n" + "\n".join(rows) +
            f"\n\nDuplicate review ({len(self.duplicates)}):\n{duplicate_rows}"
        )


def assumption_identity(item: ForecastAssumption) -> tuple[str | None, str, str | None, str]:
    return (item.period_label, item.case, item.operation_segment, item.field)


def _semantic_values(item: ForecastAssumption) -> dict:
    return {
        "value": item.value, "unit": item.unit, "currency": item.currency,
        "commodity": item.commodity, "confidence": item.confidence,
        "rationale": item.rationale.strip(), "created_by": item.created_by.strip(),
        "effective_date": item.effective_date, "price_type": item.price_type,
        "cost_definition": item.cost_definition, "fx_pair": item.fx_pair,
        "origin": item.origin, "approval_state": item.approval_state,
    }


def resolve_import_assumptions(current_plan: ForecastPlan, preview: ForecastTxtPreview,
                               conflict_action: str) -> list[ForecastAssumption]:
    if conflict_action not in {"keep_existing", "replace_as_proposed"}:
        raise ForecastTxtImportError("Duplicate conflicts require Keep Existing or Replace as Proposed")
    combined = [*current_plan.assumptions, *preview.assumptions]
    if conflict_action == "replace_as_proposed":
        for duplicate in preview.conflicts:
            identity = duplicate.identity
            combined = [item for item in combined if assumption_identity(item) != identity]
            replacement = ForecastAssumption.model_validate({
                **duplicate.imported.model_dump(),
                "approval_state": ApprovalState.PROPOSED,
                "origin": Origin.ANALYST_ASSUMPTION,
            })
            combined.append(replacement)
    ForecastPlan.model_validate({
        **current_plan.model_dump(), "horizon": preview.horizon, "assumptions": combined,
    })
    return combined


def _add_implicit_markers(text: str) -> str:
    """Accept compact files when section boundaries are unambiguous."""
    lines = text.lstrip("\ufeff").splitlines()
    if any(line.strip().upper() in {"FORECAST_PLAN", "ASSUMPTION"} for line in lines):
        return text
    output = ["FORECAST_PLAN"]
    assumption_started = False
    current_has_period = False
    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped:
            output.append(raw_line)
            continue
        if "=" not in stripped:
            output.append(raw_line)
            continue
        key = stripped.split("=", 1)[0].strip().casefold()
        if not assumption_started and key in HEADER_KEYS:
            output.append(raw_line)
            continue
        if not assumption_started or (key == "period" and current_has_period):
            output.append("ASSUMPTION")
            assumption_started = True
            current_has_period = False
        output.append(raw_line)
        if key == "period":
            current_has_period = True
    return "\n".join(output)


def _parse_sections(text: str) -> tuple[dict[str, str], list[dict[str, str]]]:
    text = _add_implicit_markers(text)
    header: dict[str, str] = {}
    assumptions: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    section: str | None = None
    for line_number, raw_line in enumerate(text.lstrip("\ufeff").splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        marker = line.upper()
        if marker == "FORECAST_PLAN":
            if section is not None:
                raise ForecastTxtImportError(f"Line {line_number}: FORECAST_PLAN must appear once at the start")
            section = "plan"
            current = header
            continue
        if marker == "ASSUMPTION":
            if section is None:
                raise ForecastTxtImportError(f"Line {line_number}: FORECAST_PLAN header is required first")
            section = "assumption"
            current = {}
            assumptions.append(current)
            continue
        if current is None or "=" not in line:
            raise ForecastTxtImportError(f"Line {line_number}: expected key=value")
        key, value = (part.strip() for part in line.split("=", 1))
        key = key.casefold()
        allowed = HEADER_KEYS if section == "plan" else ASSUMPTION_KEYS
        if key not in allowed:
            raise ForecastTxtImportError(f"Line {line_number}: unknown {section} field {key!r}")
        if key in current:
            raise ForecastTxtImportError(f"Line {line_number}: duplicate field {key!r}")
        current[key] = value
    if not header:
        raise ForecastTxtImportError("FORECAST_PLAN header is missing or empty")
    if not assumptions:
        raise ForecastTxtImportError("At least one ASSUMPTION block is required")
    return header, assumptions


def _required(block: dict[str, str], key: str, number: int) -> str:
    value = block.get(key, "").strip()
    if not value:
        raise ForecastTxtImportError(f"Assumption {number}: {key} is required")
    return value


def _optional(block: dict[str, str], key: str) -> str | None:
    return block.get(key, "").strip() or None


def _date(value: str | None, label: str, number: int) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ForecastTxtImportError(f"Assumption {number}: {label} must be YYYY-MM-DD") from exc


def validate_sector_assumption(category: str | None, assumption: ForecastAssumption) -> None:
    route = workbench_route(category)
    if route == WorkbenchRoute.RETAIL and assumption.field in MINING_FIELDS:
        raise ForecastTxtImportError(
            f"Sector compatibility: {assumption.field} is a mining field and cannot be imported for {category}"
        )


def parse_forecast_txt(text: str, *, current_plan: ForecastPlan, current_ticker: str,
                       category: str | None, source_name: str | None = None,
                       allowed_operations: set[str] | None = None) -> ForecastTxtPreview:
    header, blocks = _parse_sections(text)
    ticker = header.get("ticker", "").strip().upper()
    if not ticker:
        raise ForecastTxtImportError("FORECAST_PLAN ticker is required")
    if ticker != current_ticker.strip().upper():
        raise ForecastTxtImportError(
            f"IMPORT BLOCKED â€” ticker mismatch: current window {current_ticker}, file {ticker}"
        )
    default_case = header.get("case", "base").strip() or "base"
    horizon = list(current_plan.horizon)
    imported: list[ForecastAssumption] = []
    duplicates: list[ForecastTxtDuplicate] = []
    known = {assumption_identity(item): (item, "current in-memory draft")
             for item in current_plan.assumptions}
    working = current_plan
    for number, block in enumerate(blocks, 1):
        period_label = _required(block, "period", number)
        start = _date(_optional(block, "start"), "start", number)
        end = _date(_optional(block, "end"), "end", number)
        try:
            horizon, _ = horizon_for_assumption(working.model_copy(update={"horizon": horizon}),
                                                 period_label, start=start, end=end)
            value_text = _required(block, "value", number)
            confidence_text = _required(block, "confidence", number)
            assumption = ForecastAssumption(
                field=_required(block, "field", number),
                value=Decimal(value_text),
                unit=_required(block, "unit", number),
                currency=_optional(block, "currency"),
                period_label=period_label,
                operation_segment=_required(block, "operation", number),
                case=_optional(block, "case") or default_case,
                origin=Origin.ANALYST_ASSUMPTION,
                approval_state=ApprovalState.PROPOSED,
                rationale=_required(block, "rationale", number),
                created_by=_required(block, "analyst", number),
                commodity=_optional(block, "commodity"),
                price_type=_optional(block, "price_type"),
                cost_definition=_optional(block, "cost_definition"),
                fx_pair=_optional(block, "fx_pair"),
                confidence=Decimal(confidence_text),
                effective_date=_date(_optional(block, "project_start"), "project_start", number),
            )
            validate_sector_assumption(category, assumption)
            if allowed_operations is not None and assumption.operation_segment not in allowed_operations:
                raise ForecastTxtImportError(
                    f"Assumption {number}: unknown operation {assumption.operation_segment!r}; "
                    f"allowed operations are {sorted(allowed_operations)}")
            # Reuse the existing accepted-assumption validator to ensure every imported proposal
            # already contains the metadata required for later analyst acceptance.
            ForecastAssumption.model_validate({
                **assumption.model_dump(), "approval_state": ApprovalState.ACCEPTED,
            })
        except (ValueError, InvalidOperation) as exc:
            if isinstance(exc, ForecastTxtImportError):
                raise
            raise ForecastTxtImportError(f"Assumption {number}: {exc}") from exc
        identity = assumption_identity(assumption)
        prior = known.get(identity)
        if prior is None:
            imported.append(assumption)
            known[identity] = (assumption, "earlier TXT entry")
        else:
            existing, against = prior
            status = ("DUPLICATE_IDENTICAL" if _semantic_values(existing) == _semantic_values(assumption)
                      else "DUPLICATE_CONFLICT")
            duplicates.append(ForecastTxtDuplicate(
                status=status, identity=identity, existing=existing,
                imported=assumption, against=against))
    # Validate the default keep-existing result atomically with the existing ForecastPlan validator.
    try:
        ForecastPlan.model_validate({
            **current_plan.model_dump(),
            "horizon": horizon,
            "assumptions": [*current_plan.assumptions, *imported],
        })
    except ValueError as exc:
        raise ForecastTxtImportError(f"ForecastPlan validation failed: {exc}") from exc
    return ForecastTxtPreview(
        ticker=ticker, default_case=default_case, horizon=horizon,
        assumptions=imported, duplicates=duplicates, source_name=source_name,
    )

