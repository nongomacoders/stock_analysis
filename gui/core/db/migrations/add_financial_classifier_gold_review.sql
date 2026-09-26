-- Additive classifier gold-review benchmark storage. Never modifies production
-- financial parsers, valuation engines, or any existing table.
CREATE TABLE IF NOT EXISTS financial_classifier_gold_review (
    benchmark_id            text        PRIMARY KEY,
    ticker                  text        NOT NULL,
    publication_datetime    timestamp   NOT NULL,
    previous_sentence       text        NOT NULL,
    full_sentence           text        NOT NULL,
    next_sentence           text        NOT NULL,
    detected_numeric_tokens text        NOT NULL,
    normalized_label        text        NOT NULL,
    seed_concept            text,
    seed_scope              text,
    seed_dilution           text,
    seed_tax_basis          text,
    seed_capex_basis        text,
    seed_lease_inclusion    text,
    seed_margin_denominator text,
    seed_attribution        text,
    seed_alias_role         text,
    seed_value_pattern      text,
    seed_valuation_eligibility text,
    seed_should_abstain     boolean     NOT NULL,
    gold_concept            text,
    gold_scope              text,
    gold_dilution           text,
    gold_tax_basis          text,
    gold_capex_basis        text,
    gold_lease_inclusion    text,
    gold_basis_evidence     text,
    gold_margin_denominator text,
    gold_attribution        text,
    gold_alias_role         text,
    gold_value_pattern      text,
    gold_valuation_eligibility text,
    gold_should_abstain     boolean,
    reviewer_notes          text,
    review_decision         text        CHECK (review_decision IN ('CONFIRM_SEED','OVERRIDE','ABSTAIN','SKIP')),
    imported_at             timestamptz NOT NULL DEFAULT NOW(),
    last_updated_at         timestamptz NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS financial_classifier_gold_review_decision_idx
    ON financial_classifier_gold_review (review_decision);
CREATE INDEX IF NOT EXISTS financial_classifier_gold_review_ticker_idx
    ON financial_classifier_gold_review (ticker);
CREATE INDEX IF NOT EXISTS financial_classifier_gold_review_unreviewed_idx
    ON financial_classifier_gold_review (benchmark_id)
    WHERE review_decision IS NULL;
