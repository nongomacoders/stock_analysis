# Financial Classifier Gold Benchmark — Review Batch 001 (Deterministic Heuristic Baseline)

This artifact presents stratified SENS items for manual expert review.
Deterministic heuristic values are preserved as `seed_*` for reference.
The reviewer must confirm or correct the `gold_*` fields. Items remain in `REVIEW_REQUIRED` until confirmed.

## Review Instructions
1. **Gold Concept**: Canonical concept ID (e.g. `accounting_revenue`, `trading_profit`, `eps`) or `None` if invalid/discursive.
2. **Gold Qualifiers**: Explicit qualifiers (e.g. `scope=continuing_operations`, `tax_basis=gross`).
3. **Gold Alias Role**: `DIRECT_VALUE_LABEL`, `CHANGE_STATEMENT`, `GUIDANCE_STATEMENT`, or `CONCEPT_MENTION_ONLY`.
4. **Gold Value Pattern**: `DIRECT_LEVEL`, `CHANGE_RATE_ONLY`, `CHANGE_RATE_TO_LEVEL`, `FROM_TO_LEVEL`, `RANGE`, or `UNKNOWN`.
5. **Gold Valuation Eligibility**: `ELIGIBLE`, `ELIGIBLE_WITH_QUALIFIER`, `REQUIRES_SCOPE`, `REQUIRES_BASIS`, `REQUIRES_PERIOD`, `REQUIRES_SOURCE_SECTION`, `INFORMATIONAL_ONLY`, or `PROHIBITED`.
6. **Should Abstain**: `True` if metric cannot safely be extracted without additional external context.

## Batch Summary (Total: 178 items)
- **Distinct Tickers**: 37
- **Distinct Labels**: 82

---

### Item 001 — [`BENCH-0001`] **LAB.JO** (2025-11-14 16:40)
- **Detected Label**: `taxation` (normalized: `taxation`)
- **Section Heading**: *Other Salient Information*
- **Prior Sentence**: *"Commission or the Takeover Regulation Panel. Normal warranties have been provided, with each"*
- **Target Sentence**: **"party remaining responsible for its own taxation. No assets associated with the Disposal have been"**
- **Next Sentence**: *"pledged or ceded."*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `A. Easy/direct`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'taxation' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 002 — [`BENCH-0002`] **ATT.JO** (2025-11-14 15:30)
- **Detected Label**: `number of shares in issue` (normalized: `number of shares in issue`)
- **Section Heading**: *Details of the results of voting at the annual general meeting are as follows:*
- **Prior Sentence**: *"Details of the results of voting at the annual general meeting are as follows:"*
- **Target Sentence**: **"– total number of shares in issue as at the date of the annual general meeting: 746 198 337"**
- **Next Sentence**: *"– total number of shares that could have been voted at the annual general meeting, excluding 46 427 553 treasury"*
- **Detected Numbers**: `['746 198 337']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `REQUIRES_PERIOD`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Ambiguous share wording 'number of shares in issue' lacks point-in-time vs period-end vs WANOS specification; requires period*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 003 — [`BENCH-0006`] **EPS.JO** (2025-11-14 14:45)
- **Detected Label**: `EPS` (normalized: `eps`)
- **Section Heading**: *Share Code TSX: ELR ISIN: CA2768555096*
- **Prior Sentence**: *"Share Code TSX: ELR ISIN: CA2768555096"*
- **Target Sentence**: **"Share Code JSE: EPS ISIN: CA2768555096"**
- **Next Sentence**: *"(‘Eastplats’ or the ‘Company’)"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `A. Easy/direct`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'eps' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 004 — [`BENCH-0008`] **EPS.JO** (2025-11-14 14:45)
- **Detected Label**: `Revenue` (normalized: `revenue`)
- **Section Heading**: *in USD unless specified):*
- **Prior Sentence**: *"in USD unless specified):"*
- **Target Sentence**: **"•   Revenue for Q3 2025 increased to $13.7 million (Q3 2024 – $11.0 million), representing a $2.7"**
- **Next Sentence**: *"million or 24.5% increase. Revenue for YTD 2025 decreased to $39.3 million (YTD 2024 – $45.5"*
- **Detected Numbers**: `['2025', '$13.7 million', '2024', '$11.0 million', '$2.7']`
- **Difficulty Category**: `B. Change statements`

**Deterministic Seed Baseline:**
- Seed Concept: `accounting_revenue`
- Seed Qualifiers: `{'scope': <OperationScope.GROUP_CONSOLIDATED: 'group_consolidated'>, 'sign': <NumericSign.POSITIVE: 'positive'>}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE_WITH_QUALIFIER`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'accounting_revenue' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 005 — [`BENCH-0010`] **EPS.JO** (2025-11-14 14:45)
- **Detected Label**: `operating loss decreased by` (normalized: `operating loss decreased by`)
- **Prior Sentence**: *"million), representing a $6.2 million or 13.6% decrease."*
- **Target Sentence**: **"•   Mine operating loss decreased by $0.8 million (or -80.0%) to $0.2 million in Q3 2025 (Q3 2024 –"**
- **Next Sentence**: *"mine operating loss of $1.0 million) as gross margin improved to -1.8% in Q3 2025 from -9.4% in"*
- **Detected Numbers**: `['$0.8 million', '-80.0%', '$0.2 million', '2025', '2024']`
- **Difficulty Category**: `B. Change statements`

**Deterministic Seed Baseline:**
- Seed Concept: `operating_profit`
- Seed Qualifiers: `{'sign': <NumericSign.NEGATIVE: 'negative'>}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `CHANGE_RATE_TO_LEVEL`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Change reporting sentence with rate-to-level compound structure*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 006 — [`BENCH-0012`] **EPS.JO** (2025-11-14 14:45)
- **Detected Label**: `gross margin improved to` (normalized: `gross margin improved to`)
- **Prior Sentence**: *"•   Mine operating loss decreased by $0.8 million (or -80.0%) to $0.2 million in Q3 2025 (Q3 2024 –"*
- **Target Sentence**: **"mine operating loss of $1.0 million) as gross margin improved to -1.8% in Q3 2025 from -9.4% in"**
- **Next Sentence**: *"Q3 2024. Mine operating income in YTD 2025 decreased by $13.3 million (or -152.9%) to mine"*
- **Detected Numbers**: `['$1.0 million', '-1.8%', '2025', '-9.4%']`
- **Difficulty Category**: `D. Basis ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `gross_margin`
- Seed Qualifiers: `{'margin_denominator': <MarginDenominator.ACCOUNTING_REVENUE: 'accounting_revenue'>}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `FROM_TO_LEVEL`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Change reporting sentence with from-to level compound structure*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 007 — [`BENCH-0017`] **EPS.JO** (2025-11-14 14:45)
- **Detected Label**: `Operating loss` (normalized: `operating loss`)
- **Prior Sentence**: *"a reduced gross margin of -11.6% in YTD 2025 from 19.1% in YTD 2024."*
- **Target Sentence**: **"•   Operating loss was $3.4 million in Q3 2025 compared to an operating loss of $5.7 million in Q3"**
- **Next Sentence**: *"2024. Operating loss was $14.5 million in YTD 2025 compared to an operating loss of $4.1 million"*
- **Detected Numbers**: `['$3.4 million', '2025', '$5.7 million']`
- **Difficulty Category**: `A. Easy/direct`

**Deterministic Seed Baseline:**
- Seed Concept: `operating_profit`
- Seed Qualifiers: `{'sign': <NumericSign.NEGATIVE: 'negative'>}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'operating_profit' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 008 — [`BENCH-0019`] **EPS.JO** (2025-11-14 14:45)
- **Detected Label**: `loss per share` (normalized: `loss per share`)
- **Section Heading**: *in YTD 2024.*
- **Prior Sentence**: *"in YTD 2024."*
- **Target Sentence**: **"•   Net loss attributable to equity shareholders was $2.2 million ($0.01 loss per share) in Q3 2025"**
- **Next Sentence**: *"versus net loss attributable to equity shareholders of $3.4 million ($0.02 loss per share) in Q3"*
- **Detected Numbers**: `['$2.2 million', '$0.01', '2025']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `eps`
- Seed Qualifiers: `{'dilution': <DilutionBasis.BASIC: 'basic'>, 'sign': <NumericSign.NEGATIVE: 'negative'>, 'metric_basis': <MetricBasis.REPORTED_STATUTORY: 'reported_statutory'>}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE_WITH_QUALIFIER`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'eps' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 009 — [`BENCH-0021`] **EPS.JO** (2025-11-14 14:45)
- **Detected Label**: `revenue` (normalized: `revenue`)
- **Prior Sentence**: *"2024. The decrease in Q3 2025 net loss was largely attributable to the significantly increased"*
- **Target Sentence**: **"revenue derived from platinum group metal (‘PGM’) sales during the period."**
- **Next Sentence**: *"•   Net loss attributable to equity shareholders was $10.9 million ($0.05 loss per share) in YTD 2025"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `A. Easy/direct`

**Deterministic Seed Baseline:**
- Seed Concept: `accounting_revenue`
- Seed Qualifiers: `{'scope': <OperationScope.GROUP_CONSOLIDATED: 'group_consolidated'>, 'sign': <NumericSign.POSITIVE: 'positive'>}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'revenue' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 010 — [`BENCH-0022`] **EPS.JO** (2025-11-14 14:45)
- **Detected Label**: `sales` (normalized: `sales`)
- **Prior Sentence**: *"2024. The decrease in Q3 2025 net loss was largely attributable to the significantly increased"*
- **Target Sentence**: **"revenue derived from platinum group metal (‘PGM’) sales during the period."**
- **Next Sentence**: *"•   Net loss attributable to equity shareholders was $10.9 million ($0.05 loss per share) in YTD 2025"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `C. Scope ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'sales' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 011 — [`BENCH-0026`] **CCC.JO** (2025-11-14 14:21)
- **Detected Label**: `basic loss per share` (normalized: `basic loss per share`)
- **Section Heading**: *ended 30 September 2025 (‘interim results’) and anticipates that it will report:*
- **Prior Sentence**: *"ended 30 September 2025 (‘interim results’) and anticipates that it will report:"*
- **Target Sentence**: **"–   a basic loss per share of between 138.30 cents and 138.48 cents, compared to the basic earnings"**
- **Next Sentence**: *"per share of 0.87 cents for the previous corresponding period, which represents an expected"*
- **Detected Numbers**: `['138.30 cents', '138.48 cents']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `eps`
- Seed Qualifiers: `{'dilution': <DilutionBasis.BASIC: 'basic'>, 'sign': <NumericSign.NEGATIVE: 'negative'>, 'metric_basis': <MetricBasis.REPORTED_STATUTORY: 'reported_statutory'>}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE_WITH_QUALIFIER`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'eps' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 012 — [`BENCH-0028`] **CCC.JO** (2025-11-14 14:21)
- **Detected Label**: `headline loss per share` (normalized: `headline loss per share`)
- **Section Heading**: *decrease in excess of 100%; and*
- **Prior Sentence**: *"decrease in excess of 100%; and"*
- **Target Sentence**: **"–   a headline loss per share of between 138.30 cents and 138.48 cents compared to the headline"**
- **Next Sentence**: *"earnings per share of 0.87 cents for the previous corresponding period, which represents an expected"*
- **Detected Numbers**: `['138.30 cents', '138.48 cents']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `heps`
- Seed Qualifiers: `{'dilution': <DilutionBasis.BASIC: 'basic'>, 'attribution': <ProfitAttribution.HEADLINE_ATTRIBUTABLE: 'headline_attributable'>, 'sign': <NumericSign.NEGATIVE: 'negative'>, 'metric_basis': <MetricBasis.HEADLINE: 'headline'>}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE_WITH_QUALIFIER`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'heps' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 013 — [`BENCH-0030`] **CCC.JO** (2025-11-14 14:21)
- **Detected Label**: `earnings per share` (normalized: `earnings per share`)
- **Section Heading**: *decrease in excess of 100%; and*
- **Prior Sentence**: *"–   a headline loss per share of between 138.30 cents and 138.48 cents compared to the headline"*
- **Target Sentence**: **"earnings per share of 0.87 cents for the previous corresponding period, which represents an expected"**
- **Next Sentence**: *"decrease in excess of 100%."*
- **Detected Numbers**: `['0.87 cents']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `eps`
- Seed Qualifiers: `{'dilution': <DilutionBasis.BASIC: 'basic'>}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE_WITH_QUALIFIER`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'eps' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 014 — [`BENCH-0031`] **CCC.JO** (2025-11-14 14:21)
- **Detected Label**: `headline earnings per share for the period` (normalized: `headline earnings per share for the period`)
- **Prior Sentence**: *"of R217 480 665. These non-recurring costs have been the primary contributor to the decrease in earnings"*
- **Target Sentence**: **"and headline earnings per share for the period under review."**
- **Next Sentence**: *"The financial information on which this trading statement is based has not been reviewed or reported on"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `heps`
- Seed Qualifiers: `{'dilution': <DilutionBasis.BASIC: 'basic'>, 'attribution': <ProfitAttribution.HEADLINE_ATTRIBUTABLE: 'headline_attributable'>, 'metric_basis': <MetricBasis.HEADLINE: 'headline'>}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'headline earnings per share for the period' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 015 — [`BENCH-0035`] **KAP.JO** (2025-11-14 13:00)
- **Detected Label**: `working capital` (normalized: `working capital`)
- **Section Heading**: *4.     DISPOSAL CONSIDERATION*
- **Prior Sentence**: *"consideration equal to an aggregate amount of R138 million plus the carrying value of certain vehicles, as"*
- **Target Sentence**: **"well as the value of the net working capital and cash on hand of USH and its wholly subsidiary as at the"**
- **Next Sentence**: *"Effective Date (as defined in paragraph 6.3 below) (‘Disposal Consideration’)."*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `D. Basis ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'working capital' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 016 — [`BENCH-0036`] **KAP.JO** (2025-11-14 13:00)
- **Detected Label**: `capital expenditure` (normalized: `capital expenditure`)
- **Prior Sentence**: *"(‘Delayed Portion’) being settled in cash by the Purchaser within 95 days of the Effective Date."*
- **Target Sentence**: **"4.4.      The Disposal Consideration will be utilised by Unitrans as part of capital expenditure for the replacement"**
- **Next Sentence**: *"of its existing assets."*
- **Detected Numbers**: `['4.4']`
- **Difficulty Category**: `G. Capex ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `REQUIRES_BASIS`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Ambiguous wording 'capital expenditure' lacks accounting basis (cash vs additions, movement vs balance); requires basis*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 017 — [`BENCH-0037`] **CMH.JO** (2025-11-14 12:00)
- **Detected Label**: `taxation` (normalized: `taxation`)
- **Prior Sentence**: *"jurisdiction applicable to such Shareholder."*
- **Target Sentence**: **"4.3  Shareholders should therefore take their own advice on the taxation effects of"**
- **Next Sentence**: *"the Share Repurchase offer."*
- **Detected Numbers**: `['4.3']`
- **Difficulty Category**: `A. Easy/direct`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `REQUIRES_SOURCE_SECTION`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Ambiguous wording 'taxation' lacks balance sheet vs note presentation; requires source section*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 018 — [`BENCH-0039`] **BYI.JO** (2025-11-14 09:30)
- **Detected Label**: `Ordinary Shares in issue` (normalized: `ordinary shares in issue`)
- **Prior Sentence**: *"BTG intends to cancel all of the purchased shares. Following settlement of the above purchases and cancellation of the"*
- **Target Sentence**: **"purchased Ordinary Shares, the Company’s total number of Ordinary Shares in issue, and its total voting rights, will be"**
- **Next Sentence**: *"236,968,629 Ordinary Shares. The Company does not hold any shares in treasury."*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `issued_shares_current`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'ordinary shares in issue' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 019 — [`BENCH-0041`] **BTI.JO** (2025-11-14 09:00)
- **Detected Label**: `ordinary shares in issue` (normalized: `ordinary shares in issue`)
- **Section Heading**: *(pence):*
- **Prior Sentence**: *"Following the purchase and cancellation of these shares, the Company will have"*
- **Target Sentence**: **"2,182,962,115 ordinary shares in issue (excluding treasury shares) which carry voting rights"**
- **Next Sentence**: *"and will hold 132,998,061 ordinary shares in treasury. This information may be used by"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `issued_shares_current`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'ordinary shares in issue' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 020 — [`BENCH-0042`] **BTI.JO** (2025-11-14 09:00)
- **Detected Label**: `treasury shares` (normalized: `treasury shares`)
- **Section Heading**: *(pence):*
- **Prior Sentence**: *"Following the purchase and cancellation of these shares, the Company will have"*
- **Target Sentence**: **"2,182,962,115 ordinary shares in issue (excluding treasury shares) which carry voting rights"**
- **Next Sentence**: *"and will hold 132,998,061 ordinary shares in treasury. This information may be used by"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `treasury_shares`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'treasury shares' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 021 — [`BENCH-0044`] **CFR.JO** (2025-11-14 08:00)
- **Detected Label**: `sales` (normalized: `sales`)
- **Target Sentence**: **"Richemont delivers solid results for the six-month period ended 30 September 2025 with strong sales momentum in Q2"**
- **Next Sentence**: *"Compagnie Financière Richemont SA"*
- **Detected Numbers**: `['30', '2025']`
- **Difficulty Category**: `C. Scope ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'sales' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 022 — [`BENCH-0045`] **CFR.JO** (2025-11-14 08:00)
- **Detected Label**: `SALES` (normalized: `sales`)
- **Section Heading**: *FOR THE SIX-MONTH PERIOD ENDED 30 SEPTEMBER 2025*
- **Prior Sentence**: *"FOR THE SIX-MONTH PERIOD ENDED 30 SEPTEMBER 2025"*
- **Target Sentence**: **"WITH STRONG SALES MOMENTUM IN Q2"**
- **Next Sentence**: *"Group highlights"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `C. Scope ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'sales' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 023 — [`BENCH-0046`] **CFR.JO** (2025-11-14 08:00)
- **Detected Label**: `Group sales` (normalized: `group sales`)
- **Section Heading**: *Group highlights*
- **Prior Sentence**: *"Group highlights"*
- **Target Sentence**: **"* Group sales at EUR 10.6 billion with 10% growth at constant rates"**
- **Next Sentence**: *"(+5% actual); Q2 acceleration to +14%"*
- **Detected Numbers**: `['EUR 10.6 billion', '10%']`
- **Difficulty Category**: `B. Change statements`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{'scope': <OperationScope.GROUP_CONSOLIDATED: 'group_consolidated'>}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `CHANGE_RATE_TO_LEVEL`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Change reporting sentence with rate-to-level compound structure*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 024 — [`BENCH-0048`] **CFR.JO** (2025-11-14 08:00)
- **Detected Label**: `operating profit` (normalized: `operating profit`)
- **Section Heading**: *(+5% actual); Q2 acceleration to +14%*
- **Prior Sentence**: *"(+5% actual); Q2 acceleration to +14%"*
- **Target Sentence**: **"* Growth in operating profit to EUR 2.4 billion underpinned by strong"**
- **Next Sentence**: *"sales contribution and continued cost discipline, mitigating the impact of"*
- **Detected Numbers**: `['EUR 2.4 billion']`
- **Difficulty Category**: `H. Profit/EBIT/trading-profit ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{'sign': <NumericSign.POSITIVE: 'positive'>}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `REQUIRES_SCOPE`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Ambiguous wording 'operating profit' conflates operating definitions or segments; requires scope*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 025 — [`BENCH-0050`] **CFR.JO** (2025-11-14 08:00)
- **Detected Label**: `gross margin` (normalized: `gross margin`)
- **Section Heading**: *(+5% actual); Q2 acceleration to +14%*
- **Prior Sentence**: *"sales contribution and continued cost discipline, mitigating the impact of"*
- **Target Sentence**: **"macroeconomic headwinds on gross margin in the first half"**
- **Next Sentence**: *"* Robust financial position supporting persistent focus on nurturing Maisons’"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `D. Basis ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `gross_margin`
- Seed Qualifiers: `{'margin_denominator': <MarginDenominator.ACCOUNTING_REVENUE: 'accounting_revenue'>}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'gross margin' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 026 — [`BENCH-0051`] **CFR.JO** (2025-11-14 08:00)
- **Detected Label**: `Operating profit up by` (normalized: `operating profit up by`)
- **Section Heading**: *local demand*
- **Prior Sentence**: *"local demand"*
- **Target Sentence**: **"* Operating profit up by 7%, or by 24% at constant exchange rates, resulting"**
- **Next Sentence**: *"in a 22.2% operating margin"*
- **Detected Numbers**: `['7%', '24%']`
- **Difficulty Category**: `H. Profit/EBIT/trading-profit ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{'sign': <NumericSign.POSITIVE: 'positive'>}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `CHANGE_RATE_ONLY`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Change / directional reporting sentence with percentage-only rate; ineligible as absolute historical baseline*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 027 — [`BENCH-0053`] **CFR.JO** (2025-11-14 08:00)
- **Detected Label**: `operating margin` (normalized: `operating margin`)
- **Section Heading**: *local demand*
- **Prior Sentence**: *"* Operating profit up by 7%, or by 24% at constant exchange rates, resulting"*
- **Target Sentence**: **"in a 22.2% operating margin"**
- **Next Sentence**: *"* Strong demand fuelling Jewellery Maisons’ growth, with sales up 9% at actual"*
- **Detected Numbers**: `['22.2%']`
- **Difficulty Category**: `D. Basis ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `operating_margin`
- Seed Qualifiers: `{}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `REQUIRES_BASIS`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Margin concept 'operating margin' lacks explicit denominator in source text; requires basis*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 028 — [`BENCH-0059`] **CFR.JO** (2025-11-14 08:00)
- **Detected Label**: `operating loss` (normalized: `operating loss`)
- **Section Heading**: *in Q2); operating margin at 3.2%*
- **Prior Sentence**: *"exchange rates (at constant exchange rates: +2% in H1, +6% in Q2);"*
- **Target Sentence**: **"EUR 42 million operating loss"**
- **Next Sentence**: *"* EUR 1.8 billion profit for the period, driven by continuing operations and"*
- **Detected Numbers**: `['EUR 42 million']`
- **Difficulty Category**: `A. Easy/direct`

