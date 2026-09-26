-- =============================================================================
-- Migration: Add override-presence boolean columns to
--            financial_classifier_gold_review, create the effective view,
--            release table, evaluation tables, and all constraints/indexes.
--
-- Safe to apply once.  All new columns default FALSE so existing rows are
-- immediately valid before the back-fill step.
-- =============================================================================

-- -------------------------------------------------------------------------
-- PART 1: Add override-presence boolean columns
-- -------------------------------------------------------------------------

ALTER TABLE financial_classifier_gold_review
    ADD COLUMN IF NOT EXISTS gold_concept_is_override           boolean NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS gold_scope_is_override             boolean NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS gold_dilution_is_override          boolean NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS gold_tax_basis_is_override         boolean NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS gold_capex_basis_is_override       boolean NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS gold_lease_inclusion_is_override   boolean NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS gold_basis_evidence_is_override    boolean NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS gold_margin_denominator_is_override boolean NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS gold_attribution_is_override       boolean NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS gold_alias_role_is_override        boolean NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS gold_value_pattern_is_override     boolean NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS gold_valuation_eligibility_is_override boolean NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS gold_should_abstain_is_override    boolean NOT NULL DEFAULT FALSE;

-- -------------------------------------------------------------------------
-- PART 2: Back-fill override flags for existing reviewed rows
--
-- Rules:
--   CONFIRM_SEED -> all flags remain FALSE (already correct by default)
--   SKIP         -> all flags remain FALSE (already correct by default)
--   OVERRIDE     -> flag = TRUE iff the corresponding gold field IS NOT NULL
--                   (provenance: a non-NULL gold field was explicitly supplied
--                    by the review patch; NULL means it was never touched)
--   ABSTAIN      -> gold_should_abstain_is_override = TRUE always
--                   other flags = TRUE iff the corresponding gold field IS NOT NULL
--                   (ABSTAIN rows that also corrected other dimensions)
-- -------------------------------------------------------------------------

-- OVERRIDE rows
UPDATE financial_classifier_gold_review
SET
    gold_concept_is_override                = (gold_concept IS NOT NULL),
    gold_scope_is_override                  = (gold_scope IS NOT NULL),
    gold_dilution_is_override               = (gold_dilution IS NOT NULL),
    gold_tax_basis_is_override              = (gold_tax_basis IS NOT NULL),
    gold_capex_basis_is_override            = (gold_capex_basis IS NOT NULL),
    gold_lease_inclusion_is_override        = (gold_lease_inclusion IS NOT NULL),
    gold_basis_evidence_is_override         = (gold_basis_evidence IS NOT NULL),
    gold_margin_denominator_is_override     = (gold_margin_denominator IS NOT NULL),
    gold_attribution_is_override            = (gold_attribution IS NOT NULL),
    gold_alias_role_is_override             = (gold_alias_role IS NOT NULL),
    gold_value_pattern_is_override          = (gold_value_pattern IS NOT NULL),
    gold_valuation_eligibility_is_override  = (gold_valuation_eligibility IS NOT NULL),
    gold_should_abstain_is_override         = (gold_should_abstain IS NOT NULL)
WHERE review_decision = 'OVERRIDE';

-- ABSTAIN rows: gold_should_abstain_is_override always TRUE;
-- other flags follow non-NULL presence (reviewer may have also corrected
-- concept/dilution/etc. while abstaining on the full parse)
UPDATE financial_classifier_gold_review
SET
    gold_concept_is_override                = (gold_concept IS NOT NULL),
    gold_scope_is_override                  = (gold_scope IS NOT NULL),
    gold_dilution_is_override               = (gold_dilution IS NOT NULL),
    gold_tax_basis_is_override              = (gold_tax_basis IS NOT NULL),
    gold_capex_basis_is_override            = (gold_capex_basis IS NOT NULL),
    gold_lease_inclusion_is_override        = (gold_lease_inclusion IS NOT NULL),
    gold_basis_evidence_is_override         = (gold_basis_evidence IS NOT NULL),
    gold_margin_denominator_is_override     = (gold_margin_denominator IS NOT NULL),
    gold_attribution_is_override            = (gold_attribution IS NOT NULL),
    gold_alias_role_is_override             = (gold_alias_role IS NOT NULL),
    gold_value_pattern_is_override          = (gold_value_pattern IS NOT NULL),
    gold_valuation_eligibility_is_override  = (gold_valuation_eligibility IS NOT NULL),
    gold_should_abstain_is_override         = TRUE   -- always: ABSTAIN is an explicit human decision
