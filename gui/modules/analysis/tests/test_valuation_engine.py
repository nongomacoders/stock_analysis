"""Phase 4 deterministic arithmetic, input gate, and Jubilee preservation."""
import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from modules.analysis.financial_metrics import (AssumptionType, CostDefinition, FinancialMetric,
    ProductionStage, ShareCountType, SourceType, Unit)
from modules.analysis.valuation_preflight import candidate
from modules.analysis.valuation.models import Basis, InputRef, TerminalMethod, ValuationStatus
from modules.analysis.valuation.production import ProductionBridge, DevelopmentPeriod, bridge_production, development_production
from modules.analysis.valuation.revenue import commodity_revenue
from modules.analysis.valuation.costs import CostSchedule, cost_bridge
from modules.analysis.valuation.earnings import earnings_bridge, per_share_earnings
from modules.analysis.valuation.cashflow import unlevered_fcf
from modules.analysis.valuation.wacc import WaccInputs, calculate_wacc
from modules.analysis.valuation.dcf import ForecastYear, DcfInputs, calculate_dcf
from modules.analysis.valuation.sotp import SotpComponent, calculate_sotp
from modules.analysis.valuation.deferred_payments import DeferredPayment, present_value_payment, value_payment_scenarios
from modules.analysis.valuation.reconciliation import reconcile_equity, recalculate_target
from modules.analysis.valuation.sensitivity import dcf_sensitivity
from modules.analysis.valuation.engine import (CasePlan, ComponentSpec, DcfSpec, EquitySpec,
    SotpSpec, ValuationPlan, WaccSpec, YearInputSpec, run_valuation, render_valuation_result)

RID = uuid4()
D = lambda x: Decimal(str(x))


def test_rom_grade_recovery_saleable_and_no_double_count():
    bridge = ProductionBridge(period_start=date(2027, 1, 1), period_end=date(2027, 12, 31),
        operation_id="mine", commodity="copper", rom_tonnes=100000, grade=D("0.02"),
        recovery=D("0.80"), processing_conversion=D("0.90"), ownership=D("0.75"))
    out = bridge_production(bridge)
    assert out["contained_tonnes"] == 2000
    assert out["recovered_tonnes"] == 1600
    assert out["saleable_tonnes"] == 1440
    assert out["attributable_saleable_tonnes"] == 1080
    with pytest.raises(ValidationError):
        bridge.model_copy(update={"contained_tonnes_direct": 2000}).model_validate(
            {**bridge.model_dump(), "contained_tonnes_direct": 2000})
    direct = ProductionBridge(period_start=date(2027, 1, 1), period_end=date(2027, 12, 31),
        operation_id="roan", commodity="copper", contained_tonnes_direct=3000,
        recovery=D("0.8"), processing_conversion=D("0.9"))
    assert bridge_production(direct)["saleable_tonnes"] == 2160


def test_development_start_date_and_ramp_up():
    x = DevelopmentPeriod(period_start=date(2027, 1, 1), period_end=date(2027, 12, 31),
        start_date=date(2027, 7, 1), annual_nameplate_rom_tonnes=120000,
        utilization=D("0.8"), ramp_up=D("0.5"), grade=D("0.02"), recovery=D("0.8"),
        processing_conversion=D("0.9"), ownership=D("0.75"))
    out = development_production(x)
    assert out["active_days"] == 184
    assert out["rom_tonnes"] < 120000 * D("0.8") * D("0.5")
    assert out["attributable_saleable_tonnes"] < out["saleable_tonnes"]