**Deterministic Seed Baseline:**
- Seed Concept: `operating_profit`
- Seed Qualifiers: `{'sign': <NumericSign.NEGATIVE: 'negative'>}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'operating_profit' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 029 — [`BENCH-0060`] **CFR.JO** (2025-11-14 08:00)
- **Detected Label**: `profit for the period` (normalized: `profit for the period`)
- **Section Heading**: *EUR 42 million operating loss*
- **Prior Sentence**: *"EUR 42 million operating loss"*
- **Target Sentence**: **"* EUR 1.8 billion profit for the period, driven by continuing operations and"**
- **Next Sentence**: *"non-recurrence of the prior-year period loss from discontinued operations"*
- **Detected Numbers**: `['EUR 1.8 billion']`
- **Difficulty Category**: `A. Easy/direct`

**Deterministic Seed Baseline:**
- Seed Concept: `profit_for_period`
- Seed Qualifiers: `{'scope': <OperationScope.GROUP_CONSOLIDATED: 'group_consolidated'>, 'attribution': <ProfitAttribution.TOTAL_GROUP: 'total_group'>, 'sign': <NumericSign.POSITIVE: 'positive'>}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE_WITH_QUALIFIER`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'profit_for_period' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 030 — [`BENCH-0061`] **CFR.JO** (2025-11-14 08:00)
- **Detected Label**: `Net cash position` (normalized: `net cash position`)
- **Section Heading**: *EUR 42 million operating loss*
- **Prior Sentence**: *"non-recurrence of the prior-year period loss from discontinued operations"*
- **Target Sentence**: **"* Net cash position of EUR 6.5 billion, with EUR 1.9 billion cash flow generated"**
- **Next Sentence**: *"from operating activities and after EUR 0.6 billion cash transferred upon"*
- **Detected Numbers**: `['EUR 6.5 billion', 'EUR 1.9 billion']`
- **Difficulty Category**: `A. Easy/direct`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `REQUIRES_SCOPE`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Ambiguous wording 'net cash position'; maps to multiple concepts; requires context*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 031 — [`BENCH-0063`] **CFR.JO** (2025-11-14 08:00)
- **Detected Label**: `Sales` (normalized: `sales`)
- **Section Heading**: *+——————————–+—————+————–+———-+*
- **Prior Sentence**: *"+——————————–+—————+————–+———-+"*
- **Target Sentence**: **"|Sales				 |    EUR 10 619m|   EUR 10 077m|       +5%|"**
- **Next Sentence**: *"+——————————–+—————+————–+———-+"*
- **Detected Numbers**: `['EUR 10 619m', 'EUR 10 077m', '+5%']`
- **Difficulty Category**: `C. Scope ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `REQUIRES_SCOPE`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Ambiguous wording 'sales' conflates operating definitions or segments; requires scope*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 032 — [`BENCH-0064`] **ANH.JO** (2025-11-14 07:35)
- **Detected Label**: `revenue` (normalized: `revenue`)
- **Prior Sentence**: *"the collective strengths of approximately 144 000 colleagues based in nearly 50 countries worldwide. For 2024, AB InBev’s"*
- **Target Sentence**: **"reported revenue was 59.8 billion USD (excluding JVs and associates)."**
- **Next Sentence**: *"Anheuser-Busch InBev Contacts"*
- **Detected Numbers**: `['59.8 billion']`
- **Difficulty Category**: `A. Easy/direct`

**Deterministic Seed Baseline:**
- Seed Concept: `accounting_revenue`
- Seed Qualifiers: `{'scope': <OperationScope.GROUP_CONSOLIDATED: 'group_consolidated'>, 'sign': <NumericSign.POSITIVE: 'positive'>}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE_WITH_QUALIFIER`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'accounting_revenue' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 033 — [`BENCH-0065`] **SOL.JO** (2025-11-13 16:48)
- **Detected Label**: `taxation` (normalized: `taxation`)
- **Section Heading**: *2*
- **Prior Sentence**: *"2"*
- **Target Sentence**: **"In terms of the MSR policy, Directors and Prescribed Officers may sell vested shares to cover the taxation and transaction cost on the LTI"**
- **Next Sentence**: *"award."*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `A. Easy/direct`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'taxation' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 034 — [`BENCH-0066`] **ITE.JO** (2025-11-13 15:40)
- **Detected Label**: `treasury shares` (normalized: `treasury shares`)
- **Section Heading**: *authority to issue shares, and to sell*
- **Prior Sentence**: *"authority to issue shares, and to sell"*
- **Target Sentence**: **"treasury shares, for cash                           1 044 828 732        79.05         90.76          9.24         0.42"**
- **Next Sentence**: *"Special Resolution No 1: Acquisition of"*
- **Detected Numbers**: `['1 044 828 732', '79.05', '90.76', '9.24', '0.42']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `treasury_shares`
- Seed Qualifiers: `{}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'treasury_shares' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 035 — [`BENCH-0067`] **ITE.JO** (2025-11-13 15:40)
- **Detected Label**: `shares in issue` (normalized: `shares in issue`)
- **Section Heading**: *Ordinary Resolution No 9: Authority to*
- **Prior Sentence**: *"sign documentation                                  1 109 614 986        83.96        100.00          0.00         0.42"*
- **Target Sentence**: **"1Based on 1 321 654 148 shares in issue at the date of the annual general meeting."**
- **Next Sentence**: *"2Disclosed as a percentage of voteable shares."*
- **Detected Numbers**: `['1', '1 321 654 148']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `REQUIRES_PERIOD`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Ambiguous share wording 'shares in issue' lacks point-in-time vs period-end vs WANOS specification; requires period*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 036 — [`BENCH-0068`] **ITE.JO** (2025-11-13 15:40)
- **Detected Label**: `turnover for the period` (normalized: `turnover for the period`)
- **Prior Sentence**: *"remains constrained. The market has continued to experience pressure from low priced imports causing a decline"*
- **Target Sentence**: **"in revenue at Ceramic Industries. As a result, the Group’s systemwide turnover for the period was 1% lower year on"**
- **Next Sentence**: *"year."*
- **Detected Numbers**: `['1%']`
- **Difficulty Category**: `B. Change statements`

**Deterministic Seed Baseline:**
- Seed Concept: `turnover`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `CHANGE_RATE_ONLY`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Change / directional reporting sentence with percentage-only rate; ineligible as absolute historical baseline*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 037 — [`BENCH-0070`] **ITE.JO** (2025-11-13 15:40)
- **Detected Label**: `revenue` (normalized: `revenue`)
- **Prior Sentence**: *"remains constrained. The market has continued to experience pressure from low priced imports causing a decline"*
- **Target Sentence**: **"in revenue at Ceramic Industries. As a result, the Group’s systemwide turnover for the period was 1% lower year on"**
- **Next Sentence**: *"year."*
- **Detected Numbers**: `['1%']`
- **Difficulty Category**: `B. Change statements`

**Deterministic Seed Baseline:**
- Seed Concept: `accounting_revenue`
- Seed Qualifiers: `{'scope': <OperationScope.GROUP_CONSOLIDATED: 'group_consolidated'>, 'sign': <NumericSign.POSITIVE: 'positive'>}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `CHANGE_RATE_ONLY`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Change / directional reporting sentence with percentage-only rate; ineligible as absolute historical baseline*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 038 — [`BENCH-0071`] **SLM.JO** (2025-11-13 14:26)
- **Detected Label**: `operating profit` (normalized: `operating profit`)
- **Prior Sentence**: *"The naming conventions and definitions of key earnings metrics have been revised. Effective 1 January"*
- **Target Sentence**: **"2026, net result from financial services (NRFFS) will be replaced with operating profit, and net operational"**
- **Next Sentence**: *"earnings with adjusted headline earnings. Both measures remove Sanlam-specific shareholders’ fund"*
- **Detected Numbers**: `['2026']`
- **Difficulty Category**: `H. Profit/EBIT/trading-profit ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{'sign': <NumericSign.POSITIVE: 'positive'>}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'operating profit' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 039 — [`BENCH-0072`] **SLM.JO** (2025-11-13 14:26)
- **Detected Label**: `headline earnings` (normalized: `headline earnings`)
- **Prior Sentence**: *"2026, net result from financial services (NRFFS) will be replaced with operating profit, and net operational"*
- **Target Sentence**: **"earnings with adjusted headline earnings. Both measures remove Sanlam-specific shareholders’ fund"**
- **Next Sentence**: *"adjustments and reflect full investment market movements, resulting in greater period-to-period volatility. In"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `A. Easy/direct`

**Deterministic Seed Baseline:**
- Seed Concept: `headline_earnings`
- Seed Qualifiers: `{'attribution': <ProfitAttribution.HEADLINE_ATTRIBUTABLE: 'headline_attributable'>, 'metric_basis': <MetricBasis.HEADLINE: 'headline'>}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'headline earnings' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 040 — [`BENCH-0075`] **SLM.JO** (2025-11-13 14:26)
- **Detected Label**: `Operating profit` (normalized: `operating profit`)
- **Prior Sentence**: *"Future financial reporting framework (with effect 1 January 2026)"*
- **Target Sentence**: **"–   Operating profit excluding investment variances2                                 2%              18%"**
- **Next Sentence**: *"–   Operating profit                                                                (3%)             10%"*
- **Detected Numbers**: `['2%', '18%']`
- **Difficulty Category**: `H. Profit/EBIT/trading-profit ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{'sign': <NumericSign.POSITIVE: 'positive'>}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `CHANGE_RATE_ONLY`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Change / directional reporting sentence with percentage-only rate; ineligible as absolute historical baseline*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 041 — [`BENCH-0082`] **BID.JO** (2025-08-27 10:00)
- **Detected Label**: `Revenue` (normalized: `revenue`)
- **Section Heading**: *Financial highlights:*
- **Prior Sentence**: *"Financial highlights:"*
- **Target Sentence**: **"-       Revenue R235,6 billion, up 4,3%; up 6,8% in constant currency"**
- **Next Sentence**: *"-       Trading profit R12,9 billion, up 6,4%; up 9,3% in constant currency"*
- **Detected Numbers**: `['R235,6 billion', '4,3%', '6,8%']`
- **Difficulty Category**: `A. Easy/direct`

**Deterministic Seed Baseline:**
- Seed Concept: `accounting_revenue`
- Seed Qualifiers: `{'scope': <OperationScope.GROUP_CONSOLIDATED: 'group_consolidated'>, 'sign': <NumericSign.POSITIVE: 'positive'>}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE_WITH_QUALIFIER`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'accounting_revenue' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 042 — [`BENCH-0083`] **BID.JO** (2025-08-27 10:00)
- **Detected Label**: `Trading profit` (normalized: `trading profit`)
- **Section Heading**: *Financial highlights:*
- **Prior Sentence**: *"-       Revenue R235,6 billion, up 4,3%; up 6,8% in constant currency"*
- **Target Sentence**: **"-       Trading profit R12,9 billion, up 6,4%; up 9,3% in constant currency"**
- **Next Sentence**: *"-       Cash generated by operations before working capital R16,6 billion, up 7,5%"*
- **Detected Numbers**: `['R12,9 billion', '6,4%', '9,3%']`
- **Difficulty Category**: `H. Profit/EBIT/trading-profit ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `trading_profit`
- Seed Qualifiers: `{'sign': <NumericSign.POSITIVE: 'positive'>}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'trading_profit' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 043 — [`BENCH-0084`] **BID.JO** (2025-08-27 10:00)
- **Detected Label**: `Cash generated by operations before working capital` (normalized: `cash generated by operations before working capital`)
- **Section Heading**: *Financial highlights:*
- **Prior Sentence**: *"-       Trading profit R12,9 billion, up 6,4%; up 9,3% in constant currency"*
- **Target Sentence**: **"-       Cash generated by operations before working capital R16,6 billion, up 7,5%"**
- **Next Sentence**: *"-       Strong cash generation 122% of trading profit and 108% of EBITDA turned into cash"*
- **Detected Numbers**: `['R16,6 billion', '7,5%']`
- **Difficulty Category**: `D. Basis ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `cash_generated_from_operations`
- Seed Qualifiers: `{}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `REQUIRES_SCOPE`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Scope unverified; continuing vs total group operations requires context*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 044 — [`BENCH-0087`] **BID.JO** (2025-08-27 10:00)
- **Detected Label**: `trading profit` (normalized: `trading profit`)
- **Prior Sentence**: *"-       Cash generated by operations before working capital R16,6 billion, up 7,5%"*
- **Target Sentence**: **"-       Strong cash generation 122% of trading profit and 108% of EBITDA turned into cash"**
- **Next Sentence**: *"-       Headline earnings per share 2 562,7 cents, up 6,5%; up 9,6% in constant currency"*
- **Detected Numbers**: `['122%', '108%']`
- **Difficulty Category**: `H. Profit/EBIT/trading-profit ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `trading_profit`
- Seed Qualifiers: `{'sign': <NumericSign.POSITIVE: 'positive'>}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `CHANGE_RATE_ONLY`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Change / directional reporting sentence with percentage-only rate; ineligible as absolute historical baseline*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 045 — [`BENCH-0088`] **BID.JO** (2025-08-27 10:00)
- **Detected Label**: `EBITDA` (normalized: `ebitda`)
- **Prior Sentence**: *"-       Cash generated by operations before working capital R16,6 billion, up 7,5%"*
- **Target Sentence**: **"-       Strong cash generation 122% of trading profit and 108% of EBITDA turned into cash"**
- **Next Sentence**: *"-       Headline earnings per share 2 562,7 cents, up 6,5%; up 9,6% in constant currency"*
- **Detected Numbers**: `['122%', '108%']`
- **Difficulty Category**: `H. Profit/EBIT/trading-profit ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `ebitda`
- Seed Qualifiers: `{'scope': <OperationScope.GROUP_CONSOLIDATED: 'group_consolidated'>}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `CHANGE_RATE_ONLY`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Change / directional reporting sentence with percentage-only rate; ineligible as absolute historical baseline*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 046 — [`BENCH-0089`] **BID.JO** (2025-08-27 10:00)
- **Detected Label**: `Headline earnings per share` (normalized: `headline earnings per share`)
- **Prior Sentence**: *"-       Strong cash generation 122% of trading profit and 108% of EBITDA turned into cash"*
- **Target Sentence**: **"-       Headline earnings per share 2 562,7 cents, up 6,5%; up 9,6% in constant currency"**
- **Next Sentence**: *"-       Dividend distribution for the full year 1 160,0 cents, up 6,4%"*
- **Detected Numbers**: `['2 562,7 cents', '6,5%', '9,6%']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `heps`
- Seed Qualifiers: `{'dilution': <DilutionBasis.BASIC: 'basic'>, 'attribution': <ProfitAttribution.HEADLINE_ATTRIBUTABLE: 'headline_attributable'>, 'metric_basis': <MetricBasis.HEADLINE: 'headline'>}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE_WITH_QUALIFIER`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'heps' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 047 — [`BENCH-0092`] **BID.JO** (2025-08-27 10:00)
- **Detected Label**: `Dividend distribution for the full year` (normalized: `dividend distribution for the full year`)
- **Prior Sentence**: *"-       Headline earnings per share 2 562,7 cents, up 6,5%; up 9,6% in constant currency"*
- **Target Sentence**: **"-       Dividend distribution for the full year 1 160,0 cents, up 6,4%"**
- **Detected Numbers**: `['1 160,0 cents', '6,4%']`
- **Difficulty Category**: `A. Easy/direct`

