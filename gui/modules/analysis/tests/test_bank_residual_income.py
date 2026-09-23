"""Synthetic bank only. No figures here represent Nedbank."""
import sys
from datetime import date
from decimal import Decimal as D
from pathlib import Path
from uuid import uuid4
import pytest
from pydantic import ValidationError
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from modules.analysis.financial_metrics import FinancialMetric, Unit, SourceType, AssumptionType
from modules.analysis.forecast_plan import (ForecastPlan, ForecastPeriod, ForecastAssumption,
    Origin, ApprovalState, approve_plan, compile_plan_inputs, preview_valuation)
from modules.analysis.valuation_preflight import candidate, validate_candidate
from modules.analysis.valuation.bank import BankInputs, BankYear, calculate_residual_income, cost_of_equity, pb_cross_checks
from modules.analysis.valuation.engine import BankSpec, BankYearSpec, CasePlan, ValuationPlan, run_valuation, render_valuation_result
from modules.analysis.valuation.models import InputRef, ValuationStatus
from modules.analysis.valuation.reconciliation import recalculate_target

RID = uuid4()
DAY = date(2026, 12, 31)
TICKER = "SYNTHETIC_BANK.JO"

def pure_input(roe=D(".15"), terminal_roe=D(".12"), growth=D(".04")):
    return BankInputs(valuation_date=DAY, opening_common_equity=D(1000),
        years=[BankYear(period_end=date(2027,12,31), roe=roe, payout_ratio=D(".4")),
               BankYear(period_end=date(2028,12,31), roe=roe, payout_ratio=D(".4"))],
        cost_of_equity=D(".10"), terminal_roe=terminal_roe, terminal_growth=growth)

def fixture(override=False):
    assumptions=[]
    def assumed(field,value,unit,period=None):
        a=ForecastAssumption(field=field,value=D(str(value)),unit=unit.value,
            currency="ZAR" if unit == Unit.ZAR else None, period_label=period,
            origin=Origin.ANALYST_ASSUMPTION, rationale="Synthetic bank scenario; approved input",
            created_by="test analyst",approval_state=ApprovalState.ACCEPTED)
        assumptions.append(a)
        return InputRef(metric_id=a.assumption_id,field=field)
    opening=FinancialMetric(ticker=TICKER,report_id=RID,name="common_equity",value=D(1000),
        unit=Unit.ZAR,currency="ZAR",source="synthetic audited equity",
        source_type=SourceType.COMPANY_DISCLOSURE,assumption_type=AssumptionType.HISTORICAL_ACTUAL,
        source_date=DAY,evidence_verified=True,evidence_quote="Synthetic common equity",
        source_id="synthetic:common_equity")
    equity=InputRef(metric_id=opening.metric_id,field="common_equity")
    bank=BankSpec(opening_common_equity=equity,
        years=[BankYearSpec(period_end=date(2027,12,31),roe=assumed("bank_roe",15,Unit.PERCENTAGE,"FY2027"),
            payout_ratio=assumed("dividend_payout",40,Unit.PERCENTAGE,"FY2027")),
          BankYearSpec(period_end=date(2028,12,31),roe=assumed("bank_roe",15,Unit.PERCENTAGE,"FY2028"),
            payout_ratio=assumed("dividend_payout",40,Unit.PERCENTAGE,"FY2028"))],
        risk_free_rate=assumed("risk_free_rate",5,Unit.PERCENTAGE),
        beta=assumed("beta",1,Unit.MULTIPLE),
        equity_risk_premium=assumed("equity_risk_premium",5,Unit.PERCENTAGE),
        terminal_roe=assumed("bank_terminal_roe",12,Unit.PERCENTAGE),
        terminal_growth=assumed("terminal_growth",4,Unit.PERCENTAGE),
        shares=assumed("forecast_diluted_shares",100,Unit.SHARES))
    if override:
        bank.cost_of_equity_override=assumed("cost_of_equity",11,Unit.PERCENTAGE)
        bank.override_rationale="Synthetic approved cost-of-equity override"
    engine=ValuationPlan(ticker=TICKER,report_version_id=RID,valuation_date=DAY,sector="bank",
        cases={"base":CasePlan(rationale="Synthetic bank residual-income scenario",
            primary_method="RESIDUAL_INCOME",bank=bank)})
    draft=ForecastPlan(ticker=TICKER,created_by="test analyst",source_report_version_id=RID,
        horizon=[ForecastPeriod(label="FY2027",start=date(2027,1,1),end=date(2027,12,31)),
                 ForecastPeriod(label="FY2028",start=date(2028,1,1),end=date(2028,12,31))],
        assumptions=assumptions,engine_plan=engine)
    return approve_plan(draft,"test reviewer"),[opening]

