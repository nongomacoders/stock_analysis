import json
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from modules.analysis.financial_metrics import (
    AssumptionType, CommodityPriceType, CostDefinition, FinancialMetric, ProductionStage,
    ShareCountType, SourceType, Unit,
)
from modules.analysis.valuation_preflight import (
    CaseType, Eligibility, OverrideRecord, Severity, TargetDerivation,
    ValuationField, ValidationResult, candidate, check_double_counting,
    freshness, reconcile_target, run_preflight, validate_candidate,
)

REPORT = uuid4()


def m(name, value=None, **kwargs):
    return FinancialMetric(ticker="JBL.JO", report_id=REPORT, name=name, value=value, **kwargs)


def c(metric, field, case="base", **kwargs):
    return candidate(metric, REPORT, field, case, "Explicit test selection", **kwargs)


def codes(decision):
    return {x.code for x in decision.warnings}


def test_guidance_eligible_and_management_rom_blocked_as_copper():
    guidance = m("production_contained_metal", None, value_low=2850, value_high=3150,
                 unit=Unit.TONNES_CONTAINED_METAL, production_stage=ProductionStage.CONTAINED_METAL,
                 commodity="copper", operation_segment="Roan", assumption_type=AssumptionType.FORMAL_GUIDANCE)
    roan, _ = validate_candidate(c(guidance, "production_volume"), [guidance])
    assert roan.selected_value == 3000 and roan.validation_status == Eligibility.ELIGIBLE
    rom = m("production_rom_feed", 10000, unit=Unit.TONNES_ROM_PER_MONTH,
            production_stage=ProductionStage.ROM_FEED, commodity="copper", operation_segment="Molefe",
            assumption_type=AssumptionType.MANAGEMENT_TARGET)
    invalid, _ = validate_candidate(c(rom, "production_volume"), [rom])
    assert invalid.validation_status == Eligibility.INELIGIBLE and "ROM_AS_METAL" in codes(invalid)
    bull, _ = validate_candidate(c(rom, "mining_throughput", "bull"), [rom])
    assert bull.validation_status == Eligibility.ELIGIBLE_WITH_WARNING
    assert bull.selected_value == 120000 and bull.normalized_unit == Unit.TONNES_ROM_PER_YEAR


def test_contained_saleable_capacity_and_revenue_guards():
    contained = m("production_contained_metal", 1740, unit=Unit.TONNES_CONTAINED_METAL,
                  production_stage=ProductionStage.CONTAINED_METAL, commodity="copper")
    sale, _ = validate_candidate(c(contained, "saleable_volume"), [contained])
    revenue, _ = validate_candidate(c(contained, "revenue"), [contained])
    assert "NOT_SALEABLE" in codes(sale) and "UPSTREAM_REVENUE" in codes(revenue)
    capacity = m("production_capacity", 25000, unit=Unit.TONNES_CAPACITY_PER_YEAR,
                 production_stage=ProductionStage.CAPACITY)
    cap, _ = validate_candidate(c(capacity, "production_volume"), [capacity])
    assert "CAPACITY_AS_PRODUCTION" in codes(cap)
    feed = m("production_rom_feed", 10000, unit=Unit.TONNES_ROM_PER_MONTH,
             production_stage=ProductionStage.ROM_FEED, commodity="copper", operation_segment="Molefe")
    product = m("production_saleable_product", 1000, unit=Unit.TONNES_SALEABLE_PRODUCT,
                production_stage=ProductionStage.SALEABLE_PRODUCT, commodity="copper", operation_segment="Molefe")
    one = c(feed, "production_volume", combination_group="same-revenue-sum")
    two = c(product, "saleable_volume", combination_group="same-revenue-sum")
    assert check_double_counting([one, two])[0].severity == Severity.BLOCKING