**Deterministic Seed Baseline:**
- Seed Concept: `annual_dividend_per_share`
- Seed Qualifiers: `{'tax_basis': <DividendTaxBasis.GROSS: 'gross'>, 'period_type': <PeriodType.FULL_YEAR: 'full_year'>}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `REQUIRES_PERIOD`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Context required to verify period type, scope, or accounting attribution*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 048 — [`BENCH-0093`] **BID.JO** (2025-08-27 10:00)
- **Detected Label**: `Gross cash dividend amount per share` (normalized: `gross cash dividend amount per share`)
- **Section Heading**: *ISIN:                                               ZAE000216537*
- **Prior Sentence**: *"Company tax reference number:                       9040946841"*
- **Target Sentence**: **"Gross cash dividend amount per share:               600,0 cents"**
- **Next Sentence**: *"Net dividend amount per share:                      480,0 cents"*
- **Detected Numbers**: `['600,0 cents']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `dividend_per_share`
- Seed Qualifiers: `{'tax_basis': <DividendTaxBasis.GROSS: 'gross'>, 'basis_evidence': <BasisEvidence.EXPLICIT_NOTE_WORDING: 'explicit_note_wording'>, 'custom_notes': 'Explicit gross cash dividend before DWT'}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE_WITH_QUALIFIER`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'dividend_per_share' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 049 — [`BENCH-0094`] **BID.JO** (2025-08-27 10:00)
- **Detected Label**: `Net dividend amount per share` (normalized: `net dividend amount per share`)
- **Prior Sentence**: *"Gross cash dividend amount per share:               600,0 cents"*
- **Target Sentence**: **"Net dividend amount per share:                      480,0 cents"**
- **Next Sentence**: *"Issued shares at declaration date:                  336 904 212"*
- **Detected Numbers**: `['480,0 cents']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `dividend_per_share`
- Seed Qualifiers: `{'tax_basis': <DividendTaxBasis.NET: 'net'>, 'basis_evidence': <BasisEvidence.EXPLICIT_NOTE_WORDING: 'explicit_note_wording'>, 'custom_notes': 'Explicit net dividend after 20% SA DWT'}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE_WITH_QUALIFIER`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'dividend_per_share' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 050 — [`BENCH-0095`] **ABG.JO** (2025-08-18 10:10)
- **Detected Label**: `Headline earnings` (normalized: `headline earnings`)
- **Target Sentence**: **"Headline earnings per ordinary share                                                   Cost-to-income ratio"**
- **Next Sentence**: *"2025                  Change %              2024                                       2025             Change             2024"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `A. Easy/direct`

**Deterministic Seed Baseline:**
- Seed Concept: `headline_earnings`
- Seed Qualifiers: `{'attribution': <ProfitAttribution.HEADLINE_ATTRIBUTABLE: 'headline_attributable'>, 'metric_basis': <MetricBasis.HEADLINE: 'headline'>}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'headline earnings' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 051 — [`BENCH-0096`] **ABG.JO** (2025-08-18 10:10)
- **Detected Label**: `Basic earnings per share` (normalized: `basic earnings per share`)
- **Target Sentence**: **"Basic earnings per share                                                               Net interest margin"**
- **Next Sentence**: *"2025                  Change %              2024                                       2025             Change             2024"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `eps`
- Seed Qualifiers: `{'dilution': <DilutionBasis.BASIC: 'basic'>}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'basic earnings per share' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 052 — [`BENCH-0098`] **ABG.JO** (2025-08-18 10:10)
- **Detected Label**: `ordinary shares in issue` (normalized: `ordinary shares in issue`)
- **Section Heading**: *-   The local dividend tax rate is 20%.*
- **Prior Sentence**: *"-   The net local dividend amount is 628 cents per ordinary share for shareholders liable to pay the dividend tax."*
- **Target Sentence**: **"-   Absa Group Limited currently has 894 376 907 ordinary shares in issue (includes 65 074 525 treasury shares)."**
- **Next Sentence**: *"-   Absa Group Limited's income tax reference number is 9150116714."*
- **Detected Numbers**: `['894 376 907', '65 074 525']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `issued_shares_current`
- Seed Qualifiers: `{}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'issued_shares_current' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 053 — [`BENCH-0099`] **ABG.JO** (2025-08-18 10:10)
- **Detected Label**: `treasury shares` (normalized: `treasury shares`)
- **Section Heading**: *-   The local dividend tax rate is 20%.*
- **Prior Sentence**: *"-   The net local dividend amount is 628 cents per ordinary share for shareholders liable to pay the dividend tax."*
- **Target Sentence**: **"-   Absa Group Limited currently has 894 376 907 ordinary shares in issue (includes 65 074 525 treasury shares)."**
- **Next Sentence**: *"-   Absa Group Limited's income tax reference number is 9150116714."*
- **Detected Numbers**: `['894 376 907', '65 074 525']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `treasury_shares`
- Seed Qualifiers: `{}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'treasury_shares' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 054 — [`BENCH-0104`] **ARL.JO** (2025-11-17 07:05)
- **Detected Label**: `Earnings per share` (normalized: `earnings per share`)
- **Section Heading**: *– Revenue increase 10%*
- **Prior Sentence**: *"– Profit before interest and tax increase 11%"*
- **Target Sentence**: **"– Earnings per share increase 16%"**
- **Next Sentence**: *"– Headline earnings per share increase 14%"*
- **Detected Numbers**: `['16%']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `eps`
- Seed Qualifiers: `{'dilution': <DilutionBasis.BASIC: 'basic'>}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `CHANGE_RATE_ONLY`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Change / directional reporting sentence with percentage-only rate; ineligible as absolute historical baseline*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 055 — [`BENCH-0105`] **ARL.JO** (2025-11-17 07:05)
- **Detected Label**: `Headline earnings per share` (normalized: `headline earnings per share`)
- **Section Heading**: *– Earnings per share increase 16%*
- **Prior Sentence**: *"– Earnings per share increase 16%"*
- **Target Sentence**: **"– Headline earnings per share increase 14%"**
- **Next Sentence**: *"– Cash generated from operating activities increase 20%"*
- **Detected Numbers**: `['14%']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `heps`
- Seed Qualifiers: `{'dilution': <DilutionBasis.BASIC: 'basic'>, 'attribution': <ProfitAttribution.HEADLINE_ATTRIBUTABLE: 'headline_attributable'>, 'metric_basis': <MetricBasis.HEADLINE: 'headline'>}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `CHANGE_RATE_ONLY`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Change / directional reporting sentence with percentage-only rate; ineligible as absolute historical baseline*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 056 — [`BENCH-0108`] **ARL.JO** (2025-11-17 07:05)
- **Detected Label**: `Profit for the year` (normalized: `profit for the year`)
- **Section Heading**: *R’000   change          R’000*
- **Prior Sentence**: *"Profit before interest and tax                     1 247 369      11%      1 124 909"*
- **Target Sentence**: **"Profit for the year                                  876 389      16%        752 904"**
- **Next Sentence**: *"Total assets                                       9 325 822       3%      9 097 786"*
- **Detected Numbers**: `['876 389', '16%', '752 904']`
- **Difficulty Category**: `A. Easy/direct`

**Deterministic Seed Baseline:**
- Seed Concept: `profit_for_period`
- Seed Qualifiers: `{'attribution': <ProfitAttribution.TOTAL_GROUP: 'total_group'>, 'sign': <NumericSign.POSITIVE: 'positive'>, 'period_type': <PeriodType.FULL_YEAR: 'full_year'>}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'profit_for_period' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 057 — [`BENCH-0109`] **ARL.JO** (2025-11-17 07:05)
- **Detected Label**: `Total assets` (normalized: `total assets`)
- **Prior Sentence**: *"Profit for the year                                  876 389      16%        752 904"*
- **Target Sentence**: **"Total assets                                       9 325 822       3%      9 097 786"**
- **Next Sentence**: *"Total equity                                       5 374 623      13%      4 752 361"*
- **Detected Numbers**: `['9 325 822', '3%', '9 097 786']`
- **Difficulty Category**: `I. Unknown/long-tail`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `REQUIRES_SCOPE`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Unknown / long-tail phrase 'total assets'; requires expert review*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 058 — [`BENCH-0114`] **ARL.JO** (2025-11-17 07:05)
- **Detected Label**: `ordinary shares in issue` (normalized: `ordinary shares in issue`)
- **Prior Sentence**: *"– The net local dividend is 704 cents per ordinary share for shareholders liable to pay Dividend Tax;"*
- **Target Sentence**: **"– Astral Foods Limited has currently 42 922 235 ordinary shares in issue (which includes 4 205 574 treasury"**
- **Next Sentence**: *"shares held by a subsidiary and 189 721 held in terms a forfeitable share scheme); and"*
- **Detected Numbers**: `['42 922 235', '4 205 574']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `issued_shares_current`
- Seed Qualifiers: `{}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'issued_shares_current' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 059 — [`BENCH-0116`] **SOL.JO** (2025-11-17 07:05)
- **Detected Label**: `Ordinary Shares in issue` (normalized: `ordinary shares in issue`)
- **Prior Sentence**: *"468 586 487         72,12%            77,63%              22,37%            0,04%"*
- **Target Sentence**: **"* Based on the total number of Sasol Ordinary Shares and Sasol BEE Ordinary Shares in issue, being 649 775 104, as at"**
- **Next Sentence**: *"Friday, 7 November 2025, being the Record Date of the annual general meeting."*
- **Detected Numbers**: `['649 775 104']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `issued_shares_current`
- Seed Qualifiers: `{}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'issued_shares_current' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 060 — [`BENCH-0118`] **MTN.JO** (2025-11-17 07:05)
- **Detected Label**: `EBITDA` (normalized: `ebitda`)
- **Section Heading**: *Resumes dividend payment*
- **Prior Sentence**: *"•   Fintech transaction value increased by 38.0%* to US$342.3 billion"*
- **Target Sentence**: **"•   Further expansion in EBITDA margin to 45.0%* (+6.7pp*)"**
- **Next Sentence**: *"•   Healthy balance sheet position supported by good cash upstreaming"*
- **Detected Numbers**: `['45.0%', '+6.7']`
- **Difficulty Category**: `H. Profit/EBIT/trading-profit ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `ebitda`
- Seed Qualifiers: `{'scope': <OperationScope.GROUP_CONSOLIDATED: 'group_consolidated'>}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE_WITH_QUALIFIER`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'ebitda' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 061 — [`BENCH-0119`] **MTN.JO** (2025-11-17 07:05)
- **Detected Label**: `revenue increased by` (normalized: `revenue increased by`)
- **Section Heading**: *Highlights*
- **Prior Sentence**: *"Highlights"*
- **Target Sentence**: **"•   Group service revenue increased by 25.9%; up 22.6%* in constant currency"**
- **Next Sentence**: *"(CC)"*
- **Detected Numbers**: `['25.9%', '22.6%']`
- **Difficulty Category**: `B. Change statements`

**Deterministic Seed Baseline:**
- Seed Concept: `accounting_revenue`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `CHANGE_RATE_ONLY`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Change / directional reporting sentence with percentage-only rate; ineligible as absolute historical baseline*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 062 — [`BENCH-0123`] **MTN.JO** (2025-11-17 07:05)
- **Detected Label**: `depreciation and amortisation` (normalized: `depreciation and amortisation`)
- **Section Heading**: *9M to September 2024).*
- **Prior Sentence**: *"9M to September 2024)."*
- **Target Sentence**: **"EBITDA – earnings before interest, tax, depreciation and amortisation"**
- **Next Sentence**: *"pp – percentage points"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `A. Easy/direct`

**Deterministic Seed Baseline:**
- Seed Concept: `depreciation_and_amortisation`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'depreciation and amortisation' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 063 — [`BENCH-0127`] **MTN.JO** (2025-11-17 07:05)
- **Detected Label**: `capex of R27.9` (normalized: `capex of r27.9`)
- **Prior Sentence**: *"Strong growth performance sustained by execution"*
- **Target Sentence**: **"We deployed capex of R27.9 billion in our networks and platforms – with capex"**
- **Next Sentence**: *"intensity of 16.8% within our 15-18% target range – to sustain the growth"*
- **Detected Numbers**: `['R27.9 billion']`
- **Difficulty Category**: `G. Capex ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `REQUIRES_BASIS`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Ambiguous wording 'capex of r27.9' lacks accounting basis (cash vs additions, movement vs balance); requires basis*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 064 — [`BENCH-0129`] **MTN.JO** (2025-11-17 07:05)
- **Detected Label**: `revenue grew by` (normalized: `revenue grew by`)
- **Prior Sentence**: *"customers grew by 5.8% to close the period at 301.3 million."*
- **Target Sentence**: **"Group service revenue grew by 22.6%*, with an uptick in growth in Q3 (up"**
- **Next Sentence**: *"23.0%*). Data growth (up 35.4%*) was boosted by an expansion in active data"*
- **Detected Numbers**: `['22.6%']`
- **Difficulty Category**: `B. Change statements`

**Deterministic Seed Baseline:**
- Seed Concept: `accounting_revenue`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `CHANGE_RATE_ONLY`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Change / directional reporting sentence with percentage-only rate; ineligible as absolute historical baseline*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 065 — [`BENCH-0130`] **MTN.JO** (2025-11-17 07:05)
- **Detected Label**: `Group EBITDA` (normalized: `group ebitda`)
- **Prior Sentence**: *"continued pressure in a highly competitive prepaid market."*
- **Target Sentence**: **"Group EBITDA was 41.1%* higher, with the expansion in margin to 45.0%* (up"**
- **Next Sentence**: *"6.7pp*) underpinned by strong topline growth and the ongoing group-wide"*
- **Detected Numbers**: `['41.1%', '45.0%']`
- **Difficulty Category**: `H. Profit/EBIT/trading-profit ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `ebitda`
- Seed Qualifiers: `{'scope': <OperationScope.GROUP_CONSOLIDATED: 'group_consolidated'>}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `CHANGE_RATE_ONLY`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Change / directional reporting sentence with percentage-only rate; ineligible as absolute historical baseline*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 066 — [`BENCH-0132`] **MTN.JO** (2025-11-17 07:05)
- **Detected Label**: `net debt` (normalized: `net debt`)
- **Section Heading**: *expense efficiency programme (EEP).*
- **Prior Sentence**: *"Our balance sheet remains in a strong position with an improvement in the"*
- **Target Sentence**: **"Group net debt-to-EBITDA to 0.4x at end-September 2025 (December 2024: 0.7x)."**
- **Next Sentence**: *"The Holdco leverage of 1.4x was flat on the December 2024 level and benefitted"*
- **Detected Numbers**: `['0.4', '2025', '2024', '0.7']`
- **Difficulty Category**: `E. Debt/lease ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `REQUIRES_SOURCE_SECTION`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Ambiguous wording 'net debt' lacks balance sheet vs note presentation; requires source section*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 067 — [`BENCH-0134`] **MTN.JO** (2025-11-17 07:05)
- **Detected Label**: `capex of R33` (normalized: `capex of r33`)
- **Prior Sentence**: *"flexibility to execute our growth strategy. We will continue to invest"*
- **Target Sentence**: **"prudently in support of our ambitions with a targeted capex of R33-38 billion"**
- **Next Sentence**: *"(ex?leases) for FY 2025 based on current currency assumptions. Our medium-"*
- **Detected Numbers**: `['R33', '38 billion']`
- **Difficulty Category**: `G. Capex ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `REQUIRES_BASIS`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Ambiguous wording 'capex of r33' lacks accounting basis (cash vs additions, movement vs balance); requires basis*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 068 — [`BENCH-0138`] **WBC.JO** (2025-11-17 07:05)
- **Detected Label**: `headline earnings` (normalized: `headline earnings`)
- **Section Heading**: *the year ended 30 September 2025.*
- **Prior Sentence**: *"the year ended 30 September 2025."*
- **Target Sentence**: **"WeBuyCars utilises core headline earnings to measure and benchmark the underlying performance of"**
- **Next Sentence**: *"the business. Core headline earnings represents headline earnings adjusted for certain non-"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `A. Easy/direct`

