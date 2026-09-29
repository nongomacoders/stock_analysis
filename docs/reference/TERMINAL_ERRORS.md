# Terminal Errors and Troubleshooting Guide

This guide documents recurring terminal, PowerShell, environment, and command invocation issues in this repository, along with their known, confirmed fixes.

Consult this document before inventing shell workarounds.

---

## 1. Python executable not found or wrong Python selected

### Symptom
Running `python`, `py`, or `python -m pytest` resolves to the wrong interpreter (e.g. Python 3.13, a temporary virtualenv), fails with `command not found`, or triggers unnecessary interpreter discovery loops.

### Cause
Windows system `PATH` may prioritize other Python installations or Windows Store shims over the project's designated Python 3.11 installation.

### Confirmed fix
Explicitly invoke the confirmed Python 3.11 binary using the PowerShell `&` call operator:

```powershell
& "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" ...
```

Do not assume `python`, `py`, Python 3.13, or an unverified virtual environment.

### Example command
```powershell
& "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" --version
```

### Notes
Because this executable is located in `AppData\Local` (outside the workspace root), running terminal commands targeting this path requires `BypassSandbox: true` in agent execution tooling.

---

## 2. Python imports fail from repository root (Missing PYTHONPATH)

### Symptom
`ModuleNotFoundError: No module named 'core'` or `No module named 'modules'` when executing Python scripts or tools from the repository root (`C:\Users\Dion\Desktop\Projects\stock_analysis`).

### Cause
The application and analysis packages reside under the `gui` subdirectory (`C:\Users\Dion\Desktop\Projects\stock_analysis\gui`), which is not in `sys.path` by default when running from the root workspace directory.

### Confirmed fix
Set the `$env:PYTHONPATH` environment variable in PowerShell to point to the `gui` directory before calling Python.

### Example command
```powershell
$env:PYTHONPATH = "C:\Users\Dion\Desktop\Projects\stock_analysis\gui"
& "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" -c "import core; print(core)"
```

---

## 3. Running pytest across test suites

### Symptom
Test runner fails to discover tests, raises import errors for `core` or `modules`, or runs under the wrong Python environment.

### Cause
Invoking `pytest` directly without setting `PYTHONPATH` or using a global pytest runner attached to another Python installation.

### Confirmed fix
Set `$env:PYTHONPATH` and run pytest as a module through the designated Python 3.11 binary:

### Example command
```powershell
$env:PYTHONPATH = "C:\Users\Dion\Desktop\Projects\stock_analysis\gui"; & "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" -m pytest gui/modules/analysis/tests/test_afs_pipeline.py -v
```

---

## 4. PowerShell syntax vs Bash syntax (Chaining and Environment Variables)

### Symptom
Commands using Bash syntax such as `export VAR=val`, `VAR=val command`, or `&&` fail with errors:
`export: The term 'export' is not recognized as a name of a cmdlet, function, script file, or executable program.`

### Cause
The default shell in this environment is PowerShell on Windows, not Bash or zsh. Bash built-ins and POSIX shell idioms are invalid.

### Confirmed fix
- Set environment variables using `$env:VAR = "value"`.
- Chain sequential commands using semicolons `;`.
- Do not use `export` or POSIX prefix variable assignments.

### Example command
```powershell
$env:PYTHONPATH = "C:\Users\Dion\Desktop\Projects\stock_analysis\gui"; & "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" scratch/test_script.py
```

---

## 5. Nested quote escapes in inline Python (`python.exe -c`) commands

### Symptom
```text
SyntaxError: unterminated string literal (detected at line ...)
```
or unexpected EOF errors when executing inline Python one-liners via PowerShell.

### Cause
PowerShell processes and strips backslash-escaped inner double quotes (`\"`) inside `-c "..."` arguments before passing the string to Python.

### Confirmed fix
1. Use single quotes `'...'` to enclose the Python code block and standard double quotes `"` inside for strings.
2. Use Python triple quotes `'''` for multiline text.
3. For scripts longer than 2 lines, write a temporary `.py` script to the `scratch/` directory and execute the file instead of fighting shell escape rules.

### Example command
```powershell
& "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" -c '
import json
print(json.dumps({"status": "ok"}))
'
```

---

## 6. PowerShell variable expansion (`$_` or `$var`) in double-quoted strings

