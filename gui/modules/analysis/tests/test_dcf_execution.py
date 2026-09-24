from datetime import date
from decimal import Decimal
from uuid import uuid4

from modules.analysis.dcf_execution import (add_execution_warnings, normalized_dcf_issues,
    require_calculable_dcf, valuation_input_hash)
from modules.analysis.forecast_plan import ForecastPlan, ForecastPeriod, PlanStatus
from modules.analysis.valuation.engine import CasePlan, DcfSpec, ValuationPlan, WaccSpec, YearInputSpec
from modules.analysis.valuation.models import (
    Basis, InputRef, MethodStatus, TerminalMethod, ValuationMethodResult, ValuationResult, ValuationStatus)


def test_input_hash_is_deterministic_and_plan_specific():
    report_id=uuid4()
    plan=ForecastPlan(ticker="TRU.JO",created_by="test",source_report_version_id=report_id)
    assert valuation_input_hash(plan)==valuation_input_hash(plan)
    changed=plan.model_copy(update={"plan_version":plan.plan_version+1})
    assert valuation_input_hash(plan)!=valuation_input_hash(changed)


def test_one_year_terminal_concentration_and_dilution_warnings_are_retained():
    result=ValuationResult(
        ticker="TRU.JO",report_version_id=uuid4(),valuation_date=date(2026,9,23),
        status=ValuationStatus.PASS,
        methods={"DCF":ValuationMethodResult(
            method="DCF",status=MethodStatus.PASS,value=Decimal("100"),currency="ZAR",
            schedule=[
                {"period_end":"2027-06-27","free_cash_flow":"10","present_value":"8"},
                {"terminal":{"method":"perpetuity_growth","value":"120"},"present_value":"92"},
            ])},
        preflight={"warnings":[{"code":"DILUTION_UNMODELED"}]})
    reviewed=add_execution_warnings(result)
    assert reviewed.status==ValuationStatus.PASS_WITH_WARNINGS
    assert {"SHORT_EXPLICIT_FORECAST_HORIZON","TERMINAL_VALUE_CONCENTRATION","DILUTION_UNMODELED"} <= set(reviewed.warnings)
    assert reviewed.calculation_inputs["explicit_forecast_years"]==1
    assert reviewed.calculation_inputs["terminal_value_percentage_of_enterprise_value"]=="0.92"


def structural_plan(*, years=True, mapped_period=True):
    rid=uuid4(); wacc=InputRef(metric_id=uuid4(),field="wacc"); growth=InputRef(metric_id=uuid4(),field="terminal_growth")
    period=ForecastPeriod(label="FY2027",start=date(2026,6,29),end=date(2027,6,27))
    year=YearInputSpec(period_end=period.end if mapped_period else date(2028,6,25),inputs={})
    dcf=DcfSpec(valuation_date=date(2026,9,23),years=[year] if years else [],cash_flow_currency="ZAR",cash_flow_basis=Basis.NOMINAL,inflation_basis="ZAR_CPI",wacc=WaccSpec(currency="ZAR",basis=Basis.NOMINAL,inflation_basis="ZAR_CPI",supported_wacc=wacc),terminal_method=TerminalMethod.PERPETUITY_GROWTH,terminal_growth=growth)
    engine=ValuationPlan(ticker="TRU.JO",report_version_id=rid,valuation_date=date(2026,9,23),cases={"base":CasePlan(rationale="test",primary_method="DCF",dcf=dcf)})
    return ForecastPlan(ticker="TRU.JO",created_by="test",source_report_version_id=rid,horizon=[period],engine_plan=engine)


def test_empty_materialized_years_block_readiness_structure():
    issues=normalized_dcf_issues(structural_plan(years=False))
    assert "DCF has no explicit forecast years" in issues


def test_incorrectly_mapped_period_is_blocked():
    issues=normalized_dcf_issues(structural_plan(mapped_period=False))
    assert any("not mapped to the ForecastPlan horizon" in item for item in issues)


def test_missing_terminal_method_is_blocked_on_normalized_spec():
    plan=structural_plan()
    case=plan.engine_plan.cases["base"]
    broken=case.dcf.model_copy(update={"terminal_method":None})
    engine=plan.engine_plan.model_copy(update={"cases":{"base":case.model_copy(update={"dcf":broken})}})
    broken_plan=plan.model_copy(update={"engine_plan":engine})
    assert "DCF terminal method is missing" in normalized_dcf_issues(broken_plan)


def test_unmapped_wacc_is_blocked():
    plan=structural_plan(); case=plan.engine_plan.cases["base"]
    broken=case.dcf.model_copy(update={"wacc":case.dcf.wacc.model_copy(update={"supported_wacc":None,"components":None})})
    plan=plan.model_copy(update={"engine_plan":plan.engine_plan.model_copy(update={"cases":{"base":case.model_copy(update={"dcf":broken})}})})
    assert "DCF WACC has no supported_wacc or component mapping" in normalized_dcf_issues(plan)


def test_not_calculable_result_is_rejected_before_storage():
    result=ValuationResult(ticker="TRU.JO",report_version_id=uuid4(),valuation_date=date(2026,9,23),status=ValuationStatus.NOT_CALCULABLE,methods={"DCF":ValuationMethodResult(method="DCF",status=MethodStatus.NOT_CALCULABLE,missing_inputs=["explicit forecast years"])},warnings=["explicit forecast years"])
    import pytest
    with pytest.raises(ValueError,match="not calculable"):
        require_calculable_dcf(result)



class NoWriteDb:
    def __init__(self): self.executed=False
    async def execute(self,*args): self.executed=True


def test_not_calculable_plan_result_is_never_appended():
    from modules.data.forecast_plans import save_plan_valuation
    plan=structural_plan().model_copy(update={"status":PlanStatus.APPROVED})
    result=ValuationResult(ticker=plan.ticker,report_version_id=plan.source_report_version_id,valuation_date=date(2026,9,23),status=ValuationStatus.NOT_CALCULABLE,methods={"DCF":ValuationMethodResult(method="DCF",status=MethodStatus.NOT_CALCULABLE,missing_inputs=["explicit forecast years"])},warnings=["explicit forecast years"],calculation_inputs={"forecast_plan":{"forecast_plan_id":str(plan.forecast_plan_id)}})
    db=NoWriteDb()
    import pytest
    with pytest.raises(ValueError,match="calculable deterministic valuation"):
        __import__("asyncio").run(save_plan_valuation(plan,result,db=db))
    assert db.executed is False
