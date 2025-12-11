<#
Run GUI test runner conveniently from PowerShell, while keeping this script inside the `gui/` subproject.

Why this file lives in `gui/`:
- Your subproject is `gui/` and we should only change files under `gui/`.
- This wrapper ensures developers can easily run `gui/run_tests.py` from PowerShell without changing the CWD manually.

Usage examples (from repo root or anywhere):
  # Runs tests by discovering `gui/test/test_*.py`
  .\gui\run_gui_tests.ps1

  # Run a specific module
  .\gui\run_gui_tests.ps1 --test "gui.test.test_analysis_service"

  # Run tests with a discovery pattern
  .\gui\run_gui_tests.ps1 --pattern "test_*.py"

This wrapper:
- Locates a Python executable in PATH (python, py, python3)
- Ensures the test runner script `gui/run_tests.py` is invoked from the repo root
- Forwards CLI args to the Python test runner

#>
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [String[]]
    $Args
)

$ErrorActionPreference = 'Stop'

function Get-PythonExecutable {
    $candidates = @('python', 'py', 'python3')
    foreach ($c in $candidates) {
        $cmd = Get-Command $c -ErrorAction SilentlyContinue
        if ($null -ne $cmd) {
            return $cmd.Source
        }
    }
    return $null
}

$python = Get-PythonExecutable
if (-not $python) {
    Write-Error "Python executable not found in PATH. Install Python and ensure 'python' or 'py' is available.";
    exit 2
}

# Script root is the `gui/` folder (this script lives inside `gui/`)
$scriptDir = $PSScriptRoot
# Repo root is the parent of `gui`
$repoRoot = Resolve-Path (Join-Path $scriptDir '..')
Push-Location -ErrorAction Stop $repoRoot
try {
    $script = Join-Path $scriptDir 'run_tests.py'
    if (-not (Test-Path $script)) {
        Write-Error "Could not find gui/run_tests.py at: $script";
        exit 3
    }

    $fullArgs = $Args -join ' '
    Write-Host "Running: $($python) $script $fullArgs" -ForegroundColor Cyan

    $processInfo = @{FilePath = $python; ArgumentList = $script + ' ' + $fullArgs; Wait = $true; NoNewWindow = $true}
    $p = Start-Process @processInfo
    $code = $p.ExitCode
    exit $code
}
finally {
    Pop-Location
}
