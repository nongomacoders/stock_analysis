# Stock Analysis Agent Runbook

This file records recurring development issues and their known fixes.

Future agents should consult this file before repeating environment discovery or troubleshooting already solved problems.

---

# 1. Python executable not found / wrong Python selected

## Symptom

Commands such as:

```powershell
python --version
python -m pytest
```

resolve to the wrong interpreter, fail, or trigger unnecessary Python discovery.

## Known working interpreter

```text
C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe
```

## Preferred command

```powershell
& "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" ...
```

Do not search for:
- Python 3.13
- a venv
- another Python installation

unless the known interpreter actually fails.

Note: Since this executable is located in `AppData\Local` (outside the workspace root), running terminal commands using this path requires `BypassSandbox: true` in agent tooling.


---

# 2. Python imports fail from repository root

## Symptom

Errors such as:

```text
ModuleNotFoundError
cannot import core
cannot import modules
```

## Known fix

Set:

```powershell
$env:PYTHONPATH = "C:\Users\Dion\Desktop\Projects\stock_analysis\gui"
```

Then run:

```powershell
& "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" ...
```

---

# 3. Running pytest

Preferred pattern:

```powershell
$env:PYTHONPATH = "C:\Users\Dion\Desktop\Projects\stock_analysis\gui"

& "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" -m pytest <test paths> -v
```

Do not switch interpreters between test runs unless necessary.

---

# 4. Database access

Application DB configuration is located at:

```text
gui\core\config.py
```

Use:

```python
from core.config import DB_CONFIG
```

Typical PostgreSQL connection:

```python
import psycopg2
from core.config import DB_CONFIG

conn = psycopg2.connect(**DB_CONFIG)
```

Do not invent credentials or create duplicate config files.

---

# 5. Historical package location

Historical evidence is stored at:

```text
gui\results_history\<TICKER>\<PERIOD>\
```

Typical files:

```text
manifest.json
<TICKER>_<PERIOD>_AFS.pdf
<TICKER>_<PERIOD>_SENS.txt
```

Always validate:
- ticker
- reporting period
- period end
- source type
- publication date
- active revision

before using evidence.

---

# 6. PDF metric appears unavailable

## Symptom

The generic AFS parser reports:

```text
NOT_AVAILABLE
```

but the source AFS may contain the figure.

## Procedure

Before declaring the metric unavailable:

1. open the archived AFS PDF
2. extract text with PyPDF2
3. search the primary statements
4. search the likely note
5. inspect surrounding context
6. preserve exact page/note provenance
7. reconcile duplicate or differently defined values

Use scratch scripts when necessary, but do not hard-code company values into production code.

---

# 7. Retailer semantic traps

Always distinguish:

## Revenue concepts

```text
accounting revenue
sale of merchandise
retail sales
```

They may all differ.

## Profit concepts

```text
trading profit
operating profit
PBIT
EBIT
```

Do not substitute automatically.

## Margin concepts

Always store:
- numerator
- denominator
- semantic label

Example:

```text
trading margin = trading profit / sale of merchandise
```

Do not apply a published operating margin to accounting revenue unless that is explicitly the published definition.

---

# 8. D&A semantics

Income-statement D&A may not equal the full cash-flow D&A addback.

TRU FY2025 example:

```text
income-statement D&A expense = R1.500bn
cash-flow D&A addback = R1.526bn
```

Reason:
distribution depreciation was included in cost of sales rather than trading expenses.

Preserve separate typed concepts:

```text
depreciation_amortisation_expense
depreciation_amortisation_cashflow_addback
```

FCFF mapping must choose explicitly.

---

# 9. Capex semantics

Do not confuse:

```text
cash capex
accounting additions
```

TRU historical valuation uses a cash-capex convention.

Example FY2025:

```text
expansion cash capex    R428m
maintenance cash capex  R187m
software cash capex      R59m
total cash capex         R674m
```