def test_revenue_cost_earnings_cashflow_and_heps_gate():
    revenue = commodity_revenue(saleable_tonnes=D(100), benchmark_usd_per_tonne=D(10000),
                                realization_factor=D("0.9"), payability=D("0.95"),
                                treatment_charge_usd_per_tonne=D(100))
    assert revenue["realized_price"] == 8450 and revenue["revenue"] == 845000
    costs = cost_bridge(CostSchedule(mining=100, processing=200, refining=50, transport=10,
                                     treatment=20, royalties=30, corporate=40, sustaining_capex=25))
    assert costs["operating_cost"] == 410
    assert costs["reported_aisc_crosscheck"] is None
    with pytest.raises(ValueError):
        cost_bridge(CostSchedule(reported_aisc=500))
    earnings = earnings_bridge(revenue=D(1000), operating_cost=D(400), corporate_cost=D(100),
        depreciation=D(100), net_finance_cost=D(20), tax_rate=D("0.25"))
    assert earnings["ebitda"] == 500 and earnings["ebit"] == 400
    assert earnings["attributable_earnings"] == 285
    cash = unlevered_fcf(ebit=D(400), tax_rate=D("0.25"), depreciation=D(100),
                          sustaining_capex=D(50), growth_capex=D(25), working_capital_change=D(10))
    assert cash["unlevered_fcf"] == 315
    eps = per_share_earnings(attributable_earnings=D(285), weighted_average_shares=D(100))
    assert eps["eps"] == D("2.85") and eps["heps_status"] == "HEPS_NOT_CALCULABLE"
    assert per_share_earnings(attributable_earnings=D(285), weighted_average_shares=D(100),
                              headline_adjustments=D(15))["heps"] == 3


def simple_dcf(terminal_method=TerminalMethod.PERPETUITY_GROWTH):
    year = ForecastYear(period_end=date(2027, 12, 31), revenue=1000, ebitda=500, ebit=400,
        tax=100, sustaining_capex=50, growth_capex=25, working_capital_change=10,
        depreciation_addback=100, fcf=315)
    kwargs = dict(valuation_date=date(2026, 12, 31), forecast=[year], wacc=D("0.12"),
        cash_flow_currency="ZAR", discount_rate_currency="ZAR", cash_flow_basis=Basis.NOMINAL,
        discount_rate_basis=Basis.NOMINAL, cash_flow_inflation_basis="ZAR_CPI",
        discount_rate_inflation_basis="ZAR_CPI", terminal_method=terminal_method)
    if terminal_method == TerminalMethod.PERPETUITY_GROWTH:
        kwargs["terminal_growth"] = D("0.03")
    else:
        kwargs["exit_multiple"] = D(6); kwargs["terminal_metric"] = D(500)
    return DcfInputs(**kwargs)


def test_wacc_dcf_discount_and_terminal_alternatives():
    w = calculate_wacc(WaccInputs(risk_free_rate=D("0.05"), equity_risk_premium=D("0.06"),
        beta=1, country_risk_premium=D("0.02"), cost_of_debt=D("0.08"),
        tax_rate=D("0.25"), debt_weight=D("0.2"), equity_weight=D("0.8"),
        currency="ZAR", basis=Basis.NOMINAL, inflation_basis="ZAR_CPI"))
    assert w["cost_of_equity"] == D("0.13") and w["wacc"] == D("0.116")
    growth = calculate_dcf(simple_dcf())
    exit_value = calculate_dcf(simple_dcf(TerminalMethod.EXIT_MULTIPLE))
    assert growth.value != exit_value.value
    assert len(growth.schedule) == 2
    assert D(growth.schedule[0]["discount_factor"]) < 1
    assert growth.schedule[-1]["terminal"]["method"] == "perpetuity_growth"
    assert exit_value.schedule[-1]["terminal"]["method"] == "exit_multiple"
    with pytest.raises(ValidationError):
        simple_dcf().model_copy(update={"terminal_growth": D("0.2")}).model_validate(
            {**simple_dcf().model_dump(), "terminal_growth": D("0.2")})
    with pytest.raises(ValidationError):
        DcfInputs(**{**simple_dcf().model_dump(), "discount_rate_currency": "USD"})
    with pytest.raises(ValidationError):
        DcfInputs(**{**simple_dcf().model_dump(), "exit_multiple": D(6)})