def test_cost_of_equity_and_residual_income_roll_forward():
    assert cost_of_equity(risk_free_rate=D(".05"),beta=D(1),equity_risk_premium=D(".05")) == D(".10")
    result=calculate_residual_income(pure_input())
    assert result.status.value=="PASS"
    first,second,terminal=result.schedule
    assert D(first["earnings"])==150 and D(first["required_earnings"])==100
    assert D(first["residual_income"])==50 and D(first["dividends"])==60
    assert D(first["retained_earnings"])==90 and D(first["closing_common_equity"])==1090
    assert D(second["opening_common_equity"])==1090 and D(second["closing_common_equity"])==D("1188.10")
    assert D(terminal["terminal_residual_income"])==D("23.7620")
    assert D(terminal["pv_forecast_residual_income"])+D(terminal["pv_terminal_residual_income"])+1000==result.value
    negative=calculate_residual_income(pure_input(roe=D(".05"),terminal_roe=D(".05")))
    assert D(negative.schedule[0]["residual_income"])<0 and negative.value<1000

def test_terminal_constraint_and_pb_checks():
    with pytest.raises(ValidationError):
        pure_input(growth=D(".10"))
    pb=pb_cross_checks(equity_value=D(1500),shares=D(100),opening_book_equity=D(1000),
        forecast_book_equity=D(1200),target_pb=D("1.5"),terminal_roe=D(".12"),
        cost_of_equity=D(".10"),growth=D(".04"))
    assert pb["implied_pb"]=="1.5" and pb["target_pb_crosscheck_per_share"]=="18.0"
    assert D(pb["justified_pb_terminal"])==D(".08")/D(".06")

def test_approved_synthetic_bank_target_and_reconciliation():
    plan,evidence=fixture()
    metrics,candidates=compile_plan_inputs(plan,evidence)
    result=preview_valuation(plan,metrics,candidates)
    assert result.status in {ValuationStatus.PASS,ValuationStatus.PASS_WITH_WARNINGS}
    assert result.target_price is not None and recalculate_target(result)==result.target_price
    assert result.reconciliation.opening_common_equity==1000
    assert result.reconciliation.shares==100
    assert result.reconciliation.shares_metric_id==plan.engine_plan.cases["base"].bank.shares.metric_id
    assert result.implied_checks["implied_pb"]
    assert "Opening common equity" in render_valuation_result(result)
    assert "Enterprise/operating value" not in render_valuation_result(result)

def test_historical_roe_and_wacc_rejected():
    old=FinancialMetric(ticker=TICKER,report_id=RID,name="bank_roe",value=D(15),unit=Unit.PERCENTAGE,
        source="synthetic annual report",source_type=SourceType.COMPANY_DISCLOSURE,
        assumption_type=AssumptionType.HISTORICAL_ACTUAL,source_date=DAY,
        evidence_verified=True,evidence_quote="Historical ROE",source_id="synthetic:roe")
    checked,_=validate_candidate(candidate(old,RID,"bank_roe","base","Synthetic historical"),[old])
    assert "HISTORICAL_BANK_RATE_FORWARD" in {w.code for w in checked.warnings}
    assert checked.validation_status.value=="ineligible"
    wacc=old.model_copy(update={"name":"wacc","unit":Unit.PERCENTAGE})
    checked,_=validate_candidate(candidate(wacc,RID,"cost_of_equity","base","Invalid WACC"),[wacc])
    assert "BANK_WACC_MISMATCH" in {w.code for w in checked.warnings}

