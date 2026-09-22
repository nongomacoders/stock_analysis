"""Synthetic holding-company integration; no Naspers or Prosus values."""
import sys
from datetime import date
from decimal import Decimal as D
from pathlib import Path
from uuid import uuid4
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from modules.analysis.financial_metrics import FinancialMetric, Unit, SourceType, AssumptionType, convert_fx
from modules.analysis.valuation_preflight import candidate, validate_candidate
from modules.analysis.valuation.sotp import SotpComponent, calculate_sotp, listed_holding_value, holding_discount_schedule
from modules.analysis.valuation.reconciliation import reconcile_equity
from modules.analysis.valuation.engine import run_valuation
from modules.analysis.valuation.models import ValuationStatus

DAY = date(2026, 9, 22)

def component(name, boundary, gross, ownership, **kw):
    return SotpComponent(component_id=name, name=name, boundary_id=boundary, method="listed_market",
        gross_value=D(str(gross)), ownership=D(str(ownership)), currency="ZAR", valuation_date=DAY, **kw)

def test_synthetic_holding_nav_parent_shares_and_discount():
    # HKD, USD, EUR and ZAR inputs; explicit direct FX pairs.
    hkd = convert_fx(100, rate=2, pair="HKDZAR", from_currency="HKD", to_currency="ZAR")
    usd = convert_fx(200, rate=18, pair="USDZAR", from_currency="USD", to_currency="ZAR")
    eur = convert_fx(300, rate=20, pair="EURZAR", from_currency="EUR", to_currency="ZAR")
    listed = listed_holding_value(share_price=D(10), underlying_shares=D(100), ownership=D("0.25"),
        currency="HKD", price_date=DAY, ownership_date=DAY, price_source="synthetic:quote",
        ownership_source="synthetic:register")
    assert listed["gross_equity_value"] == 1000 and listed["attributable_value"] == 250
    schedule = calculate_sotp([component("A", "holding:A", hkd, ".25"),
        component("B", "holding:B", usd, ".5"), component("C", "holding:C", eur, "1"),
        component("D", "holding:D", 100, "1")], currency="ZAR", valuation_date=DAY)
    assert schedule.value == 50 + 1800 + 6000 + 100
    # Parent cash/debt are reconciled once, outside the asset schedule.
    nav = reconcile_equity(enterprise_or_operating_value=schedule.value, non_operating_assets=D(0),
        receivables=D(0), cash=D(500), debt=D(450), lease_adjustments=D(0),
        minorities=D(0), other_equity_adjustments=D(0), forward_shares=D(100), shares_metric_id=uuid4())
    assert nav.equity_value == 8000 and nav.unrounded_target_zar == 80
    discounted = holding_discount_schedule(nav_per_share=nav.unrounded_target_zar, discount=D(".20"),
        rationale="Synthetic holding-company friction", origin="analyst_assumption", approved=True,
        sensitivity=(D(".10"), D(".30")))
    assert discounted["target_per_share"] == 64
    assert discounted["sensitivity"] == {"0.10": D(72), "0.30": D(56)}

def test_discount_requires_explicit_approval():
    with pytest.raises(ValueError):
        holding_discount_schedule(nav_per_share=D(80), discount=D(".2"), rationale="",
            origin="gemini_suggestion", approved=False)

def test_parent_child_and_duplicate_asset_exposure_rejected():
    parent = component("subsidiary", "entity:sub", 100, 1, included_boundary_ids={"asset:inside"})
    child = component("asset", "asset:inside", 20, 1)
    with pytest.raises(ValueError, match="Duplicate economic exposure"):
        calculate_sotp([parent, child], currency="ZAR", valuation_date=DAY)
    with pytest.raises(ValueError):
        calculate_sotp([child, child], currency="ZAR", valuation_date=DAY)