def test_sotp_ownership_probability_payment_pv_and_boundaries():
    today = date(2026, 12, 31)
    c = SotpComponent(component_id="mine", name="Mine", boundary_id="asset:m",
        method="project_dcf", gross_value=1000, currency="ZAR", valuation_date=today,
        ownership=D("0.8"), probability=D("0.5"), risk_basis="Permitting")
    result = calculate_sotp([c], currency="ZAR", valuation_date=today)
    assert result.value == 400
    assert D(result.schedule[0]["gross_attributable"]) == 800
    with pytest.raises(ValueError):
        calculate_sotp([c, c], currency="ZAR", valuation_date=today)
    proceeds = SotpComponent(component_id="sale", name="Sale", boundary_id="payment:m",
        method="payment_pv", gross_value=500, currency="ZAR", valuation_date=today,
        ownership=1, value_kind="disposal_proceeds", disposed_boundary_id="asset:m")
    with pytest.raises(ValueError):
        calculate_sotp([c, proceeds], currency="ZAR", valuation_date=today)
    payment = DeferredPayment(payment_id="p1", amount=35, currency="USD",
        expected_date=date(2028, 12, 31), discount_rate=D("0.1"),
        completion_probability=D("0.8"), settlement_scenario="staged")
    pv = present_value_payment(payment, today)
    assert pv < 35 and pv > 0
    alternative = payment.model_copy(update={"payment_id": "p2", "settlement_scenario": "accelerated"})
    scenarios = value_payment_scenarios([payment, alternative], today)
    assert len(scenarios) == 2 and scenarios["staged"]["present_value"] == pv


def test_equity_reconciliation_zar_cents_rounding_and_tamper_detection():
    mid = uuid4()
    r = reconcile_equity(enterprise_or_operating_value=D(1000), non_operating_assets=D(100),
        receivables=D(50), cash=D(20), debt=D(100), lease_adjustments=D(10),
        minorities=D(20), other_equity_adjustments=D(-40), forward_shares=D(100), shares_metric_id=mid)
    assert r.equity_value == 1000 and r.rounded_target_zar == 10
    assert r.rounded_target_cents == 1000
    from modules.analysis.valuation.models import ValuationResult
    result = ValuationResult(ticker="TEST.JO", report_version_id=RID, valuation_date=date.today(),
        status=ValuationStatus.PASS, target_price=10, reconciliation=r)
    assert recalculate_target(result) == 10
    result.target_price = 11
    with pytest.raises(ValueError):
        recalculate_target(result)


def test_sensitivity_recalculates_without_changing_base():
    base = simple_dcf()
    original = calculate_dcf(base).value
    result = dcf_sensitivity(base, wacc_values=[D("0.1"), D("0.12")],
        growth_values=[D("0.02"), D("0.03")], commodity_price_factors=[D("0.9"), D(1)],
        production_factors=[D(1)], operating_cost_factors=[D(1)], fx_factors=[D(1)])
    assert len(result["wacc_terminal_growth"]) == 4
    assert len({x["value"] for x in result["wacc_terminal_growth"]}) == 4
    assert result["operating_factors"][0]["value"] != str(original)
    assert calculate_dcf(base).value == original
    with pytest.raises(ValueError):
        dcf_sensitivity(base, wacc_values=[D("0.12")], growth_values=[D("0.03")], fx_factors=[D("1.1")])


def funded(field, value, *, unit=Unit.ZAR, currency="ZAR", name=None, case="base", **kwargs):
    if field == "current_issued_shares":
        name = "issued_shares_current"; unit=Unit.SHARES; currency=None
        kwargs["share_count_type"] = ShareCountType.ISSUED_SHARES_CURRENT
        kwargs["assumption_type"] = AssumptionType.HISTORICAL_ACTUAL
    if field == "operating_cost":
        kwargs["cost_definition"] = CostDefinition.OPERATING_COST
        kwargs["period_start"] = date(2027, 1, 1); kwargs["period_end"] = date(2027, 12, 31)
    metric = FinancialMetric(ticker="TEST.JO", report_id=RID, name=name or field,
        value=D(value), unit=unit, currency=currency, source="Approved source schedule",
        source_type=SourceType.COMPANY_DISCLOSURE,
        assumption_type=kwargs.pop("assumption_type", AssumptionType.MODEL_ASSUMPTION),
        notes="Documented synthetic test input", evidence_verified=True,
        evidence_quote="Synthetic source excerpt", source_id="synthetic:test", **kwargs)
    return metric, candidate(metric, RID, field, case, "Explicit synthetic test plan")


