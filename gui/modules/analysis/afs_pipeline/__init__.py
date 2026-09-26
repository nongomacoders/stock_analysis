"""Production AFS Evidence Pipeline.

Stage-by-stage auditable pipeline:
PDF
  ↓
source archive (Stage 1)
  ↓
text/layout extraction (Stage 2)
  ↓
candidate numeric occurrence detection (Stage 3)
  ↓
context/evidence package (Stage 4)
  ↓
Kev semantic classification (Stage 5)
  ↓
deterministic safety policy (Stage 6)
  ↓
Gemini adjudication when required (Stage 7)
  ↓
typed historical actual candidate (Stage 8)
  ↓
cross-document/accounting reconciliation (Stage 9)
  ↓
whole-document Gemini challenge pass (Stage 10)
  ↓
analyst review package (Stage 11)
"""
