# Phase 1: report evidence and assumption audit

This phase preserves generation requests and reports; it does not implement or
validate a DCF/SOTP valuation. Existing sector valuation formulas, model selection,
temperatures and price rounding are retained. Prompt changes disclose provenance,
units and the unverified status of historical reports. Gemini output remains
stochastic: an exact request can be reconstructed, but identical future responses
are not guaranteed. Target calculation reproducibility remains a warning until a
deterministic valuation model exists.

## Schema and installation

Run `gui/core/db/migrations/add_deepresearch_versions.sql` in a transaction before
using the updated generator or manual report editor. It is additive and repeatable:

- `deepresearch_versions` retains each attempt's UUID, ticker, generation timestamp,
  previous-context version, status, evidence path, input JSON, response JSON, report
  text, audit JSON and completion time.
- `stock_analysis.current_report_id` identifies the published current version.
  Existing `deepresearch` / `deepresearch_date` remain the GUI projection.
- Existing reports are snapshotted as `legacy`, explicitly without recovered
  generation provenance. The migration leaves their content and dates unchanged.
- Manual saves create `manual` versions. They are never represented as Gemini output.
- Publication and pointer updates are transactional. Failed/rejected attempts do
  not replace the current report. The application does not overwrite final versions.

`previous_report_id` refers to the report actually supplied as historical context.
`response.supersedes_report_id` records the current report replaced at publication;
these can differ when two generations overlap. `inputs.previous_report` retains the
exact historical text even if an older client edited it without updating its pointer.
An unversioned edit is also snapshotted at publication before replacing it.

## Evidence layout

`gui/report_evidence/<ticker>/<report UUID>/` is independent of scraper staging:

- `inputs.json`: ticker, timestamp, requested model/temperature, exact prompt,
  previous report and ID/date, source-set ID, source metadata, template text/hash,
  price context and share price/date. Commodity context includes source observation
  IDs, currency/unit, averaging period, original average, rounded supplied value,
  sample count and provider names.
- `prompt.txt`: exact prompt sent to Gemini.
- `sources/`: byte-for-byte copies of supplied text/PDF files, identified by IDs,
  original paths/names and SHA-256 hashes in the manifest. PDFs are sent from these
  copies; text payloads are rebuilt from the copies. PDF text extraction is used
  only to check citations and does not replace inline PDF inputs.
- `request_trace.json`: actual attempted models, temperatures, fallback/errors,
  and returned model version when available. No credentials are recorded.
- `result.json`: full serialised SDK response (including candidates/usage), response
  text, request trace, audit, publication status and error if applicable.

The database stores input/response JSON as well; PDF bytes live in the filesystem
archive. Back up **both PostgreSQL and report_evidence**. The evidence directory is
gitignored because reports and source documents can contain private information.
Generation no longer deletes staging inputs. Existing scraper cleanup cannot delete
the independent archive. No automatic archive retention/deletion policy is added.

If inference succeeds but publication fails, the raw response remains on disk with
pending status. Do not delete pending archives: they are recovery evidence. Archive
or database infrastructure failures can stop generation/publication; assumption
warnings do not. The schema must be installed, rather than falling back to an
unaudited report write.

## Audit interpretation

Every generated report requests a structured assumption array and receives an
application audit appendix. The original response is always retained unchanged.
The application extracts labelled values conservatively if JSON is absent/broken.
Multiple assets/scenarios can each have an entry. Unsupported source references or
quotes are not converted into authoritative facts. Citation checks verify a literal
source/excerpt/value match only; they do not prove semantic/accounting correctness.
Dates inferred from filenames are labelled as such. PDF extraction failure leaves
the PDF intact but prevents automatic quote verification.

Allowed classifications: `historical_actual`, `formal_guidance`,
`management_target`, `external_consensus`, `model_assumption`, `previous_report`,
`python_calculation`, `unresolved`. No Gemini target is labelled Python-calculated.

Warnings cover missing source/unit/date/classification, reliance on an earlier
report, WACC without inputs, unsupported growth/multiples, stale or mismatched
shares, and a target without a registered deterministic calculation. Share checks
compare explicit dated issued-capital disclosures with the report denominator.
Weighted-average shares can legitimately differ from issued shares: this warning
asks for a denominator review, not an automatic numerical correction.

SENS records retrieved only for stale-share checks are marked
`supplied_to_model: false`. They are preserved separately and must not be claimed
as inputs to the original generation. Identical supplied announcement text is
matched to its SENS ID/date where possible.

Historical price averaging still starts at the latest results **release date**,
uses collection timestamps and observation weighting, and retains the top-ten
selection. Currency/unit groups are separated to avoid averaging unlike units.
The prompt explicitly calls these historical averages rather than spot prices.

## Inspection and tests

Read-only inspection, with no Gemini call or report publication:

```powershell
python -B gui/scripts/inspect_valuation_audit.py --ticker JBL.JO --output tmp/jubilee_phase1_audit.json
python -B gui/scripts/inspect_valuation_audit.py --ticker JBL.JO --report-id <UUID>
python -B gui/scripts/inspect_valuation_audit.py --ticker JBL.JO --list-versions
python -B -m pytest gui/modules/analysis/tests -q
$env:RUN_PROVENANCE_DB_TESTS = '1'
python -B -m pytest gui/modules/analysis/tests/test_report_versions_db.py -q
```

The opt-in DB test uses an isolated, uniquely named schema inside a transaction and
rolls the entire transaction back. It does not modify live application tables.

The Jubilee regression fixture contains the actual stored 18 September 2026 report
and an exact excerpt from SENS 4955 (11 August 2026), exported read-only. It is not
a fabricated response to the new audit prompt. Its expected findings are:

| Assumption | Finding |
|---|---|
| Target ZAR1.70 | `previous_report`; report explicitly says maintained; not Python-calculated |
| Production 12,000 tonnes | `unresolved`; no recovered source/derivation |
| AISC US$5,950/t | `unresolved`; no recovered source/derivation |
| Shares 3,146,295,996 | source unresolved; newer issued count 3,381,330,240 in SENS 4955 |
| WACC 12% | unresolved and unsupported |
| Growth 5% | unresolved and unsupported |
| Exit multiple 6x | unresolved and unsupported |

This cannot recover the old prompt, original attachments, original model settings
or the report preceding that legacy report. Matching public numbers or reconstructed
price averages is not proof of what the old request contained. The inspection does
not invent these missing links or change the report's values.
