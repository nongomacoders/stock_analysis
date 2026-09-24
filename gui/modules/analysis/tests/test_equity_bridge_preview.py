from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from modules.analysis.equity_bridge_preview import (
    NON_OPERATING_ASSET_RATIONALE, build_reviewed_equity_spec,
    equity_bridge_preview, map_reviewed_equity_bridge,
    render_equity_bridge_preview,
)
from modules.analysis.forecast_plan import (
    ApprovalState, ForecastAssumption, ForecastPeriod, ForecastPlan, Origin,
    configure_terminal_method,
)
from modules.analysis.valuation.engine import EquitySpec
from modules.analysis.valuation.models import InputRef


REPORT = uuid4()
CASH_ID = UUID("a5bb31a4-b2dd-43af-9c40-de9383abb7a5")
SHARES_ID = UUID("84ddb897-a2de-4203-b240-dbf831fd7829")


def evidence():
    return [
        {
            "metric_id": str(CASH_ID), "name": "net_debt_cash",
            "value": "196000000", "normalized_value": "196000000",
            "unit": "ZAR", "source_type": "company_disclosure",
            "source_date": "2026-08-27", "evidence_verified": True,
            "evidence_quote": "Net cash* R196 million",
        },
        {
            "metric_id": str(SHARES_ID), "name": "issued_shares_current",
            "value": "400551604", "unit": "shares",
            "share_count_type": "issued_shares_current",
            "source_type": "company_disclosure",
            "source_date": "2026-08-27", "evidence_verified": True,
            "evidence_quote": "400 551 604 ordinary shares in issue",
        },
        {
            "metric_id": str(uuid4()), "name": "net_debt_cash",
            "value": "196", "unit": "ZAR", "source_type": "unresolved",
            "source_date": "2026-08-27", "evidence_verified": True,
            "evidence_quote": "Net cash* R196 million",
        },
    ]


def accepted(field, value):
    return ForecastAssumption(
        field=field, value=Decimal(str(value)), unit="ZAR", currency="ZAR",
        period_label="FY2027", operation_segment="Group", case="base",
        origin=Origin.ANALYST_ASSUMPTION,
        approval_state=ApprovalState.ACCEPTED,
        rationale=f"Reviewed {field}", created_by="Dion",
    )


def plan(accepted_state=True):
    assumptions = [
        accepted("lease_adjustments", 4218000000),
        accepted("minorities", 0),
        accepted("non_operating_assets", 0),
        accepted("other_equity_adjustments", 0),
    ]
    if not accepted_state:
        assumptions[0] = assumptions[0].model_copy(
            update={"approval_state": ApprovalState.PROPOSED})
    return ForecastPlan(
        ticker="TRU.JO", created_by="Dion", source_report_version_id=REPORT,
        horizon=[ForecastPeriod(
            label="FY2027", start=date(2026, 6, 29), end=date(2027, 6, 27))],
        assumptions=assumptions,
    )


def mapped_plan():
    draft = configure_terminal_method(
        plan(), "perpetuity_growth", sector="General Retail")
    ids = {item.field: item.assumption_id for item in draft.assumptions}
    adjustments = {
        "net_cash": InputRef(metric_id=CASH_ID, field="net_cash"),
        **{field: InputRef(metric_id=ids[field], field=field)
           for field in (
               "lease_adjustments", "minorities",
               "non_operating_assets", "other_equity_adjustments")},
    }
    equity = EquitySpec(
        adjustments=adjustments,
        shares=InputRef(metric_id=SHARES_ID, field="current_issued_shares"),
        lease_treatment="lease_debt_adjustment",
        non_operating_asset_rationale=(
            "Money-market funds are included in net cash; operating assets excluded."),
    )
    engine = draft.engine_plan
    base = engine.cases["base"].model_copy(update={"equity": equity})
    return draft.model_copy(update={
        "engine_plan": engine.model_copy(update={
            "cases": {**engine.cases, "base": base}})})