WHERE review_decision = 'ABSTAIN';

-- -------------------------------------------------------------------------
-- PART 3: Validation constraints
-- -------------------------------------------------------------------------

-- Helper expression: at least one override flag is true
-- Used in multiple constraints; defined inline.

-- 3a. CONFIRM_SEED: no override flag may be true
ALTER TABLE financial_classifier_gold_review
    DROP CONSTRAINT IF EXISTS chk_confirm_seed_no_overrides;
ALTER TABLE financial_classifier_gold_review
    ADD CONSTRAINT chk_confirm_seed_no_overrides CHECK (
        review_decision <> 'CONFIRM_SEED'
        OR (
            NOT gold_concept_is_override
            AND NOT gold_scope_is_override
            AND NOT gold_dilution_is_override
            AND NOT gold_tax_basis_is_override
            AND NOT gold_capex_basis_is_override
            AND NOT gold_lease_inclusion_is_override
            AND NOT gold_basis_evidence_is_override
            AND NOT gold_margin_denominator_is_override
            AND NOT gold_attribution_is_override
            AND NOT gold_alias_role_is_override
            AND NOT gold_value_pattern_is_override
            AND NOT gold_valuation_eligibility_is_override
            AND NOT gold_should_abstain_is_override
        )
    );

-- 3b. SKIP: no override flag may be true
ALTER TABLE financial_classifier_gold_review
    DROP CONSTRAINT IF EXISTS chk_skip_no_overrides;
ALTER TABLE financial_classifier_gold_review
    ADD CONSTRAINT chk_skip_no_overrides CHECK (
        review_decision <> 'SKIP'
        OR (
            NOT gold_concept_is_override
            AND NOT gold_scope_is_override
            AND NOT gold_dilution_is_override
            AND NOT gold_tax_basis_is_override
            AND NOT gold_capex_basis_is_override
            AND NOT gold_lease_inclusion_is_override
            AND NOT gold_basis_evidence_is_override
            AND NOT gold_margin_denominator_is_override
            AND NOT gold_attribution_is_override
            AND NOT gold_alias_role_is_override
            AND NOT gold_value_pattern_is_override
            AND NOT gold_valuation_eligibility_is_override
            AND NOT gold_should_abstain_is_override
        )
    );

-- 3c. OVERRIDE: at least one override flag must be true
ALTER TABLE financial_classifier_gold_review
    DROP CONSTRAINT IF EXISTS chk_override_has_at_least_one_flag;
ALTER TABLE financial_classifier_gold_review
    ADD CONSTRAINT chk_override_has_at_least_one_flag CHECK (
        review_decision <> 'OVERRIDE'
        OR (
            gold_concept_is_override
            OR gold_scope_is_override
            OR gold_dilution_is_override
            OR gold_tax_basis_is_override
            OR gold_capex_basis_is_override
            OR gold_lease_inclusion_is_override
            OR gold_basis_evidence_is_override
            OR gold_margin_denominator_is_override
            OR gold_attribution_is_override
            OR gold_alias_role_is_override
            OR gold_value_pattern_is_override
            OR gold_valuation_eligibility_is_override
            OR gold_should_abstain_is_override
        )
    );

-- 3d. ABSTAIN: gold_should_abstain_is_override must be true,
--              and the effective gold_should_abstain must be true.
--              Effective = CASE WHEN gold_should_abstain_is_override THEN gold_should_abstain
--                               ELSE seed_should_abstain END
ALTER TABLE financial_classifier_gold_review
    DROP CONSTRAINT IF EXISTS chk_abstain_should_abstain_flag;
ALTER TABLE financial_classifier_gold_review
    ADD CONSTRAINT chk_abstain_should_abstain_flag CHECK (
        review_decision <> 'ABSTAIN'
        OR (
            gold_should_abstain_is_override = TRUE
            AND CASE
                    WHEN gold_should_abstain_is_override THEN gold_should_abstain
                    ELSE seed_should_abstain
                END = TRUE
        )
    );

-- 3e. Consistency: if a flag is false, the gold value should be NULL
--     (advisory via CHECK; a flag=TRUE + gold=NULL means intentional override-to-unknown,
--      which is explicitly allowed per spec)
ALTER TABLE financial_classifier_gold_review
    DROP CONSTRAINT IF EXISTS chk_gold_null_when_no_flag;