def ref(c):
    return InputRef(metric_id=c.metric_id, field=c.valuation_field.value, case=c.case_type.value)


def synthetic_sotp():
    pairs=[]
    def add(field,value,**kw):
        pair=funded(field,value,**kw);pairs.append(pair);return ref(pair[1])
    gross=add("asset_value",1000)
    ownership=add("ownership_percentage",80,unit=Unit.PERCENTAGE,currency=None)
    probability=add("probability",50,unit=Unit.PERCENTAGE,currency=None)
    share=add("current_issued_shares",100)
    adjustments={f:add(f,0) for f in ("non_operating_assets","receivables","net_cash","net_debt",
                                      "lease_adjustments","minorities","other_equity_adjustments")}
    component=ComponentSpec(component_id="mine",name="Mine",boundary_id="mine:1",method="project_npv",
        gross_value=gross,ownership=ownership,probability=probability,currency="ZAR",
        valuation_date=date(2026,12,31),risk_basis="Permitting")
    plan=ValuationPlan(ticker="TEST.JO",report_version_id=RID,valuation_date=date(2026,12,31),
        cases={"base":CasePlan(rationale="Explicit sourced scenario",primary_method="SOTP",
            sotp=SotpSpec(components=[component]),equity=EquitySpec(adjustments=adjustments,shares=share))})
    return plan,[p[0] for p in pairs],[p[1] for p in pairs]


def test_guarded_engine_sotp_reconciles_and_current_shares_warn():
    plan,metrics,candidates=synthetic_sotp()
    result=run_valuation(ticker="TEST.JO",report_version_id=RID,candidates=candidates,
                         metrics=metrics,plan=plan)
    assert result.status == ValuationStatus.PASS_WITH_WARNINGS
    assert result.target_price == 4
    assert result.reconciliation.equity_value == 400
    assert recalculate_target(result) == 4
    assert "Deterministic target: ZAR 4.00" in render_valuation_result(result)
    assert result.legacy_gemini_target is None
    assert result.valuation_engine_version == "1.0"


def test_engine_refuses_ineligible_blocking_and_missing():
    plan,metrics,candidates=synthetic_sotp()
    missing=run_valuation(ticker="TEST.JO",report_version_id=RID,candidates=candidates[:-1],
                          metrics=metrics,plan=plan)
    assert missing.status == ValuationStatus.NOT_CALCULABLE and missing.target_price is None
    bad_metric=metrics[0].model_copy(update={"assumption_type":AssumptionType.UNRESOLVED})
    bad_candidate=candidate(bad_metric,RID,"asset_value","base","Unresolved")
    blocked=run_valuation(ticker="TEST.JO",report_version_id=RID,
        candidates=[bad_candidate]+candidates[1:],metrics=[bad_metric]+metrics[1:],plan=plan)
    assert blocked.status == ValuationStatus.FAIL and blocked.target_price is None
    # A BLOCKING share-basis conflict stays ineligible even with an override.
    share_idx=next(i for i,c in enumerate(candidates) if c.valuation_field.value=="current_issued_shares")
    from modules.analysis.financial_metrics import ShareCountType
    wrong=metrics[share_idx].model_copy(update={"share_count_type":ShareCountType.WEIGHTED_AVERAGE_BASIC_SHARES,
                                          "name":"weighted_average_basic_shares"})
    wrong_candidate=candidate(wrong,RID,"current_issued_shares","base","Wrong denominator")
    invalid=run_valuation(ticker="TEST.JO",report_version_id=RID,
        candidates=candidates[:share_idx]+[wrong_candidate]+candidates[share_idx+1:],
        metrics=metrics[:share_idx]+[wrong]+metrics[share_idx+1:],plan=plan)
    assert invalid.status == ValuationStatus.FAIL and invalid.target_price is None


