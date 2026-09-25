"""Audit trail and provenance records for Historical Assumption Assistant."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4
from pydantic import BaseModel, Field
from modules.analysis.historical_assistant import (
    HistoricalAssumptionProposal, HistoricalAssistantAudit
)
from modules.analysis.historical_plan import HistoricalForecastPlan

class ProposalAuditRecord(BaseModel):
    record_id: UUID = Field(default_factory=uuid4)
    proposal_id: UUID
    field: str
    proposed_value: str
    unit: str
    rationale: str
    assumption_type: str
    quality: str
    generation_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    snapshot_hash: str
    evidence_ids: list[str] = Field(default_factory=list)
    model_version: str = "deterministic_rules_v1"
    prompt_version: str = "1.0"
    final_analyst_decision: str = "proposed"

def create_proposal_audit_records(
    proposals: list[HistoricalAssumptionProposal],
    audit: HistoricalAssistantAudit,
    model_version: str = "deterministic_rules_v1",
    prompt_version: str = "1.0"
) -> list[ProposalAuditRecord]:
    now = datetime.now(timezone.utc)
    records: list[ProposalAuditRecord] = []
    for p in proposals:
        rec = ProposalAuditRecord(
            proposal_id=p.proposal_id,
            field=p.field,
            proposed_value=str(p.proposed_value),
            unit=p.unit,
            rationale=p.rationale,
            assumption_type=p.assumption_type.value,
            quality=p.quality.value,
            generation_timestamp=now,
            snapshot_hash=audit.snapshot_hash,
            evidence_ids=p.evidence_ids,
            model_version=model_version,
            prompt_version=prompt_version,
            final_analyst_decision=p.approval_state.value,
        )
        records.append(rec)
    return records

def attach_assistant_audit_to_plan(
    plan: HistoricalForecastPlan,
    audit: HistoricalAssistantAudit,
    records: list[ProposalAuditRecord]
) -> HistoricalForecastPlan:
    current_audit = dict(plan.audit_metadata)
    provenance_list = current_audit.get("assistant_provenance", [])
    new_entries = [r.model_dump(mode="json") for r in records]
    updated_provenance = provenance_list + new_entries
    
    current_audit["assistant_provenance"] = updated_provenance
    current_audit["assistant_audit_summary"] = audit.model_dump(mode="json")
    return plan.model_copy(update={"audit_metadata": current_audit})