def test_current_tru_inputs_are_visible_but_equity_mapping_is_missing():
    preview = equity_bridge_preview(
        configure_terminal_method(
            plan(), "perpetuity_growth", sector="General Retail"),
        evidence())
    assert preview["rows"]["net_cash"]["value"] == Decimal("196000000")
    assert preview["rows"]["net_cash"]["id"] == str(CASH_ID)
    assert preview["rows"]["net_cash"]["eligibility"] == "SOURCE-BACKED"
    assert preview["rows"]["current_issued_shares"]["value"] == Decimal("400551604")
    assert preview["rows"]["current_issued_shares"]["eligibility"] == "SOURCE-BACKED"
    for field in (
            "lease_adjustments", "minorities",
            "non_operating_assets", "other_equity_adjustments"):
        assert preview["rows"][field]["eligibility"] == "ACCEPTED"
    assert preview["status"] == "MISSING MAPPINGS"
    assert set(preview["missing_mappings"]) >= {
        "net_cash", "lease_adjustments", "minorities",
        "non_operating_assets", "other_equity_adjustments",
        "current_issued_shares", "lease_treatment",
        "non_operating_asset_rationale",
    }


def test_complete_equity_mapping_is_ready_and_renders_ids():
    preview = equity_bridge_preview(mapped_plan(), evidence())
    assert preview["status"] == "READY"
    assert preview["missing_mappings"] == []
    assert all(row["mapping"] == "MAPPED" for row in preview["rows"].values())
    rendered = render_equity_bridge_preview(preview)
    assert "R196m" in rendered
    assert "R4.218bn" in rendered
    assert "400,551,604" in rendered
    assert str(CASH_ID) in rendered
    assert str(SHARES_ID) in rendered
    assert "SOURCE-BACKED | MAPPED" in rendered
    assert "ACCEPTED | MAPPED" in rendered


def test_proposed_assumption_is_missing_not_eligible():
    preview = equity_bridge_preview(plan(accepted_state=False), evidence())
    assert preview["rows"]["lease_adjustments"]["eligibility"] == "MISSING"
    assert "lease_adjustments" in preview["missing_inputs"]


def test_wrong_or_double_counted_mapping_is_invalid():
    draft = mapped_plan()
    equity = draft.engine_plan.cases["base"].equity
    adjustments = {
        **equity.adjustments,
        "net_debt": InputRef(metric_id=uuid4(), field="net_debt"),
    }
    invalid_equity = equity.model_copy(update={"adjustments": adjustments})
    base = draft.engine_plan.cases["base"].model_copy(
        update={"equity": invalid_equity})
    invalid_plan = draft.model_copy(update={
        "engine_plan": draft.engine_plan.model_copy(update={
            "cases": {"base": base}})})
    preview = equity_bridge_preview(invalid_plan, evidence())
    assert preview["status"] == "INVALID/DOUBLE-COUNTED"
    assert "net_cash/net_debt" in preview["invalid"]


def draft_plan(accepted_state=True):
    return configure_terminal_method(
        plan(accepted_state=accepted_state), "perpetuity_growth",
        sector="General Retail")


def attach_equity(draft, equity):
    engine = draft.engine_plan
    base = engine.cases["base"].model_copy(update={"equity": equity})
    return draft.model_copy(update={
        "engine_plan": engine.model_copy(update={
            "cases": {**engine.cases, "base": base}})})


def test_successful_tru_mapping_uses_exact_current_ids_and_values():
    source = draft_plan()
    mapped = map_reviewed_equity_bridge(
        source, evidence(), changed_by="Dion")
    equity = mapped.engine_plan.cases["base"].equity
    assert equity.adjustments["net_cash"].metric_id == CASH_ID
    assert "net_debt" not in equity.adjustments
    assert equity.adjustments["lease_adjustments"].metric_id == next(
        a.assumption_id for a in source.assumptions
        if a.field == "lease_adjustments")
    assert equity.shares.metric_id == SHARES_ID
    assert equity.shares.field == "current_issued_shares"
    assert equity.lease_treatment == "lease_debt_adjustment"
    assert equity.non_operating_asset_rationale == NON_OPERATING_ASSET_RATIONALE
    assert mapped.status.value == "draft"
    assert source.engine_plan.cases["base"].equity is None


def test_mapping_rejects_missing_accepted_lease_adjustment():
    with pytest.raises(ValueError, match="lease_adjustments"):
        build_reviewed_equity_spec(draft_plan(accepted_state=False), evidence())


def test_mapping_rejects_missing_source_backed_net_cash():
    without_cash = [item for item in evidence()
                    if item.get("name") != "net_debt_cash"]
    with pytest.raises(ValueError, match="net_cash"):
        build_reviewed_equity_spec(draft_plan(), without_cash)