def test_share_basis_staleness_and_forward_preference():
    old = m("issued_shares_current", 3146295996, unit=Unit.SHARES,
            share_count_type=ShareCountType.ISSUED_SHARES_CURRENT,
            source_type=SourceType.COMPANY_DISCLOSURE, assumption_type=AssumptionType.HISTORICAL_ACTUAL,
            source_date=date(2025, 8, 11))
    new = m("issued_shares_current", 3381330240, unit=Unit.SHARES,
            share_count_type=ShareCountType.ISSUED_SHARES_CURRENT,
            source_type=SourceType.COMPANY_DISCLOSURE, assumption_type=AssumptionType.HISTORICAL_ACTUAL,
            source_date=date(2026, 8, 11))
    old_decision, old_fresh = validate_candidate(c(old, "current_issued_shares"), [old, new])
    assert old_decision.validation_status == Eligibility.INELIGIBLE
    assert "STALE_FORWARD_SHARES" in codes(old_decision)
    assert old_fresh["freshness_status"] == "superseded" and old_fresh["age_difference_days"] == 365
    new_decision, _ = validate_candidate(c(new, "current_issued_shares"), [old, new])
    assert new_decision.validation_status == Eligibility.ELIGIBLE_WITH_WARNING
    assert "DILUTION_UNMODELED" in codes(new_decision)
    weighted = m("weighted_average_basic_shares", 3000000000, unit=Unit.SHARES,
                 share_count_type=ShareCountType.WEIGHTED_AVERAGE_BASIC_SHARES,
                 assumption_type=AssumptionType.HISTORICAL_ACTUAL)
    w, _ = validate_candidate(c(weighted, "weighted_average_basic_shares"), [weighted])
    assert "HISTORICAL_SHARES_FORWARD" in codes(w)
    mismatch, _ = validate_candidate(c(weighted, "current_issued_shares"), [weighted])
    assert "SHARE_BASIS_MISMATCH" in codes(mismatch)


def test_identical_later_share_observation_confirms_value_without_stale_block():
    selected = m("issued_shares_current", 400551604, unit=Unit.SHARES,
        share_count_type=ShareCountType.ISSUED_SHARES_CURRENT,
        source_type=SourceType.COMPANY_DISCLOSURE,
        assumption_type=AssumptionType.HISTORICAL_ACTUAL,
        period_end=date(2026, 6, 28), source_date=date(2026, 8, 27))
    duplicate = m("issued_shares_current", 400551604, unit=Unit.SHARES,
        share_count_type=ShareCountType.ISSUED_SHARES_CURRENT,
        source_type=SourceType.COMPANY_DISCLOSURE,
        assumption_type=AssumptionType.HISTORICAL_ACTUAL,
        effective_date=date(2026, 8, 27), source_date=date(2026, 8, 27))
    decision, fresh = validate_candidate(
        c(selected, "current_issued_shares"), [selected, duplicate])
    assert fresh["freshness_status"] == "current"
    assert "STALE_FORWARD_SHARES" not in codes(decision)
    assert decision.validation_status == Eligibility.ELIGIBLE_WITH_WARNING

def test_cost_definition_freshness_and_like_for_like():
    old = m("production_cost_per_tonne", 5948, unit=Unit.USD_PER_TONNE, commodity="copper",
            source="H1 FY25", cost_definition=CostDefinition.PRODUCTION_COST, source_type=SourceType.COMPANY_DISCLOSURE,
            period_start=date(2024, 7, 1), period_end=date(2024, 12, 31))
    new = m("production_cost_per_tonne", 8062, unit=Unit.USD_PER_TONNE, commodity="copper",
            source="H1 FY26", cost_definition=CostDefinition.PRODUCTION_COST, source_type=SourceType.COMPANY_DISCLOSURE,
            period_start=date(2025, 7, 1), period_end=date(2025, 12, 31))
    cost, fresh = validate_candidate(c(old, "production_cost"), [old, new])
    assert "STALE_COST" in codes(cost) and fresh["freshness_status"] == "superseded"
    aisc, _ = validate_candidate(c(old, "aisc"), [old, new])
    assert "COST_DEFINITION_MISMATCH" in codes(aisc)
    other = m("aisc_per_tonne", 9000, unit=Unit.USD_PER_TONNE, commodity="copper",
              source_type=SourceType.COMPANY_DISCLOSURE, cost_definition=CostDefinition.AISC,
              period_end=date(2026, 6, 30))
    assert freshness(new, [old, new, other])["freshness_status"] == "current"
    assert freshness(old, [old, new, other])["comparable_metric_id"] == str(new.metric_id)


def test_price_currency_unit_and_spot_horizon():
    missing = m("commodity_price", 6.21, commodity="copper", assumption_type=AssumptionType.MODEL_ASSUMPTION)
    decision, _ = validate_candidate(c(missing, "commodity_price"), [missing])
    assert "PRICE_CURRENCY_UNIT" in codes(decision) and decision.validation_status == Eligibility.INELIGIBLE
    spot = m("commodity_price", 6.21, unit=Unit.USD_PER_LB, currency="USD", commodity="copper",
             price_type=CommodityPriceType.CURRENT_SPOT, intended_use="long_term",
             assumption_type=AssumptionType.HISTORICAL_ACTUAL)
    spot_decision, _ = validate_candidate(c(spot, "commodity_price"), [spot])
    assert "SPOT_PERPETUAL" in codes(spot_decision)
    assert spot_decision.validation_status == Eligibility.ELIGIBLE_WITH_WARNING