**Deterministic Seed Baseline:**
- Seed Concept: `headline_earnings`
- Seed Qualifiers: `{'attribution': <ProfitAttribution.HEADLINE_ATTRIBUTABLE: 'headline_attributable'>, 'metric_basis': <MetricBasis.HEADLINE: 'headline'>}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'headline earnings' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 069 — [`BENCH-0140`] **WBC.JO** (2025-11-17 07:05)
- **Detected Label**: `headline earnings per share` (normalized: `headline earnings per share`)
- **Prior Sentence**: *"Core headline earnings (i)                      Rm           937,6          815,4          15,0"*
- **Target Sentence**: **"Core headline earnings per share (i,ii)      Cents           224,6          217,4           3,3"**
- **Next Sentence**: *"Basic earnings                                  Rm           935,4          343,1         > 100"*
- **Detected Numbers**: `['224,6', '217,4', '3,3']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `heps`
- Seed Qualifiers: `{'dilution': <DilutionBasis.BASIC: 'basic'>, 'attribution': <ProfitAttribution.HEADLINE_ATTRIBUTABLE: 'headline_attributable'>, 'metric_basis': <MetricBasis.HEADLINE: 'headline'>}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE_WITH_QUALIFIER`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'heps' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 070 — [`BENCH-0142`] **WBC.JO** (2025-11-17 07:05)
- **Detected Label**: `Basic earnings per share` (normalized: `basic earnings per share`)
- **Prior Sentence**: *"Basic earnings                                  Rm           935,4          343,1         > 100"*
- **Target Sentence**: **"Basic earnings per share (ii)                Cents           224,1           91,5         > 100"**
- **Next Sentence**: *"Headline earnings                               Rm           937,6          343,9         > 100"*
- **Detected Numbers**: `['224,1', '91,5', '100']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `eps`
- Seed Qualifiers: `{'dilution': <DilutionBasis.BASIC: 'basic'>}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `REQUIRES_PERIOD`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Ambiguous share wording 'basic earnings per share' lacks point-in-time vs period-end vs WANOS specification; requires period*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 071 — [`BENCH-0144`] **WBC.JO** (2025-11-17 07:05)
- **Detected Label**: `Headline earnings per share` (normalized: `headline earnings per share`)
- **Prior Sentence**: *"Headline earnings                               Rm           937,6          343,9         > 100"*
- **Target Sentence**: **"Headline earnings per share (ii)             Cents           224,6           91,7         > 100"**
- **Next Sentence**: *"Final cash dividend per share                Cents              30             25          20,0"*
- **Detected Numbers**: `['224,6', '91,7', '100']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `heps`
- Seed Qualifiers: `{'dilution': <DilutionBasis.BASIC: 'basic'>, 'attribution': <ProfitAttribution.HEADLINE_ATTRIBUTABLE: 'headline_attributable'>, 'metric_basis': <MetricBasis.HEADLINE: 'headline'>}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE_WITH_QUALIFIER`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'heps' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 072 — [`BENCH-0145`] **WBC.JO** (2025-11-17 07:05)
- **Detected Label**: `dividend per share` (normalized: `dividend per share`)
- **Prior Sentence**: *"Headline earnings per share (ii)             Cents           224,6           91,7         > 100"*
- **Target Sentence**: **"Final cash dividend per share                Cents              30             25          20,0"**
- **Next Sentence**: *"i.  Core headline earnings is a non-IFRS measure which excludes gains/losses, costs and adjustments"*
- **Detected Numbers**: `['30', '25', '20,0']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `dividend_per_share`
- Seed Qualifiers: `{'tax_basis': <DividendTaxBasis.GROSS: 'gross'>}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE_WITH_QUALIFIER`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'dividend_per_share' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 073 — [`BENCH-0146`] **WBC.JO** (2025-11-17 07:05)
- **Detected Label**: `number of Shares in issue` (normalized: `number of shares in issue`)
- **Prior Sentence**: *"ii. Weighted average number of ordinary shares (‘Shares’) in issue at 30 September 2025: 417 401 341"*
- **Target Sentence**: **"(30 September 2024: 375 029 205). Actual number of Shares in issue at 30 September 2025:"**
- **Next Sentence**: *"417 675 981 (30 September 2024: 417 181 120)."*
- **Detected Numbers**: `['30', '2024', '375 029 205', '30', '2025']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `REQUIRES_PERIOD`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Ambiguous share wording 'number of shares in issue' lacks point-in-time vs period-end vs WANOS specification; requires period*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 074 — [`BENCH-0148`] **WBC.JO** (2025-11-17 07:05)
- **Detected Label**: `headline earnings for the year` (normalized: `headline earnings for the year`)
- **Section Heading**: *Financial Results*
- **Prior Sentence**: *"Financial Results"*
- **Target Sentence**: **"The Group continued on its long-term growth trajectory with core headline earnings for the year ended"**
- **Next Sentence**: *"30 September 2025 at R937,6 million growing 15,0% and core headline earnings per share growing 3,3%"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `B. Change statements`

**Deterministic Seed Baseline:**
- Seed Concept: `headline_earnings`
- Seed Qualifiers: `{'attribution': <ProfitAttribution.HEADLINE_ATTRIBUTABLE: 'headline_attributable'>, 'metric_basis': <MetricBasis.HEADLINE: 'headline'>, 'period_type': <PeriodType.FULL_YEAR: 'full_year'>}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'headline earnings for the year' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 075 — [`BENCH-0150`] **WBC.JO** (2025-11-17 07:05)
- **Detected Label**: `Group revenue` (normalized: `group revenue`)
- **Prior Sentence**: *"net insurance result, lower finance costs and cost efficiencies driven by economies of scale."*
- **Target Sentence**: **"Group revenue at R26,4 billion increased by 13,1% when compared to the prior year. Buying and selling"**
- **Next Sentence**: *"volumes at 180 576 and 179 006 units were up 7,7% and 8,4%, respectively. The number of vehicles"*
- **Detected Numbers**: `['R26,4 billion', '13,1%']`
- **Difficulty Category**: `B. Change statements`

**Deterministic Seed Baseline:**
- Seed Concept: `accounting_revenue`
- Seed Qualifiers: `{'scope': <OperationScope.GROUP_CONSOLIDATED: 'group_consolidated'>, 'sign': <NumericSign.POSITIVE: 'positive'>}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `CHANGE_RATE_TO_LEVEL`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Change reporting sentence with rate-to-level compound structure*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 076 — [`BENCH-0152`] **WBC.JO** (2025-11-17 07:05)
- **Detected Label**: `basic earnings per share` (normalized: `basic earnings per share`)
- **Prior Sentence**: *"The 83 185 241 new Shares issued on 29 February 2024, 27 March 2024 and 11 April 2024, have had an"*
- **Target Sentence**: **"unfavourable impact on the core headline earnings per share, the basic earnings per share and the"**
- **Next Sentence**: *"headline earnings per share for the year ended 30 September 2025. These new Shares were issued in terms"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `eps`
- Seed Qualifiers: `{'dilution': <DilutionBasis.BASIC: 'basic'>}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'basic earnings per share' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 077 — [`BENCH-0153`] **WBC.JO** (2025-11-17 07:05)
- **Detected Label**: `headline earnings per share for the year` (normalized: `headline earnings per share for the year`)
- **Prior Sentence**: *"unfavourable impact on the core headline earnings per share, the basic earnings per share and the"*
- **Target Sentence**: **"headline earnings per share for the year ended 30 September 2025. These new Shares were issued in terms"**
- **Next Sentence**: *"of the pre-listing capital raise, which was approved by shareholders prior to the listing of WeBuyCars"*
- **Detected Numbers**: `['30', '2025']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `heps`
- Seed Qualifiers: `{'dilution': <DilutionBasis.BASIC: 'basic'>, 'attribution': <ProfitAttribution.HEADLINE_ATTRIBUTABLE: 'headline_attributable'>, 'metric_basis': <MetricBasis.HEADLINE: 'headline'>, 'period_type': <PeriodType.FULL_YEAR: 'full_year'>}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'headline earnings per share for the year' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 078 — [`BENCH-0156`] **WBC.JO** (2025-11-17 07:05)
- **Detected Label**: `capital expenditure` (normalized: `capital expenditure`)
- **Section Heading**: *Dividends*
- **Prior Sentence**: *"The Company’s dividend policy is to declare between 25% and 33% of its headline earnings as a dividend,"*
- **Target Sentence**: **"subject to working capital requirements and capital expenditure required for expansion and maintenance."**
- **Next Sentence**: *"WeBuyCars is a company that intends to grow its footprint across South Africa responsibly. The Group"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `G. Capex ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'capital expenditure' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 079 — [`BENCH-0157`] **WBC.JO** (2025-11-17 07:05)
- **Detected Label**: `working capital` (normalized: `working capital`)
- **Section Heading**: *Dividends*
- **Prior Sentence**: *"The Company’s dividend policy is to declare between 25% and 33% of its headline earnings as a dividend,"*
- **Target Sentence**: **"subject to working capital requirements and capital expenditure required for expansion and maintenance."**
- **Next Sentence**: *"WeBuyCars is a company that intends to grow its footprint across South Africa responsibly. The Group"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `D. Basis ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'working capital' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 080 — [`BENCH-0158`] **PRX.JO** (2025-11-17 07:50)
- **Detected Label**: `headline earnings per share` (normalized: `headline earnings per share`)
- **Prior Sentence**: *"Both of the above measures are driven by strong growth in revenue and profitability of our consolidated Ecommerce"*
- **Target Sentence**: **"businesses and our equity-accounted investments, particularly Tencent. Core headline earnings per share also"**
- **Next Sentence**: *"benefited from the exclusion of foreign currency translation losses, which are included in headline earnings."*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `heps`
- Seed Qualifiers: `{'dilution': <DilutionBasis.BASIC: 'basic'>, 'attribution': <ProfitAttribution.HEADLINE_ATTRIBUTABLE: 'headline_attributable'>, 'metric_basis': <MetricBasis.HEADLINE: 'headline'>}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'headline earnings per share' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 081 — [`BENCH-0159`] **PRX.JO** (2025-11-17 07:50)
- **Detected Label**: `profit for the year` (normalized: `profit for the year`)
- **Section Heading**: *by the Group’s auditors.*
- **Prior Sentence**: *"by the Group’s auditors."*
- **Target Sentence**: **"*** Headline earnings represents net profit for the year attributable to the Group’s equity holders, excluding certain"**
- **Next Sentence**: *"defined separately identifiable remeasurements relating to, amongst others, impairments of tangible assets, intangible"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `A. Easy/direct`

**Deterministic Seed Baseline:**
- Seed Concept: `profit_for_period`
- Seed Qualifiers: `{'attribution': <ProfitAttribution.TOTAL_GROUP: 'total_group'>, 'sign': <NumericSign.POSITIVE: 'positive'>, 'period_type': <PeriodType.FULL_YEAR: 'full_year'>}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'profit for the year' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 082 — [`BENCH-0160`] **PRX.JO** (2025-11-17 07:50)
- **Detected Label**: `basic earnings per share` (normalized: `basic earnings per share`)
- **Prior Sentence**: *"Accountants, at the request of the JSE Limited in relation to the calculation of headline earnings and disclosure of a"*
- **Target Sentence**: **"detailed reconciliation of headline earnings to the earnings numbers used in the calculation of basic earnings per share"**
- **Next Sentence**: *"in accordance with the requirements of IAS 33 – Earnings per Share, under the JSE Listings Requirements."*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `eps`
- Seed Qualifiers: `{'dilution': <DilutionBasis.BASIC: 'basic'>}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'basic earnings per share' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 083 — [`BENCH-0161`] **PRX.JO** (2025-11-17 07:50)
- **Detected Label**: `headline earnings for the period` (normalized: `headline earnings for the period`)
- **Prior Sentence**: *"in accordance with the requirements of IAS 33 – Earnings per Share, under the JSE Listings Requirements."*
- **Target Sentence**: **"**** Core headline earnings, a non-IFRS performance measure, represent headline earnings for the period, excluding"**
- **Next Sentence**: *"certain non-operating items. Specifically, headline earnings are adjusted for the following items to derive core headline"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `A. Easy/direct`

**Deterministic Seed Baseline:**
- Seed Concept: `headline_earnings`
- Seed Qualifiers: `{'attribution': <ProfitAttribution.HEADLINE_ATTRIBUTABLE: 'headline_attributable'>, 'metric_basis': <MetricBasis.HEADLINE: 'headline'>}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'headline earnings for the period' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 084 — [`BENCH-0162`] **PRX.JO** (2025-11-17 07:50)
- **Detected Label**: `treasury shares` (normalized: `treasury shares`)
- **Prior Sentence**: *"earnings: (i) equity-settled share-based payment expenses on transactions where there is no cash cost to us. These"*
- **Target Sentence**: **"include those relating to share-based incentive awards settled by issuing treasury shares, as well as certain share-based"**
- **Next Sentence**: *"payment expenses that are deemed to arise on shareholder transactions; (ii) subsequent fair-value remeasurement of"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `treasury_shares`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'treasury shares' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 085 — [`BENCH-0163`] **PRX.JO** (2025-11-17 07:50)
- **Detected Label**: `taxation` (normalized: `taxation`)
- **Prior Sentence**: *"cash-settled share-based incentive expenses; (iii) cash-settled share-based compensation expenses deemed to arise"*
- **Target Sentence**: **"from shareholder transactions by virtue of employment; (iv) deferred taxation income recognised on the first-time"**
- **Next Sentence**: *"recognition of deferred tax assets as this generally relates to multiple prior periods and distorts current period"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `A. Easy/direct`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'taxation' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 086 — [`BENCH-0164`] **PRX.JO** (2025-11-17 07:50)
- **Detected Label**: `amortisation` (normalized: `amortisation`)
- **Prior Sentence**: *"acquisitions and disposals of businesses as these items relate to changes in our composition and are not reflective of our"*
- **Target Sentence**: **"underlying operating performance and (vii) the amortisation of intangible assets recognised in business combinations"**
- **Next Sentence**: *"and acquisitions. These adjustments are made to the earnings of businesses controlled by us, as well as our share of"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `A. Easy/direct`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'amortisation' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 087 — [`BENCH-0165`] **PRX.JO** (2025-11-17 07:50)
- **Detected Label**: `ordinary shares in issue` (normalized: `ordinary shares in issue`)
- **Prior Sentence**: *"earnings of associates and joint ventures, to the extent that the information is available."*
- **Target Sentence**: **"(1) Per share information is based on the net number of N ordinary shares in issue during the respective periods. The A"**
- **Next Sentence**: *"ordinary shareholders and B ordinary shareholders share 1/5 th and 1/1 000 000th respectively of the earnings"*
- **Detected Numbers**: `['1']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `issued_shares_current`
- Seed Qualifiers: `{}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'issued_shares_current' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 088 — [`BENCH-0166`] **NPN.JO** (2025-11-17 07:50)
- **Detected Label**: `diluted earnings per share` (normalized: `diluted earnings per share`)
- **Prior Sentence**: *"In October 2025, a five-for-one (5:1) share split was completed. The prior periods have been adjusted to enable comparability"*
- **Target Sentence**: **"for earnings and diluted earnings per share. Illustrated below are the impact on earnings, headline earnings and core headline"**
- **Next Sentence**: *"earnings per share for continuing operations for the period ended 30 September 2025, as compared to 30 September 2024,"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `diluted_eps`
- Seed Qualifiers: `{'dilution': <DilutionBasis.DILUTED: 'diluted'>}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'diluted earnings per share' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 089 — [`BENCH-0167`] **NPN.JO** (2025-11-17 07:50)
- **Detected Label**: `headline earnings for the period` (normalized: `headline earnings for the period`)
- **Section Heading**: *Group’s auditors.*
- **Prior Sentence**: *"Group’s auditors."*
- **Target Sentence**: **"* Core headline earnings, a non-IFRS performance measure, represent headline earnings for the period, excluding certain non-"**
- **Next Sentence**: *"operating items. Specifically, headline earnings are adjusted for the following items to derive core headline earnings: (i) equity-"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `A. Easy/direct`

**Deterministic Seed Baseline:**
- Seed Concept: `headline_earnings`
- Seed Qualifiers: `{'attribution': <ProfitAttribution.HEADLINE_ATTRIBUTABLE: 'headline_attributable'>, 'metric_basis': <MetricBasis.HEADLINE: 'headline'>}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'headline earnings for the period' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 090 — [`BENCH-0168`] **NPN.JO** (2025-11-17 07:50)
- **Detected Label**: `treasury shares` (normalized: `treasury shares`)
- **Prior Sentence**: *"settled share-based payment expenses on transactions where there is no cash cost to us. These include those relating to share-"*
- **Target Sentence**: **"based incentive awards settled by issuing treasury shares, as well as certain share-based"**
- **Next Sentence**: *"payment expenses that are deemed to arise on shareholder transactions; (ii) subsequent fair-value remeasurement of cash-"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `treasury_shares`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'treasury shares' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 091 — [`BENCH-0169`] **NPN.JO** (2025-11-17 07:50)
- **Detected Label**: `taxation` (normalized: `taxation`)
- **Prior Sentence**: *"settled share-based incentive expenses; (iii) cash-settled share-based compensation expenses deemed to arise from shareholder"*
- **Target Sentence**: **"transactions by virtue of employment; (iv) deferred taxation income recognised on the first-time recognition of deferred tax"**
- **Next Sentence**: *"assets as this generally relates to multiple prior periods and distorts current period performance; (v) fair-value adjustments on"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `A. Easy/direct`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'taxation' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 092 — [`BENCH-0170`] **NPN.JO** (2025-11-17 07:50)
- **Detected Label**: `amortisation` (normalized: `amortisation`)
- **Prior Sentence**: *"items relate to changes in our composition and are not reflective of our underlying operating performance and (vii) the"*
- **Target Sentence**: **"amortisation of intangible assets recognised in business combinations and acquisitions. These adjustments are made to the"**
- **Next Sentence**: *"earnings of businesses controlled by us, as well as our share of earnings of associates and joint ventures, to the extent that the"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `A. Easy/direct`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'amortisation' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 093 — [`BENCH-0171`] **NPN.JO** (2025-11-17 07:50)
- **Detected Label**: `ordinary shares in issue` (normalized: `ordinary shares in issue`)
- **Section Heading**: *information is available.*
- **Prior Sentence**: *"The pro forma financial information is the responsibility of the Group’s directors."*
- **Target Sentence**: **"(1) Per share information is based on the net number of A and N ordinary shares in issue during the respective periods."**
- **Next Sentence**: *"17 November 2025"*
- **Detected Numbers**: `['1']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `issued_shares_current`
- Seed Qualifiers: `{}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'issued_shares_current' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 094 — [`BENCH-0172`] **ANI.JO** (2025-11-17 11:32)
- **Detected Label**: `diluted earnings per share` (normalized: `diluted earnings per share`)
- **Prior Sentence**: *"Distributable earnings                                         R18 964 807       R14 697 212         29.04%"*
- **Target Sentence**: **"Basic and diluted earnings per share (cents)                         26.14             22.04         18.60%"**
- **Next Sentence**: *"Headline earnings per share (cents)                                  26.15             22.04         18.65%"*
- **Detected Numbers**: `['26.14', '22.04', '18.60%']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `diluted_eps`
- Seed Qualifiers: `{'dilution': <DilutionBasis.DILUTED: 'diluted'>}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `REQUIRES_PERIOD`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Ambiguous share wording 'diluted earnings per share' lacks point-in-time vs period-end vs WANOS specification; requires period*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 095 — [`BENCH-0173`] **ANI.JO** (2025-11-17 11:32)
- **Detected Label**: `Dividend per share` (normalized: `dividend per share`)
- **Prior Sentence**: *"Headline earnings per share (cents)                                  26.15             22.04         18.65%"*
- **Target Sentence**: **"Dividend per share (cents) (Note 1)                                  22.30             20.50          8.78%"**
- **Next Sentence**: *"Net asset value per share                                            R4.65             R4.07         14.25%"*
- **Detected Numbers**: `['1', '22.30', '20.50', '8.78%']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `dividend_per_share`
- Seed Qualifiers: `{'tax_basis': <DividendTaxBasis.GROSS: 'gross'>}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE_WITH_QUALIFIER`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'dividend_per_share' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 096 — [`BENCH-0174`] **ANI.JO** (2025-11-17 11:32)
- **Detected Label**: `Net asset value per share` (normalized: `net asset value per share`)
- **Prior Sentence**: *"Dividend per share (cents) (Note 1)                                  22.30             20.50          8.78%"*
- **Target Sentence**: **"Net asset value per share                                            R4.65             R4.07         14.25%"**
- **Next Sentence**: *"Notes:"*
- **Detected Numbers**: `['R4.65', 'R4.07', '14.25%']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `nav_per_share`
- Seed Qualifiers: `{}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'nav_per_share' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 097 — [`BENCH-0175`] **ANI.JO** (2025-11-17 11:32)
- **Detected Label**: `dividend per share` (normalized: `dividend per share`)
- **Section Heading**: *Notes:*
- **Prior Sentence**: *"Notes:"*
- **Target Sentence**: **"1.   The dividend per share of 22.30 cents relates to the financial year ended February 2025 and which was"**
- **Next Sentence**: *"subsequently paid in June 2025."*
- **Detected Numbers**: `['1', '22.30 cents', '2025']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `dividend_per_share`
- Seed Qualifiers: `{'tax_basis': <DividendTaxBasis.GROSS: 'gross'>}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE_WITH_QUALIFIER`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'dividend_per_share' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 098 — [`BENCH-0176`] **ANI.JO** (2025-11-17 11:32)
- **Detected Label**: `taxation` (normalized: `taxation`)
- **Prior Sentence**: *"received by a non-resident from a REIT will be subject to dividend withholding tax at 20%, unless the rate is"*
- **Target Sentence**: **"reduced in terms of any applicable agreement for the avoidance of double taxation (‘DTA’) between South"**
- **Next Sentence**: *"Africa and the country of residence of the shareholder concerned. Assuming dividend withholding tax will"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `B. Change statements`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'taxation' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 099 — [`BENCH-0177`] **GLN.JO** (2025-11-17 10:05)
- **Detected Label**: `treasury Shares` (normalized: `treasury shares`)
- **Section Heading**: *Swiss Tax Authorities.*
- **Prior Sentence**: *"The Company purchases the Shares for cancellation. Following this transaction (and cancellation"*
- **Target Sentence**: **"upon settlement), the Company will have 11,781,216,854 Shares in issue (excluding treasury Shares"**
- **Next Sentence**: *"held in treasury), which corresponds to the total number of voting rights. It will also hold"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `treasury_shares`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'treasury shares' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 100 — [`BENCH-0178`] **BYI.JO** (2025-11-17 09:30)
- **Detected Label**: `Ordinary Shares in issue` (normalized: `ordinary shares in issue`)
- **Prior Sentence**: *"BTG intends to cancel all of the purchased shares. Following settlement of the above purchases and"*
- **Target Sentence**: **"cancellation of the purchased Ordinary Shares, the Company’s total number of Ordinary Shares in issue,"**
- **Next Sentence**: *"and its total voting rights, will be 236,893,629 Ordinary Shares. The Company does not hold any shares"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `issued_shares_current`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'ordinary shares in issue' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 101 — [`BENCH-0179`] **SRE.JO** (2025-11-17 09:00)
- **Detected Label**: `profit after tax` (normalized: `profit after tax`)
- **Prior Sentence**: *"Operating platform continues to drive rental and FFO growth"*
- **Target Sentence**: **"•   56.8% increase in profit after tax to €87.0m (30 September 2024: €55.5m) due to strong operational performance, valuation"**
- **Next Sentence**: *"gain and release of deferred tax liabilities in the German portfolio as the German government enacted an annual 1% reduction"*
- **Detected Numbers**: `['56.8%', '€87.0m', '30', '2024', '€55.5m']`
- **Difficulty Category**: `B. Change statements`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{'sign': <NumericSign.POSITIVE: 'positive'>}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `CHANGE_RATE_TO_LEVEL`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Change reporting sentence with rate-to-level compound structure*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 102 — [`BENCH-0180`] **SRE.JO** (2025-11-17 09:00)
- **Detected Label**: `profit before tax` (normalized: `profit before tax`)
- **Section Heading**: *acquisitions in future periods*
- **Prior Sentence**: *"acquisitions in future periods"*
- **Target Sentence**: **"•   6.0% decrease in profit before tax to €57.5m (30 September 2024: €61.2m) primarily due to a net foreign exchange loss of"**
- **Next Sentence**: *"€14.2m on sterling cash reserves held in anticipation of UK investments made in the period"*
- **Detected Numbers**: `['6.0%', '€57.5m', '30', '2024', '€61.2m']`
- **Difficulty Category**: `B. Change statements`