def test_jubilee_no_forced_target_and_legacy_preserved():
    old=json.loads((Path(__file__).resolve().parents[4]/"tmp/jubilee_phase1_audit.json").read_text(encoding="utf-8"))
    fixture=json.loads((Path(__file__).parent/"fixtures/jubilee_phase2_metrics.json").read_text(encoding="utf-8"))
    metrics=[FinancialMetric.model_validate(x) for x in fixture]
    current=metrics[6]
    result=run_valuation(ticker="JBL.JO",report_version_id=old["report_id"],
        candidates=[candidate(metrics[0],old["report_id"],"production_volume","base","Roan guidance"),
                    candidate(current,old["report_id"],"current_issued_shares","base","Current shares")],
        metrics=metrics,plan=None,valuation_date=date(2026,9,18),
        legacy_gemini_target=D("1.70"),legacy_target_derivation="carried_forward")
    assert result.status == ValuationStatus.NOT_CALCULABLE
    assert result.target_price is None and result.legacy_gemini_target == D("1.70")
    assert "Historical Gemini target (not used): ZAR 1.70" in render_valuation_result(result)


def test_guarded_dcf_builds_forecast_from_eligible_candidate_refs():
    pairs=[]
    def add(field,value,**kw):
        pair=funded(field,value,**kw);pairs.append(pair);return ref(pair[1])
    year={}
    values={"revenue":1000,"operating_cost":400,"corporate_cost":100,"depreciation":100,
            "net_finance_cost":20,"tax_rate":25,"sustaining_capex":50,"growth_capex":25,
            "working_capital":10,"other_recurring_cash":0}
    for field,value in values.items():
        year[field]=add(field,value,unit=Unit.PERCENTAGE if field=="tax_rate" else Unit.ZAR,
                        currency=None if field=="tax_rate" else "ZAR")
    wacc={}
    for field,value in {"risk_free_rate":5,"equity_risk_premium":6,"beta":1,
                        "country_risk_premium":2,"cost_of_debt":8,"tax_rate":25,
                        "debt_weight":20,"equity_weight":80}.items():
        # Tax rate may have separate finance and operating provenance.
        wacc[field]=add(field,value,unit=Unit.MULTIPLE if field=="beta" else Unit.PERCENTAGE,
                        currency="ZAR" if field in {"risk_free_rate","cost_of_debt"} else None)
    growth=add("terminal_growth",3,unit=Unit.PERCENTAGE,currency=None)
    share=add("current_issued_shares",100)
    adjustments={f:add(f,0) for f in ("non_operating_assets","receivables","net_cash","net_debt",
                                      "lease_adjustments","minorities","other_equity_adjustments")}
    dcf=DcfSpec(valuation_date=date(2026,12,31),
        years=[YearInputSpec(period_end=date(2027,12,31),inputs=year)],
        cash_flow_currency="ZAR",cash_flow_basis=Basis.NOMINAL,inflation_basis="ZAR_CPI",
        wacc=WaccSpec(currency="ZAR",basis=Basis.NOMINAL,inflation_basis="ZAR_CPI",components=wacc),
        terminal_method=TerminalMethod.PERPETUITY_GROWTH,terminal_growth=growth)
    plan=ValuationPlan(ticker="TEST.JO",report_version_id=RID,valuation_date=date(2026,12,31),
        cases={"base":CasePlan(rationale="Explicit synthetic forecast",primary_method="DCF",
            dcf=dcf,equity=EquitySpec(adjustments=adjustments,shares=share))})
    result=run_valuation(ticker="TEST.JO",report_version_id=RID,
        candidates=[p[1] for p in pairs],metrics=[p[0] for p in pairs],plan=plan)
    assert result.status == ValuationStatus.PASS_WITH_WARNINGS
    assert result.methods["DCF"].status.value == "PASS"
    assert result.methods["SOTP"].status.value == "NOT_CALCULABLE"
    assert result.target_price is not None and recalculate_target(result)==result.target_price
    assert result.methods["DCF"].schedule[0]["growth_capex"] == "25"
    assert result.methods["DCF"].schedule[-1]["terminal"]["method"] == "perpetuity_growth"
    # Removing one cash-flow candidate makes the method, not the legacy target, unavailable.
    no_capex=[p[1] for p in pairs if p[1].metric_id != year["growth_capex"].metric_id]
    missing=run_valuation(ticker="TEST.JO",report_version_id=RID,
        candidates=no_capex,metrics=[p[0] for p in pairs],plan=plan)
    assert missing.status == ValuationStatus.NOT_CALCULABLE and missing.target_price is None
    historical_metric, historical_candidate = funded("revenue", 100, case="informational")
    plan.historical_calibration["revenue"] = ref(historical_candidate)
    calibrated = run_valuation(ticker="TEST.JO", report_version_id=RID,
        candidates=[p[1] for p in pairs] + [historical_candidate],
        metrics=[p[0] for p in pairs] + [historical_metric], plan=plan)
    assert any("Forecast revenue differs by >2x" in warning for warning in calibrated.warnings)
    assert "ev_ebitda" in calibrated.implied_checks
    assert "fcf_yield" in calibrated.implied_checks