def test_previous_unresolved_and_unsupported_model_inputs():
    previous = m("production_contained_metal", 12000, unit=Unit.TONNES_CONTAINED_METAL,
                 production_stage=ProductionStage.CONTAINED_METAL,
                 assumption_type=AssumptionType.PREVIOUS_REPORT)
    p, _ = validate_candidate(c(previous, "production_volume"), [previous])
    assert "PREVIOUS_REPORT_BASE" in codes(p) and p.validation_status == Eligibility.INELIGIBLE
    unresolved = m("production_unresolved", 12000, assumption_type=AssumptionType.UNRESOLVED)
    u, _ = validate_candidate(c(unresolved, "production_volume"), [unresolved])
    assert u.validation_status == Eligibility.UNRESOLVED
    wacc = m("wacc", 12, unit=Unit.PERCENTAGE, assumption_type=AssumptionType.MODEL_ASSUMPTION)
    w, _ = validate_candidate(c(wacc, "wacc"), [wacc])
    assert "WACC_UNSUPPORTED" in codes(w) and w.validation_status == Eligibility.INELIGIBLE


def test_override_requires_original_findings_and_cannot_bypass_blocking():
    wacc = m("wacc", 12, unit=Unit.PERCENTAGE, assumption_type=AssumptionType.MODEL_ASSUMPTION)
    original, _ = validate_candidate(c(wacc, "wacc"), [wacc])
    override = OverrideRecord(original_validation_result=[x for x in original.warnings if x.severity == Severity.ERROR],
                              override_timestamp=datetime.now(timezone.utc), override_reason="Documented committee scenario",
                              overridden_by="analyst@example", selected_replacement="12% model WACC", case_type=CaseType.BASE)
    accepted, _ = validate_candidate(c(wacc, "wacc", override=override), [wacc])
    assert accepted.validation_status == Eligibility.ELIGIBLE_WITH_WARNING
    fake = override.model_copy(update={"original_validation_result": []})
    rejected, _ = validate_candidate(c(wacc, "wacc", override=fake), [wacc])
    assert rejected.validation_status == Eligibility.INELIGIBLE
    rom = m("production_rom_feed", 10000, unit=Unit.TONNES_ROM_PER_MONTH,
            production_stage=ProductionStage.ROM_FEED, commodity="copper")
    blocked, _ = validate_candidate(c(rom, "production_volume", override=override), [rom])
    assert blocked.validation_status == Eligibility.INELIGIBLE and "ROM_AS_METAL" in codes(blocked)
    with pytest.raises(ValidationError):
        c(wacc, "wacc", selected_value=15)


def test_target_reconciliation_and_high_upside_review():
    assert reconcile_target({"classification": "previous_report"}) == TargetDerivation.CARRIED_FORWARD
    assert reconcile_target({"calculation": "visible", "supporting_inputs": "partial"}) == TargetDerivation.PARTIAL_RECONCILIATION
    assert reconcile_target({"classification": "model_assumption"}) == TargetDerivation.UNSUPPORTED
    assert reconcile_target(None) == TargetDerivation.UNRESOLVED
    share = m("issued_shares_current", 3381330240, unit=Unit.SHARES,
              share_count_type=ShareCountType.ISSUED_SHARES_CURRENT)
    result = run_preflight("JBL.JO", REPORT, [c(share, "current_issued_shares")], [share],
                           current_price="0.45", target_price="1.70",
                           target_assumption={"classification": "previous_report"})
    assert result["enhanced_target_review"]["severity"] == "ERROR"
    assert result["enhanced_target_review"]["requires_reconciliation"] is True
    assert result["target_reconciliation"] == "carried_forward"
    assert any(x["code"] == "HIGH_UPSIDE_REVIEW" for x in result["warnings"])