ALTER TABLE financial_classifier_gold_review
    ADD CONSTRAINT chk_gold_null_when_no_flag CHECK (
        (gold_concept_is_override              OR gold_concept IS NULL)
        AND (gold_scope_is_override            OR gold_scope IS NULL)
        AND (gold_dilution_is_override         OR gold_dilution IS NULL)
        AND (gold_tax_basis_is_override        OR gold_tax_basis IS NULL)
        AND (gold_capex_basis_is_override      OR gold_capex_basis IS NULL)
        AND (gold_lease_inclusion_is_override  OR gold_lease_inclusion IS NULL)
        AND (gold_basis_evidence_is_override   OR gold_basis_evidence IS NULL)
        AND (gold_margin_denominator_is_override OR gold_margin_denominator IS NULL)
        AND (gold_attribution_is_override      OR gold_attribution IS NULL)
        AND (gold_alias_role_is_override       OR gold_alias_role IS NULL)
        AND (gold_value_pattern_is_override    OR gold_value_pattern IS NULL)
        AND (gold_valuation_eligibility_is_override OR gold_valuation_eligibility IS NULL)
        AND (gold_should_abstain_is_override   OR gold_should_abstain IS NULL)
    );

-- -------------------------------------------------------------------------
-- PART 4: Additional indexes for new columns
-- -------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS financial_classifier_gold_review_override_flag_idx
    ON financial_classifier_gold_review (review_decision)
    WHERE gold_concept_is_override
       OR gold_scope_is_override
       OR gold_dilution_is_override
       OR gold_tax_basis_is_override
       OR gold_capex_basis_is_override
       OR gold_lease_inclusion_is_override
       OR gold_basis_evidence_is_override
       OR gold_margin_denominator_is_override
       OR gold_attribution_is_override
       OR gold_alias_role_is_override
       OR gold_value_pattern_is_override
       OR gold_valuation_eligibility_is_override
       OR gold_should_abstain_is_override;

-- -------------------------------------------------------------------------
-- PART 5: Effective view
-- -------------------------------------------------------------------------

DROP VIEW IF EXISTS financial_classifier_gold_effective;
CREATE VIEW financial_classifier_gold_effective AS
SELECT
    -- Identity / context
    r.benchmark_id,
    r.ticker,
    r.publication_datetime,
    r.previous_sentence,
    r.full_sentence,
    r.next_sentence,
    r.detected_numeric_tokens,
    r.normalized_label,
    r.review_decision,
    r.reviewer_notes,

    -- Seed fields
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

    -- Gold fields (raw, nullable)
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

    -- Override-presence flags
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

    -- Effective labels (CASE, not COALESCE)
    CASE WHEN r.gold_concept_is_override
         THEN r.gold_concept
         ELSE r.seed_concept
    END AS effective_concept,

    CASE WHEN r.gold_scope_is_override
         THEN r.gold_scope
         ELSE r.seed_scope
    END AS effective_scope,

    CASE WHEN r.gold_dilution_is_override
         THEN r.gold_dilution
         ELSE r.seed_dilution
    END AS effective_dilution,

    CASE WHEN r.gold_tax_basis_is_override
         THEN r.gold_tax_basis
         ELSE r.seed_tax_basis
    END AS effective_tax_basis,

    CASE WHEN r.gold_capex_basis_is_override
         THEN r.gold_capex_basis
         ELSE r.seed_capex_basis
    END AS effective_capex_basis,

    CASE WHEN r.gold_lease_inclusion_is_override
         THEN r.gold_lease_inclusion
         ELSE r.seed_lease_inclusion
    END AS effective_lease_inclusion,

    -- gold_basis_evidence has no seed counterpart; effective = gold when overridden
    CASE WHEN r.gold_basis_evidence_is_override
         THEN r.gold_basis_evidence
         ELSE NULL
    END AS effective_basis_evidence,

    CASE WHEN r.gold_margin_denominator_is_override
         THEN r.gold_margin_denominator
         ELSE r.seed_margin_denominator
    END AS effective_margin_denominator,

    CASE WHEN r.gold_attribution_is_override
         THEN r.gold_attribution
         ELSE r.seed_attribution
    END AS effective_attribution,

    CASE WHEN r.gold_alias_role_is_override
         THEN r.gold_alias_role
         ELSE r.seed_alias_role
    END AS effective_alias_role,

    CASE WHEN r.gold_value_pattern_is_override
         THEN r.gold_value_pattern
         ELSE r.seed_value_pattern
    END AS effective_value_pattern,

    CASE WHEN r.gold_valuation_eligibility_is_override
         THEN r.gold_valuation_eligibility
         ELSE r.seed_valuation_eligibility
    END AS effective_valuation_eligibility,

    CASE WHEN r.gold_should_abstain_is_override
         THEN r.gold_should_abstain
         ELSE r.seed_should_abstain
    END AS effective_should_abstain,

    -- was_overridden: OVERRIDE/ABSTAIN and at least one flag is true
    (
        r.review_decision IN ('OVERRIDE', 'ABSTAIN')
        AND (
            r.gold_concept_is_override
            OR r.gold_scope_is_override
            OR r.gold_dilution_is_override
            OR r.gold_tax_basis_is_override
            OR r.gold_capex_basis_is_override
            OR r.gold_lease_inclusion_is_override
            OR r.gold_basis_evidence_is_override
            OR r.gold_margin_denominator_is_override
            OR r.gold_attribution_is_override
            OR r.gold_alias_role_is_override
            OR r.gold_value_pattern_is_override
            OR r.gold_valuation_eligibility_is_override
            OR r.gold_should_abstain_is_override
        )
    ) AS was_overridden

