import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from modules.analysis.financial_metrics import (
    FinancialMetric, ProductionStage, ShareCountType, SourceType, Unit,
    cents_to_zar, convert_fx, monthly_to_annualised, normalize_metric,
    scale_quantity, usd_per_lb_to_usd_per_tonne, zar_to_cents,
)
from modules.analysis.metric_extraction import structure_report_metrics
from modules.analysis.metric_validation import (
    assert_compatible_for_revenue, assert_compatible_shares_for_target, validate_metrics,
)


def metric(name, **kwargs):
    return FinancialMetric(ticker="JBL.JO", name=name, **kwargs)


def test_exact_conversions_preserve_original():
    assert usd_per_lb_to_usd_per_tonne("6.21") == Decimal("6.21") * Decimal("2204.6226218487757")
    assert zar_to_cents("1.70") == 170
    assert cents_to_zar(170) == Decimal("1.70")
    assert monthly_to_annualised(10000) == 120000
    assert scale_quantity("3.146295996", "billions") == 3146295996
    assert convert_fx(1, rate="17.5", pair="USDZAR", from_currency="USD", to_currency="ZAR") == Decimal("17.5")
    assert convert_fx("17.5", rate="17.5", pair="USD/ZAR", from_currency="ZAR", to_currency="USD") == 1
    raw = metric("commodity_price", value=Decimal("6.21"), unit=Unit.USD_PER_LB, commodity="copper")
    normal = normalize_metric(raw)
    assert normal.value == Decimal("6.21") and normal.unit == Unit.USD_PER_LB
    assert normal.normalized_unit == Unit.USD_PER_TONNE


def test_stage_and_share_semantics_cannot_be_silently_conflated():
    rom = metric("production_rom_feed", value=10000, unit=Unit.TONNES_ROM_PER_MONTH,
                 production_stage=ProductionStage.ROM_FEED, commodity="copper")
    price = metric("commodity_price", value=6, unit=Unit.USD_PER_LB, commodity="copper")
    assert normalize_metric(rom).normalized_value == 120000
    assert normalize_metric(rom).normalized_unit == Unit.TONNES_ROM_PER_YEAR
    with pytest.raises(ValidationError):
        metric("production_contained_metal", value=10000, unit=Unit.TONNES_ROM_PER_MONTH,
               production_stage=ProductionStage.CONTAINED_METAL)
    with pytest.raises(ValueError):
        assert_compatible_for_revenue(rom, price)
    weighted = metric("weighted_average_basic_shares", value=3146295996, unit=Unit.SHARES,
                      share_count_type=ShareCountType.WEIGHTED_AVERAGE_BASIC_SHARES)
    with pytest.raises(ValueError):
        assert_compatible_shares_for_target(weighted)


def test_jubilee_source_periods_freshness_and_guidance_warnings():
    old = metric("production_cost_per_tonne", value=5948, unit=Unit.USD_PER_TONNE,
                 period_start=date(2024, 7, 1), period_end=date(2024, 12, 31),
                 source_date=date(2025, 3, 31), source_type=SourceType.COMPANY_DISCLOSURE,
                 commodity="copper")
    new = metric("production_cost_per_tonne", value=8062, unit=Unit.USD_PER_TONNE,
                 period_start=date(2025, 7, 1), period_end=date(2025, 12, 31),
                 source_date=date(2026, 3, 31), source_type=SourceType.COMPANY_DISCLOSURE,
                 commodity="copper")
    old_shares = metric("issued_shares_current", value=3146295996, unit=Unit.SHARES,
                        share_count_type=ShareCountType.ISSUED_SHARES_CURRENT,
                        source_date=date(2025, 8, 11), source_type=SourceType.COMPANY_DISCLOSURE)
    new_shares = metric("issued_shares_current", value=3381330240, unit=Unit.SHARES,
                        share_count_type=ShareCountType.ISSUED_SHARES_CURRENT,
                        source_date=date(2026, 8, 11), source_type=SourceType.COMPANY_DISCLOSURE)
    codes = [w["code"] for w in validate_metrics([old, new, old_shares, new_shares])]
    assert codes.count("STALE_INPUT") == 2
    assert old.period_end == date(2024, 12, 31) and new.period_end == date(2025, 12, 31)


def test_unresolved_gemini_fields_retained_and_warned():
    audit = {"assumptions": [
        {"assumption": "production", "value": "12,000", "unit": "tonnes", "classification": "unresolved"},
        {"assumption": "production", "value": "10,000", "unit_code": "tonnes_rom_per_month",
         "production_stage": "contained_metal", "classification": "management_target"},
        {"assumption": "target_price", "value": "ZAR1.70", "unit_code": "ZAR",
         "classification": "previous_report", "source": "previous_report"},
    ]}
    metrics, warnings = structure_report_metrics("JBL.JO", uuid4(), audit)
    assert len(metrics) == 2
    assert metrics[0].production_stage is None and metrics[0].raw_unit == "tonnes"
    assert metrics[1].name == "target_price" and metrics[1].assumption_type.value == "previous_report"
    assert {w["code"] for w in warnings} >= {"INVALID_METRIC", "PRODUCTION_STAGE_UNRESOLVED"}


def test_jubilee_structured_regression_fixture():
    import json
    fixture = Path(__file__).resolve().parent / "fixtures/jubilee_phase2_metrics.json"
    metrics = [FinancialMetric.model_validate(x) for x in json.loads(fixture.read_text(encoding="utf-8"))]
    assert len(metrics) == 11
    roan, molefe_rom, molefe_copper, pre_refining, saleable = metrics[:5]
    assert roan.assumption_type.value == "formal_guidance" and (roan.value_low, roan.value_high) == (2850, 3150)
    assert molefe_rom.production_stage == ProductionStage.ROM_FEED
    assert molefe_rom.assumption_type.value == "management_target"
    assert normalize_metric(molefe_rom).normalized_value == 120000
    assert molefe_copper.production_stage == ProductionStage.CONTAINED_METAL and molefe_copper.value == 1740
    assert pre_refining.production_stage == ProductionStage.CONTAINED_METAL and pre_refining.value == 3739
    assert saleable.production_stage == ProductionStage.SALEABLE_PRODUCT and saleable.value == 2120
    assert metrics[5].value == 3146295996 and metrics[6].value == 3381330240
    assert metrics[7].period_end == date(2024, 12, 31) and metrics[8].period_end == date(2025, 12, 31)
    assert metrics[9].value == 5950 and metrics[9].period_end is None and metrics[9].source is None
    assert metrics[10].value == Decimal("1.70") and metrics[10].assumption_type.value == "previous_report"
    codes = [w["code"] for w in validate_metrics(metrics)]
    assert codes.count("STALE_INPUT") >= 2
    assert "TARGET_NOT_GUIDANCE" in codes and "MISSING_PERIOD" in codes
    with pytest.raises(ValueError):
        assert_compatible_for_revenue(molefe_copper, metric("commodity_price", unit=Unit.USD_PER_TONNE, commodity="copper"))
