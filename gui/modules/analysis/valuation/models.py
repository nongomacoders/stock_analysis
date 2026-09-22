"""Serializable deterministic valuation results and explicit plan inputs."""
from __future__ import annotations
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Literal
from uuid import UUID, uuid4
from pydantic import BaseModel, Field, model_validator


class ValuationStatus(str, Enum):
    PASS = "PASS"
    PASS_WITH_WARNINGS = "PASS_WITH_WARNINGS"
    FAIL = "FAIL"
    NOT_CALCULABLE = "NOT_CALCULABLE"


class MethodStatus(str, Enum):
    PASS = "PASS"
    NOT_CALCULABLE = "NOT_CALCULABLE"
    FAIL = "FAIL"


class TerminalMethod(str, Enum):
    PERPETUITY_GROWTH = "perpetuity_growth"
    EXIT_MULTIPLE = "exit_multiple"


class Basis(str, Enum):
    NOMINAL = "nominal"
    REAL = "real"


class InputRef(BaseModel):
    metric_id: UUID
    field: str
    case: Literal["base", "bear", "bull", "sensitivity", "informational"] = "base"


class ValuationMethodResult(BaseModel):
    method: str
    status: MethodStatus
    value: Decimal | None = None
    currency: str | None = None
    missing_inputs: list[str] = Field(default_factory=list)
    schedule: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    input_ids: list[UUID] = Field(default_factory=list)


class TargetReconciliation(BaseModel):
    enterprise_or_operating_value: Decimal
    non_operating_assets: Decimal
    receivables: Decimal
    cash: Decimal
    debt: Decimal
    lease_adjustments: Decimal
    minorities: Decimal
    other_equity_adjustments: Decimal
    equity_value: Decimal
    shares: Decimal
    shares_metric_id: UUID
    unrounded_target_zar: Decimal
    rounded_target_zar: Decimal
    rounded_target_cents: Decimal
    display_currency: str = "ZAR"
    display_unit: str = "ZAR_per_share"
    rounding_tolerance: Decimal = Decimal("0.005")


class ValuationResult(BaseModel):
    valuation_id: UUID = Field(default_factory=uuid4)
    ticker: str
    report_version_id: UUID
    valuation_date: date
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    valuation_engine_version: str = "1.0"
    currency: str = "ZAR"
    cases: dict[str, Any] = Field(default_factory=dict)
    case_differences: list[dict[str, Any]] = Field(default_factory=list)
    methods: dict[str, ValuationMethodResult] = Field(default_factory=dict)
    sotp: dict[str, Any] | None = None
    target_price: Decimal | None = None
    reconciliation: TargetReconciliation | None = None
    warnings: list[str] = Field(default_factory=list)
    status: ValuationStatus
    preflight: dict[str, Any] | None = None
    input_ids: list[UUID] = Field(default_factory=list)
    calculation_inputs: dict[str, Any] = Field(default_factory=dict)
    legacy_gemini_target: Decimal | None = None
    legacy_target_derivation: str | None = None
    implied_checks: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def no_unreconciled_target(self):
        if self.status in {ValuationStatus.FAIL, ValuationStatus.NOT_CALCULABLE} and self.target_price is not None:
            raise ValueError("Failed or unavailable valuation cannot publish a deterministic target")
        if self.target_price is not None and self.reconciliation is None:
            raise ValueError("Deterministic target requires equity-to-share reconciliation")
        return self