For forecast-vs-actual comparisons, use the same semantic basis on both sides.

---

# 10. Working-capital signs

Never store an ambiguous working-capital number without sign semantics.

Preferred concept:

```text
working_capital_cash_flow
```

Convention:

```text
positive = cash inflow
negative = cash outflow
```

If the FCFF engine uses:

```text
FCFF = ... - change_in_working_capital
```

convert deliberately before calculation.

Do not double-negate.

---

# 11. Net cash reconciliation

Reported net cash may not equal:

```text
cash - debt
```

Check:
- cash
- restricted/charitable cash
- money-market funds
- borrowings
- overdraft
- other treasury adjustments

TRU FY2025 example:

```text
Cash                     +R964m
Charitable trust cash     -R14m
Money-market funds      +R2.224bn
Borrowings              -R1.479bn
Overdraft                 -R975m
                         -------
Reported net cash         +R720m
```

Lease liabilities remain a separate equity-bridge adjustment.

---

# 12. Share-count semantics

Keep separate:

```text
issued shares
treasury shares
external shares ex treasury
weighted average basic shares
weighted average diluted shares
```

Also distinguish:
- reporting-period end count
- announcement-date count
- valuation-date count

Use the most appropriate point-in-time count available as of the valuation date.

Do not use weighted-average EPS shares automatically for DCF valuation.

---

# 13. Historical valuation immutability

Once a historical valuation is locked:

Do not modify:
- approved historical plan
- historical result
- valuation output
- input hash

Corrections after reveal belong in append-only outcome revisions.

---

# 14. Outcome corrections

If a reveal analysis is incomplete or wrong:

Do not overwrite prior outcome rows.

Create:

```text
Revision N+1
```

with:

```text
supersedes_outcome_id
```

The newest valid completed revision becomes authoritative.

The original locked valuation remains unchanged.

---

# 15. TRU reference retailer backtest

Canonical reference:

```text
Ticker:
TRU.JO

Historical period:
FY2025

Historical as-of date:
2025-08-31

Outcome period:
FY2026

Historical Result ID:
6768e249-36c9-4f4d-afff-e3bd832e5f6a

Locked fair value:
R72.8232/share

Locked EV:
R30,356,971,061.15

Locked Equity Value:
R27,334,971,061.15

Locked Input Hash:
ccf6a05b91b47ec458186ad1e73f9a78496d64f34c96f2e99dfbba7c8872f959

Authoritative reveal:
Revision 3
```

This reference exists for regression verification.

Do not create TRU-specific branches in production valuation code.

---

# 16. Historical backtest lifecycle

Keep these concepts separate.

## Backtest lifecycle

```text
draft -> locked -> completed
```

## Historical plan

Typical final state:

```text
approved
```

## Historical result

Insert-only and immutable after creation.

## Outcomes

Append-only revision chain.

Do not describe a backtest as:

```text
completed / locked
```

when these refer to different lifecycle concepts.

---

# 17. Before adding new infrastructure

Before creating:
- a parser
- migration
- valuation helper
- lifecycle helper
- historical package handler
- test utility

search the repository first.

Prefer:
- extending existing generic code
- typed semantics
- configuration/adapters

over:
- duplicate workflows
- one-off scripts promoted into production
- ticker-specific branches

---

# 18. Gemini vs Python responsibilities

Gemini may assist with:
- interpretation
- semantic suggestions
- assumption proposals
- research

Python should own:
- extraction where deterministic
- normalization
- arithmetic
- valuation
- validation
- persistence
- reproducibility
- regression tests

Never let an AI-generated target overwrite a deterministic valuation result.

---

# 19. When a known fix fails or new error occurs

Only rediscover environment details after confirming the documented fix genuinely no longer works.

