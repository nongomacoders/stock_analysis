-- =============================================================================
-- Migration: Benchmark Release Identity Hardening & Population Isolation
--
-- 1. Updates financial_classifier_gold_effective to expose review_batch and dataset_role.
-- 2. Creates dedicated release-population view financial_classifier_gold_001_effective.
-- 3. Adds source_hash, label_hash, release_hash, and release_manifest to
--    financial_classifier_gold_releases.
-- 4. Adds release_hash, source_hash, and label_hash to
--    financial_classifier_evaluation_runs.
-- 5. Backfills GOLD-001 release row and BASELINE-SEED-GOLD-001 evaluation run.
-- =============================================================================

-- 1. Recreate effective view with review_batch and dataset_role
DROP VIEW IF EXISTS financial_classifier_gold_001_effective;
DROP VIEW IF EXISTS financial_classifier_gold_effective;

CREATE VIEW financial_classifier_gold_effective AS
SELECT
    r.benchmark_id,
    r.review_batch,
    r.dataset_role,
    r.ticker,
    r.publication_datetime,
    r.previous_sentence,
    r.full_sentence,
    r.next_sentence,
    r.detected_numeric_tokens,
    r.normalized_label,
    r.review_decision,
    r.reviewer_notes,

    -- Seed dimensions
    r.seed_concept,
    r.seed_scope,
    r.seed_dilution,
    r.seed_tax_basis,
    r.seed_capex_basis,
    r.seed_lease_inclusion,
    r.seed_margin_denominator,
    r.seed_attribution,
    r.seed_alias_role,
    r.seed_value_pattern,
    r.seed_valuation_eligibility,
    r.seed_should_abstain,

    -- Raw gold dimensions
    r.gold_concept,
    r.gold_scope,
    r.gold_dilution,
    r.gold_tax_basis,
    r.gold_capex_basis,
    r.gold_lease_inclusion,
    r.gold_basis_evidence,
    r.gold_margin_denominator,
    r.gold_attribution,
    r.gold_alias_role,
    r.gold_value_pattern,
    r.gold_valuation_eligibility,
    r.gold_should_abstain,

    -- Override presence flags
    r.gold_concept_is_override,
    r.gold_scope_is_override,
    r.gold_dilution_is_override,
    r.gold_tax_basis_is_override,
    r.gold_capex_basis_is_override,
    r.gold_lease_inclusion_is_override,
    r.gold_basis_evidence_is_override,
    r.gold_margin_denominator_is_override,
    r.gold_attribution_is_override,
    r.gold_alias_role_is_override,
    r.gold_value_pattern_is_override,
    r.gold_valuation_eligibility_is_override,
    r.gold_should_abstain_is_override,

    -- Effective evaluation dimensions
    CASE WHEN r.gold_concept_is_override THEN r.gold_concept ELSE r.seed_concept END AS effective_concept,
    CASE WHEN r.gold_scope_is_override THEN r.gold_scope ELSE r.seed_scope END AS effective_scope,
    CASE WHEN r.gold_dilution_is_override THEN r.gold_dilution ELSE r.seed_dilution END AS effective_dilution,
    CASE WHEN r.gold_tax_basis_is_override THEN r.gold_tax_basis ELSE r.seed_tax_basis END AS effective_tax_basis,
    CASE WHEN r.gold_capex_basis_is_override THEN r.gold_capex_basis ELSE r.seed_capex_basis END AS effective_capex_basis,
    CASE WHEN r.gold_lease_inclusion_is_override THEN r.gold_lease_inclusion ELSE r.seed_lease_inclusion END AS effective_lease_inclusion,
    CASE WHEN r.gold_basis_evidence_is_override THEN r.gold_basis_evidence ELSE NULL END AS effective_basis_evidence,
    CASE WHEN r.gold_margin_denominator_is_override THEN r.gold_margin_denominator ELSE r.seed_margin_denominator END AS effective_margin_denominator,
    CASE WHEN r.gold_attribution_is_override THEN r.gold_attribution ELSE r.seed_attribution END AS effective_attribution,
    CASE WHEN r.gold_alias_role_is_override THEN r.gold_alias_role ELSE r.seed_alias_role END AS effective_alias_role,
    CASE WHEN r.gold_value_pattern_is_override THEN r.gold_value_pattern ELSE r.seed_value_pattern END AS effective_value_pattern,
    CASE WHEN r.gold_valuation_eligibility_is_override THEN r.gold_valuation_eligibility ELSE r.seed_valuation_eligibility END AS effective_valuation_eligibility,
    CASE WHEN r.gold_should_abstain_is_override THEN r.gold_should_abstain ELSE r.seed_should_abstain END AS effective_should_abstain,

    (
        r.review_decision IN ('OVERRIDE', 'ABSTAIN')
        AND (
            r.gold_concept_is_override OR r.gold_scope_is_override OR
            r.gold_dilution_is_override OR r.gold_tax_basis_is_override OR
            r.gold_capex_basis_is_override OR r.gold_lease_inclusion_is_override OR
            r.gold_basis_evidence_is_override OR r.gold_margin_denominator_is_override OR
            r.gold_attribution_is_override OR r.gold_alias_role_is_override OR
            r.gold_value_pattern_is_override OR r.gold_valuation_eligibility_is_override OR
            r.gold_should_abstain_is_override
        )
    ) AS was_overridden

