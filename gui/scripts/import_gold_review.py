"""Import a financial-classifier gold-review CSV into PostgreSQL.

Usage
-----
    python gui/scripts/import_gold_review.py --csv path/to/file.csv [--force-overwrite-reviewed]

Behaviour
---------
- Runs entirely inside a single transaction; rolls back on any validation error.
- Inserts rows that do not yet exist in the table.
- Updates source / seed fields for existing rows (safe re-import of corrected source data).
- NEVER replaces a non-blank review_decision, reviewer_notes, or gold_* field with
  a blank CSV value unless --force-overwrite-reviewed is explicitly supplied.
- Reports inserted / updated / unchanged / rejected row counts.
- Safe to rerun; idempotent for unchanged source data.
- No DROP TABLE / TRUNCATE / DELETE operations.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Optional

import psycopg2
import psycopg2.extras

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.config import DB_CONFIG


# ---------------------------------------------------------------------------
# Column manifest
# ---------------------------------------------------------------------------

REQUIRED_COLUMNS = {
    "benchmark_id",
    "ticker",
    "publication_datetime",
    "previous_sentence",
    "full_sentence",
    "next_sentence",
    "detected_numeric_tokens",
    "normalized_label",
    "seed_concept",
    "seed_scope",
    "seed_dilution",
    "seed_tax_basis",
    "seed_capex_basis",
    "seed_lease_inclusion",
    "seed_margin_denominator",
    "seed_attribution",
    "seed_alias_role",
    "seed_value_pattern",
    "seed_valuation_eligibility",
    "seed_should_abstain",
    "gold_concept",
    "gold_scope",
    "gold_dilution",
    "gold_tax_basis",
    "gold_capex_basis",
    "gold_lease_inclusion",
    "gold_basis_evidence",
    "gold_margin_denominator",
    "gold_attribution",
    "gold_alias_role",
    "gold_value_pattern",
    "gold_valuation_eligibility",
    "gold_should_abstain",
    "reviewer_notes",
    "review_decision",
}

BOOLEAN_COLUMNS = {"seed_should_abstain", "gold_should_abstain"}

# Text columns that are NOT NULL in the schema: empty CSV value stays as ""
# (some rows legitimately have no previous_sentence, e.g. first in a document).
NOT_NULL_TEXT_COLUMNS = {
    "ticker",
    "previous_sentence",
    "full_sentence",
    "next_sentence",
    "detected_numeric_tokens",
    "normalized_label",
}

REVIEW_FIELD_COLUMNS = {
    "review_decision",
    "reviewer_notes",
    "gold_concept",
    "gold_scope",
    "gold_dilution",
    "gold_tax_basis",
    "gold_capex_basis",
    "gold_lease_inclusion",
    "gold_basis_evidence",
    "gold_margin_denominator",
    "gold_attribution",
    "gold_alias_role",
    "gold_value_pattern",
    "gold_valuation_eligibility",
    "gold_should_abstain",
}

SOURCE_FIELDS = [
    "ticker",
    "publication_datetime",
    "previous_sentence",
    "full_sentence",
    "next_sentence",
    "detected_numeric_tokens",
    "normalized_label",
    "seed_concept",
    "seed_scope",
    "seed_dilution",
    "seed_tax_basis",
    "seed_capex_basis",
    "seed_lease_inclusion",
    "seed_margin_denominator",
    "seed_attribution",
    "seed_alias_role",
    "seed_value_pattern",
    "seed_valuation_eligibility",
    "seed_should_abstain",
]

VALID_REVIEW_DECISIONS = {"CONFIRM_SEED", "OVERRIDE", "ABSTAIN", "SKIP"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalise_cmp(v):
    """Normalise a value for equality comparison across CSV and DB representations."""
    from datetime import datetime
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        # Format as "YYYY-MM-DD HH:MM" to match the CSV publication_datetime format.
        return v.strftime("%Y-%m-%d %H:%M")
    return v


def _vals_equal(a, b) -> bool:
    """Compare a CSV-derived value with a DB row value semantically."""
    return _normalise_cmp(a) == _normalise_cmp(b)


def _none_or_empty(v) -> bool:
    return v is None or v == ""


def parse_bool(value: str, column: str, benchmark_id: str) -> Optional[bool]:
    if value == "":
        return None
    if value == "True":
        return True
    if value == "False":
        return False
    raise ValueError(
        f"Row {benchmark_id!r}: column {column!r} must be True, False, or empty; got {value!r}"
    )


def normalise_row(raw: dict[str, str]) -> dict:
    bid = raw.get("benchmark_id", "").strip()
    if not bid:
        raise ValueError("Row with empty benchmark_id encountered")

    row: dict = {}
    for col in REQUIRED_COLUMNS:
        raw_val = raw.get(col, "")
        if col in BOOLEAN_COLUMNS:
            parsed = parse_bool(raw_val, col, bid)
            if col == "seed_should_abstain" and parsed is None:
                raise ValueError(
                    f"Row {bid!r}: seed_should_abstain must not be empty"
                )
            row[col] = parsed
        elif col == "review_decision":
            stripped = raw_val.strip()
            if stripped and stripped not in VALID_REVIEW_DECISIONS:
                raise ValueError(
                    f"Row {bid!r}: invalid review_decision {stripped!r}; "
                    f"must be one of {sorted(VALID_REVIEW_DECISIONS)}"
                )
            row[col] = stripped or None
        else:
            # NOT NULL text columns keep "" so the DB constraint is satisfied.
            # Nullable text columns convert "" -> None (SQL NULL).
            if col in NOT_NULL_TEXT_COLUMNS:
                row[col] = raw_val  # may be empty string; schema allows it
            else:
                row[col] = raw_val if raw_val != "" else None
    return row


# ---------------------------------------------------------------------------
# Main import logic
# ---------------------------------------------------------------------------

def run_import(csv_path: Path, force_overwrite_reviewed: bool = False) -> None:
    rows_raw = csv_path.read_text(encoding="utf-8-sig")
    reader = csv.DictReader(rows_raw.splitlines())

    header_cols = set(reader.fieldnames or [])
    missing = REQUIRED_COLUMNS - header_cols
    if missing:
        raise ValueError(
            f"CSV is missing required columns: {sorted(missing)}"
        )

    all_rows: list[dict] = []
    seen_ids: set[str] = set()
    rejected: list[str] = []

    for raw in reader:
        bid = raw.get("benchmark_id", "").strip()
        if not bid:
            print(f"  WARN: Skipping row with empty benchmark_id", file=sys.stderr)
            rejected.append("<empty>")
            continue
        if bid in seen_ids:
            rejected.append(bid)
            print(f"  ERROR: Duplicate benchmark_id in CSV: {bid!r}", file=sys.stderr)
            continue
        seen_ids.add(bid)
        row = normalise_row(raw)
        all_rows.append(row)

    if rejected:
        raise ValueError(
            f"Duplicate benchmark_id -- CSV validation failed: {len(rejected)} rejected id(s): {rejected[:10]}"
        )

    print(f"CSV validated: {len(all_rows)} distinct rows read from {csv_path.name}")

    conn = psycopg2.connect(**DB_CONFIG)
    try:
        conn.autocommit = False
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:

            # Fetch ALL columns so change detection can compare source fields too
            cur.execute("SELECT * FROM financial_classifier_gold_review")
            existing: dict[str, dict] = {r["benchmark_id"]: dict(r) for r in cur.fetchall()}

            inserted = 0
            updated = 0
            unchanged = 0

            for row in all_rows:
                bid = row["benchmark_id"]

                if bid not in existing:
                    # --- INSERT new row ----------------------------------------
                    cur.execute(
                        """
                        INSERT INTO financial_classifier_gold_review (
                            benchmark_id, ticker, publication_datetime,
                            previous_sentence, full_sentence, next_sentence,
                            detected_numeric_tokens, normalized_label,
                            seed_concept, seed_scope, seed_dilution,
                            seed_tax_basis, seed_capex_basis, seed_lease_inclusion,
                            seed_margin_denominator, seed_attribution,
                            seed_alias_role, seed_value_pattern,
                            seed_valuation_eligibility, seed_should_abstain,
                            gold_concept, gold_scope, gold_dilution,
                            gold_tax_basis, gold_capex_basis, gold_lease_inclusion,
                            gold_basis_evidence, gold_margin_denominator,
                            gold_attribution, gold_alias_role, gold_value_pattern,
                            gold_valuation_eligibility, gold_should_abstain,
                            reviewer_notes, review_decision
                        ) VALUES (
                            %(benchmark_id)s, %(ticker)s,
                            %(publication_datetime)s::timestamp,
                            %(previous_sentence)s, %(full_sentence)s,
                            %(next_sentence)s, %(detected_numeric_tokens)s,
                            %(normalized_label)s,
                            %(seed_concept)s, %(seed_scope)s, %(seed_dilution)s,
                            %(seed_tax_basis)s, %(seed_capex_basis)s,
                            %(seed_lease_inclusion)s, %(seed_margin_denominator)s,
                            %(seed_attribution)s, %(seed_alias_role)s,
                            %(seed_value_pattern)s, %(seed_valuation_eligibility)s,
                            %(seed_should_abstain)s,
                            %(gold_concept)s, %(gold_scope)s, %(gold_dilution)s,
                            %(gold_tax_basis)s, %(gold_capex_basis)s,
                            %(gold_lease_inclusion)s, %(gold_basis_evidence)s,
                            %(gold_margin_denominator)s, %(gold_attribution)s,
                            %(gold_alias_role)s, %(gold_value_pattern)s,
                            %(gold_valuation_eligibility)s, %(gold_should_abstain)s,
                            %(reviewer_notes)s, %(review_decision)s
                        )
                        """,
                        row,
                    )
                    inserted += 1

                else:
                    # --- UPDATE existing row -------------------------------------
                    db_row = existing[bid]
                    effective: dict = dict(row)

                    if not force_overwrite_reviewed:
                        for field in REVIEW_FIELD_COLUMNS:
                            db_val = db_row.get(field)
                            csv_val = row.get(field)
                            db_nonempty = not _none_or_empty(db_val)
                            csv_empty = _none_or_empty(csv_val)
                            if db_nonempty and csv_empty:
                                effective[field] = db_val

                    # Detect whether any change is actually needed
                    all_update_fields = SOURCE_FIELDS + list(REVIEW_FIELD_COLUMNS)
                    needs_update = any(
                        not _vals_equal(effective.get(f), db_row.get(f))
                        for f in all_update_fields
                    )

                    if not needs_update:
                        unchanged += 1
                        continue

                    cur.execute(
                        """
                        UPDATE financial_classifier_gold_review SET
                            ticker                  = %(ticker)s,
                            publication_datetime    = %(publication_datetime)s::timestamp,
                            previous_sentence       = %(previous_sentence)s,
                            full_sentence           = %(full_sentence)s,
                            next_sentence           = %(next_sentence)s,
                            detected_numeric_tokens = %(detected_numeric_tokens)s,
                            normalized_label        = %(normalized_label)s,
                            seed_concept            = %(seed_concept)s,
                            seed_scope              = %(seed_scope)s,
                            seed_dilution           = %(seed_dilution)s,
                            seed_tax_basis          = %(seed_tax_basis)s,
                            seed_capex_basis        = %(seed_capex_basis)s,
                            seed_lease_inclusion    = %(seed_lease_inclusion)s,
                            seed_margin_denominator = %(seed_margin_denominator)s,
                            seed_attribution        = %(seed_attribution)s,
                            seed_alias_role         = %(seed_alias_role)s,
                            seed_value_pattern      = %(seed_value_pattern)s,
                            seed_valuation_eligibility = %(seed_valuation_eligibility)s,
                            seed_should_abstain     = %(seed_should_abstain)s,
                            gold_concept            = %(gold_concept)s,
                            gold_scope              = %(gold_scope)s,
                            gold_dilution           = %(gold_dilution)s,
                            gold_tax_basis          = %(gold_tax_basis)s,
                            gold_capex_basis        = %(gold_capex_basis)s,
                            gold_lease_inclusion    = %(gold_lease_inclusion)s,
                            gold_basis_evidence     = %(gold_basis_evidence)s,
                            gold_margin_denominator = %(gold_margin_denominator)s,
                            gold_attribution        = %(gold_attribution)s,
                            gold_alias_role         = %(gold_alias_role)s,
                            gold_value_pattern      = %(gold_value_pattern)s,
                            gold_valuation_eligibility = %(gold_valuation_eligibility)s,
                            gold_should_abstain     = %(gold_should_abstain)s,
                            reviewer_notes          = %(reviewer_notes)s,
                            review_decision         = %(review_decision)s,
                            last_updated_at         = NOW()
                        WHERE benchmark_id = %(benchmark_id)s
                        """,
                        effective,
                    )
                    updated += 1

            conn.commit()

        print(
            f"\nImport complete:\n"
            f"  Inserted : {inserted}\n"
            f"  Updated  : {updated}\n"
            f"  Unchanged: {unchanged}\n"
            f"  Rejected : {len(rejected)}"
        )

    except Exception:
        conn.rollback()
        print("  ROLLED BACK: no changes were committed.", file=sys.stderr)
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import financial-classifier gold-review CSV into PostgreSQL."
    )
    parser.add_argument(
        "--csv",
        type=Path,
        required=True,
        help="Path to the gold-review CSV file.",
    )
    parser.add_argument(
        "--force-overwrite-reviewed",
        action="store_true",
        default=False,
        help=(
            "Explicit opt-in to allow overwriting non-blank review_decision, "
            "reviewer_notes, and gold_* fields with blank CSV values. "
            "NEVER enable this without explicit intention."
        ),
    )
    args = parser.parse_args()

    csv_path = args.csv.resolve()
    if not csv_path.exists():
        sys.exit(f"ERROR: CSV file not found: {csv_path}")

    run_import(csv_path, force_overwrite_reviewed=args.force_overwrite_reviewed)


if __name__ == "__main__":
    main()