### Midstream recording rule (mandatory)
Whenever any command, script, parser, or shell operation fails due to quoting, variable expansion, platform difference, or unexpected syntax:
1. Identify the root cause and verified working alternative.
2. **Log the error and fix in this runbook immediately midstream as a new section.**
3. Never defer documentation until after task completion or wait for the user to ask for it.
4. If a documented fix changes, update the existing section so future conversations inherit the correction.

---

# 20. PowerShell quoting and "SyntaxError: unterminated string literal"

## Symptom

Executing inline Python commands via PowerShell like:

```powershell
& "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" -c "..."
```

fails with:

```text
SyntaxError: unterminated string literal (detected at line 1)
```

or PowerShell parser errors such as:

```text
The string is missing the terminator: '
```

## Root cause

PowerShell parses arguments before passing them to the executable. When double quotes (`"`) are used both around the `-c` argument and inside Python code, PowerShell strips or mishandles the inner quotes. Windows paths with unescaped backslashes (`\`) or multi-line strings further corrupt quoting.

## Failing patterns (avoid)

```powershell
# FAILS: Python f-strings with inner quotes inside PowerShell double quotes
& "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" -c "print(f\"{c['key']}\")"
```

## Correct inline patterns

1. **Outer single quotes, inner double quotes**:
   ```powershell
   & "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" -c 'import os; print("hello")'
   ```

2. **Escaped internal double quotes (`\"` or ``` `"` )**:
   ```powershell
   & "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" -c "import os; print(\"hello\")"
   ```

3. **Raw string or forward slashes for Windows paths**:
   ```powershell
   & "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" -c 'from pathlib import Path; print(Path(r"C:\Users\Dion"))'
   ```

## Preferred robust alternative: Scratch scripts

For any script longer than a single simple expression, **do not pass multi-line or complex strings via `-c`**.

Instead, write a temporary scratch script and execute it directly:

```powershell
# Save to a temporary file (e.g. scratch/temp_task.py), then run:
$env:PYTHONPATH = "C:\Users\Dion\Desktop\Projects\stock_analysis\gui"
& "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" path\to\scratch\temp_task.py
```

This bypasses shell quoting and tokenizer mismatches entirely.

---

# 21. PowerShell `$_` Variable Expansion in `-Command "..."`

## Symptom

Running nested PowerShell commands like:

```powershell
powershell -Command "Get-ChildItem -File -Recurse | Where-Object { $_.Name -like '*test*' }"
```

fails with repeated errors:

```text
.Name : The term '.Name' is not recognized as the name of a cmdlet, function, script file, or operable program.
At line:1 char:67
+ ... ChildItem -File -Recurse | Where-Object { .Name -like '*test*' }
+                                               ~~~~~
    + CategoryInfo          : ObjectNotFound: (.Name:String) [], CommandNotFoundException
    + FullyQualifiedErrorId : CommandNotFoundException
```

## Root cause

When executing a PowerShell command string wrapped in double quotes (`"..."`), the calling shell expands variables *before* executing the string. Because `$_` is not defined in the parent scope, it expands to an empty string. The pipeline block `{ $_.Name ... }` becomes `{ .Name ... }`, which PowerShell attempts to execute as a cmdlet named `.Name`.

## Failing pattern (avoid)

```powershell
# FAILS: Outer double quotes evaluate $_ to empty string
powershell -Command "Get-ChildItem | Where-Object { $_.Name -like '*doc*' }"
```

## Correct patterns

1. **Escape the `$` with a backtick (`` `$ ``)**:
   ```powershell
   powershell -Command "Get-ChildItem | Where-Object { `$_.Name -like '*doc*' }"
   ```

2. **Wrap `-Command` in single quotes**:
   ```powershell
   powershell -Command 'Get-ChildItem | Where-Object { $_.Name -like "*doc*" }'
   ```

3. **Run directly without nested `powershell -Command` wrapper**:
   When already in PowerShell, avoid wrapping commands in `powershell -Command "..."`:
   ```powershell
   Get-ChildItem -File -Recurse | Where-Object { $_.Name -like '*doc*' }
   ```

---

# 22. Nested Quoting / Triple-Quotes in `powershell -Command "..."` with `python -c`

## Symptom

Executing an inline Python command wrapped in PowerShell, such as:

```powershell
powershell -Command "$env:PYTHONPATH='...'; & '...' -c 'cur.execute(\"\"\"SELECT ...\"\"\")'"
```

fails with:

```text
The string is missing the terminator: '.
ParentContainsErrorRecordException
CommandNotFoundException
```

## Root cause

PowerShell parses `\"\"\"` inside `-Command "..."` by stripping the backslashes before Python is invoked, which truncates the string and leaves unclosed quotes, or misinterprets inner single quotes.

