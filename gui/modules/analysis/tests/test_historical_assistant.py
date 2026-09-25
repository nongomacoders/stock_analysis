"""Tests for Historical Assumption Assistant: fact vs forecast classification, fail-closed WACC & terminal growth."""
from datetime import date
from decimal import Decimal
import pytest
from modules.analysis.forecast_plan import ApprovalState
from modules.analysis.historical_backtest import (
    HistoricalBacktest, HistoricalEvidence, HistoricalMarketObservation, Availability
)
from modules.analysis.historical_plan import create_historical_draft, HistoricalPlanStatus
from modules.analysis.historical_assistant import (
    AssumptionType, QualityLabel, generate_historical_assumptions, resolve_historical_assistant_inputs
)
from modules.analysis.historical_assistant_txt import (
    export_proposals_to_txt, proposals_to_forecast_assumptions
)
from modules.analysis.historical_assistant_audit import (
    create_proposal_audit_records, attach_assistant_audit_to_plan
)

def test_historical_only_source_payload_and_leakage_exclusion(cached_tru_backtest):
    bt = cached_tru_backtest
    fy26_ev = HistoricalEvidence(
        evidence_id="fy26_leak", kind="revenue", available_date=date(2026, 8, 28),
        period_end=date(2026, 6, 28), source_id="leak",
        payload={"name": "revenue", "value": "26000000000", "period_label": "FY2026"},
        availability=Availability.UNAVAILABLE
    )
    unknown_ev = HistoricalEvidence(
        evidence_id="unknown_date_item", kind="margin", available_date=None,
        source_id="unk", payload={"name": "margin", "value": "15.0"},
        availability=Availability.UNCERTAIN
    )
    bt_with_leak = bt.model_copy(update={
        "evidence_snapshot": bt.evidence_snapshot + [fy26_ev, unknown_ev]
    })
    lookup, audit = resolve_historical_assistant_inputs(bt_with_leak)
    assert audit.excluded_later_source_count >= 1
    assert audit.unknown_date_exclusions >= 1
    assert "fy26_leak" not in [v.get("evidence_id") for v in lookup.values()]

def test_source_backed_means_factual_only(cached_tru_backtest):
    bt = cached_tru_backtest
    proposals, _ = generate_historical_assumptions(bt)
    forecast_fields = [
        "revenue_growth", "sale_of_merchandise_growth", "trading_margin",
        "depreciation", "tax_rate", "total_capex"
    ]
    for f in forecast_fields:
        p = next(x for x in proposals if x.field == f)
        assert p.quality == QualityLabel.HISTORICALLY_ANCHORED_ANALYST_JUDGMENT
        assert p.quality != QualityLabel.SOURCE_BACKED
        assert p.historical_anchor != ""
        assert len(p.evidence_ids) > 0

from modules.data.historical_market_storage import clear_historical_market_store_for_tests

@pytest.fixture(autouse=True)
def clean_market_inputs():
    clear_historical_market_store_for_tests()
    yield
    clear_historical_market_store_for_tests()

def test_wacc_must_fail_closed_without_persisted_components(cached_tru_backtest):
    bt = cached_tru_backtest
    proposals, _ = generate_historical_assumptions(bt)
    wacc_p = next(p for p in proposals if p.field == "wacc")
    assert wacc_p.proposed_value == "N/A - insufficient historical market evidence"
    assert wacc_p.quality == QualityLabel.INSUFFICIENT_EVIDENCE
    assert "risk_free_rate" in wacc_p.missing_components
    assert "equity_risk_premium" in wacc_p.missing_components
    assert "beta" in wacc_p.missing_components
    assert "cost_of_debt" in wacc_p.missing_components
    assert "Failed closed" in wacc_p.rationale

def test_terminal_growth_fails_closed_without_persisted_macro_evidence(cached_tru_backtest):
    bt = cached_tru_backtest
    proposals, _ = generate_historical_assumptions(bt)
    tg_p = next(p for p in proposals if p.field == "terminal_growth")
    assert tg_p.proposed_value == "N/A - insufficient historical macro evidence"
    assert tg_p.quality == QualityLabel.INSUFFICIENT_EVIDENCE
    assert "inflation_long_run" in tg_p.missing_components
    assert "Failed closed" in tg_p.rationale

def test_zero_assumptions_distinguish_normalization_and_no_material_item(cached_tru_backtest):
    bt = cached_tru_backtest
    proposals, _ = generate_historical_assumptions(bt)
    wc_p = next(p for p in proposals if p.field == "working_capital")
    assert wc_p.quality == QualityLabel.ANALYST_NORMALIZATION_TO_ZERO
    assert "inflow of R166m" in wc_p.rationale
    for f in ("other_recurring_cash", "minorities", "non_operating_assets", "other_equity_adjustments"):
        p = next(x for x in proposals if x.field == f)
        assert p.quality == QualityLabel.NO_MATERIAL_ITEM_IDENTIFIED
        assert p.quality != QualityLabel.SOURCE_BACKED
        assert p.proposed_value == Decimal("0")

def test_lease_adjustments_factual_amount_with_policy_choice(cached_tru_backtest):
    bt = cached_tru_backtest
    proposals, _ = generate_historical_assumptions(bt)
    lease_p = next(p for p in proposals if p.field == "lease_adjustments")
    assert lease_p.proposed_value == Decimal("3742000000")
    assert lease_p.quality == QualityLabel.SOURCE_BACKED
    assert lease_p.assumption_type == AssumptionType.VALUATION_POLICY_CHOICE
    assert "valuation policy choice" in lease_p.rationale

def test_proposals_include_both_anchor_and_forecast_for_ui(cached_tru_backtest):
    bt = cached_tru_backtest
    proposals, _ = generate_historical_assumptions(bt)
    for p in proposals:
        assert p.historical_anchor != ""
        assert p.field != ""

def test_missing_evidence_returns_na(cached_tru_backtest):
    empty_bt = cached_tru_backtest.model_copy(update={"evidence_snapshot": []})
    proposals, _ = generate_historical_assumptions(empty_bt)
    rev_p = next(p for p in proposals if p.field == "revenue_growth")
    assert rev_p.proposed_value == "N/A - insufficient historical evidence"
    assert rev_p.quality == QualityLabel.INSUFFICIENT_EVIDENCE

def test_txt_export_preserves_context_and_skips_na_values(cached_tru_backtest):
    bt = cached_tru_backtest
    proposals, _ = generate_historical_assumptions(bt)
    txt = export_proposals_to_txt(proposals, bt.ticker, bt.as_of_date)
    assert "BACKTEST\nticker=TRU.JO\nas_of_date=2025-08-31\nforecast_period=FY2026" in txt
    assert "field=revenue_growth\nvalue=5.0" in txt
    assert "field=trading_margin\nvalue=13.56" in txt
    assert "wacc" not in txt  # N/A values excluded from numeric TXT export

def test_audit_provenance_and_no_mutation_to_live_state(cached_tru_backtest):
    bt = cached_tru_backtest
    plan = create_historical_draft(bt)
    proposals, audit = generate_historical_assumptions(bt)
    records = create_proposal_audit_records(proposals, audit)
    updated_plan = attach_assistant_audit_to_plan(plan, audit, records)
    assert len(updated_plan.audit_metadata["assistant_provenance"]) == 14
    assert updated_plan.status == HistoricalPlanStatus.DRAFT
    assert updated_plan.is_locked is False