**Deterministic Seed Baseline:**
- Seed Concept: `profit_before_tax`
- Seed Qualifiers: `{'sign': <NumericSign.POSITIVE: 'positive'>}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `CHANGE_RATE_TO_LEVEL`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Change reporting sentence with rate-to-level compound structure*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 103 — [`BENCH-0181`] **SRE.JO** (2025-11-17 09:00)
- **Detected Label**: `Basic earnings per share increased by` (normalized: `basic earnings per share increased by`)
- **Section Heading**: *acquisitions in future periods*
- **Prior Sentence**: *"€14.2m on sterling cash reserves held in anticipation of UK investments made in the period"*
- **Target Sentence**: **"•   Basic earnings per share increased by 47.2% to 5.77c (30 September 2024: 3.92c) reflecting the strong 57% growth in profit"**
- **Next Sentence**: *"after tax and the higher shares in issue following the equity issuance in July 2024 while headline earnings and EPRA earnings"*
- **Detected Numbers**: `['47.2%', '5.77c', '30', '2024', '3.92c', '57%']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `eps`
- Seed Qualifiers: `{'dilution': <DilutionBasis.BASIC: 'basic'>}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `CHANGE_RATE_TO_LEVEL`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Change reporting sentence with rate-to-level compound structure*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 104 — [`BENCH-0184`] **SRE.JO** (2025-11-17 09:00)
- **Detected Label**: `dividend per share` (normalized: `dividend per share`)
- **Section Heading**: *€14.2m in the period*
- **Prior Sentence**: *"Sustainable FFO growth supports 24th progressive dividend payout"*
- **Target Sentence**: **"•   Progressive H1 dividend of 3.18c per share (30 September 2024: 3.06c) amounting to a 4.0% increase in dividend per share"**
- **Next Sentence**: *"Valuations underpinned by income"*
- **Detected Numbers**: `['3.18c', '30', '2024', '3.06c', '4.0%']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `dividend_per_share`
- Seed Qualifiers: `{'tax_basis': <DividendTaxBasis.GROSS: 'gross'>}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `CHANGE_RATE_TO_LEVEL`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Change reporting sentence with rate-to-level compound structure*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 105 — [`BENCH-0185`] **SRE.JO** (2025-11-17 09:00)
- **Detected Label**: `NAV per share` (normalized: `nav per share`)
- **Prior Sentence**: *"reflecting the industrial focused acquisition activity (31 March 2025: 6.3% and 8.9%) respectively"*
- **Target Sentence**: **"•   0.9% decrease in Adjusted NAV per share to 117.84c (31 March 2025: 118.89c), with valuation gains being offset by unrealised"**
- **Next Sentence**: *"foreign currency translation effects in the period on the Group’s UK assets being converted into the euro based reporting"*
- **Detected Numbers**: `['0.9%', '117.84c', '31', '2025', '118.89c']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `nav_per_share`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `CHANGE_RATE_TO_LEVEL`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Change reporting sentence with rate-to-level compound structure*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 106 — [`BENCH-0186`] **SRE.JO** (2025-11-17 09:00)
- **Detected Label**: `capex` (normalized: `capex`)
- **Prior Sentence**: *"•   New 5 year €150.0m undrawn Revolving Credit Facility from a syndicate of three banks, ABN Amro, BNP Paribas and HSBC,"*
- **Target Sentence**: **"providing capacity for acquisitions and capex investment, as well as efficient cash management"**
- **Next Sentence**: *"•   Additional €105.0m capital raised from its €359.9m 1.75% bonds due in November 2028 to provide firepower for the Group’s"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `G. Capex ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'capex' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 107 — [`BENCH-0187`] **SRE.JO** (2025-11-17 09:00)
- **Detected Label**: `Net Debt` (normalized: `net debt`)
- **Section Heading**: *acquisition pipeline*
- **Prior Sentence**: *"acquisition pipeline"*
- **Target Sentence**: **"•   38.3% net LTV (31 March 2025: 31.4%) (higher as available cash was invested into property) and Net Debt to EBITDA of 6.7x,"**
- **Next Sentence**: *"within our 40.0% net LTV and 8x target caps respectively"*
- **Detected Numbers**: `['38.3%', '31', '2025', '31.4%', '6.7']`
- **Difficulty Category**: `E. Debt/lease ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `REQUIRES_SOURCE_SECTION`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Ambiguous wording 'net debt' lacks balance sheet vs note presentation; requires source section*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 108 — [`BENCH-0188`] **SRE.JO** (2025-11-17 09:00)
- **Detected Label**: `EBITDA` (normalized: `ebitda`)
- **Section Heading**: *acquisition pipeline*
- **Prior Sentence**: *"acquisition pipeline"*
- **Target Sentence**: **"•   38.3% net LTV (31 March 2025: 31.4%) (higher as available cash was invested into property) and Net Debt to EBITDA of 6.7x,"**
- **Next Sentence**: *"within our 40.0% net LTV and 8x target caps respectively"*
- **Detected Numbers**: `['38.3%', '31', '2025', '31.4%', '6.7']`
- **Difficulty Category**: `H. Profit/EBIT/trading-profit ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `ebitda`
- Seed Qualifiers: `{'scope': <OperationScope.GROUP_CONSOLIDATED: 'group_consolidated'>}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE_WITH_QUALIFIER`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'ebitda' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 109 — [`BENCH-0191`] **SRE.JO** (2025-11-17 09:00)
- **Detected Label**: `basic earnings per share` (normalized: `basic earnings per share`)
- **Prior Sentence**: *"** Variance between basic and headline earnings per share is attributable to the gain on revaluation of investment properties (see"*
- **Target Sentence**: **"note 10 of the Group’s September 2025 interim results) being included in the calculation of basic earnings per share and excluded"**
- **Next Sentence**: *"from headline earnings per share."*
- **Detected Numbers**: `['10', '2025']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `eps`
- Seed Qualifiers: `{'dilution': <DilutionBasis.BASIC: 'basic'>}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `REQUIRES_PERIOD`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Ambiguous share wording 'basic earnings per share' lacks point-in-time vs period-end vs WANOS specification; requires period*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 110 — [`BENCH-0192`] **NY1.JO** (2025-11-17 09:00)
- **Detected Label**: `Adjusted operating profit` (normalized: `adjusted operating profit`)
- **Section Heading**: *Highlights*
- **Prior Sentence**: *"–    Net inflows of £4.3 billion (of which £1.9 billion related to Sanlam UK take-on in June)."*
- **Target Sentence**: **"–    Adjusted operating profit up 12% to £98.8 million."**
- **Next Sentence**: *"–    Adjusted operating profit margin improved to 32.1%."*
- **Detected Numbers**: `['12%', '£98.8 million']`
- **Difficulty Category**: `H. Profit/EBIT/trading-profit ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{'sign': <NumericSign.POSITIVE: 'positive'>, 'metric_basis': <MetricBasis.UNDERLYING_ADJUSTED: 'underlying_adjusted'>}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `REQUIRES_SCOPE`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Unknown / long-tail phrase 'adjusted operating profit'; requires expert review*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 111 — [`BENCH-0193`] **NY1.JO** (2025-11-17 09:00)
- **Detected Label**: `Adjusted operating profit margin improved to` (normalized: `adjusted operating profit margin improved to`)
- **Prior Sentence**: *"–    Adjusted operating profit up 12% to £98.8 million."*
- **Target Sentence**: **"–    Adjusted operating profit margin improved to 32.1%."**
- **Next Sentence**: *"–    Adjusted earnings per share up 15% to 8.4p."*
- **Detected Numbers**: `['32.1%']`
- **Difficulty Category**: `H. Profit/EBIT/trading-profit ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{'sign': <NumericSign.POSITIVE: 'positive'>, 'metric_basis': <MetricBasis.UNDERLYING_ADJUSTED: 'underlying_adjusted'>}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `CHANGE_RATE_ONLY`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Change / directional reporting sentence with percentage-only rate; ineligible as absolute historical baseline*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 112 — [`BENCH-0197`] **NY1.JO** (2025-11-17 09:00)
- **Detected Label**: `Dividend per share` (normalized: `dividend per share`)
- **Prior Sentence**: *"–    Adjusted earnings per share up 15% to 8.4p."*
- **Target Sentence**: **"–    Dividend per share up 11% to 6.0p."**
- **Next Sentence**: *"–    Competitive long-term investment performance."*
- **Detected Numbers**: `['11%', '6.0']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `dividend_per_share`
- Seed Qualifiers: `{'tax_basis': <DividendTaxBasis.GROSS: 'gross'>}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE_WITH_QUALIFIER`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'dividend_per_share' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 113 — [`BENCH-0198`] **NY1.JO** (2025-11-17 09:00)
- **Detected Label**: `Profit before tax` (normalized: `profit before tax`)
- **Prior Sentence**: *"30 September 2025                30 September 2024                    %"*
- **Target Sentence**: **"Profit before tax (£’m)                                   102.2                               93.3           10"**
- **Next Sentence**: *"Adjusted operating profit (£’m)                             98.8                              88.6           12"*
- **Detected Numbers**: `['102.2', '93.3', '10']`
- **Difficulty Category**: `A. Easy/direct`

