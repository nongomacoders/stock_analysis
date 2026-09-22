"""Typed facts and deterministic unit conversions; no target-price model."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AssumptionType(str, Enum):
    HISTORICAL_ACTUAL = "historical_actual"
    FORMAL_GUIDANCE = "formal_guidance"
    MANAGEMENT_TARGET = "management_target"
    EXTERNAL_CONSENSUS = "external_consensus"
    MODEL_ASSUMPTION = "model_assumption"
    PREVIOUS_REPORT = "previous_report"
    PYTHON_CALCULATION = "python_calculation"
    UNRESOLVED = "unresolved"


class SourceType(str, Enum):
    COMPANY_DISCLOSURE = "company_disclosure"
    MARKET_DATA = "market_data"
    EXTERNAL_CONSENSUS = "external_consensus"
    PREVIOUS_REPORT = "previous_report"
    MODEL = "model"
    PYTHON = "python"
    MANUAL = "manual"
    UNRESOLVED = "unresolved"


class ProductionStage(str, Enum):
    ORE_MINED = "ore_mined"
    ROM_FEED = "rom_feed"
    PROCESSED_ORE = "processed_ore"
    CONCENTRATE = "concentrate"
    CONTAINED_METAL = "contained_metal"
    REFINED_PRODUCT = "refined_product"
    SALEABLE_PRODUCT = "saleable_product"
    SALES_VOLUME = "sales_volume"
    CAPACITY = "capacity"


class CostDefinition(str, Enum):
    PRODUCTION_COST = "production_cost"
    CASH_COST = "cash_cost"
    AISC = "aisc"
    OPERATING_COST = "operating_cost"


class CommodityPriceType(str, Enum):
    CURRENT_SPOT = "current_spot"
    HISTORICAL_AVERAGE = "historical_average"
    ANALYST_FORECAST = "analyst_forecast"
    LONG_TERM_NORMALIZED = "long_term_normalized"


class ShareCountType(str, Enum):
    ISSUED_SHARES_CURRENT = "issued_shares_current"
    WEIGHTED_AVERAGE_BASIC_SHARES = "weighted_average_basic_shares"
    WEIGHTED_AVERAGE_DILUTED_SHARES = "weighted_average_diluted_shares"
    FORECAST_DILUTED_SHARES = "forecast_diluted_shares"


class Unit(str, Enum):
    TONNES_ROM_PER_MONTH = "tonnes_rom_per_month"
    TONNES_ROM_PER_YEAR = "tonnes_rom_per_year"
    TONNES_ORE = "tonnes_ore"
    TONNES_PROCESSED_ORE = "tonnes_processed_ore"
    TONNES_CONCENTRATE = "tonnes_concentrate"
    TONNES_CONTAINED_METAL = "tonnes_contained_metal"
    TONNES_REFINED_PRODUCT = "tonnes_refined_product"
    TONNES_SALEABLE_PRODUCT = "tonnes_saleable_product"
    TONNES_SALES_VOLUME = "tonnes_sales_volume"
    TONNES_CAPACITY_PER_YEAR = "tonnes_capacity_per_year"
    USD_PER_LB = "USD_per_lb"
    USD_PER_TONNE = "USD_per_tonne"
    ZAR = "ZAR"
    ZAR_CENTS = "ZAR_cents"
    USD = "USD"
    SHARES = "shares"
    PERCENTAGE = "percentage"
    MULTIPLE = "multiple"


PRODUCTION_UNITS = {
    ProductionStage.ORE_MINED: {Unit.TONNES_ORE},
    ProductionStage.ROM_FEED: {Unit.TONNES_ROM_PER_MONTH, Unit.TONNES_ROM_PER_YEAR},
    ProductionStage.PROCESSED_ORE: {Unit.TONNES_PROCESSED_ORE},
    ProductionStage.CONCENTRATE: {Unit.TONNES_CONCENTRATE},
    ProductionStage.CONTAINED_METAL: {Unit.TONNES_CONTAINED_METAL},
    ProductionStage.REFINED_PRODUCT: {Unit.TONNES_REFINED_PRODUCT},
    ProductionStage.SALEABLE_PRODUCT: {Unit.TONNES_SALEABLE_PRODUCT},
    ProductionStage.SALES_VOLUME: {Unit.TONNES_SALES_VOLUME},
    ProductionStage.CAPACITY: {Unit.TONNES_CAPACITY_PER_YEAR},
}


class FinancialMetric(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=False)

    metric_id: UUID = Field(default_factory=uuid4)
    ticker: str
    report_id: UUID | None = None
    name: str
    value: Decimal | None = None
    value_low: Decimal | None = None
    value_high: Decimal | None = None
    currency: str | None = None
    unit: Unit | None = None
    period_start: date | None = None
    period_end: date | None = None
    source_date: date | None = None
    source: str | None = None
    source_type: SourceType = SourceType.UNRESOLVED
    assumption_type: AssumptionType = AssumptionType.UNRESOLVED
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    operation_segment: str | None = None
    commodity: str | None = None
    price_type: CommodityPriceType | None = None
    cost_definition: CostDefinition | None = None
    production_stage: ProductionStage | None = None
    share_count_type: ShareCountType | None = None
    annualised: bool | None = None
    notes: str | None = None
    raw_value: str | None = None
    raw_unit: str | None = None
    normalized_value: Decimal | None = None
    normalized_unit: Unit | None = None
    conversion: str | None = None
    evidence_quote: str | None = None
    evidence_verified: bool = False
    source_id: str | None = None
    intended_use: str | None = None

    @model_validator(mode="after")
    def enforce_semantics(self):
        if self.name == "shares" or self.name == "production" or self.name == "cost":
            raise ValueError("Use a specific metric name; generic shares/production/cost loses meaning")
        if self.share_count_type:
            if self.unit not in (None, Unit.SHARES):
                raise ValueError("Share counts require the shares unit")
            if self.name != self.share_count_type.value:
                raise ValueError("Share metric name must identify its share-count basis")
        if self.name in {x.value for x in ShareCountType} and self.share_count_type is None:
            raise ValueError("Named share count requires share_count_type")
        if self.production_stage:
            if self.name != f"production_{self.production_stage.value}":
                raise ValueError("Production metric name must identify its stage")
            if self.unit is not None and self.unit not in PRODUCTION_UNITS[self.production_stage]:
                raise ValueError("Production stage and unit are incompatible")
        if self.period_start and self.period_end and self.period_start > self.period_end:
            raise ValueError("period_start must be on or before period_end")
        if self.value_low is not None and self.value_high is not None and self.value_low > self.value_high:
            raise ValueError("value_low must not exceed value_high")
        return self


LB_PER_METRIC_TONNE = Decimal("2204.6226218487757")


def usd_per_lb_to_usd_per_tonne(value: Decimal | str | int) -> Decimal:
    return Decimal(str(value)) * LB_PER_METRIC_TONNE


def zar_to_cents(value: Decimal | str | int) -> Decimal:
    return Decimal(str(value)) * 100


def cents_to_zar(value: Decimal | str | int) -> Decimal:
    return Decimal(str(value)) / 100


def monthly_to_annualised(value: Decimal | str | int) -> Decimal:
    return Decimal(str(value)) * 12


def scale_quantity(value: Decimal | str | int, scale: str) -> Decimal:
    factors = {"ones": 1, "thousands": 10**3, "millions": 10**6, "billions": 10**9}
    if scale not in factors:
        raise ValueError(f"Unsupported quantity scale: {scale}")
    return Decimal(str(value)) * factors[scale]


def convert_fx(value: Decimal | str | int, *, rate: Decimal | str | int,
               pair: str, from_currency: str, to_currency: str) -> Decimal:
    """Pair ABCXYZ means one ABC buys `rate` XYZ; no unstated cross-rate."""
    pair = pair.upper().replace("/", "")
    src, dst = from_currency.upper(), to_currency.upper()
    fx_rate = Decimal(str(rate))
    if len(pair) != 6 or fx_rate <= 0:
        raise ValueError("FX pair must contain two currencies and rate must be positive")
    if src == pair[:3] and dst == pair[3:]:
        return Decimal(str(value)) * fx_rate
    if src == pair[3:] and dst == pair[:3]:
        return Decimal(str(value)) / fx_rate
    raise ValueError("Currencies do not match the explicit FX pair")


def normalize_metric(metric: FinancialMetric) -> FinancialMetric:
    """Return a copy; raw value/unit remain unchanged for auditability."""
    if metric.value is None or metric.unit is None:
        return metric
    if metric.unit == Unit.USD_PER_LB:
        return metric.model_copy(update={"normalized_value": usd_per_lb_to_usd_per_tonne(metric.value),
                                         "normalized_unit": Unit.USD_PER_TONNE,
                                         "conversion": "USD_per_lb_to_USD_per_tonne * 2204.6226218487757"})
    if metric.unit == Unit.ZAR and metric.name in {"target_price", "current_share_price"}:
        return metric.model_copy(update={"normalized_value": zar_to_cents(metric.value),
                                         "normalized_unit": Unit.ZAR_CENTS,
                                         "conversion": "ZAR_to_ZAR_cents * 100"})
    if metric.unit == Unit.ZAR_CENTS and metric.name in {"target_price", "current_share_price"}:
        return metric.model_copy(update={"normalized_value": cents_to_zar(metric.value),
                                         "normalized_unit": Unit.ZAR,
                                         "conversion": "ZAR_cents_to_ZAR / 100"})
    if metric.unit == Unit.TONNES_ROM_PER_MONTH:
        return metric.model_copy(update={"normalized_value": monthly_to_annualised(metric.value),
                                         "normalized_unit": Unit.TONNES_ROM_PER_YEAR,
                                         "conversion": "monthly_ROM_to_annual_ROM * 12"})
    return metric.model_copy(update={"normalized_value": metric.value, "normalized_unit": metric.unit})


def metric_json(metric: FinancialMetric) -> dict[str, Any]:
    return metric.model_dump(mode="json")