def test_stale_ownership_warning_and_date_mismatch():
    report_id = uuid4()
    metric = FinancialMetric(ticker="SYNTHETIC.JO", report_id=report_id, name="ownership_percentage",
        value=D(25), unit=Unit.PERCENTAGE, source="synthetic register", source_id="synthetic:register",
        source_type=SourceType.COMPANY_DISCLOSURE, assumption_type=AssumptionType.HISTORICAL_ACTUAL,
        source_date=date(2024, 1, 1), evidence_verified=True, evidence_quote="Synthetic register")
    checked, _ = validate_candidate(candidate(metric, report_id, "ownership_percentage", "base", "Synthetic"), [metric])
    assert "STALE_OWNERSHIP" in {w.code for w in checked.warnings}
    result = calculate_sotp([component("old", "holding:old", 100, 1, value_source_date=DAY,
        ownership_source_date=date(2024, 1, 1))], currency="ZAR", valuation_date=DAY)
    assert any("ownership source date" in w for w in result.warnings)

def test_missing_unlisted_component_and_real_entities_do_not_force_targets():
    for ticker in ("NPN.JO", "PRX.JO"):
        result = run_valuation(ticker=ticker, report_version_id=uuid4(), metrics=[], candidates=[],
            missing_input_reasons=["No source-backed holding component schedule"] )
        assert result.status == ValuationStatus.NOT_CALCULABLE and result.target_price is None


@pytest.mark.parametrize("native,rate", [(Unit.HKD, D(2)), (Unit.EUR, D(20)), (Unit.USD, D(18))])
def test_engine_converts_native_component_and_retains_fx_audit(native, rate):
    from test_valuation_engine import synthetic_sotp, funded, ref, RID
    plan, metrics, candidates = synthetic_sotp()
    item = plan.cases["base"].sotp.components[0]
    gross, gross_c = funded("asset_value", 1000, unit=native, currency=native.value)
    fx, fx_c = funded("fx_rate", rate, unit=Unit.MULTIPLE, currency=None)
    item.gross_value = ref(gross_c); item.currency = native.value
    item.fx_rate = ref(fx_c); item.fx_pair = native.value + "ZAR"
    metrics = [m for m in metrics if m.name != "asset_value"] + [gross, fx]
    candidates = [c for c in candidates if c.valuation_field.value != "asset_value"] + [gross_c, fx_c]
    result = run_valuation(ticker="TEST.JO", report_version_id=RID,
                           metrics=metrics, candidates=candidates, plan=plan)
    assert result.status == ValuationStatus.PASS_WITH_WARNINGS
    row = result.methods["SOTP"].schedule[0]
    assert row["native_currency"] == native.value and D(row["native_gross_value"]) == 1000
    assert D(row["fx_rate_applied"]) == rate and row["fx_pair"] == native.value + "ZAR"
    assert D(row["gross_value"]) == 1000 * rate
    item.fx_pair = None
    missing = run_valuation(ticker="TEST.JO", report_version_id=RID,
                            metrics=metrics, candidates=candidates, plan=plan)
    assert missing.status == ValuationStatus.NOT_CALCULABLE

@pytest.mark.parametrize("kind,bridge_field", [("cash", "net_cash"), ("debt", "net_debt")])
def test_engine_rejects_component_and_parent_bridge_double_count(kind, bridge_field):
    from test_valuation_engine import synthetic_sotp, funded, ref, RID
    plan, metrics, candidates = synthetic_sotp()
    item = plan.cases["base"].sotp.components[0]
    item.value_kind = kind
    metric, selected = funded(bridge_field, 50)
    plan.cases["base"].equity.adjustments[bridge_field] = ref(selected)
    metrics = [m for m in metrics if m.name != bridge_field] + [metric]
    candidates = [c for c in candidates if c.valuation_field.value != bridge_field] + [selected]
    result = run_valuation(ticker="TEST.JO", report_version_id=RID,
                           metrics=metrics, candidates=candidates, plan=plan)
    assert result.status == ValuationStatus.FAIL and result.target_price is None
    assert any("both SOTP components and equity bridge" in w for w in result.warnings)