def test_mapping_rejects_missing_current_share_metric():
    without_shares = [item for item in evidence()
                      if item.get("name") != "issued_shares_current"]
    with pytest.raises(ValueError, match="current_issued_shares"):
        build_reviewed_equity_spec(draft_plan(), without_shares)


def test_mapping_rejects_existing_net_cash_net_debt_conflict():
    draft = draft_plan()
    equity = EquitySpec(
        adjustments={"net_debt": InputRef(metric_id=uuid4(), field="net_debt")},
        shares=InputRef(metric_id=SHARES_ID, field="current_issued_shares"))
    conflicted = attach_equity(draft, equity)
    with pytest.raises(ValueError, match="net_cash/net_debt conflict"):
        build_reviewed_equity_spec(conflicted, evidence())


def test_mapping_rejects_missing_non_operating_rationale():
    with pytest.raises(ValueError, match="rationale is required"):
        build_reviewed_equity_spec(
            draft_plan(), evidence(), non_operating_asset_rationale=" ")


def test_mapping_rejects_retail_receivables_adjustment():
    draft = draft_plan()
    equity = EquitySpec(
        adjustments={
            "net_cash": InputRef(metric_id=CASH_ID, field="net_cash"),
            "receivables": InputRef(metric_id=uuid4(), field="receivables"),
        },
        shares=InputRef(metric_id=SHARES_ID, field="current_issued_shares"))
    invalid = attach_equity(draft, equity)
    with pytest.raises(ValueError, match="receivables"):
        build_reviewed_equity_spec(invalid, evidence())


def test_mapping_enforces_lease_treatment_consistency():
    draft = mapped_plan()
    existing = draft.engine_plan.cases["base"].equity.model_copy(
        update={"lease_treatment": "leases_in_operating_cash_flows"})
    inconsistent = attach_equity(draft, existing)
    with pytest.raises(ValueError, match="lease treatment conflicts"):
        build_reviewed_equity_spec(inconsistent, evidence())


def test_mapping_preserves_source_backed_and_accepted_provenance():
    mapped = map_reviewed_equity_bridge(
        draft_plan(), evidence(), changed_by="Dion")
    preview = equity_bridge_preview(mapped, evidence())
    assert preview["status"] == "READY"
    assert preview["rows"]["net_cash"]["eligibility"] == "SOURCE-BACKED"
    assert preview["rows"]["current_issued_shares"]["eligibility"] == "SOURCE-BACKED"
    assert preview["rows"]["lease_adjustments"]["eligibility"] == "ACCEPTED"
    assert preview["rows"]["minorities"]["value"] == 0
    assert all(row["mapping"] == "MAPPED" for row in preview["rows"].values())


def test_mapping_does_not_approve_and_saved_json_restores_equity_spec():
    source = draft_plan()
    mapped = map_reviewed_equity_bridge(
        source, evidence(), changed_by="Dion")
    assert mapped.status.value == "draft"
    assert mapped.approval_status == "unapproved"
    restored = ForecastPlan.model_validate_json(mapped.model_dump_json())
    assert (restored.engine_plan.cases["base"].equity.model_dump()
            == mapped.engine_plan.cases["base"].equity.model_dump())


def test_mapping_button_confirms_without_running_valuation(monkeypatch):
    from types import SimpleNamespace
    import components.valuation_workbench_tab as workbench
    source = draft_plan()
    mapped = map_reviewed_equity_bridge(
        source, evidence(), changed_by="Dion")
    calls = []
    monkeypatch.setattr(
        workbench, "map_reviewed_equity_bridge",
        lambda *args, **kwargs: mapped)
    monkeypatch.setattr(workbench.messagebox, "askyesno", lambda *args: True)
    class Var:
        def get(self): return "Dion"
    class Status:
        def set(self,value): calls.append(("status",value))
    fake = SimpleNamespace(
        plan=source, evidence=evidence(), fields={"analyst": Var()},
        pending=[], status=Status(),
        _render=lambda: calls.append(("render",None)),
        async_run_bg=lambda *args, **kwargs: calls.append(("valuation",None)),
    )
    fake._stage_plan=lambda proposed: (
        setattr(fake,'plan',proposed), setattr(fake,'pending',[proposed]),
        fake._render())
    workbench.ValuationWorkbenchTab.map_reviewed_equity(fake)
    assert fake.plan is mapped
    assert fake.pending == [mapped]
    assert not any(name == "valuation" for name, _ in calls)