def test_new_gemini_prompt_cannot_publish_a_numeric_target():
    from scripts import generate_deepresearch_from_results as generator
    template=(Path(generator.GUI_ROOT)/"prompts/commodity_prompt.txt").read_text(encoding="utf-8")
    prompt=generator._build_llm_prompt(template,ticker="JBL.JO",price=45,payload="Source")
    assert "Report target price: <Your calculated" not in prompt
    assert "HEPS = [(Spot Price - AISC)" not in prompt
    assert "Python alone calculates valuation" in prompt
    assert generator._contains_gemini_target("Report target price: ZAR 1.70")
    assert generator._contains_gemini_target("Target price: ZAR 1.70")
    assert generator._contains_gemini_target("Our target price is ZAR 1.70")
    assert not generator._contains_gemini_target("Deterministic target price: NOT_CALCULABLE")


def test_post_python_narrative_is_read_only():
    from modules.analysis.valuation.narrative import build_valuation_narrative_prompt
    result=run_valuation(ticker="JBL.JO",report_version_id=RID,candidates=[],metrics=[],plan=None)
    text=build_valuation_narrative_prompt(result)
    assert "Do not change, recalculate, replace or infer alternative target prices" in text
    assert '"status": "NOT_CALCULABLE"' in text


def test_sotp_fx_is_explicit_and_probability_cannot_double_risk():
    plan,metrics,candidates=synthetic_sotp()
    component=plan.cases["base"].sotp.components[0]
    with pytest.raises(ValidationError):
        SotpComponent(component_id="risky",name="Project",boundary_id="p",method="DCF",
            gross_value=100,currency="ZAR",valuation_date=date(2026,12,31),
            ownership=1,probability=D("0.5"),risk_basis="development",
            risk_in_discount_rate=True)
    usd_gross,usd_c=funded("asset_value",1000,unit=Unit.USD,currency="USD")
    fx_metric,fx_c=funded("fx_rate",17,unit=Unit.MULTIPLE,currency=None)
    component.gross_value=ref(usd_c)
    component.currency="USD"
    component.fx_rate=ref(fx_c)
    component.fx_pair="USDZAR"
    candidates=[c for c in candidates if c.valuation_field.value!="asset_value"]+[usd_c,fx_c]
    metrics=[m for m in metrics if m.name!="asset_value"]+[usd_gross,fx_metric]
    result=run_valuation(ticker="TEST.JO",report_version_id=RID,candidates=candidates,metrics=metrics,plan=plan)
    assert result.status==ValuationStatus.PASS_WITH_WARNINGS
    assert result.reconciliation.enterprise_or_operating_value == 6800
    assert result.target_price == 68
    component.fx_pair=None
    missing=run_valuation(ticker="TEST.JO",report_version_id=RID,candidates=candidates,metrics=metrics,plan=plan)
    assert missing.status==ValuationStatus.NOT_CALCULABLE