def test_jubilee_legacy_preflight_regression():
    fixture = Path(__file__).parent / "fixtures/jubilee_phase2_metrics.json"
    disclosure = [FinancialMetric.model_validate(x) for x in json.loads(fixture.read_text(encoding="utf-8"))]
    old = json.loads((Path(__file__).resolve().parents[4] / "tmp/jubilee_phase1_audit.json").read_text(encoding="utf-8"))
    from modules.analysis.metric_extraction import structure_report_metrics
    legacy, _ = structure_report_metrics("JBL.JO", old["report_id"], old["audit"])
    by_name = {x.name: x for x in legacy}
    report_id = old["report_id"]
    selected = [
        candidate(disclosure[0], report_id, "production_volume", "base", "Roan FY2027 guidance midpoint"),
        candidate(disclosure[1], report_id, "mining_throughput", "bull", "Molefe ROM target"),
        candidate(disclosure[2], report_id, "production_volume", "informational", "Molefe indicated copper"),
        candidate(disclosure[3], report_id, "production_volume", "informational", "FY2026 pre-refining"),
        candidate(disclosure[4], report_id, "saleable_volume", "informational", "FY2026 cathode"),
        candidate(by_name["production_unresolved"], report_id, "production_volume", "base", "Legacy report input"),
        candidate(by_name["production_cost_per_tonne"], report_id, "aisc", "base", "Legacy report AISC claim"),
        candidate(disclosure[5], report_id, "current_issued_shares", "base", "Old issued share comparison"),
        candidate(disclosure[6], report_id, "current_issued_shares", "base", "New issued shares"),
        candidate(disclosure[8], report_id, "production_cost", "informational", "Newer disclosed cost reference"),
        candidate(by_name["wacc"], report_id, "wacc", "base", "Legacy unsupported WACC"),
        candidate(by_name["growth"], report_id, "production_growth", "base", "Ambiguous growth"),
        candidate(by_name["exit_multiple"], report_id, "exit_multiple", "base", "Legacy multiple"),
    ]
    target = next(x for x in old["audit"]["assumptions"] if x["assumption"] == "target_price")
    result = run_preflight("JBL.JO", report_id, selected, legacy + disclosure,
                           current_price="0.45", target_price="1.70", target_assumption=target)
    assert result["status"] == "FAIL" and result["target_reconciliation"] == "carried_forward"
    assert result["enhanced_target_review"]["requires_reconciliation"]
    statuses = {(x["candidate"]["valuation_field"], x["candidate"]["selected_value"]): x["candidate"]["validation_status"]
                for x in result["all_candidates"]}
    assert statuses[("production_volume", "3000")] == "eligible"
    assert statuses[("mining_throughput", "120000")] == "eligible_with_warning"
    assert statuses[("production_volume", "12000")] in {"unresolved", "ineligible"}
    assert statuses[("aisc", "5950")] in {"unresolved", "ineligible"}
    assert statuses[("current_issued_shares", "3146295996")] == "ineligible"
    assert statuses[("current_issued_shares", "3381330240")] == "eligible_with_warning"


def test_guidance_hierarchy_and_growth_thresholds():
    formal = m("production_contained_metal", 3000, unit=Unit.TONNES_CONTAINED_METAL,
               production_stage=ProductionStage.CONTAINED_METAL, commodity="copper",
               operation_segment="Roan", assumption_type=AssumptionType.FORMAL_GUIDANCE)
    model = m("production_contained_metal", 3900, unit=Unit.TONNES_CONTAINED_METAL,
              production_stage=ProductionStage.CONTAINED_METAL, commodity="copper",
              operation_segment="Roan", assumption_type=AssumptionType.MODEL_ASSUMPTION)
    model_decision, _ = validate_candidate(c(model, "production_volume"), [formal, model])
    assert "GUIDANCE_PREFERRED" in codes(model_decision)
    assert "PRODUCTION_GROWTH_ELEVATED" in codes(model_decision)
    target = model.model_copy(update={"metric_id": uuid4(), "value": Decimal(4800),
                                      "assumption_type": AssumptionType.MANAGEMENT_TARGET})
    target_decision, _ = validate_candidate(c(target, "production_volume"), [formal, target])
    assert "TARGET_VS_GUIDANCE" in codes(target_decision)
    assert "PRODUCTION_GROWTH_HIGH" in codes(target_decision)
    assert target_decision.validation_status == Eligibility.INELIGIBLE


def test_forecast_dilution_preferred_and_controlled_case():
    issued = m("issued_shares_current", 3381330240, unit=Unit.SHARES,
               share_count_type=ShareCountType.ISSUED_SHARES_CURRENT,
               assumption_type=AssumptionType.HISTORICAL_ACTUAL)
    forecast = m("forecast_diluted_shares", 3500000000, unit=Unit.SHARES,
                 share_count_type=ShareCountType.FORECAST_DILUTED_SHARES,
                 assumption_type=AssumptionType.MODEL_ASSUMPTION)
    decision, _ = validate_candidate(c(issued, "current_issued_shares"), [issued, forecast])
    assert "FORECAST_DILUTION_AVAILABLE" in codes(decision)
    assert decision.validation_status == Eligibility.INELIGIBLE
    forward, _ = validate_candidate(c(forecast, "forecast_diluted_shares"), [issued, forecast])
    assert forward.validation_status == Eligibility.ELIGIBLE
    with pytest.raises(ValidationError):
        c(issued, "current_issued_shares", "hero")