**Deterministic Seed Baseline:**
- Seed Concept: `profit_before_tax`
- Seed Qualifiers: `{'sign': <NumericSign.POSITIVE: 'positive'>}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'profit_before_tax' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 114 — [`BENCH-0202`] **NY1.JO** (2025-11-17 09:00)
- **Detected Label**: `Basic earnings per share` (normalized: `basic earnings per share`)
- **Prior Sentence**: *"Adjusted operating profit margin                         32.1%                               30.5%"*
- **Target Sentence**: **"Basic earnings per share (p)                                 8.9                               7.8           14"**
- **Next Sentence**: *"Headline earnings per share (p)                              8.9                               7.8           14"*
- **Detected Numbers**: `['8.9', '7.8', '14']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `eps`
- Seed Qualifiers: `{'dilution': <DilutionBasis.BASIC: 'basic'>}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `REQUIRES_PERIOD`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Ambiguous share wording 'basic earnings per share' lacks point-in-time vs period-end vs WANOS specification; requires period*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 115 — [`BENCH-0203`] **NY1.JO** (2025-11-17 09:00)
- **Detected Label**: `Interim dividend per share` (normalized: `interim dividend per share`)
- **Prior Sentence**: *"Adjusted earnings per share (p)                              8.4                               7.3           15"*
- **Target Sentence**: **"Interim dividend per share (p)                               6.0                               5.4           11"**
- **Next Sentence**: *"Hendrik du Toit, Founder and Chief Executive Officer, commented:"*
- **Detected Numbers**: `['6.0', '5.4', '11']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `dividend_per_share`
- Seed Qualifiers: `{'tax_basis': <DividendTaxBasis.GROSS: 'gross'>, 'period_type': <PeriodType.INTERIM: 'interim'>}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE_WITH_QUALIFIER`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'dividend_per_share' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 116 — [`BENCH-0205`] **BTI.JO** (2025-11-17 09:00)
- **Detected Label**: `ordinary shares in issue` (normalized: `ordinary shares in issue`)
- **Section Heading**: *(pence):*
- **Prior Sentence**: *"Following the purchase and cancellation of these shares, the Company will have"*
- **Target Sentence**: **"2,182,847,115 ordinary shares in issue (excluding treasury shares) which carry voting rights"**
- **Next Sentence**: *"and will hold 132,998,061 ordinary shares in treasury. This information may be used by"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `issued_shares_current`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'ordinary shares in issue' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 117 — [`BENCH-0206`] **BTI.JO** (2025-11-17 09:00)
- **Detected Label**: `treasury shares` (normalized: `treasury shares`)
- **Section Heading**: *(pence):*
- **Prior Sentence**: *"Following the purchase and cancellation of these shares, the Company will have"*
- **Target Sentence**: **"2,182,847,115 ordinary shares in issue (excluding treasury shares) which carry voting rights"**
- **Next Sentence**: *"and will hold 132,998,061 ordinary shares in treasury. This information may be used by"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `treasury_shares`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'treasury shares' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 118 — [`BENCH-0207`] **MSP.JO** (2025-11-17 08:30)
- **Detected Label**: `treasury shares` (normalized: `treasury shares`)
- **Prior Sentence**: *"No Shares were repurchased during a closed period."*
- **Target Sentence**: **"Following the General Repurchase: MAS holds 37,749,201 Shares as treasury shares, representing 5.40% of the Company’s Shares in"**
- **Next Sentence**: *"issue as at the date of this announcement. Of these, 16,586,906 are held by a subsidiary of the Company. The extent of the general authority"*
- **Detected Numbers**: `['5.40%']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `treasury_shares`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `CHANGE_RATE_ONLY`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Change / directional reporting sentence with percentage-only rate; ineligible as absolute historical baseline*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 119 — [`BENCH-0208`] **MSP.JO** (2025-11-17 08:30)
- **Detected Label**: `total liabilities` (normalized: `total liabilities`)
- **Section Heading**: *following the date of the General Authority, under which the General Repurchase was executed:*
- **Prior Sentence**: *"• the Company and the Group will be able to pay its debts in the ordinary course of business;"*
- **Target Sentence**: **"• the total assets of the Company and the Group will be in excess of the total liabilities of the Company and the Group. For this purpose, the"**
- **Next Sentence**: *"assets and liabilities were recognised and measured in accordance with the accounting policies used in the latest audited annual Group"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `I. Unknown/long-tail`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'total liabilities' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 120 — [`BENCH-0209`] **MSP.JO** (2025-11-17 08:30)
- **Detected Label**: `total assets` (normalized: `total assets`)
- **Section Heading**: *following the date of the General Authority, under which the General Repurchase was executed:*
- **Prior Sentence**: *"• the Company and the Group will be able to pay its debts in the ordinary course of business;"*
- **Target Sentence**: **"• the total assets of the Company and the Group will be in excess of the total liabilities of the Company and the Group. For this purpose, the"**
- **Next Sentence**: *"assets and liabilities were recognised and measured in accordance with the accounting policies used in the latest audited annual Group"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `I. Unknown/long-tail`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'total assets' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 121 — [`BENCH-0210`] **MSP.JO** (2025-11-17 08:30)
- **Detected Label**: `working capital` (normalized: `working capital`)
- **Section Heading**: *financial statements;*
- **Prior Sentence**: *"financial statements;"*
- **Target Sentence**: **"• the share capital, reserves and working capital of the Company and the Group will be adequate for ordinary business purposes; and"**
- **Next Sentence**: *"• the Company and the Group have passed the solvency and liquidity test and since the test was performed there have been no material"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `D. Basis ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'working capital' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 122 — [`BENCH-0211`] **THA.JO** (2025-11-17 15:00)
- **Detected Label**: `Ordinary Shares in issue` (normalized: `ordinary shares in issue`)
- **Prior Sentence**: *"dealing and associated costs) of GBP2 579 653.77."*
- **Target Sentence**: **"Following the purchases during this period, the Company has 302 596 743 Ordinary Shares in issue,"**
- **Next Sentence**: *"of which 8 571 346 Ordinary Shares are held in treasury."*
- **Detected Numbers**: `['302 596 743']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `issued_shares_current`
- Seed Qualifiers: `{}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'issued_shares_current' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 123 — [`BENCH-0212`] **SRE.JO** (2025-11-17 16:00)
- **Detected Label**: `taxation` (normalized: `taxation`)
- **Section Heading**: *estate.com/investors/dividends/.*
- **Prior Sentence**: *"estate.com/investors/dividends/."*
- **Target Sentence**: **"4. Property Income Distribution (‘PID’), non-PID and taxation"**
- **Next Sentence**: *"Shareholders are advised that the cash dividend declared will be paid as 53% PID and 47% non-PID."*
- **Detected Numbers**: `['4']`
- **Difficulty Category**: `A. Easy/direct`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `REQUIRES_SOURCE_SECTION`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Ambiguous wording 'taxation' lacks balance sheet vs note presentation; requires source section*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 124 — [`BENCH-0214`] **WHL.JO** (2025-11-17 17:05)
- **Detected Label**: `Treasury Shares` (normalized: `treasury shares`)
- **Section Heading**: *(repurchase) shares*
- **Prior Sentence**: *"*  The total issued share capital of the Company as at the record date of 7 November 2025 was 982,598,237"*
- **Target Sentence**: **"ordinary shares, including 84,261,465 Treasury Shares."**
- **Next Sentence**: *"** Having engaged extensively with the Company’s major shareholders prior to the AGM, the Board is"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `treasury_shares`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'treasury shares' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 125 — [`BENCH-0215`] **BTI.JO** (2025-11-18 09:00)
- **Detected Label**: `treasury shares` (normalized: `treasury shares`)
- **Section Heading**: *(pence):*
- **Prior Sentence**: *"Following the purchase and cancellation of these shares, the Company will have"*
- **Target Sentence**: **"2,182,709,115 ordinary shares in issue (excluding treasury shares) which carry voting rights"**
- **Next Sentence**: *"and will hold 132,998,061 ordinary shares in treasury. This information may be used by"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `treasury_shares`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'treasury shares' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 126 — [`BENCH-0216`] **RNI.JO** (2025-11-18 08:00)
- **Detected Label**: `Net asset value per share` (normalized: `net asset value per share`)
- **Prior Sentence**: *"–  The net asset value at 30 September 2025 reflects a decrease of EUR 257 million or 3.7 per cent from EUR 6 915 million at 31 March 2025"*
- **Target Sentence**: **"–  Net asset value per share at 30 September 2025: EUR 36.62 (31 March 2025: EUR 38.04, 30 September 2024: EUR 36.25)"**
- **Next Sentence**: *"–  Commitments totalling EUR 298 million in respect of new and existing investments were made during the period, with a total of EUR 7 million funded"*
- **Detected Numbers**: `['30', '2025', 'EUR 36.62', '31', '2025', 'EUR 38.04', '30', '2024', 'EUR 36.25']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `nav_per_share`
- Seed Qualifiers: `{}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'nav_per_share' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 127 — [`BENCH-0217`] **CML.JO** (2025-11-18 07:30)
- **Detected Label**: `Revenue increased by` (normalized: `revenue increased by`)
- **Section Heading**: *1.   SALIENT FEATURES*
- **Prior Sentence**: *"1.   SALIENT FEATURES"*
- **Target Sentence**: **"Revenue increased by 10% to R4,291 million from R3,913 million in the prior"**
- **Next Sentence**: *"corresponding period."*
- **Detected Numbers**: `['10%', 'R4,291 million', 'R3,913 million']`
- **Difficulty Category**: `B. Change statements`

**Deterministic Seed Baseline:**
- Seed Concept: `accounting_revenue`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `FROM_TO_LEVEL`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Change reporting sentence with from-to level compound structure*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 128 — [`BENCH-0218`] **CML.JO** (2025-11-18 07:30)
- **Detected Label**: `earnings per share decreased by` (normalized: `earnings per share decreased by`)
- **Prior Sentence**: *"foreign exchange movements on investment securities held for seeding products. Fund"*
- **Target Sentence**: **"management earnings per share decreased by 26% to 454.0 cents per share from 617.1"**
- **Next Sentence**: *"cents per share in the prior corresponding period. Headline earnings per share and"*
- **Detected Numbers**: `['26%', '454.0 cents', '617.1']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `eps`
- Seed Qualifiers: `{'dilution': <DilutionBasis.BASIC: 'basic'>, 'metric_basis': <MetricBasis.REPORTED_STATUTORY: 'reported_statutory'>}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `FROM_TO_LEVEL`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Change reporting sentence with from-to level compound structure*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 129 — [`BENCH-0220`] **TKG.JO** (2025-11-18 07:15)
- **Detected Label**: `Group revenue` (normalized: `group revenue`)
- **Section Heading**: *Group highlights*
- **Prior Sentence**: *"Group highlights"*
- **Target Sentence**: **"– Group revenue up 3.4% to R22 104 million, driven by robust mobile data"**
- **Next Sentence**: *"revenue growth (+10.3%) and fibre-related data revenue (+12.3%)."*
- **Detected Numbers**: `['3.4%', 'R22 104 million']`
- **Difficulty Category**: `A. Easy/direct`

**Deterministic Seed Baseline:**
- Seed Concept: `accounting_revenue`
- Seed Qualifiers: `{'scope': <OperationScope.GROUP_CONSOLIDATED: 'group_consolidated'>, 'sign': <NumericSign.POSITIVE: 'positive'>}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE_WITH_QUALIFIER`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'accounting_revenue' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 130 — [`BENCH-0221`] **TKG.JO** (2025-11-18 07:15)
- **Detected Label**: `total revenue` (normalized: `total revenue`)
- **Section Heading**: *Group highlights*
- **Prior Sentence**: *"revenue growth (+10.3%) and fibre-related data revenue (+12.3%)."*
- **Target Sentence**: **"– Group data revenue up 7.9% contributing 59.1% to total revenue."**
- **Next Sentence**: *"– Group EBITDA(1,2) up 7.4%(3) to R6 023 million, due to revenue growth"*
- **Detected Numbers**: `['7.9%', '59.1%']`
- **Difficulty Category**: `B. Change statements`

**Deterministic Seed Baseline:**
- Seed Concept: `accounting_revenue`
- Seed Qualifiers: `{'scope': <OperationScope.GROUP_CONSOLIDATED: 'group_consolidated'>, 'sign': <NumericSign.POSITIVE: 'positive'>}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `CHANGE_RATE_ONLY`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Change / directional reporting sentence with percentage-only rate; ineligible as absolute historical baseline*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 131 — [`BENCH-0222`] **TKG.JO** (2025-11-18 07:15)
- **Detected Label**: `Group EBITDA` (normalized: `group ebitda`)
- **Prior Sentence**: *"– Group data revenue up 7.9% contributing 59.1% to total revenue."*
- **Target Sentence**: **"– Group EBITDA(1,2) up 7.4%(3) to R6 023 million, due to revenue growth"**
- **Next Sentence**: *"and ongoing cost optimisation initiatives, resulting in the EBITDA margin(1)"*
- **Detected Numbers**: `['1,2', '7.4%', '3', 'R6 023 million']`
- **Difficulty Category**: `H. Profit/EBIT/trading-profit ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `ebitda`
- Seed Qualifiers: `{'scope': <OperationScope.GROUP_CONSOLIDATED: 'group_consolidated'>}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `CHANGE_RATE_TO_LEVEL`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Change reporting sentence with rate-to-level compound structure*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 132 — [`BENCH-0225`] **TKG.JO** (2025-11-18 07:15)
- **Detected Label**: `Net debt` (normalized: `net debt`)
- **Section Heading**: *expanding to 27.2%.*
- **Prior Sentence**: *"expanding to 27.2%."*
- **Target Sentence**: **"– Net debt to EBITDA(1,2,4) stable at 0.7x indicating a robust financial position"**
- **Next Sentence**: *"and allowing for investment in future growth opportunities."*
- **Detected Numbers**: `['1,2', '4', '0.7']`
- **Difficulty Category**: `E. Debt/lease ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `REQUIRES_SOURCE_SECTION`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Ambiguous wording 'net debt' lacks balance sheet vs note presentation; requires source section*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 133 — [`BENCH-0227`] **TKG.JO** (2025-11-18 07:15)
- **Detected Label**: `Free cash flow` (normalized: `free cash flow`)
- **Section Heading**: *expanding to 27.2%.*
- **Prior Sentence**: *"and allowing for investment in future growth opportunities."*
- **Target Sentence**: **"– Free cash flow stable at R724 million, reflecting disciplined and sustainable"**
- **Next Sentence**: *"cash generation."*
- **Detected Numbers**: `['R724 million']`
- **Difficulty Category**: `I. Unknown/long-tail`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `REQUIRES_SCOPE`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Unknown / long-tail phrase 'free cash flow'; requires expert review*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 134 — [`BENCH-0228`] **TKG.JO** (2025-11-18 07:15)
- **Detected Label**: `HEPS` (normalized: `heps`)
- **Section Heading**: *cash generation.*
- **Prior Sentence**: *"cash generation."*
- **Target Sentence**: **"– Headline earnings per share (HEPS)(1) up 16.4%(3) to 305.6 cents underscoring"**
- **Next Sentence**: *"the benefits of focused execution and improved profitability."*
- **Detected Numbers**: `['1', '16.4%', '3', '305.6 cents']`
- **Difficulty Category**: `A. Easy/direct`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `REQUIRES_SCOPE`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Ambiguous wording 'heps' conflates operating definitions or segments; requires scope*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 135 — [`BENCH-0229`] **TKG.JO** (2025-11-18 07:15)
- **Detected Label**: `Basic earnings per share` (normalized: `basic earnings per share`)
- **Section Heading**: *cash generation.*
- **Prior Sentence**: *"the benefits of focused execution and improved profitability."*
- **Target Sentence**: **"– Basic earnings per share (BEPS) up 12.7%(3) to 325.7 cents."**
- **Next Sentence**: *"Summary financial results"*
- **Detected Numbers**: `['12.7%', '3', '325.7 cents']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `eps`
- Seed Qualifiers: `{'dilution': <DilutionBasis.BASIC: 'basic'>}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `REQUIRES_PERIOD`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Ambiguous share wording 'basic earnings per share' lacks point-in-time vs period-end vs WANOS specification; requires period*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 136 — [`BENCH-0230`] **TKG.JO** (2025-11-18 07:15)
- **Detected Label**: `Profit for the period` (normalized: `profit for the period`)
- **Section Heading**: *EBITDA(1,2,4)                   6 023       4 828      +24.8          5 606          +7.4*
- **Prior Sentence**: *"EBITDA(1,2,4)                   6 023       4 828      +24.8          5 606          +7.4"*
- **Target Sentence**: **"Profit for the period           1 604         853      +88.0          1 421         +12.9"**
- **Next Sentence**: *"Dividend (cps)                      –           –          –              –             –"*
- **Detected Numbers**: `['1 604', '853', '+88.0', '1 421', '+12.9']`
- **Difficulty Category**: `A. Easy/direct`

**Deterministic Seed Baseline:**
- Seed Concept: `profit_for_period`
- Seed Qualifiers: `{'scope': <OperationScope.GROUP_CONSOLIDATED: 'group_consolidated'>, 'attribution': <ProfitAttribution.TOTAL_GROUP: 'total_group'>, 'sign': <NumericSign.POSITIVE: 'positive'>}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE_WITH_QUALIFIER`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'profit_for_period' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 137 — [`BENCH-0232`] **TKG.JO** (2025-11-18 07:15)
- **Detected Label**: `depreciation and amortisation` (normalized: `depreciation and amortisation`)
- **Prior Sentence**: *"Discontinued(5)                                –          44.6       (100.0)         44.6        (100.0)"*
- **Target Sentence**: **"1 Earnings before interest, tax, depreciation and amortisation."**
- **Next Sentence**: *"2 This is a non-IFRS financial measure."*
- **Detected Numbers**: `['1']`
- **Difficulty Category**: `A. Easy/direct`

