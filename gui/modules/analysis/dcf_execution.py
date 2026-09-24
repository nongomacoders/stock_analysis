"""Safe execution checks and result presentation for deterministic DCFs."""
from __future__ import annotations
from decimal import Decimal
import hashlib, json
from modules.analysis.equity_bridge_preview import equity_bridge_preview
from modules.analysis.financial_metrics import FinancialMetric
from modules.analysis.forecast_plan import ForecastPlan, PlanStatus, compile_plan_inputs, preview_valuation, terminal_configuration_status
from modules.analysis.valuation.engine import WACC_FIELDS, _active_refs
from modules.analysis.valuation.models import MethodStatus, ValuationStatus
from modules.analysis.valuation_preflight import ValuationField, run_preflight

def valuation_input_hash(plan):
    raw=json.dumps({"forecast_plan":plan.model_dump(mode="json"),"engine":plan.valuation_engine_version},sort_keys=True,separators=(",",":"),default=str)
    return hashlib.sha256(raw.encode()).hexdigest()

def normalized_dcf_issues(plan:ForecastPlan)->list[str]:
    """Validate the exact DcfSpec consumed by the engine."""
    if plan.engine_plan is None or "base" not in plan.engine_plan.cases:
        return ["Approved plan has no base-case engine mapping"]
    case=plan.engine_plan.cases["base"]
    if case.primary_method!="DCF": return ["Base case primary method is not DCF"]
    spec=case.dcf
    if spec is None: return ["Base case has no DCF specification"]
    issues=[]
    if not spec.years: issues.append("DCF has no explicit forecast years")
    horizon_ends={p.end for p in plan.horizon}
    for year in spec.years:
        if year.period_end not in horizon_ends:
            issues.append(f"DCF period {year.period_end} is not mapped to the ForecastPlan horizon")
    if len({y.period_end for y in spec.years})!=len(spec.years):
        issues.append("DCF contains duplicate explicit forecast periods")
    if spec.wacc.supported_wacc is None and not spec.wacc.components:
        issues.append("DCF WACC has no supported_wacc or component mapping")
    elif spec.wacc.components:
        missing=sorted(set(WACC_FIELDS)-set(spec.wacc.components))
        if missing: issues.append("DCF WACC missing component mappings: "+", ".join(missing))
    if spec.terminal_method is None: issues.append("DCF terminal method is missing")
    elif spec.terminal_method.value=="perpetuity_growth" and spec.terminal_growth is None:
        issues.append("DCF perpetuity method has no terminal_growth mapping")
    elif spec.terminal_method.value=="exit_multiple" and (spec.exit_multiple is None or spec.terminal_metric not in {"EBIT","EBITDA"}):
        issues.append("DCF exit-multiple method lacks exit_multiple or EBIT/EBITDA basis")
    return issues

def execution_readiness(plan:ForecastPlan,evidence:list[dict]):
    reasons=[]
    if plan.status!=PlanStatus.APPROVED: reasons.append("ForecastPlan is not approved")
    terminal=terminal_configuration_status(plan)
    if terminal.get("status")!="ready":
        reasons += [f"DCF terminal configuration: {x}" for x in terminal.get("missing",[])]
        if terminal.get("error"): reasons.append(f"DCF terminal configuration: {terminal['error']}")
    equity=equity_bridge_preview(plan,evidence)
    if equity.get("status")!="READY":
        reasons += [f"Equity bridge: {x}" for x in equity.get("missing",[])+equity.get("invalid",[])]
    metrics=candidates=preflight=preview=None
    structural=normalized_dcf_issues(plan)
    reasons += structural
    if plan.engine_plan is None or "base" not in plan.engine_plan.cases: reasons.append("Approved plan has no base-case engine mapping")
    else:
        try:
            typed=[FinancialMetric.model_validate(x) for x in evidence]
            metrics,candidates=compile_plan_inputs(plan,typed)
            refs=_active_refs(plan.engine_plan.cases["base"])
            preflight=run_preflight(plan.ticker,plan.source_report_version_id,candidates,metrics,required_fields={ValuationField(r.field) for r in refs})
            if structural:
                preflight={**preflight,"status":"FAIL",
                    "reasons":[*preflight.get("reasons",[]),*structural],
                    "blocking_errors":[*preflight.get("blocking_errors",[]),
                        *[{"code":"INVALID_NORMALIZED_DCF","severity":"BLOCKING","message":item} for item in structural]]}
            if preflight["status"]!="PASS":
                reasons += preflight.get("reasons",[])
                reasons += [f"{x.get('code')}: {x.get('message')}" for x in preflight.get("blocking_errors",[]) if x.get("code")!="INVALID_NORMALIZED_DCF"]
            if not reasons:
                preview=preview_valuation(plan,metrics,candidates)
                dcf=preview.methods.get("DCF")
                if preview.status not in {ValuationStatus.PASS,ValuationStatus.PASS_WITH_WARNINGS}:
                    reasons += preview.warnings or ["Deterministic engine dry-run was not calculable"]
                elif not dcf or dcf.status!=MethodStatus.PASS or not dcf.schedule:
                    reasons.append("Deterministic engine produced no usable DCF schedule")
        except Exception as exc: reasons.append(str(exc))
    reasons=list(dict.fromkeys(reasons))
    return {"status":"READY" if not reasons else "BLOCKED","reasons":reasons,"preflight":preflight,"preview":preview,"metrics":metrics,"candidates":candidates}

