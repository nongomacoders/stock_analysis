-- =============================================================================
-- Migration: Add semantic_hash and audit_hash columns to
--            financial_classifier_gold_releases and evaluation_runs.
--
-- Establishes dual hash semantics:
-- 1. semantic_hash: Represents the evaluation dataset itself.
--    Hashes ONLY stable evaluation-relevant dimensions and inclusion status.
--    Ordered deterministically by benchmark_id.
--    Independent of reviewer_notes, timestamps, reviewer_id, or internal audit metadata.
--
-- 2. audit_hash: Represents the complete annotation and provenance state.
--    Hashes seed fields, gold fields, override flags, review decisions, reviewer notes,
--    and stable item descriptors. Excludes volatile timestamps.
--
-- Compatibility:
--    dataset_hash is preserved as the legacy audit hash field (points to audit_hash).
-- =============================================================================

-- 1. Update financial_classifier_gold_releases table schema
ALTER TABLE financial_classifier_gold_releases
    ADD COLUMN IF NOT EXISTS semantic_hash text,
    ADD COLUMN IF NOT EXISTS audit_hash text,
    ADD COLUMN IF NOT EXISTS semantic_column_manifest text,
    ADD COLUMN IF NOT EXISTS audit_column_manifest text;

-- 2. Update financial_classifier_evaluation_runs table schema
ALTER TABLE financial_classifier_evaluation_runs
    ADD COLUMN IF NOT EXISTS semantic_hash text;

-- 3. Backfill GOLD-001 release record
UPDATE financial_classifier_gold_releases
SET
    semantic_hash = 'd759e827f4c9469db407edfc08d7ab73fd21ff3767bb3e44d8255d896f467976',
    audit_hash = '7f95fc104c59dfcdc42a7ced35ea102884c95b9829f15d1c1960895dcd7b1d43',
    semantic_column_manifest = '["benchmark_id", "is_included", "effective_concept", "effective_scope", "effective_dilution", "effective_tax_basis", "effective_capex_basis", "effective_lease_inclusion", "effective_basis_evidence", "effective_margin_denominator", "effective_attribution", "effective_alias_role", "effective_value_pattern", "effective_valuation_eligibility", "effective_should_abstain"]',
    audit_column_manifest = '["benchmark_id", "ticker", "normalized_label", "review_decision", "seed_concept", "seed_scope", "seed_dilution", "seed_tax_basis", "seed_capex_basis", "seed_lease_inclusion", "seed_margin_denominator", "seed_attribution", "seed_alias_role", "seed_value_pattern", "seed_valuation_eligibility", "seed_should_abstain", "gold_concept", "gold_scope", "gold_dilution", "gold_tax_basis", "gold_capex_basis", "gold_lease_inclusion", "gold_basis_evidence", "gold_margin_denominator", "gold_attribution", "gold_alias_role", "gold_value_pattern", "gold_valuation_eligibility", "gold_should_abstain", "gold_concept_is_override", "gold_scope_is_override", "gold_dilution_is_override", "gold_tax_basis_is_override", "gold_capex_basis_is_override", "gold_lease_inclusion_is_override", "gold_basis_evidence_is_override", "gold_margin_denominator_is_override", "gold_attribution_is_override", "gold_alias_role_is_override", "gold_value_pattern_is_override", "gold_valuation_eligibility_is_override", "gold_should_abstain_is_override", "reviewer_notes"]',
    notes = COALESCE(notes, '') || E'\n[2026-09-26] Dual hash semantics established. Canonical evaluation semantic_hash: d759e827f4c9469db407edfc08d7ab73fd21ff3767bb3e44d8255d896f467976. Post-finalization audit_hash: 7f95fc104c59dfcdc42a7ced35ea102884c95b9829f15d1c1960895dcd7b1d43. Initial candidate pre-release audit snapshot: 3c5e1ce829eac535a4c7263b3caed47266f67ed7fd16b8f61586164992efbc24. Both audit snapshots evaluate to the identical semantic evaluation dataset.'
WHERE release_id = 'GOLD-001';

-- 4. Link BASELINE-SEED-GOLD-001 evaluation run to semantic_hash
UPDATE financial_classifier_evaluation_runs
SET semantic_hash = 'd759e827f4c9469db407edfc08d7ab73fd21ff3767bb3e44d8255d896f467976'
WHERE run_id = 'BASELINE-SEED-GOLD-001' AND release_id = 'GOLD-001';
