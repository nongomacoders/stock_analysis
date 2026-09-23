-- Additive post-publication research comparison and learning records.
CREATE TABLE IF NOT EXISTS deepresearch_comparisons (
 comparison_id uuid PRIMARY KEY, ticker text NOT NULL,
 previous_report_id uuid NOT NULL REFERENCES deepresearch_versions(report_id),
 current_report_id uuid NOT NULL REFERENCES deepresearch_versions(report_id),
 created_at timestamptz NOT NULL DEFAULT NOW(), completed_at timestamptz,
 comparison_engine_version text NOT NULL, comparison_prompt_version text NOT NULL,
 status text NOT NULL CHECK (status IN ('pending','completed','failed','no_prior_report')),
 deterministic_summary_json jsonb NOT NULL DEFAULT '{}'::jsonb,
 qualitative_review_json jsonb, overall_summary text, model_name text, error_message text,
 UNIQUE(previous_report_id,current_report_id,comparison_engine_version,comparison_prompt_version),
 CHECK(previous_report_id <> current_report_id)
);
CREATE INDEX IF NOT EXISTS deepresearch_comparisons_ticker_created_idx ON deepresearch_comparisons(ticker,created_at DESC);
CREATE INDEX IF NOT EXISTS deepresearch_comparisons_current_report_idx ON deepresearch_comparisons(current_report_id);
CREATE TABLE IF NOT EXISTS research_learning_points (
 learning_point_id uuid PRIMARY KEY,
 comparison_id uuid NOT NULL REFERENCES deepresearch_comparisons(comparison_id), ticker text NOT NULL,
 category text NOT NULL CHECK (category IN ('MISSED_RISK','MISSED_CATALYST','UNDERWEIGHTED_AREA','OVERWEIGHTED_AREA','UNSUPPORTED_ASSUMPTION','FORECAST_ERROR','CAUSAL_INFERENCE_ERROR','SOURCE_GAP','STALE_DATA','UNIT_ERROR','SHARE_COUNT_ERROR','VALUATION_ERROR','THESIS_ERROR','GOOD_CALL','GOOD_DISCIPLINE','NEW_INFORMATION','MODEL_LIMITATION')),
 scope text NOT NULL CHECK (scope IN ('ticker_analysis','sector_analysis','research_process','valuation_process','data_pipeline')),
 severity text NOT NULL CHECK (severity IN ('low','medium','high','critical')),
 area text NOT NULL, finding text NOT NULL, evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
 previous_report_reference text, current_report_reference text,
 source_metric_ids uuid[] NOT NULL DEFAULT '{}', recommended_action text NOT NULL,
 status text NOT NULL CHECK (status IN ('open','reinforced','resolved','superseded','dismissed')),
 recurrence_count integer NOT NULL DEFAULT 1 CHECK (recurrence_count > 0),
 created_at timestamptz NOT NULL DEFAULT NOW(), resolved_at timestamptz, resolution_notes text
);
CREATE INDEX IF NOT EXISTS research_learning_points_ticker_status_idx ON research_learning_points(ticker,status,created_at DESC);
CREATE INDEX IF NOT EXISTS research_learning_points_pattern_idx ON research_learning_points(ticker,category,scope,area,status);
CREATE INDEX IF NOT EXISTS research_learning_points_category_idx ON research_learning_points(category,scope,created_at DESC);