def require_calculable_dcf(result):
    dcf=result.methods.get("DCF")
    if result.status not in {ValuationStatus.PASS,ValuationStatus.PASS_WITH_WARNINGS}:
        raise ValueError("Deterministic DCF is not calculable: "+"; ".join(result.warnings))
    if not dcf or dcf.status!=MethodStatus.PASS or not dcf.schedule:
        raise ValueError("Deterministic DCF has no usable explicit and terminal schedule")
    if not any("period_end" in row for row in dcf.schedule):
        raise ValueError("Deterministic DCF has no materialized explicit forecast periods")
    if not any("terminal" in row for row in dcf.schedule):
        raise ValueError("Deterministic DCF has no materialized terminal value")
    return result

def add_execution_warnings(result):
    dcf=result.methods.get("DCF")
    if not dcf or dcf.status!=MethodStatus.PASS: return result
    explicit=[r for r in dcf.schedule if "period_end" in r]; terminal=next((r for r in reversed(dcf.schedule) if "terminal" in r),None)
    warnings=list(result.warnings)
    if len(explicit)<3 and "SHORT_EXPLICIT_FORECAST_HORIZON" not in warnings: warnings.append("SHORT_EXPLICIT_FORECAST_HORIZON")
    pct=Decimal(str(terminal["present_value"]))/Decimal(str(dcf.value)) if terminal and dcf.value else None
    if pct is not None and pct>Decimal("0.80") and "TERMINAL_VALUE_CONCENTRATION" not in warnings: warnings.append("TERMINAL_VALUE_CONCENTRATION")
    codes=[x.get("code") for x in (result.preflight or {}).get("warnings",[])]
    if "DILUTION_UNMODELED" in codes and "DILUTION_UNMODELED" not in warnings: warnings.append("DILUTION_UNMODELED")
    result=result.model_copy(update={"warnings":warnings,"status":ValuationStatus.PASS_WITH_WARNINGS if warnings and result.status==ValuationStatus.PASS else result.status},deep=True)
    result.calculation_inputs.update(explicit_forecast_years=len(explicit),terminal_value_percentage_of_enterprise_value=str(pct) if pct is not None else None)
    return result

def render_dcf_result(result,plan,*,reused=False):
    dcf=result.methods.get("DCF")
    if not dcf: return "Deterministic DCF unavailable.\nWarnings: "+"; ".join(result.warnings)
    explicit=[r for r in dcf.schedule if "period_end" in r]; terminal=next((r for r in reversed(dcf.schedule) if "terminal" in r),{})
    pv_explicit=sum((Decimal(str(r.get("present_value",0))) for r in explicit),Decimal(0)); pv_terminal=Decimal(str(terminal.get("present_value",0))); ev=Decimal(str(dcf.value or 0)); pct=pv_terminal/ev*100 if ev else None
    accepted={(a.case,a.field):a for a in plan.assumptions if a.approval_state.value=="accepted"}; wacc=accepted.get(("base","wacc_override")) or accepted.get(("base","wacc")); growth=accepted.get(("base","terminal_growth")); rec=result.reconciliation; spec=plan.engine_plan.cases["base"].equity; money=lambda x:f"R{Decimal(str(x)):,.2f}"
    lines=["DETERMINISTIC DCF RESULT"+(" (existing idempotent result)" if reused else ""),f"Engine version: {result.valuation_engine_version}",f"ForecastPlan: {plan.forecast_plan_id} / v{plan.plan_version}",f"Valuation ID: {result.valuation_id}",f"Valuation status: {result.status.value}","Explicit forecast periods: "+(", ".join(str(r.get("period_end")) for r in explicit) or "none")]
    lines += [f"FCFF {r.get('period_end')}: {money(r.get('fcf',0))}" for r in explicit]
    lines += [f"WACC: {wacc.value if wacc else 'missing'}%",f"Terminal method: {terminal.get('terminal',{}).get('method','missing')}",f"Terminal growth: {growth.value if growth else 'n/a'}%",f"Terminal value: {money(terminal.get('undiscounted_terminal_value',0))}",f"Present value of explicit FCFF: {money(pv_explicit)}",f"Present value of terminal value: {money(pv_terminal)}",f"Enterprise value: {money(ev)}",f"Terminal value percentage of enterprise value: {pct:.2f}%" if pct is not None else "Terminal value percentage of enterprise value: unavailable"]
    if rec: lines += [f"Net cash: {money(rec.cash-rec.debt)}",f"Lease treatment: {spec.lease_treatment if spec else 'missing'}",f"Lease adjustment: {money(rec.lease_adjustments)}",f"Minorities: {money(rec.minorities)}",f"Non-operating assets: {money(rec.non_operating_assets)}",f"Other equity adjustments: {money(rec.other_equity_adjustments)}",f"Equity value: {money(rec.equity_value)}",f"Share denominator: {rec.shares:,.0f}",f"Deterministic value per share: R{rec.unrounded_target_zar:,.4f}"]
    lines.append("Warnings: "+("; ".join(result.warnings) if result.warnings else "none")); return "\n".join(lines)