**Deterministic Seed Baseline:**
- Seed Concept: `depreciation_and_amortisation`
- Seed Qualifiers: `{}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'depreciation_and_amortisation' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 138 — [`BENCH-0235`] **TKG.JO** (2025-11-18 07:15)
- **Detected Label**: `net debt` (normalized: `net debt`)
- **Prior Sentence**: *"4 EBITDA is annualised to ensure comparability between EBITDA and the cumulative"*
- **Target Sentence**: **"balance of net debt when determining the net debt to EBITDA ratio."**
- **Next Sentence**: *"5 Swiftnet continued to meet the IFRS 5 requirements and was classified as"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `E. Debt/lease ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'net debt' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 139 — [`BENCH-0236`] **TKG.JO** (2025-11-18 07:15)
- **Detected Label**: `revenue grew by` (normalized: `revenue grew by`)
- **Section Heading**: *Telkom Consumer*
- **Prior Sentence**: *"Telkom Consumer"*
- **Target Sentence**: **"– Mobile service revenue grew by 7.9%"**
- **Next Sentence**: *"– 26.7% increase in mobile data subscriber base to 18.5 million"*
- **Detected Numbers**: `['7.9%']`
- **Difficulty Category**: `B. Change statements`

**Deterministic Seed Baseline:**
- Seed Concept: `accounting_revenue`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `CHANGE_RATE_ONLY`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Change / directional reporting sentence with percentage-only rate; ineligible as absolute historical baseline*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 140 — [`BENCH-0239`] **TKG.JO** (2025-11-18 07:15)
- **Detected Label**: `revenue increased by` (normalized: `revenue increased by`)
- **Section Heading**: *BCX*
- **Prior Sentence**: *"BCX"*
- **Target Sentence**: **"– Fibre-related data revenue increased by 13.8%"**
- **Next Sentence**: *"– Cloud services revenue growth of 10.4%"*
- **Detected Numbers**: `['13.8%']`
- **Difficulty Category**: `B. Change statements`

**Deterministic Seed Baseline:**
- Seed Concept: `accounting_revenue`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `CHANGE_RATE_ONLY`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Change / directional reporting sentence with percentage-only rate; ineligible as absolute historical baseline*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 141 — [`BENCH-0240`] **SRE.JO** (2025-11-17 10:00)
- **Detected Label**: `profit after tax` (normalized: `profit after tax`)
- **Target Sentence**: **"?   56.8% increase in profit after tax to ?87.0m (30 September 2024: ?55.5m) due to strong operational performance, valuation"**
- **Next Sentence**: *"gain and release of deferred tax liabilities in the German portfolio as the German government enacted an annual 1% reduction"*
- **Detected Numbers**: `['56.8%', '87.0m', '30', '2024', '55.5m']`
- **Difficulty Category**: `B. Change statements`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{'sign': <NumericSign.POSITIVE: 'positive'>}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `CHANGE_RATE_TO_LEVEL`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Change reporting sentence with rate-to-level compound structure*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 142 — [`BENCH-0241`] **SRE.JO** (2025-11-17 10:00)
- **Detected Label**: `profit before tax` (normalized: `profit before tax`)
- **Section Heading**: *acquisitions in future periods*
- **Prior Sentence**: *"acquisitions in future periods"*
- **Target Sentence**: **"?   6.0% decrease in profit before tax to ?57.5m (30 September 2024: ?61.2m) primarily due to a net foreign exchange loss of"**
- **Next Sentence**: *"?14.2m on sterling cash reserves held in anticipation of UK investments made in the period"*
- **Detected Numbers**: `['6.0%', '57.5m', '30', '2024', '61.2m']`
- **Difficulty Category**: `B. Change statements`

**Deterministic Seed Baseline:**
- Seed Concept: `profit_before_tax`
- Seed Qualifiers: `{'sign': <NumericSign.POSITIVE: 'positive'>}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `CHANGE_RATE_TO_LEVEL`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Change reporting sentence with rate-to-level compound structure*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 143 — [`BENCH-0242`] **SRE.JO** (2025-11-17 10:00)
- **Detected Label**: `Basic earnings per share increased by` (normalized: `basic earnings per share increased by`)
- **Section Heading**: *acquisitions in future periods*
- **Prior Sentence**: *"?14.2m on sterling cash reserves held in anticipation of UK investments made in the period"*
- **Target Sentence**: **"?   Basic earnings per share increased by 47.2% to 5.77c (30 September 2024: 3.92c) reflecting the strong 57% growth in profit"**
- **Next Sentence**: *"after tax and the higher shares in issue following the equity issuance in July 2024 while headline earnings and EPRA earnings"*
- **Detected Numbers**: `['47.2%', '5.77c', '30', '2024', '3.92c', '57%']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `eps`
- Seed Qualifiers: `{'dilution': <DilutionBasis.BASIC: 'basic'>}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `CHANGE_RATE_TO_LEVEL`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Change reporting sentence with rate-to-level compound structure*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 144 — [`BENCH-0245`] **NRP.JO** (2025-11-19 09:00)
- **Detected Label**: `turnover increased by` (normalized: `turnover increased by`)
- **Section Heading**: *for 9M 2024).*
- **Prior Sentence**: *"for 9M 2024)."*
- **Target Sentence**: **"Tenant turnover increased by 3.5% LFL for the period, while footfall was slightly lower (-0.6%). Average spend per"**
- **Next Sentence**: *"visitor rose 9% overall – supported by the higher basket size in the two large properties acquired in Poland last year"*
- **Detected Numbers**: `['3.5%', '-0.6%']`
- **Difficulty Category**: `B. Change statements`

**Deterministic Seed Baseline:**
- Seed Concept: `turnover`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `CHANGE_RATE_ONLY`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Change / directional reporting sentence with percentage-only rate; ineligible as absolute historical baseline*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 145 — [`BENCH-0247`] **NRP.JO** (2025-11-19 09:00)
- **Detected Label**: `sales increased by` (normalized: `sales increased by`)
- **Section Heading**: *Trading update*
- **Prior Sentence**: *"Trading update"*
- **Target Sentence**: **"LFL tenant sales increased by 3.5% year-on-year in 9M 2025 and footfall decreased by 0.6%. On a quarterly basis,"**
- **Next Sentence**: *"tenant sales rose 2.9% in Q3 year-on-year, while footfall was down 1.5% following a strong start to the year that"*
- **Detected Numbers**: `['3.5%', '9M', '2025', '0.6%']`
- **Difficulty Category**: `C. Scope ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `CHANGE_RATE_TO_LEVEL`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Change reporting sentence with rate-to-level compound structure*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 146 — [`BENCH-0248`] **NRP.JO** (2025-11-19 09:00)
- **Detected Label**: `interest bearing debt` (normalized: `interest bearing debt`)
- **Section Heading**: *CASH MANAGEMENT AND DEBT*
- **Prior Sentence**: *"As of 30 September 2025, NEPI Rockcastle had a very strong liquidity profile, with EUR421 million in cash and"*
- **Target Sentence**: **"EUR690 million in undrawn committed credit facilities. The Group’s gearing ratio (interest bearing debt less cash,"**
- **Next Sentence**: *"divided by investment property plus cost incurred for photovoltaic plants) was 31.4%, comfortably below the 35%"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `E. Debt/lease ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `interest_bearing_borrowings`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'interest bearing debt' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 147 — [`BENCH-0249`] **NRP.JO** (2025-11-19 09:00)
- **Detected Label**: `total assets` (normalized: `total assets`)
- **Section Heading**: *covenants, as follows:*
- **Prior Sentence**: *"– Consolidated Interest Coverage Ratio: 4.9 actual compared to minimum 2.0 requirement"*
- **Target Sentence**: **"– Unencumbered consolidated total assets/unsecured consolidated total debt: 270% actual compared to"**
- **Next Sentence**: *"minimum 150% requirement"*
- **Detected Numbers**: `['270%']`
- **Difficulty Category**: `B. Change statements`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `CHANGE_RATE_ONLY`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Change / directional reporting sentence with percentage-only rate; ineligible as absolute historical baseline*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 148 — [`BENCH-0250`] **NRP.JO** (2025-11-19 09:00)
- **Detected Label**: `earnings per share for the year` (normalized: `earnings per share for the year`)
- **Section Heading**: *OUTLOOK*
- **Prior Sentence**: *"OUTLOOK"*
- **Target Sentence**: **"The Board reaffirms its guidance updated in August 2025 that distributable earnings per share for the year will be"**
- **Next Sentence**: *"2.5% to 3% higher than 2024 distributable earnings per share, with no change in the Company’s current 90%"*
- **Detected Numbers**: `['2025']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `eps`
- Seed Qualifiers: `{'dilution': <DilutionBasis.BASIC: 'basic'>, 'metric_basis': <MetricBasis.REPORTED_STATUTORY: 'reported_statutory'>, 'period_type': <PeriodType.FULL_YEAR: 'full_year'>}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'earnings per share for the year' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 149 — [`BENCH-0251`] **MTM.JO** (2025-11-19 07:30)
- **Detected Label**: `headline earnings (NHE) of R1` (normalized: `headline earnings (nhe) of r1`)
- **Section Heading**: *of IFRS 17.*
- **Prior Sentence**: *"The positive earnings trajectory established during F2025 continued into the first quarter of F2026. The Group delivered a strong operational performance"*
- **Target Sentence**: **"with normalised headline earnings (NHE) of R1 759 million, for the three months ended 30 September 2025. These results were underpinned by effective"**
- **Next Sentence**: *"strategic execution and continued focus on profitable growth across the Group’s business units. The Group’s earnings were further supported by positive"*
- **Detected Numbers**: `['R1 759 million', '30', '2025']`
- **Difficulty Category**: `A. Easy/direct`

**Deterministic Seed Baseline:**
- Seed Concept: `headline_earnings`
- Seed Qualifiers: `{'attribution': <ProfitAttribution.HEADLINE_ATTRIBUTABLE: 'headline_attributable'>, 'metric_basis': <MetricBasis.HEADLINE: 'headline'>}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `REQUIRES_PERIOD`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Context required to verify period type, scope, or accounting attribution*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 150 — [`BENCH-0252`] **SSU.JO** (2025-11-19 07:15)
- **Detected Label**: `Net debt` (normalized: `net debt`)
- **Section Heading**: *– AHEPS steady at 24.9 cents*
- **Prior Sentence**: *"– AHEPS steady at 24.9 cents"*
- **Target Sentence**: **"– Net debt at R481 million"**
- **Next Sentence**: *"Supplementary information"*
- **Detected Numbers**: `['R481 million']`
- **Difficulty Category**: `E. Debt/lease ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `REQUIRES_SOURCE_SECTION`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Ambiguous wording 'net debt' lacks balance sheet vs note presentation; requires source section*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 151 — [`BENCH-0253`] **SSU.JO** (2025-11-19 07:15)
- **Detected Label**: `Attributable earnings for the period` (normalized: `attributable earnings for the period`)
- **Section Heading**: *Unaudited      Unaudited      change*
- **Prior Sentence**: *"Ebitdar (Rm)                                                       818            822           –"*
- **Target Sentence**: **"Attributable earnings for the period (Rm)                          329            332          (1)"**
- **Next Sentence**: *"Adjusted headline earnings for the period (Rm)                     334            334           –"*
- **Detected Numbers**: `['329', '332', '1']`
- **Difficulty Category**: `A. Easy/direct`

**Deterministic Seed Baseline:**
- Seed Concept: `attributable_earnings`
- Seed Qualifiers: `{'attribution': <ProfitAttribution.PARENT_EQUITY_HOLDERS: 'parent_equity_holders'>}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `REQUIRES_PERIOD`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Context required to verify period type, scope, or accounting attribution*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 152 — [`BENCH-0255`] **SSU.JO** (2025-11-19 07:15)
- **Detected Label**: `headline earnings for the period` (normalized: `headline earnings for the period`)
- **Prior Sentence**: *"Attributable earnings for the period (Rm)                          329            332          (1)"*
- **Target Sentence**: **"Adjusted headline earnings for the period (Rm)                     334            334           –"**
- **Next Sentence**: *"Basic earnings per share (cents)                                  24.5           24.7          (1)"*
- **Detected Numbers**: `['334', '334']`
- **Difficulty Category**: `A. Easy/direct`

**Deterministic Seed Baseline:**
- Seed Concept: `headline_earnings`
- Seed Qualifiers: `{'attribution': <ProfitAttribution.HEADLINE_ATTRIBUTABLE: 'headline_attributable'>, 'metric_basis': <MetricBasis.HEADLINE: 'headline'>}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE_WITH_QUALIFIER`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'headline_earnings' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 153 — [`BENCH-0256`] **SSU.JO** (2025-11-19 07:15)
- **Detected Label**: `interest-bearing debt` (normalized: `interest-bearing debt`)
- **Prior Sentence**: *"successfully refinanced its debt package into two-year revolving credit facilities maturing on 30 September 2027, with an"*
- **Target Sentence**: **"option to extend for a further 12 months to 30 September 2028. Net interest-bearing debt increased to R481 million at"**
- **Next Sentence**: *"30 September (2024: R995 million), up R215 million from the year-end balance of R266 million."*
- **Detected Numbers**: `['12', '30', '2028', 'R481 million']`
- **Difficulty Category**: `E. Debt/lease ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `REQUIRES_SOURCE_SECTION`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Ambiguous wording 'interest-bearing debt' lacks balance sheet vs note presentation; requires source section*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 154 — [`BENCH-0257`] **LHC.JO** (2025-11-19 07:05)
- **Detected Label**: `revenue growth for the year` (normalized: `revenue growth for the year`)
- **Prior Sentence**: *"The Group delivered good overall revenue growth between 5.5% and 6.5% driven by paid patient days (PPDs) increasing by c.1.1% (1)"*
- **Target Sentence**: **"supported by a 5.1% tariff increase. The acute business revenue growth for the year was c. 5.0% with acute PPDs growing by c.0.9%. On a"**
- **Next Sentence**: *"like-for-like basis, the acute revenue increased between 6.1% and 6.5%. Complementary services revenue growth was c. 24.7% benefitting"*
- **Detected Numbers**: `['5.1%', '5.0%', '0.9%']`
- **Difficulty Category**: `B. Change statements`

**Deterministic Seed Baseline:**
- Seed Concept: `accounting_revenue`
- Seed Qualifiers: `{'sign': <NumericSign.POSITIVE: 'positive'>, 'period_type': <PeriodType.FULL_YEAR: 'full_year'>}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `CHANGE_RATE_ONLY`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Change / directional reporting sentence with percentage-only rate; ineligible as absolute historical baseline*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 155 — [`BENCH-0258`] **LHC.JO** (2025-11-19 07:05)
- **Detected Label**: `revenue declined by` (normalized: `revenue declined by`)
- **Prior Sentence**: *"like-for-like basis, the acute revenue increased between 6.1% and 6.5%. Complementary services revenue growth was c. 24.7% benefitting"*
- **Target Sentence**: **"from acquisitions and PPDs grew by c.3.1%. Healthcare services businesses’ revenue declined by c. 7.5 %, impacted by the loss of two"**
- **Next Sentence**: *"government contracts during H2-FY2024."*
- **Detected Numbers**: `['3.1%', '7.5']`
- **Difficulty Category**: `B. Change statements`

