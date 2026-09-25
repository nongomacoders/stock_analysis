"""Tests for PostgreSQL persistence, revisions, provenance classification, and hash integrity."""
from datetime import date
from decimal import Decimal
import pytest
from modules.analysis.historical_market_inputs import (
    MarketConcept, InputScope, ProvenanceQuality, make_historical_market_input,
    check_bond_remaining_maturity, DebtComponent, calculate_weighted_cost_of_debt,
    propagate_calculation_provenance
)
from modules.data.historical_market_storage import (
    save_historical_market_input, batch_import_historical_market_inputs,
    list_historical_market_inputs, supersede_historical_market_input,
    clear_historical_market_store_for_tests
)
from modules.analysis.historical_backtest import backtest_input_hash
from modules.analysis.historical_wacc_resolver import resolve_historical_wacc

@pytest.fixture(autouse=True)
def clean_market_store():
    clear_historical_market_store_for_tests(clear_db=True)
    yield
    clear_historical_market_store_for_tests(clear_db=True)

def test_postgresql_persistence_and_provenance_retention():
    inp = make_historical_market_input(
        MarketConcept.COST_OF_DEBT, Decimal("8.59"), date(2025, 6, 29), date(2025, 8, 28),
        "TRU FY2025 AFS", ticker="TRU.JO", provenance_quality=ProvenanceQuality.DERIVED_FROM_SOURCE_DOCUMENT,
        source_document_id="hist:afs", evidence_uri="results_history/TRU/FY2025/TRU_FY2025_AFS.pdf",
        evidence_hash="7e2389d7"
    )
    saved = save_historical_market_input(inp)
    assert saved.provenance_quality == ProvenanceQuality.DERIVED_FROM_SOURCE_DOCUMENT
    assert saved.source_document_id == "hist:afs"
    assert saved.evidence_hash == "7e2389d7"

    loaded = list_historical_market_inputs(concept=MarketConcept.COST_OF_DEBT)
    assert len(loaded) == 1
    assert loaded[0].input_id == saved.input_id
    assert loaded[0].provenance_quality == ProvenanceQuality.DERIVED_FROM_SOURCE_DOCUMENT

def test_bond_maturity_prevents_false_10y_label():
    res = check_bond_remaining_maturity("R2030", date(2030, 1, 31), date(2025, 8, 31))
    assert res["remaining_years"] == 4.42
    assert res["is_10y_benchmark"] is False
    assert "TENOR_LIMITATION" in res["classification"]

def test_distinguish_source_fact_from_derived_cost_of_debt():
    rf_fact = make_historical_market_input(
        MarketConcept.COST_OF_DEBT, Decimal("8.60"), date(2025, 6, 29), date(2025, 8, 28),
        "TRU FY2025 AFS Note 25.3.2", ticker="TRU.JO", provenance_quality=ProvenanceQuality.RAW_SOURCE_FACT
    )
    blended_derived = make_historical_market_input(
        MarketConcept.COST_OF_DEBT, Decimal("8.59"), date(2025, 6, 29), date(2025, 8, 28),
        "TRU FY2025 AFS Note 25.3.2", ticker="TRU.JO", provenance_quality=ProvenanceQuality.DERIVED_FROM_SOURCE_DOCUMENT
    )
    assert rf_fact.provenance_quality != blended_derived.provenance_quality
    assert rf_fact.provenance_quality == ProvenanceQuality.RAW_SOURCE_FACT
    assert blended_derived.provenance_quality == ProvenanceQuality.DERIVED_FROM_SOURCE_DOCUMENT

def test_weighted_debt_cost_calculation_retains_component_provenance():
    comps = [
        DebtComponent("RCF", Decimal("1200000000"), Decimal("0.086"), "Note 25.3.2", True),
        DebtComponent("Green loan", Decimal("268000000"), Decimal("0.089"), "Note 25.3.2", True),
        DebtComponent("Bank overdraft", Decimal("975000000"), Decimal("0.085"), "Note 25.3.2", True)
    ]
    kd, all_backed, details = calculate_weighted_cost_of_debt(comps)
    assert kd == Decimal("0.0859")
    assert all_backed is True
    assert details["status"] == "DERIVED_FROM_SOURCE_DOCUMENT"