def test_case_differences_capture_explicit_bull_input_lineage():
    plan,metrics,candidates=synthetic_sotp()
    import copy
    base=plan.cases["base"]
    bull=copy.deepcopy(base)
    bull.rationale="Explicit improved asset-value scenario"
    bull_refs={}
    bull_metrics=[];bull_candidates=[]
    for metric,original in zip(metrics,candidates):
        new_metric=metric.model_copy(update={"metric_id":uuid4(),
            "value":metric.value + 200 if original.valuation_field.value=="asset_value" else metric.value})
        new_candidate=candidate(new_metric,RID,original.valuation_field,"bull","Bull source-backed case")
        bull_metrics.append(new_metric);bull_candidates.append(new_candidate)
        bull_refs[original.metric_id]=ref(new_candidate)
    bull.sotp.components[0].gross_value=bull_refs[bull.sotp.components[0].gross_value.metric_id]
    bull.sotp.components[0].ownership=bull_refs[bull.sotp.components[0].ownership.metric_id]
    bull.sotp.components[0].probability=bull_refs[bull.sotp.components[0].probability.metric_id]
    bull.equity.shares=bull_refs[bull.equity.shares.metric_id]
    bull.equity.adjustments={name:bull_refs[r.metric_id] for name,r in bull.equity.adjustments.items()}
    plan.cases["bull"]=bull
    result=run_valuation(ticker="TEST.JO",report_version_id=RID,
        candidates=candidates+bull_candidates,metrics=metrics+bull_metrics,plan=plan)
    assert result.cases["bull"]["status"]=="PASS"
    assert result.cases["bull"]["target_price_zar"] != result.cases["base"]["target_price_zar"]
    diff=next(x for x in result.case_differences if x["valuation_field"]=="asset_value")
    assert diff["cases"]["base"][0]["value"]=="1000"
    assert diff["cases"]["bull"][0]["value"]=="1200"
    assert diff["cases"]["bull"][0]["eligibility"] in {"eligible","eligible_with_warning"}


def test_operational_dcf_revenue_bridge_uses_saleable_units_and_explicit_fx():
    from modules.analysis.valuation.engine import OperationalRevenueSpec, Resolver, _operational_revenue, MissingInput, IneligibleInput
    from modules.analysis.financial_metrics import CommodityPriceType
    pairs=[]
    def add(field,value,**kw):
        pair=funded(field,value,**kw);pairs.append(pair);return ref(pair[1])
    contained=add("production_volume",3000,name="production_contained_metal",
        unit=Unit.TONNES_CONTAINED_METAL,currency=None,commodity="copper",
        production_stage=ProductionStage.CONTAINED_METAL,
        assumption_type=AssumptionType.FORMAL_GUIDANCE)
    recovery=add("recovery",80,unit=Unit.PERCENTAGE,currency=None)
    conversion=add("processing_conversion",90,unit=Unit.PERCENTAGE,currency=None)
    ownership=add("ownership_percentage",100,unit=Unit.PERCENTAGE,currency=None)
    price=add("commodity_price",10000,unit=Unit.USD_PER_TONNE,currency="USD",commodity="copper",
              price_type=CommodityPriceType.ANALYST_FORECAST)
    realization=add("realization_factor",90,unit=Unit.PERCENTAGE,currency=None)
    payability=add("payability",95,unit=Unit.PERCENTAGE,currency=None)
    treatment=add("treatment_charge",100,unit=Unit.USD_PER_TONNE,currency="USD")
    fx=add("fx_rate",17,unit=Unit.MULTIPLE,currency=None)
    resolver=Resolver([x[1] for x in pairs],[x[0] for x in pairs],RID)
    spec=OperationalRevenueSpec(operation_id="Roan",commodity="copper",
        period_start=date(2027,1,1),production_stage="contained_metal",volume=contained,
        recovery=recovery,processing_conversion=conversion,ownership=ownership,
        commodity_price=price,realization_factor=realization,payability=payability,
        treatment_charge=treatment,fx_rate=fx,fx_pair="USDZAR")
    revenue,schedule=_operational_revenue(spec,date(2027,12,31),resolver,"base","ZAR")
    assert schedule["production"]["saleable_tonnes"] == "2160.00"
    assert revenue == 2160 * 8450 * 17
    spec.recovery=None
    with pytest.raises(MissingInput):
        _operational_revenue(spec,date(2027,12,31),resolver,"base","ZAR")
    spec.recovery=recovery
    price_metric=next(x[0] for x in pairs if x[1].valuation_field.value=="commodity_price")
    price_metric.price_type=CommodityPriceType.CURRENT_SPOT
    with pytest.raises(IneligibleInput):
        _operational_revenue(spec,date(2029,12,31),resolver,"base","ZAR")