## Failing pattern (avoid)

```powershell
powershell -Command "$env:PYTHONPATH='C:\...'; & 'C:\...\python.exe' -c '... cur.execute(\"\"\"SELECT ...\"\"\") ...'"
```

## Working fix

1. **Avoid nested `powershell -Command`**: The terminal shell is already PowerShell. Run directly:
   ```powershell
   $env:PYTHONPATH = "C:\Users\Dion\Desktop\Projects\stock_analysis\gui"
   & "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" -c "..."
   ```

2. **Or use a dedicated scratch script**:
   Write the script to a `.py` file (e.g. in the artifact scratch directory or workspace scratch directory) and execute it with:
   ```powershell
   & "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" scratch_script.py
   ```

---

# 23. PowerShell Variable Expansion Inside Double-Quoted `-Command "..."`

## Symptom

Executing:

```powershell
powershell -Command "$env:PYTHONPATH='C:\Users\Dion\Desktop\Projects\stock_analysis\gui'; & 'C:\...\python.exe' -m pytest ..."
```

fails with:

```text
=C:\Users\Dion\Desktop\Projects\stock_analysis\gui : The term '=C:\Users\Dion\Desktop\Projects\stock_analysis\gui' is 
not recognized as the name of a cmdlet, function, script file, or operable program.
ModuleNotFoundError: No module named 'modules'
```

## Root cause

When PowerShell runs `-Command "$env:PYTHONPATH=..."`, the outer PowerShell evaluates `$env:PYTHONPATH` *before* launching the subshell. Because `$env:PYTHONPATH` was empty in the parent environment, it expands to `""`, leaving `'=C:\...'` as the command string, which is an invalid cmdlet.

## Failing pattern (avoid)

```powershell
powershell -Command "$env:PYTHONPATH='...'; & '...' -m pytest ..."
```

## Working fix

Since the shell tool already runs in PowerShell, execute assignments and invocations directly without a nested `powershell` process:

```powershell
$env:PYTHONPATH = "C:\Users\Dion\Desktop\Projects\stock_analysis\gui"; & "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" -m pytest ...
```

---

# 24. PowerShell Pipeline Parser Error with Inline `python -c` Containing Pipe `|` Characters

## Symptom

Executing inline python statements in PowerShell such as:

```powershell
& "C:\...\python.exe" -c "print(f\"| {r['benchmark_id']} | {r['ticker']} |\")"
```

fails with:

```text
An empty pipe element is not allowed.
Unexpected token '}' in expression or statement.
    + CategoryInfo          : ParserError: (:) [], ParentContainsErrorRecordException
    + FullyQualifiedErrorId : UnexpectedToken
```

## Root cause

PowerShell parses unquoted or weakly quoted pipe characters `|` as shell pipeline operators instead of passing them as string literals to Python's `-c` argument.

## Failing pattern (avoid)

```powershell
& "C:\...\python.exe" -c "print(f\"| {var} |\")"
```

## Working fix

Do not pass markdown table formatting or complex multi-line strings via inline `-c`. Always write the code to a `.py` script file in `scratch/` and execute via:

```powershell
$env:PYTHONPATH = "C:\Users\Dion\Desktop\Projects\stock_analysis\gui"; & "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" scratch/script.py
```


