-- Add reporting-period semantics and economically meaningful recurrence metadata.
ALTER TABLE deepresearch_comparisons
    ADD COLUMN IF NOT EXISTS comparison_type text,
    ADD COLUMN IF NOT EXISTS previous_period_json jsonb,
    ADD COLUMN IF NOT EXISTS current_period_json jsonb,
    ADD COLUMN IF NOT EXISTS reporting_transition_key text;

ALTER TABLE deepresearch_comparisons
    DROP CONSTRAINT IF EXISTS deepresearch_comparisons_comparison_type_check;
ALTER TABLE deepresearch_comparisons
    ADD CONSTRAINT deepresearch_comparisons_comparison_type_check
    CHECK (comparison_type IS NULL OR comparison_type IN
        ('SAME_PERIOD_REVISION','NEW_REPORTING_PERIOD','MANUAL_OTHER'));

ALTER TABLE research_learning_points
    ADD COLUMN IF NOT EXISTS information_availability text,
    ADD COLUMN IF NOT EXISTS previous_analysis_quality text,
    ADD COLUMN IF NOT EXISTS recurrence_key text,
    ADD COLUMN IF NOT EXISTS reporting_transition_key text;

ALTER TABLE research_learning_points
    DROP CONSTRAINT IF EXISTS research_learning_points_information_availability_check;
ALTER TABLE research_learning_points
    ADD CONSTRAINT research_learning_points_information_availability_check
    CHECK (information_availability IS NULL OR information_availability IN
        ('available','unavailable','uncertain'));

ALTER TABLE research_learning_points
    DROP CONSTRAINT IF EXISTS research_learning_points_analysis_quality_check;
ALTER TABLE research_learning_points
    ADD CONSTRAINT research_learning_points_analysis_quality_check
    CHECK (previous_analysis_quality IS NULL OR previous_analysis_quality IN
        ('adequate','underweighted','missed','unsupported','incorrect'));

CREATE INDEX IF NOT EXISTS deepresearch_comparisons_type_idx
    ON deepresearch_comparisons (ticker, comparison_type, created_at DESC);
CREATE INDEX IF NOT EXISTS research_learning_transition_idx
    ON research_learning_points (recurrence_key, reporting_transition_key)
    WHERE recurrence_key IS NOT NULL;