def test_monthly_rom_target_needs_ramp_and_historical_cost_is_not_forecast():
    from modules.analysis.valuation.engine import OperationalRevenueSpec, Resolver, _operational_revenue, MissingInput, IneligibleInput
    from modules.analysis.financial_metrics import CommodityPriceType
    rom_metric=FinancialMetric(ticker="TEST.JO",report_id=RID,name="production_rom_feed",value=10000,
        unit=Unit.TONNES_ROM_PER_MONTH,production_stage=ProductionStage.ROM_FEED,commodity="copper",
        assumption_type=AssumptionType.MANAGEMENT_TARGET,source="Management target")
    rom_c=candidate(rom_metric,RID,"mining_throughput","bull","Explicit bull-case ROM target")
    price_m=FinancialMetric(ticker="TEST.JO",report_id=RID,name="commodity_price",value=10000,
        unit=Unit.USD_PER_TONNE,currency="USD",commodity="copper",
        price_type=CommodityPriceType.LONG_TERM_NORMALIZED,
        assumption_type=AssumptionType.MODEL_ASSUMPTION,source="Analyst forecast")
    price_c=candidate(price_m,RID,"commodity_price","bull","Explicit forecast price")
    resolver=Resolver([rom_c,price_c],[rom_metric,price_m],RID)
    spec=OperationalRevenueSpec(operation_id="Mine",commodity="copper",period_start=date(2027,1,1),
        production_stage="rom_feed",volume=ref(rom_c),commodity_price=ref(price_c),
        realization_factor=ref(price_c),payability=ref(price_c),treatment_charge=ref(price_c))
    with pytest.raises(MissingInput,match="timing/ramp"):
        _operational_revenue(spec,date(2027,12,31),resolver,"bull","ZAR")
    historical=FinancialMetric(ticker="TEST.JO",report_id=RID,name="corporate_cost",value=100,
        unit=Unit.ZAR,currency="ZAR",period_start=date(2025,1,1),period_end=date(2025,12,31),
        assumption_type=AssumptionType.HISTORICAL_ACTUAL,source="Old financials")
    hc=candidate(historical,RID,"corporate_cost","base","Historical reference")
    r=Resolver([hc],[historical],RID)
    with pytest.raises(IneligibleInput,match="historical actual"):
        r.get(ref(hc),required_case="base",currency="ZAR",forecast_period_start=date(2027,1,1))


def test_engine_feeds_reconciled_high_upside_into_phase3_review():
    plan,metrics,candidates=synthetic_sotp()
    price_metric,price_candidate=funded("current_share_price",1,unit=Unit.ZAR,currency="ZAR")
    plan.market_price=ref(price_candidate)
    result=run_valuation(ticker="TEST.JO",report_version_id=RID,
        candidates=candidates+[price_candidate],metrics=metrics+[price_metric],plan=plan)
    assert result.target_price==4
    assert D(result.preflight["enhanced_target_review"]["implied_upside_pct"])==300
    assert "HIGH_UPSIDE_REVIEW: ERROR" in result.warnings
    assert result.implied_checks["implied_market_cap"]=="400.00"
    assert result.implied_checks["current_market_cap"]=="100"