FROM financial_classifier_gold_review r
WHERE r.review_decision <> 'SKIP';

-- 2. Dedicated GOLD-001 release effective view (strictly isolated to BATCH-001)
CREATE VIEW financial_classifier_gold_001_effective AS
SELECT *
FROM financial_classifier_gold_effective
WHERE review_batch = 'BATCH-001';

-- 3. Extend financial_classifier_gold_releases table schema
ALTER TABLE financial_classifier_gold_releases
    ADD COLUMN IF NOT EXISTS source_hash text,
    ADD COLUMN IF NOT EXISTS label_hash text,
    ADD COLUMN IF NOT EXISTS release_hash text,
    ADD COLUMN IF NOT EXISTS release_manifest text;

-- 4. Extend financial_classifier_evaluation_runs table schema
ALTER TABLE financial_classifier_evaluation_runs
    ADD COLUMN IF NOT EXISTS release_hash text,
    ADD COLUMN IF NOT EXISTS source_hash text,
    ADD COLUMN IF NOT EXISTS label_hash text;

-- 5. Backfill GOLD-001 release row
UPDATE financial_classifier_gold_releases
SET
    source_hash = '4b8594e5b34d7d05273fecda2dd4b817b9dc2e055d77cf0bc6de31cf79ff7610',
    label_hash = 'f9139858b89ea102d30c22e1007b1e807c5aecc684048ffb31df1dcb73e9ef75',
    release_hash = 'f0b3138d32a033b66cd0823cfd83ae89461433209a0552bece6722d2ca98f179',
    release_manifest = 'release_id=GOLD-001|schema_version=1.1.0|source_hash=4b8594e5b34d7d05273fecda2dd4b817b9dc2e055d77cf0bc6de31cf79ff7610|label_hash=f9139858b89ea102d30c22e1007b1e807c5aecc684048ffb31df1dcb73e9ef75\n',
    notes = COALESCE(notes, '') || E'\n[2026-09-26] Release identity hardened: authoritative release_hash=f0b3138d32a033b66cd0823cfd83ae89461433209a0552bece6722d2ca98f179, source_hash=4b8594e5b34d7d05273fecda2dd4b817b9dc2e055d77cf0bc6de31cf79ff7610, label_hash=f9139858b89ea102d30c22e1007b1e807c5aecc684048ffb31df1dcb73e9ef75. Legacy semantic_hash (d759e827...) and audit_hash (7f95fc10...) preserved.'
WHERE release_id = 'GOLD-001';

-- 6. Backfill BASELINE-SEED-GOLD-001 evaluation run
UPDATE financial_classifier_evaluation_runs
SET
    release_hash = 'f0b3138d32a033b66cd0823cfd83ae89461433209a0552bece6722d2ca98f179',
    source_hash = '4b8594e5b34d7d05273fecda2dd4b817b9dc2e055d77cf0bc6de31cf79ff7610',
    label_hash = 'f9139858b89ea102d30c22e1007b1e807c5aecc684048ffb31df1dcb73e9ef75'
WHERE run_id = 'BASELINE-SEED-GOLD-001' AND release_id = 'GOLD-001';
