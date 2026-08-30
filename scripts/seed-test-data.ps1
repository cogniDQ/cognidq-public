# Seed deterministic connector test data into Postgres + MinIO.
#
# Usage:
#   .\scripts\seed-test-data.ps1
#   .\scripts\seed-test-data.ps1 -OnlyGenerate
#   .\scripts\seed-test-data.ps1 -NoPostgres
#   .\scripts\seed-test-data.ps1 -NoMinio
[CmdletBinding()]
param(
    [switch]$OnlyGenerate,
    [switch]$NoPostgres,
    [switch]$NoMinio
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

$python = if ($env:PYTHON) { $env:PYTHON } else { "python" }

$args = @((Join-Path $repoRoot "scripts\seed_test_data.py"))
if ($OnlyGenerate) { $args += "--only-generate" }
if ($NoPostgres)   { $args += "--no-postgres" }
if ($NoMinio)      { $args += "--no-minio" }

Write-Host "→ $python $($args -join ' ')" -ForegroundColor Cyan
& $python @args
exit $LASTEXITCODE