### Symptom
Variables intended for Python or internal commands evaluate to empty strings, or PowerShell raises syntax errors before Python starts.

### Cause
PowerShell expands any expression starting with `$` inside double-quoted strings (`"..."`) before passing arguments to the process.

### Confirmed fix
- Escape the dollar sign with a backtick (`` `$_ `` or `` `$var ``).
- Alternatively, enclose the outer argument in single quotes `'...'`.

### Example command
```powershell
& "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" -c '
import sys
print([p for p in sys.path if "gui" in p])
'
```

---

## 7. Pipeline parser errors with pipe characters (`|`) in inline scripts

### Symptom
`An empty pipe element is not allowed` or `The term '...' is not recognized` when running commands containing the pipe character `|`.

### Cause
PowerShell interprets bare or improperly quoted `|` characters as shell pipeline redirection operators rather than string literals for Python (e.g. in regular expressions or Python 3.10+ union types).

### Confirmed fix
Wrap the entire command in single quotes `'...'`, escape pipes using `` `| ``, or execute from a script file.

### Example command
```powershell
& "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" -c 'import re; print(re.search("foo|bar", "foo").group())'
```

---

## 8. Windows PowerShell `Select-String` syntax limitations

### Symptom
`Select-String : A parameter cannot be found that matches parameter name 'First'`, or boolean switch errors when searching text.

### Cause
Windows PowerShell 5.1's `Select-String` cmdlet does not support the `-First` parameter (unlike Unix `head`), and `-CaseSensitive` is a switch parameter that fails if passed arguments like `-CaseSensitive:$true`.

### Confirmed fix
- Pipe output to `Select-Object -First <N>` for line limits.
- Use `-CaseSensitive` as a standalone switch without a value.

### Example command
```powershell
Get-Content file.txt | Select-String "pattern" -CaseSensitive | Select-Object -First 10
```

---

## 9. PowerShell `foreach` statement cannot pipe directly

### Symptom
`Expressions are only allowed as the first element of a pipeline` when attempting to pipe directly from a `foreach ($x in $y) { ... }` block.

### Cause
In PowerShell, `foreach (...) { ... }` is a language statement, not an expression or cmdlet, and cannot be followed directly by a pipe operator `|`.

### Confirmed fix
Wrap the `foreach` statement in `$()` subexpression syntax, or use the `ForEach-Object` cmdlet in the pipeline:

### Example command
```powershell
$(foreach ($f in Get-ChildItem -Filter *.pdf) { $f.FullName }) | Select-Object -First 5
# OR:
Get-ChildItem -Filter *.pdf | ForEach-Object { $_.FullName } | Select-Object -First 5
```

---

## 10. PowerShell `Set-Content -Encoding UTF8` adds unwanted UTF-8 BOM

### Symptom
Text or JSON files written via PowerShell contain leading Byte Order Mark bytes (`\xef\xbb\xbf`), causing JSON parsing errors or hash mismatches in SHA-256 validation.

### Cause
Windows PowerShell 5.1's `Set-Content -Encoding UTF8` and `Out-File -Encoding UTF8` always prepend a 3-byte UTF-8 BOM.

### Confirmed fix
Write UTF-8 files without BOM using the .NET API or through Python:

### Example command
```powershell
[System.IO.File]::WriteAllText($filePath, $content, [System.Text.UTF8Encoding]::new($false))
# OR via Python:
& "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" -c "open('manifest.json', 'w', encoding='utf-8').write('{}')"
```

---

## 11. PostgreSQL / Application environment loading

### Symptom
Database connection fails or configuration attributes are missing when connecting from scratch scripts or command-line utilities.

### Cause
Attempting to connect without importing application configuration or attempting to read database credentials from uninitialized environment variables.

### Confirmed fix
Always load database credentials via `core.config.DB_CONFIG` (ensuring `PYTHONPATH` includes `gui`). Never invent credentials or create alternate configuration files.

### Example command
```powershell
$env:PYTHONPATH = "C:\Users\Dion\Desktop\Projects\stock_analysis\gui"; & "C:\Users\Dion\AppData\Local\Programs\Python\Python311\python.exe" -c "
import psycopg2
from core.config import DB_CONFIG
conn = psycopg2.connect(**DB_CONFIG)
print('Connected successfully:', conn.status)
conn.close()
"
```