def test_auto_proposals_remain_python_eligible_only():
    from modules.analysis.valuation_preflight import propose_report_candidates
    unresolved = m("production_unresolved", 12000, assumption_type=AssumptionType.UNRESOLVED)
    target = m("target_price", Decimal("1.70"), unit=Unit.ZAR,
               assumption_type=AssumptionType.PREVIOUS_REPORT)
    proposals, unmapped = propose_report_candidates([unresolved, target], REPORT)
    assert len(proposals) == 1 and not unmapped
    result = run_preflight("JBL.JO", REPORT, proposals, [unresolved, target],
                           current_price="0.45", target_price="1.70",
                           target_assumption={"classification": "previous_report"})
    assert result["status"] == "FAIL"
    assert proposals[0].validation_status == Eligibility.UNRESOLVED
    assert result["ineligible_inputs"][0]["candidate"]["validation_status"] == "unresolved"


def test_upside_over_100_below_200_is_warning_only():
    share = m("issued_shares_current", 3381330240, unit=Unit.SHARES,
              share_count_type=ShareCountType.ISSUED_SHARES_CURRENT,
              assumption_type=AssumptionType.HISTORICAL_ACTUAL)
    result = run_preflight("JBL.JO", REPORT, [c(share, "current_issued_shares")], [share],
                           current_price="1", target_price="2.5")
    assert result["enhanced_target_review"]["severity"] == "WARNING"
    assert not result["enhanced_target_review"]["requires_reconciliation"]


def test_formal_guidance_is_not_replaced_by_newer_actual():
    guidance = m("production_contained_metal", 3000, unit=Unit.TONNES_CONTAINED_METAL,
                 production_stage=ProductionStage.CONTAINED_METAL,
                 assumption_type=AssumptionType.FORMAL_GUIDANCE,
                 source_type=SourceType.COMPANY_DISCLOSURE, source_date=date(2026, 1, 1))
    actual = m("production_contained_metal", 2000, unit=Unit.TONNES_CONTAINED_METAL,
               production_stage=ProductionStage.CONTAINED_METAL,
               assumption_type=AssumptionType.HISTORICAL_ACTUAL,
               source_type=SourceType.COMPANY_DISCLOSURE, source_date=date(2026, 6, 1))
    assert freshness(guidance, [guidance, actual])["freshness_status"] == "current"


def test_unknown_raw_unit_blocks_conversion():
    price = m("commodity_price", 6.21, currency="USD", raw_unit="mystery/lb",
              assumption_type=AssumptionType.MODEL_ASSUMPTION)
    decision, _ = validate_candidate(c(price, "commodity_price"), [price])
    assert "UNRESOLVED_CONVERSION" in codes(decision)
    assert decision.validation_status == Eligibility.INELIGIBLE


def test_margin_warning_only_with_supplied_comparators():
    margin = m("operating_margin", 40, unit=Unit.PERCENTAGE,
               assumption_type=AssumptionType.MODEL_ASSUMPTION)
    plain, _ = validate_candidate(c(margin, "operating_margin"), [margin])
    assert "MARGIN_OPTIMISM" not in codes(plain)
    elevated, _ = validate_candidate(c(margin, "operating_margin"), [margin],
                                     margin_history=Decimal(25), margin_guidance=Decimal(28),
                                     peer_margin_range=(Decimal(20), Decimal(30)))
    assert "MARGIN_OPTIMISM" in codes(elevated)


def test_configurable_production_growth_thresholds():
    actual = m("production_contained_metal", 1000, unit=Unit.TONNES_CONTAINED_METAL,
               production_stage=ProductionStage.CONTAINED_METAL,
               assumption_type=AssumptionType.HISTORICAL_ACTUAL, commodity="copper")
    forecast = m("production_contained_metal", 1200, unit=Unit.TONNES_CONTAINED_METAL,
                 production_stage=ProductionStage.CONTAINED_METAL,
                 assumption_type=AssumptionType.MODEL_ASSUMPTION, commodity="copper")
    ordinary, _ = validate_candidate(c(forecast, "production_volume"), [actual, forecast])
    strict, _ = validate_candidate(c(forecast, "production_volume"), [actual, forecast],
                                   guidance_warn=Decimal("1.10"), guidance_error=Decimal("1.15"))
    assert "PRODUCTION_GROWTH_ELEVATED" not in codes(ordinary)
    assert "PRODUCTION_GROWTH_HIGH" in codes(strict)
