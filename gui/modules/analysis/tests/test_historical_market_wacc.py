"""Tests for historical market and macro inputs, WACC resolver, and cutoff enforcement."""
from datetime import date
from decimal import Decimal
import pytest
from modules.analysis.historical_market_inputs import (
    MarketConcept, InputScope, ProvenanceQuality, make_historical_market_input
)
from modules.data.historical_market_storage import (
    save_historical_market_input, batch_import_historical_market_inputs,
    list_historical_market_inputs, clear_historical_market_store_for_tests
)
from modules.analysis.historical_wacc_resolver import (
    resolve_historical_wacc, resolve_historical_macro, derive_historical_capital_weights
)
from modules.analysis.historical_assistant import generate_historical_assumptions, QualityLabel

@pytest.fixture(autouse=True)
def clean_market_store():
    clear_historical_market_store_for_tests(clear_db=True)
    yield
    clear_historical_market_store_for_tests(clear_db=True)

def test_cutoff_enforcement_and_later_inputs_excluded(cached_tru_backtest):
    bt = cached_tru_backtest
    valid_rfr = make_historical_market_input(
        MarketConcept.RISK_FREE_RATE, Decimal("10.25"), date(2025, 8, 29), date(2025, 8, 29), "SARB"
    )
    future_rfr = make_historical_market_input(
        MarketConcept.RISK_FREE_RATE, Decimal("9.50"), date(2026, 3, 1), date(2026, 3, 1), "SARB"
    )
    future_beta = make_historical_market_input(
        MarketConcept.BETA, Decimal("0.75"), date(2026, 4, 1), date(2026, 4, 1), "Bloomberg", ticker="TRU.JO"
    )
    save_historical_market_input(valid_rfr)
    save_historical_market_input(future_rfr)
    save_historical_market_input(future_beta)

    res = resolve_historical_wacc(bt)
    assert res.components["risk_free_rate"].value == Decimal("10.25")
    assert res.components["risk_free_rate"].available_date == date(2025, 8, 29)
    assert "beta" in res.missing_components

def test_missing_component_yields_not_calculable(cached_tru_backtest):
    bt = cached_tru_backtest
    save_historical_market_input(make_historical_market_input(
        MarketConcept.RISK_FREE_RATE, Decimal("10.25"), date(2025, 8, 29), date(2025, 8, 29), "SARB"
    ))
    res = resolve_historical_wacc(bt)
    assert res.status == "NOT_CALCULABLE"
    assert "beta" in res.missing_components
    assert "equity_risk_premium" in res.missing_components
    assert "cost_of_debt" in res.missing_components
    assert res.calculated_wacc is None

def test_multiple_beta_candidates_retained_and_latest_selected(cached_tru_backtest):
    bt = cached_tru_backtest
    b1 = make_historical_market_input(MarketConcept.BETA, Decimal("0.85"), date(2025, 6, 30), date(2025, 6, 30), "S&P", ticker="TRU.JO", lookback_period="3Y")
    b2 = make_historical_market_input(MarketConcept.BETA, Decimal("0.92"), date(2025, 8, 29), date(2025, 8, 29), "Bloomberg", ticker="TRU.JO", lookback_period="2Y")
    save_historical_market_input(b1); save_historical_market_input(b2)
    res = resolve_historical_wacc(bt)
    assert len(res.beta_candidates) == 2
    assert res.components["beta"].value == Decimal("0.92")
    assert res.components["beta"].lag_days == 2

def test_capital_weights_calculated_from_historical_data(cached_tru_backtest):
    bt = cached_tru_backtest
    d_wt, e_wt, note = derive_historical_capital_weights(bt)
    assert d_wt + e_wt == Decimal("1.0")
    assert Decimal("0.05") < d_wt < Decimal("0.15")
    assert Decimal("0.85") < e_wt < Decimal("0.95")
    assert "Mkt Equity" in note

def test_full_historical_wacc_resolution_and_proposal_integration(cached_tru_backtest):
    bt = cached_tru_backtest
    batch = [
        make_historical_market_input(MarketConcept.RISK_FREE_RATE, Decimal("10.25"), date(2025, 8, 29), date(2025, 8, 29), "SARB", provenance_quality=ProvenanceQuality.ANALYST_ENTERED),
        make_historical_market_input(MarketConcept.EQUITY_RISK_PREMIUM, Decimal("6.00"), date(2025, 6, 30), date(2025, 7, 5), "PwC SA", provenance_quality=ProvenanceQuality.ANALYST_ENTERED),
        make_historical_market_input(MarketConcept.BETA, Decimal("0.92"), date(2025, 8, 29), date(2025, 8, 29), "Bloomberg", ticker="TRU.JO", provenance_quality=ProvenanceQuality.ANALYST_ENTERED),
        make_historical_market_input(MarketConcept.COST_OF_DEBT, Decimal("8.59"), date(2025, 6, 29), date(2025, 8, 28), "TRU FY2025 AFS Note 25.3.2", ticker="TRU.JO", provenance_quality=ProvenanceQuality.DERIVED_FROM_SOURCE_DOCUMENT, source_document_id="hist:afs", evidence_hash="7e2389d7"),
        make_historical_market_input(MarketConcept.INFLATION_LONG_RUN, Decimal("4.50"), date(2025, 8, 15), date(2025, 8, 15), "SARB MPC", provenance_quality=ProvenanceQuality.ANALYST_ENTERED),
    ]
    batch_import_historical_market_inputs(batch)
    res = resolve_historical_wacc(bt)
    assert res.status == "READY"
    assert res.calculated_wacc == Decimal("14.86")
    assert res.evidence_quality == "MIXED"
    assert res.provenance_summary.get("derived_from_source_document") == 1
    assert res.provenance_summary.get("analyst_entered") == 3

    proposals, audit = generate_historical_assumptions(bt)
    wacc_p = next(p for p in proposals if p.field == "wacc")
    tg_p = next(p for p in proposals if p.field == "terminal_growth")
    assert wacc_p.proposed_value == Decimal("14.86")
    assert "Quality: MIXED" in wacc_p.historical_anchor
    assert tg_p.proposed_value == Decimal("4.50")
    assert tg_p.proposed_value < wacc_p.proposed_value

def test_persisted_storage_replay_offline(cached_tru_backtest):
    bt = cached_tru_backtest
    item = make_historical_market_input(MarketConcept.RISK_FREE_RATE, Decimal("10.25"), date(2025, 8, 29), date(2025, 8, 29), "SARB")
    save_historical_market_input(item)
    loaded = list_historical_market_inputs(max_available_date=bt.as_of_date)
    assert len(loaded) == 1
    assert loaded[0].value == Decimal("10.25")
    assert loaded[0].input_hash != ""
