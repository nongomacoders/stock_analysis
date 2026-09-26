from collections import defaultdict

from modules.analysis.financial_classifier_benchmark import load_benchmark_json, NumericTokenType, GUIDANCE_KEYWORDS

items = load_benchmark_json("gui/modules/analysis/data/financial_classifier_benchmark.json")
first_100 = items[:100]

print(f"Auditing first {len(first_100)} items...")

flagged = []

# Build ownership claims from the entire artifact so a first-100 item is checked
# against competing aliases even when the competing item falls outside the slice.
ownership_claims = defaultdict(list)
for candidate in items:
    source_key = (
        candidate.sens_id,
        candidate.sentence_start_offset,
        candidate.sentence_end_offset,
        candidate.full_sentence,
    )
    for role, token in (
        ('metric', candidate.candidate_metric_token),
        ('change', candidate.candidate_change_token),
    ):
        if token:
            ownership_claims[(source_key, token)].append(
                (candidate.benchmark_id, candidate.normalized_label, role)
            )

for it in first_100:
    b_id = it.benchmark_id
    issues = []
    
    # 1. Guidance / Context Leakage
    context_text = f"{it.previous_sentence or ''} {it.full_sentence} {it.next_sentence or ''}".lower()
    has_guidance_trigger = any(k in context_text for k in GUIDANCE_KEYWORDS)
    if has_guidance_trigger and it.seed_alias_role != "GUIDANCE_STATEMENT":
        # Check if it actually contains a forecast target or if it's past results announcement
        if any(w in it.full_sentence.lower() for w in ["will report", "expect to report", "anticipates that it will report", "expected to be"]):
            issues.append(f"Guidance leakage: Trigger in context but role is {it.seed_alias_role.value}")

    # 2. Section-number false positives
    for t in it.detected_typed_numeric_tokens:
        if t.token_type in (NumericTokenType.SECTION_NUMBER, NumericTokenType.LIST_MARKER):
            if it.seed_alias_role == "DIRECT_VALUE_LABEL" and len(it.detected_typed_numeric_tokens) == 1:
                issues.append(f"Section number {t.raw_text} satisfied numeric presence for DIRECT_VALUE_LABEL")

    # 3. Missed share-count integers
    if "shares in issue" in it.normalized_label or "ordinary shares" in it.normalized_label:
        if not it.detected_numeric_tokens and any(c.isdigit() for c in it.full_sentence):
            issues.append(f"Possible missed share count integer in: {it.full_sentence}")

    # 4. Aggregate / per-share mismatches
    if "per" in it.normalized_label and "share" in it.normalized_label:
        if it.seed_concept in {"headline_earnings", "earnings", "operating_profit", "trading_profit", "profit"}:
            issues.append(f"Aggregate concept {it.seed_concept} assigned to per-share label {it.normalized_label}")
    elif it.seed_concept in {"eps", "heps", "diluted_eps", "diluted_heps", "dividend_per_share", "nav_per_share"}:
        if "per" not in it.normalized_label and "share" not in it.normalized_label and "eps" not in it.normalized_label and "heps" not in it.normalized_label:
            issues.append(f"Per-share concept {it.seed_concept} assigned to aggregate label {it.normalized_label}")

    # 5. Incompatible numeric association
    is_margin = (it.seed_concept in {"gross_margin", "trading_margin", "operating_margin", "ebitda_margin"}) or ("margin" in it.normalized_label)
    if is_margin and it.candidate_metric_token:
        # Must be percentage
        if not ("%" in it.candidate_metric_token or "percent" in it.candidate_metric_token):
            issues.append(f"Incompatible margin metric token: {it.candidate_metric_token}")

    is_per_share = it.seed_concept in {"eps", "heps", "diluted_eps", "diluted_heps", "dividend_per_share", "nav_per_share"}
    if is_per_share and it.candidate_metric_token:
        if any(scale in it.candidate_metric_token.lower() for scale in ["million", "billion"]):
            issues.append(f"Incompatible per-share metric token (scaled currency): {it.candidate_metric_token}")

    # 6. Duplicate occurrence identity
    # (Checked globally across dataset)

    # 7. Cross-concept numeric-token ownership
    source_key = (
        it.sens_id,
        it.sentence_start_offset,
        it.sentence_end_offset,
        it.full_sentence,
    )
    for token in {it.candidate_metric_token, it.candidate_change_token} - {None}:
        claims = ownership_claims[(source_key, token)]
        competing = [claim for claim in claims if claim[0] != b_id and claim[1] != it.normalized_label]
        if competing:
            details = ', '.join(f'{label} ({role})' for _, label, role in competing)
            issues.append(f'Cross-concept ownership: {token} also claimed by {details}')

    if issues:
        flagged.append((b_id, it.ticker, it.normalized_label, it.seed_alias_role.value, it.candidate_metric_token, "; ".join(issues)))

print(f"Total flagged items in first 100: {len(flagged)}")
if flagged:
    print("| Benchmark ID | Ticker | Normalized Label | Role | Candidate Metric Token | Flagged Reason |")
    print("| :--- | :--- | :--- | :--- | :--- | :--- |")
    for f in flagged:
        print(f"| `{f[0]}` | **{f[1]}** | `{f[2]}` | `{f[3]}` | `{f[4]}` | {f[5]} |")
else:
    print("Zero integrity defects found in first 100 items.")