FROM financial_classifier_gold_review r
WHERE r.review_decision <> 'SKIP';

-- -------------------------------------------------------------------------
-- PART 6: Gold dataset releases table
-- -------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS financial_classifier_gold_releases (
    release_id              text        PRIMARY KEY,
    schema_version          text        NOT NULL,
    created_at              timestamptz NOT NULL DEFAULT NOW(),
    review_row_count        integer     NOT NULL,
    evaluation_row_count    integer     NOT NULL,
    confirm_seed_count      integer     NOT NULL,
    override_count          integer     NOT NULL,
    abstain_count           integer     NOT NULL,
    skip_count              integer     NOT NULL,
    source_description      text        NOT NULL,
    hash_column_manifest    text        NOT NULL,  -- JSON array: which columns participate in hash
    dataset_hash            text        NOT NULL,
    released_by             text,
    notes                   text
);

-- -------------------------------------------------------------------------
-- PART 7: Evaluation runs table (append-only)
-- -------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS financial_classifier_evaluation_runs (
    run_id                  text        PRIMARY KEY,
    release_id              text        NOT NULL REFERENCES financial_classifier_gold_releases(release_id),
    model_name              text        NOT NULL,
    model_version           text        NOT NULL,
    configuration_json      jsonb,
    started_at              timestamptz,
    completed_at            timestamptz,
    status                  text        NOT NULL DEFAULT 'pending'
                                CHECK (status IN ('pending','running','completed','failed')),
    summary_metrics_json    jsonb,
    created_at              timestamptz NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS financial_classifier_eval_runs_release_idx
    ON financial_classifier_evaluation_runs (release_id);

CREATE INDEX IF NOT EXISTS financial_classifier_eval_runs_model_idx
    ON financial_classifier_evaluation_runs (model_name, model_version);

-- -------------------------------------------------------------------------
-- PART 8: Evaluation predictions table (append-only)
-- -------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS financial_classifier_evaluation_predictions (
    run_id                          text        NOT NULL REFERENCES financial_classifier_evaluation_runs(run_id),
    benchmark_id                    text        NOT NULL,
    -- Predicted dimensions
    predicted_concept               text,
    predicted_scope                 text,
    predicted_dilution              text,
    predicted_tax_basis             text,
    predicted_capex_basis           text,
    predicted_lease_inclusion       text,
    predicted_margin_denominator    text,
    predicted_attribution           text,
    predicted_alias_role            text,
    predicted_value_pattern         text,
    predicted_valuation_eligibility text,
    predicted_should_abstain        boolean,
    -- Confidence / probabilities (optional, stored as JSONB for flexibility)
    confidence_json                 jsonb,
    -- Raw model output (optional)
    raw_model_output                text,
    created_at                      timestamptz NOT NULL DEFAULT NOW(),

    PRIMARY KEY (run_id, benchmark_id),
    FOREIGN KEY (benchmark_id)
        REFERENCES financial_classifier_gold_review(benchmark_id)
);

CREATE INDEX IF NOT EXISTS financial_classifier_eval_pred_run_idx
    ON financial_classifier_evaluation_predictions (run_id);

CREATE INDEX IF NOT EXISTS financial_classifier_eval_pred_benchmark_idx
    ON financial_classifier_evaluation_predictions (benchmark_id);