def test_missing_overdraft_rate_cannot_silently_become_source_backed_kd():
    comps = [
        DebtComponent("RCF", Decimal("1200000000"), Decimal("0.086"), "Note 25.3.2", True),
        DebtComponent("Bank overdraft", Decimal("975000000"), Decimal("0.098"), "Analyst assumption", False)
    ]
    kd, all_backed, details = calculate_weighted_cost_of_debt(comps)
    assert all_backed is False
    assert details["status"] == "NOT_FULLY_SOURCE_BACKED"

def test_generic_provenance_propagation_rule():
    # 1. 100% raw source facts -> derived_from_source_document
    assert propagate_calculation_provenance([
        ProvenanceQuality.RAW_SOURCE_FACT, ProvenanceQuality.RAW_SOURCE_FACT
    ]) == ProvenanceQuality.DERIVED_FROM_SOURCE_DOCUMENT
    # 2. Inherits weakest material input
    assert propagate_calculation_provenance([
        ProvenanceQuality.RAW_SOURCE_FACT, ProvenanceQuality.ANALYST_ENTERED_HISTORICAL_OBSERVATION
    ]) == ProvenanceQuality.HISTORICALLY_ANCHORED_ANALYST_CALCULATION

def test_recalculated_wacc_preserves_provenance_summary(cached_tru_backtest):
    bt = cached_tru_backtest
    batch = [
        make_historical_market_input(MarketConcept.RISK_FREE_RATE, Decimal("10.25"), date(2025, 8, 29), date(2025, 8, 29), "SARB", provenance_quality=ProvenanceQuality.ANALYST_ENTERED_HISTORICAL_OBSERVATION, notes="R2030 proxy 4.4Y tenor"),
        make_historical_market_input(MarketConcept.EQUITY_RISK_PREMIUM, Decimal("6.00"), date(2025, 6, 30), date(2025, 7, 5), "PwC SA", provenance_quality=ProvenanceQuality.ANALYST_ENTERED_HISTORICAL_OBSERVATION),
        make_historical_market_input(MarketConcept.BETA, Decimal("0.92"), date(2025, 8, 29), date(2025, 8, 29), "Bloomberg", ticker="TRU.JO", provenance_quality=ProvenanceQuality.ANALYST_ENTERED_HISTORICAL_OBSERVATION),
        make_historical_market_input(MarketConcept.COST_OF_DEBT, Decimal("8.59"), date(2025, 6, 29), date(2025, 8, 28), "TRU FY2025 AFS Note 25.3.2", ticker="TRU.JO", provenance_quality=ProvenanceQuality.DERIVED_FROM_SOURCE_DOCUMENT, source_document_id="hist:afs", evidence_hash="7e2389d7"),
    ]
    batch_import_historical_market_inputs(batch)
    res = resolve_historical_wacc(bt)
    assert res.status == "READY"
    assert res.calculated_wacc == Decimal("14.86")
    assert res.cost_of_equity_provenance == "historically_anchored_analyst_calculation"
    assert res.cost_of_debt_provenance == "derived_from_source_document"
    assert res.wacc_provenance == "historically_anchored_analyst_calculation"
    assert res.methodological_status == "READY_WITH_MANUAL_INPUTS"
    assert any("R2.443bn" in n for n in res.notes)

def test_revision_append_only_and_supersedes_linkage():
    inp1 = make_historical_market_input(MarketConcept.BETA, Decimal("0.90"), date(2025, 8, 29), date(2025, 8, 29), "Bloomberg", ticker="TRU.JO", revision=1)
    saved1 = save_historical_market_input(inp1)
    inp2 = make_historical_market_input(MarketConcept.BETA, Decimal("0.92"), date(2025, 8, 29), date(2025, 8, 29), "Bloomberg", ticker="TRU.JO", revision=2)
    revised = supersede_historical_market_input(saved1.input_id, inp2)
    assert revised.supersedes_input_id == saved1.input_id
    assert revised.revision == 2

def test_backtest_integrity_hash_changes_on_market_input_revision(cached_tru_backtest):
    bt = cached_tru_backtest
    h1 = backtest_input_hash(bt, market_input_tokens=["inp_1:r1:hash_a:"])
    h2 = backtest_input_hash(bt, market_input_tokens=["inp_1:r2:hash_c:"])
    assert h1 != h2