**Deterministic Seed Baseline:**
- Seed Concept: `accounting_revenue`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `CHANGE_RATE_TO_LEVEL`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Change reporting sentence with rate-to-level compound structure*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 156 — [`BENCH-0259`] **LHC.JO** (2025-11-19 07:05)
- **Detected Label**: `Normalised EBITDA` (normalized: `normalised ebitda`)
- **Section Heading**: *government contracts during H2-FY2024.*
- **Prior Sentence**: *"The weighted average occupancy for FY2025 was 69.7% vs FY2024 of 69.0%."*
- **Target Sentence**: **"Normalised EBITDA(2) increased between 4.5% and 5.0%. On a like-for-like basis, the normalised EBITDA increased between 6.6% and 7.1%."**
- **Next Sentence**: *"The Group’s normalised EBITDA margin remained stable in H1-FY2025 and H2-FY2025, with the acute business delivering an improved"*
- **Detected Numbers**: `['2', '4.5%', '5.0%', '6.6%', '7.1%']`
- **Difficulty Category**: `H. Profit/EBIT/trading-profit ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `normalised_ebitda`
- Seed Qualifiers: `{'metric_basis': <MetricBasis.NORMALISED: 'normalised'>}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `CHANGE_RATE_TO_LEVEL`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Change reporting sentence with rate-to-level compound structure*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 157 — [`BENCH-0261`] **LHC.JO** (2025-11-19 07:05)
- **Detected Label**: `operating profit before depreciation on property, plant and equipment, amortisation of intangible assets` (normalized: `operating profit before depreciation on property, plant and equipment, amortisation of intangible assets`)
- **Section Heading**: *of the Alliance Medical Group (AMG).*
- **Prior Sentence**: *"(1) On a like for like basis, excluding PPDs of a facility sold in the current year."*
- **Target Sentence**: **"(2) Life Healthcare defines normalised EBITDA as operating profit before depreciation on property, plant and equipment, amortisation of intangible assets"**
- **Next Sentence**: *"and non-trading related costs and income."*
- **Detected Numbers**: `['2']`
- **Difficulty Category**: `H. Profit/EBIT/trading-profit ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `operating_profit`
- Seed Qualifiers: `{'sign': <NumericSign.POSITIVE: 'positive'>}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `REQUIRES_PERIOD`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Context required to verify period type, scope, or accounting attribution*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 158 — [`BENCH-0267`] **LHC.JO** (2025-11-19 07:05)
- **Detected Label**: `EPS` (normalized: `eps`)
- **Prior Sentence**: *"(associated with LMI). The table also includes impairments of c.R210 million in respect of underperforming units."*
- **Target Sentence**: **"Normalised earnings per share (NEPS), which excludes non-trading related items, better reflects the performance of our southern African"**
- **Next Sentence**: *"underlying business."*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `A. Easy/direct`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'eps' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 159 — [`BENCH-0268`] **LHC.JO** (2025-11-19 07:05)
- **Detected Label**: `HEPS` (normalized: `heps`)
- **Section Heading**: *operations*
- **Prior Sentence**: *"EPS                                          -104.2 to -108.8                          201.0       +92.2 to +96.8         92.2*         >-100%            0% to 5%         2"*
- **Target Sentence**: **"HEPS                                           -91.7 to -96.4                          201.0     +104.6 to +109.3         93.4*         >-100%          12% to 17%         2"**
- **Next Sentence**: *"From continuing and"*
- **Detected Numbers**: `['-91.7', '-96.4', '201.0', '+104.6', '+109.3', '93.4', '-100%', '12%', '17%', '2']`
- **Difficulty Category**: `A. Easy/direct`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `REQUIRES_SCOPE`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Ambiguous wording 'heps' conflates operating definitions or segments; requires scope*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 160 — [`BENCH-0271`] **LHC.JO** (2025-11-19 07:05)
- **Detected Label**: `HEPS or NEPS from continuing operations` (normalized: `heps or neps from continuing operations`)
- **Prior Sentence**: *"earnings per share (HEPS) from continuing and discontinued operations."*
- **Target Sentence**: **"– The above had no impact on EPS, HEPS or NEPS from continuing operations."**
- **Next Sentence**: *"2. Disposal of LMI"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `C. Scope ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `heps`
- Seed Qualifiers: `{'scope': <OperationScope.CONTINUING_OPERATIONS: 'continuing_operations'>, 'dilution': <DilutionBasis.BASIC: 'basic'>}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'heps or neps from continuing operations' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 161 — [`BENCH-0277`] **EPE.JO** (2025-11-18 17:27)
- **Detected Label**: `Total assets` (normalized: `total assets`)
- **Prior Sentence**: *"Residual Assets (Other unlisted portfolio assets)                     881               901"*
- **Target Sentence**: **"Total assets                                                        2,371             2,428"**
- **Next Sentence**: *"Net (debt) / cash                                                   (177)             (149)"*
- **Detected Numbers**: `['2,371', '2,428']`
- **Difficulty Category**: `I. Unknown/long-tail`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `REQUIRES_SCOPE`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Unknown / long-tail phrase 'total assets'; requires expert review*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 162 — [`BENCH-0278`] **EPE.JO** (2025-11-18 17:27)
- **Detected Label**: `Net debt` (normalized: `net debt`)
- **Prior Sentence**: *"NAVPS – Rand                                                      8.90                     9.41"*
- **Target Sentence**: **"(1) Net debt decreased to net cash post IPO proceeds"**
- **Next Sentence**: *"The adjusted NAVPS of R9.41 represents a 9.8% increase over Ethos Capital’s 30 June 2025 NAVPS"*
- **Detected Numbers**: `['1']`
- **Difficulty Category**: `E. Debt/lease ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `REQUIRES_SOURCE_SECTION`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Ambiguous wording 'net debt' lacks balance sheet vs note presentation; requires source section*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 163 — [`BENCH-0279`] **EPE.JO** (2025-11-18 17:27)
- **Detected Label**: `net cash` (normalized: `net cash`)
- **Prior Sentence**: *"NAVPS – Rand                                                      8.90                     9.41"*
- **Target Sentence**: **"(1) Net debt decreased to net cash post IPO proceeds"**
- **Next Sentence**: *"The adjusted NAVPS of R9.41 represents a 9.8% increase over Ethos Capital’s 30 June 2025 NAVPS"*
- **Detected Numbers**: `['1']`
- **Difficulty Category**: `B. Change statements`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `REQUIRES_SCOPE`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Ambiguous wording 'net cash'; maps to multiple concepts; requires context*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 164 — [`BENCH-0280`] **EPE.JO** (2025-11-18 17:27)
- **Detected Label**: `TAXATION` (normalized: `taxation`)
- **Prior Sentence**: *"in accordance with the JSE Listings Requirements."*
- **Target Sentence**: **"5.      TAXATION"**
- **Next Sentence**: *"5.1          The 2025 Brait Unbundling constitutes a return of capital by Ethos Capital (a company"*
- **Detected Numbers**: `['5']`
- **Difficulty Category**: `A. Easy/direct`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `REQUIRES_SOURCE_SECTION`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Ambiguous wording 'taxation' lacks balance sheet vs note presentation; requires source section*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 165 — [`BENCH-0281`] **BTN.JO** (2025-11-19 11:47)
- **Detected Label**: `capital expenditure` (normalized: `capital expenditure`)
- **Section Heading**: *Overall DIPS performance was partially offset by:*
- **Prior Sentence**: *"–   Marginally dilutive South African asset sales in FY25; and"*
- **Target Sentence**: **"–   The impact of funding capital expenditure, deployment into Australian investments, deferred consideration and transactional cash"**
- **Next Sentence**: *"flow timing"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `G. Capex ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'capital expenditure' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 166 — [`BENCH-0283`] **BTN.JO** (2025-11-19 11:47)
- **Detected Label**: `amortisation` (normalized: `amortisation`)
- **Section Heading**: *have yet to be completed.*
- **Prior Sentence**: *"have yet to be completed."*
- **Target Sentence**: **"–   Net asset value (‘NAV’) has decreased by 2.1% to R11.53ps (FY25: R11.78ps) largely as a result of mark-to market, amortisation and foreign exchange."**
- **Next Sentence**: *"Property-related valuations for the period have remained relatively flat, with nominal fair value gain recognised in respect of the various portfolios."*
- **Detected Numbers**: `['2.1%', 'R11.53', 'R11.78']`
- **Difficulty Category**: `B. Change statements`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `CHANGE_RATE_TO_LEVEL`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Change reporting sentence with rate-to-level compound structure*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 167 — [`BENCH-0284`] **BTN.JO** (2025-11-19 11:47)
- **Detected Label**: `Net asset value per share` (normalized: `net asset value per share`)
- **Prior Sentence**: *"Distributable earnings per share (cents)                                                      51.07           49.53         3.0%"*
- **Target Sentence**: **"Net asset value per share (ZAR)                                                               11.53           13.95      (17.0%)"**
- **Next Sentence**: *"Basic earnings/(loss) per share (cents)                                                       22.24        (101.71)       123.95"*
- **Detected Numbers**: `['11.53', '13.95', '17.0%']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `nav_per_share`
- Seed Qualifiers: `{}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'nav_per_share' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 168 — [`BENCH-0285`] **BTN.JO** (2025-11-19 11:47)
- **Detected Label**: `Diluted earnings per share` (normalized: `diluted earnings per share`)
- **Prior Sentence**: *"Basic earnings/(loss) per share (cents)                                                       22.24        (101.71)       123.95"*
- **Target Sentence**: **"Diluted earnings per share (cents)                                                            22.27        (100.72)       122.99"**
- **Next Sentence**: *"Headline earnings per share (cents)                                                           17.84         (89.65)       107.49"*
- **Detected Numbers**: `['22.27', '100.72', '122.99']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `diluted_eps`
- Seed Qualifiers: `{'dilution': <DilutionBasis.DILUTED: 'diluted'>}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `REQUIRES_PERIOD`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Ambiguous share wording 'diluted earnings per share' lacks point-in-time vs period-end vs WANOS specification; requires period*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 169 — [`BENCH-0286`] **BTN.JO** (2025-11-19 11:47)
- **Detected Label**: `net debt` (normalized: `net debt`)
- **Prior Sentence**: *"Pro-forma LTV (gearing)*                                                                                 39.0%              36.3%"*
- **Target Sentence**: **"Total Group net debt (ZAR and Euro)                                                                     R6.8bn             R6.2bn"**
- **Next Sentence**: *"Debt maturity (years) (pre-refinancing)                                                                    2.6                3.0"*
- **Detected Numbers**: `['R6.8bn', 'R6.2bn']`
- **Difficulty Category**: `E. Debt/lease ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `None`
- Seed Qualifiers: `{}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `REQUIRES_SOURCE_SECTION`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Ambiguous wording 'net debt' lacks balance sheet vs note presentation; requires source section*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 170 — [`BENCH-0287`] **MRP.JO** (2025-11-20 07:05)
- **Detected Label**: `total revenue` (normalized: `total revenue`)
- **Section Heading**: *MR PRICE GROUP INTERIM RESULTS FOR THE 26 WEEKS ENDED 27 SEPTEMBER 2025*
- **Prior Sentence**: *"MR PRICE GROUP INTERIM RESULTS FOR THE 26 WEEKS ENDED 27 SEPTEMBER 2025"*
- **Target Sentence**: **"For the 26 weeks ended 27 September 2025 (‘Period’), Mr Price Group increased total revenue by 5.4% to R18.6bn. The"**
- **Next Sentence**: *"group’s retail sales growth of 5.5%, was higher than the comparable market’s sales growth of 5.3% (RLC: April 2025 –"*
- **Detected Numbers**: `['26', '27', '2025', '5.4%', 'R18.6bn']`
- **Difficulty Category**: `B. Change statements`

**Deterministic Seed Baseline:**
- Seed Concept: `accounting_revenue`
- Seed Qualifiers: `{'scope': <OperationScope.GROUP_CONSOLIDATED: 'group_consolidated'>, 'sign': <NumericSign.POSITIVE: 'positive'>}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `CHANGE_RATE_TO_LEVEL`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Change reporting sentence with rate-to-level compound structure*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 171 — [`BENCH-0288`] **MRP.JO** (2025-11-20 07:05)
- **Detected Label**: `retail sales` (normalized: `retail sales`)
- **Section Heading**: *MR PRICE GROUP INTERIM RESULTS FOR THE 26 WEEKS ENDED 27 SEPTEMBER 2025*
- **Prior Sentence**: *"For the 26 weeks ended 27 September 2025 (‘Period’), Mr Price Group increased total revenue by 5.4% to R18.6bn. The"*
- **Target Sentence**: **"group’s retail sales growth of 5.5%, was higher than the comparable market’s sales growth of 5.3% (RLC: April 2025 –"**
- **Next Sentence**: *"September 2025). Despite a highly promotional retail sector for most of the period, the group expanded its gross profit (GP)"*
- **Detected Numbers**: `['5.5%', '5.3%', '2025']`
- **Difficulty Category**: `B. Change statements`

**Deterministic Seed Baseline:**
- Seed Concept: `retail_sales`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `CHANGE_RATE_ONLY`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Change / directional reporting sentence with percentage-only rate; ineligible as absolute historical baseline*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 172 — [`BENCH-0289`] **MRP.JO** (2025-11-20 07:05)
- **Detected Label**: `gross profit` (normalized: `gross profit`)
- **Section Heading**: *MR PRICE GROUP INTERIM RESULTS FOR THE 26 WEEKS ENDED 27 SEPTEMBER 2025*
- **Prior Sentence**: *"group’s retail sales growth of 5.5%, was higher than the comparable market’s sales growth of 5.3% (RLC: April 2025 –"*
- **Target Sentence**: **"September 2025). Despite a highly promotional retail sector for most of the period, the group expanded its gross profit (GP)"**
- **Next Sentence**: *"margin by 30bps to 40.0% and delivered positive operating leverage through strict cost control, expanding its operating"*
- **Detected Numbers**: `['2025']`
- **Difficulty Category**: `A. Easy/direct`

**Deterministic Seed Baseline:**
- Seed Concept: `gross_profit`
- Seed Qualifiers: `{'sign': <NumericSign.POSITIVE: 'positive'>}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'gross profit' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 173 — [`BENCH-0290`] **MRP.JO** (2025-11-20 07:05)
- **Detected Label**: `Diluted headline earnings per share` (normalized: `diluted headline earnings per share`)
- **Section Heading**: *margin by 10bps to 11.5%.*
- **Prior Sentence**: *"margin by 10bps to 11.5%."*
- **Target Sentence**: **"Basic and headline earnings per share of 512.8 cents and 513.0 cents were up 6.5%. Diluted headline earnings per share"**
- **Next Sentence**: *"grew 6.4% to 497.9 cents."*
- **Detected Numbers**: `['512.8 cents', '513.0 cents', '6.5%']`
- **Difficulty Category**: `F. Shares ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `diluted_heps`
- Seed Qualifiers: `{'dilution': <DilutionBasis.DILUTED: 'diluted'>, 'attribution': <ProfitAttribution.HEADLINE_ATTRIBUTABLE: 'headline_attributable'>, 'metric_basis': <MetricBasis.HEADLINE: 'headline'>}`
- Seed Alias Role: `DIRECT_VALUE_LABEL`
- Seed Value Pattern: `DIRECT_LEVEL`
- Seed Valuation Eligibility: `ELIGIBLE_WITH_QUALIFIER`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Approved canonical concept 'diluted_heps' with verified explicit qualifiers*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 174 — [`BENCH-0291`] **MRP.JO** (2025-11-20 07:05)
- **Detected Label**: `gross margin` (normalized: `gross margin`)
- **Prior Sentence**: *"Group CEO Mark Blair said, ‘I am pleased that we have once again executed our strategic intent of maximising sales growth"*
- **Target Sentence**: **"at improved margins. Our gross margin increased despite a very challenging retail environment. Our value focused business"**
- **Next Sentence**: *"model enabled us to effectively manage overheads and ensure that we consistently deliver positive earnings growth and"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `D. Basis ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `gross_margin`
- Seed Qualifiers: `{'margin_denominator': <MarginDenominator.ACCOUNTING_REVENUE: 'accounting_revenue'>}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'gross margin' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 175 — [`BENCH-0292`] **MRP.JO** (2025-11-20 07:05)
- **Detected Label**: `retail sales of R17` (normalized: `retail sales of r17`)
- **Section Heading**: *Group results summary*
- **Prior Sentence**: *"Group results summary"*
- **Target Sentence**: **"Group retail sales of R17.8bn increased 5.5% and comparable store sales increased 2.1%. Other revenue of R625m"**
- **Next Sentence**: *"decreased 1.6%."*
- **Detected Numbers**: `['R17.8bn', '5.5%', '2.1%', 'R625m']`
- **Difficulty Category**: `B. Change statements`

**Deterministic Seed Baseline:**
- Seed Concept: `retail_sales`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `CHANGE_RATE_TO_LEVEL`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Change reporting sentence with rate-to-level compound structure*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 176 — [`BENCH-0296`] **MRP.JO** (2025-11-20 07:05)
- **Detected Label**: `Operating margin` (normalized: `operating margin`)
- **Prior Sentence**: *"Profit from operating activities increased 5.7% to R2.1bn. Effective cost control initiatives ensured total expense growth was"*
- **Target Sentence**: **"contained at 5.6%, despite trading space growth. Operating margin increased 10bps to 11.5% of retail sales and other"**
- **Next Sentence**: *"revenue. The group’s operating margin in H1 is typically seasonally lower than H2."*
- **Detected Numbers**: `['5.6%', '10', '11.5%']`
- **Difficulty Category**: `D. Basis ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `operating_margin`
- Seed Qualifiers: `{'margin_denominator': <MarginDenominator.ACCOUNTING_REVENUE: 'accounting_revenue'>}`
- Seed Alias Role: `CHANGE_STATEMENT`
- Seed Value Pattern: `CHANGE_RATE_TO_LEVEL`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `False`
- Seed Heuristic Note: *Change reporting sentence with rate-to-level compound structure*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 177 — [`BENCH-0298`] **MRP.JO** (2025-11-20 07:05)
- **Detected Label**: `operating margin` (normalized: `operating margin`)
- **Prior Sentence**: *"contained at 5.6%, despite trading space growth. Operating margin increased 10bps to 11.5% of retail sales and other"*
- **Target Sentence**: **"revenue. The group’s operating margin in H1 is typically seasonally lower than H2."**
- **Next Sentence**: *"Segmental performance"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `D. Basis ambiguity`

**Deterministic Seed Baseline:**
- Seed Concept: `operating_margin`
- Seed Qualifiers: `{'margin_denominator': <MarginDenominator.ACCOUNTING_REVENUE: 'accounting_revenue'>}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'operating margin' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---

### Item 178 — [`BENCH-0299`] **MRP.JO** (2025-11-20 07:05)
- **Detected Label**: `Retail sales` (normalized: `retail sales`)
- **Section Heading**: *Segmental performance*
- **Prior Sentence**: *"Segmental performance"*
- **Target Sentence**: **"Retail sales growth      Cont. to retail sales"**
- **Next Sentence**: *"H1 FY2026 vs H1 FY2025"*
- **Detected Numbers**: `[]`
- **Difficulty Category**: `B. Change statements`

**Deterministic Seed Baseline:**
- Seed Concept: `retail_sales`
- Seed Qualifiers: `{}`
- Seed Alias Role: `CONCEPT_MENTION_ONLY`
- Seed Value Pattern: `UNKNOWN`
- Seed Valuation Eligibility: `INFORMATIONAL_ONLY`
- Seed Should Abstain: `True`
- Seed Heuristic Note: *Narrative mention of 'retail sales' without usable numeric level (only dates/years or non-metric tokens detected)*

**Human Reviewer Confirmation:**
- [ ] Gold Concept: `[                                        ]`
- [ ] Gold Qualifiers: `[                                     ]`
- [ ] Gold Alias Role: `[                                     ]`
- [ ] Gold Value Pattern: `[                                  ]`
- [ ] Gold Valuation Eligibility: `[                          ]`
- [ ] Gold Should Abstain: `[ ] Yes  [ ] No`
- [ ] Reviewer Notes: `[                                      ]`

---