def test_enterprise_bridge_and_wrong_sector_rejected():
    plan,_=fixture()
    data=plan.engine_plan.model_dump()
    data["cases"]["base"]["equity"]={"adjustments":{},"shares":data["cases"]["base"]["bank"]["shares"]}
    with pytest.raises(ValidationError): ValuationPlan.model_validate(data)
    data=plan.engine_plan.model_dump();data["sector"]="retail"
    with pytest.raises(ValidationError): ValuationPlan.model_validate(data)

def test_nedbank_insufficient_typed_forecast_not_calculable():
    result=run_valuation(ticker="NED.JO",report_version_id=uuid4(),metrics=[],candidates=[],
        missing_input_reasons=["No approved, source-backed bank forecast plan"] )
    assert result.status==ValuationStatus.NOT_CALCULABLE and result.target_price is None


def test_direct_earnings_explicit_dividends_and_capital_warning():
    inputs=BankInputs(valuation_date=DAY,opening_common_equity=D(1000),
        years=[BankYear(period_end=date(2027,12,31),earnings=D(80),dividends=D(90),
                        cet1_ratio=D(".10"))],cost_of_equity=D(".10"),
        terminal_roe=D(".08"),terminal_growth=D(".03"),
        cet1_minimum=D(".11"),cet1_target=D(".12"))
    result=calculate_residual_income(inputs)
    year=result.schedule[0]
    assert D(year["residual_income"])==-20
    assert D(year["retained_earnings"])==-10
    assert D(year["closing_common_equity"])==990
    assert any("forecast CET1 below sourced minimum" in x for x in result.warnings)
    assert any("payout exceeds earnings" in x for x in result.warnings)

def test_serialized_bank_reconciliation_survives_publication_check():
    from modules.analysis.valuation.models import ValuationResult
    plan,evidence=fixture()
    result=preview_valuation(plan,*compile_plan_inputs(plan,evidence))
    restored=ValuationResult.model_validate_json(result.model_dump_json())
    assert recalculate_target(restored)==result.target_price
    assert restored.reconciliation.opening_common_equity==1000

def test_incomplete_approved_bank_plan_stays_not_calculable():
    plan,evidence=fixture()
    metrics,candidates=compile_plan_inputs(plan,evidence)
    candidates=[c for c in candidates if c.valuation_field.value!="bank_terminal_roe"]
    result=preview_valuation(plan,metrics,candidates)
    assert result.status==ValuationStatus.NOT_CALCULABLE
    assert result.target_price is None
    assert result.methods["RESIDUAL_INCOME"].status.value=="NOT_CALCULABLE"

def test_historical_credit_loss_and_invalid_pb_unit_rejected():
    old=FinancialMetric(ticker=TICKER,report_id=RID,name="credit_loss_ratio",value=D(2),
        unit=Unit.PERCENTAGE,source="synthetic annual report",
        source_type=SourceType.COMPANY_DISCLOSURE,assumption_type=AssumptionType.HISTORICAL_ACTUAL,
        source_date=DAY,evidence_verified=True,evidence_quote="Historic credit loss",
        source_id="synthetic:credit_loss")
    checked,_=validate_candidate(candidate(old,RID,"credit_loss_ratio","base","Historical"),[old])
    assert checked.validation_status.value=="ineligible"
    pb=old.model_copy(update={"name":"target_pb","unit":Unit.ZAR})
    checked,_=validate_candidate(candidate(pb,RID,"target_pb","base","Wrong unit"),[pb])
    assert "BANK_PB_UNIT" in {w.code for w in checked.warnings}


def test_approved_cost_of_equity_override_preserves_calculated_rate():
    plan,evidence=fixture(override=True)
    result=preview_valuation(plan,*compile_plan_inputs(plan,evidence))
    assert result.status in {ValuationStatus.PASS,ValuationStatus.PASS_WITH_WARNINGS}
    first=result.methods["RESIDUAL_INCOME"].schedule[0]
    assert first["calculated_cost_of_equity"]=="0.10"
    assert first["selected_cost_of_equity"]=="0.11"
    assert "override" in first["cost_of_equity_override_rationale"]
    plan.engine_plan.cases["base"].bank.override_rationale=None
    with pytest.raises(ValidationError):
        BankSpec.model_validate(plan.engine_plan.cases["base"].bank.model_dump())
