# Run the F-CONN connector test suite.
#
# Usage:
#   .\scripts\run-connector-tests.ps1
#   .\scripts\run-connector-tests.ps1 -Verbose
[CmdletBinding()]
param(
    [switch]$VerboseOutput
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$backend  = Join-Path $repoRoot "backend"

$python = if ($env:PYTHON) { $env:PYTHON } else { "python" }

$tests = @(
    "tests/test_f_conn_core_registry.py",
    "tests/test_f_conn_core_lifecycle.py",
    "tests/test_f_conn_core_base_connector.py",
    "tests/test_f_conn_rbac_isolation.py",
    "tests/test_f_conn_p0_csv.py",
    "tests/test_f_conn_p0_files.py",
    "tests/test_f_conn_p0_s3.py",
    "tests/test_f_conn_p0_postgres_preview.py",
    "tests/test_f_conn_p0_dataset_preview_api.py"
)

$pytestArgs = @("-m", "pytest") + $tests + @("-q", "--no-header")
if ($VerboseOutput) { $pytestArgs += "-v" }

Push-Location $backend
try {
    $env:PYTHONIOENCODING = "utf-8"
    Write-Host "→ $python $($pytestArgs -join ' ')" -ForegroundColor Cyan
    & $python @pytestArgs
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
