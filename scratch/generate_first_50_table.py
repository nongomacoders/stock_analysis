import json

with open("scratch/first_50_audit.json", "r", encoding="utf-8") as f:
    rows = json.load(f)

lines = []
lines.append("| benchmark_id | ticker | normalized_label | full_sentence | detected typed numeric tokens | seed_concept | seed_alias_role | seed_value_pattern | seed_valuation_eligibility | seed_should_abstain |")
lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")

for r in rows:
    sent_clean = r["full_sentence"].replace("|", "/").replace('"', '&quot;')
    if len(sent_clean) > 60:
        sent_clean = sent_clean[:57] + "..."
    toks_clean = r["detected_typed_tokens"].replace("|", "/")
    if len(toks_clean) > 50:
        toks_clean = toks_clean[:47] + "..."
    lines.append(
        f"| `{r['benchmark_id']}` | **{r['ticker']}** | `{r['normalized_label']}` | *\"{sent_clean}\"* | "
        f"`{toks_clean}` | `{r['seed_concept']}` | `{r['seed_alias_role']}` | `{r['seed_value_pattern']}` | "
        f"`{r['seed_valuation_eligibility']}` | `{r['seed_should_abstain']}` |"
    )

with open("scratch/first_50_table.md", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print("Generated scratch/first_50_table.md successfully!")
