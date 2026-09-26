import psycopg2, json, re
from core.config import DB_CONFIG
from modules.analysis.financial_concept_dictionary import normalize_label
from modules.analysis.financial_classifier_benchmark import TRIGGER_WORDS, resolve_nested_alias_spans

conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor()
cur.execute('SELECT sens_id, ticker, publication_datetime, source_document_id, content FROM sens ORDER BY sens_id;')
rows = cur.fetchall()

dict_data = json.load(open('gui/modules/analysis/data/financial_concept_aliases.json', encoding='utf-8'))
alias_meta = {a['normalized_label']: a for a in dict_data['aliases']}
sorted_aliases = sorted(alias_meta.keys(), key=len, reverse=True)
alias_regexes = [(a, re.compile(r'(?i)\b' + re.escape(a).replace(r'\ ', r'\s+') + r'\b')) for a in sorted_aliases]

PER_SHARE_SUFFIX = re.compile(r'^\s+per\s+(?:ordinary\s+|weighted\s+average\s+|diluted\s+|ordinary\s+issued\s+)?shares?\b', re.IGNORECASE)

distinct_restored = 0
true_duplicate_spans = 0

seen_old = set()
seen_spans = set()
restored_examples = []

for sens_id, ticker, pub_dt, src_doc_id, content in rows:
    if not content or len(content) < 50:
        continue
    offset = 0
    lines = content.splitlines(keepends=True)
    for line_idx, line_raw in enumerate(lines):
        line_len = len(line_raw)
        line_clean = line_raw.strip()
        line_start = offset
        offset += line_len
        if not line_clean or len(line_clean) < 15 or len(line_clean) > 350:
            continue
        line_lower = line_clean.lower()
        if not any(tw in line_lower for tw in TRIGGER_WORDS):
            continue
        line_matches = []
        for norm_label, pat in alias_regexes:
            first_word = norm_label.split()[0]
            if first_word not in line_lower:
                continue
            for m in pat.finditer(line_clean):
                m_start, m_end = m.start(), m.end()
                matched_text = m.group(0)
                # Check per-share extension
                post_text = line_clean[m_end:]
                m_suff = PER_SHARE_SUFFIX.match(post_text)
                if m_suff and norm_label in {'headline earnings', 'earnings', 'profit', 'dividend', 'dividends', 'nav', 'net asset value'}:
                    m_end = m_end + m_suff.end()
                    matched_text = line_clean[m_start:m_end]
                    norm_label = normalize_label(matched_text)
                line_matches.append((m_start, m_end, norm_label, matched_text))
        if not line_matches:
            continue
        resolved = resolve_nested_alias_spans(line_matches)
        for m_s, m_e, n_lbl, r_found in resolved:
            abs_start = line_start + m_s
            abs_end = line_start + m_e
            old_key = (sens_id, line_clean, n_lbl)
            span_key = (sens_id, abs_start, abs_end, n_lbl)
            if span_key in seen_spans:
                true_duplicate_spans += 1
                continue
            seen_spans.add(span_key)
            if old_key in seen_old:
                distinct_restored += 1
                if len(restored_examples) < 10:
                    restored_examples.append((sens_id, line_idx, abs_start, line_clean, n_lbl))
            seen_old.add(old_key)

print(f'Distinct occurrences restored: {distinct_restored}')
print(f'True duplicate spans: {true_duplicate_spans}')
print('Sample restored examples:')
for ex in restored_examples:
    print(ex)
