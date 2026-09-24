from modules.analysis.forecast_plan_history import (
    clone_as_repaired_draft,derived_reference_status,history_rows,render_readonly_plan)
from modules.analysis.tests.test_dcf_mapping import fixture
from modules.analysis.dcf_mapping import map_accepted_fy2027_inputs
from modules.analysis.forecast_plan import ForecastPlan,PlanStatus
from modules.analysis.valuation.models import InputRef
from uuid import uuid4


def mapped_pair():
    source,evidence=fixture()
    mapped,_=map_accepted_fy2027_inputs(source,evidence,changed_by="Dion")
    return source,mapped,evidence


def test_version_list_for_ticker_data_and_v24_availability():
    source,mapped,_=mapped_pair()
    rows=history_rows([mapped,source])
    assert [r["version"] for r in rows]==[mapped.plan_version,source.plan_version]
    assert any(r["version"]==mapped.plan_version for r in rows)
    assert rows[0]["parent_id"]==str(source.forecast_plan_id)


def test_readonly_historical_view_contains_assumptions_mapping_and_approval():
    source,_,_=mapped_pair(); before=source.model_dump_json()
    text=render_readonly_plan(source)
    assert "ASSUMPTIONS" in text and "ENGINE MAPPING" in text and "Approval:" in text
    assert source.model_dump_json()==before


def test_stale_reference_repaired_only_in_cloned_draft():
    source,mapped,evidence=mapped_pair()
    year=mapped.engine_plan.cases["base"].dcf.years[0]
    stale_id=uuid4(); broken_year=year.model_copy(update={"inputs":{**year.inputs,"ebit":InputRef(metric_id=stale_id,field="ebit")}})
    dcf=mapped.engine_plan.cases["base"].dcf.model_copy(update={"years":[broken_year]})
    base=mapped.engine_plan.cases["base"].model_copy(update={"dcf":dcf})
    approved=mapped.model_copy(update={"status":PlanStatus.APPROVED,
        "engine_plan":mapped.engine_plan.model_copy(update={"cases":{"base":base}})})
    before=approved.model_dump_json()
    status=derived_reference_status(approved,evidence)
    assert status["status"]=="STALE" and status["stale"][0]["metric_id"]==str(stale_id)
    repaired,details=clone_as_repaired_draft(approved,evidence,changed_by="Dion")
    assert approved.model_dump_json()==before and approved.status==PlanStatus.APPROVED
    assert repaired.status==PlanStatus.DRAFT and repaired.forecast_plan_id!=approved.forecast_plan_id
    assert details["repair"]=="DERIVED_REFERENCES_REGENERATED"
    assert derived_reference_status(repaired,evidence)["status"]=="CURRENT"
    restored=ForecastPlan.model_validate_json(repaired.model_dump_json())
    assert derived_reference_status(restored,evidence)["status"]=="CURRENT"


def test_clone_current_version_is_new_draft_without_valuation():
    _,mapped,evidence=mapped_pair(); before=mapped.model_dump_json()
    clone,details=clone_as_repaired_draft(mapped,evidence,changed_by="Dion")
    assert details["repair"]=="NOT_REQUIRED"
    assert clone.status==PlanStatus.DRAFT and clone.plan_version==mapped.plan_version+1
    assert mapped.model_dump_json()==before
