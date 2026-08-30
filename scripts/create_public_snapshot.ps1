# Create a clean public snapshot of the working tree.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts/create_public_snapshot.ps1 -OutDir ..\cognidq-public
#
# Result:
#   <OutDir>/   a fresh Git repo with one commit:
#               "Initial commit — CogniDQ v0.1.0-alpha"
#               and one tag: v0.1.0-alpha
#
# What it copies:
#   Every tracked file at HEAD of the current repo (`git ls-files -z`).
#
# What it does NOT copy:
#   .git/, untracked files, ignored files, files matched by .gitignore
#   in the source tree (because we filter through `git ls-files`).

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [string]$OutDir,

    [string]$ReleaseTag = "v0.1.0-alpha",

    [string]$CommitMessage = "Initial commit - CogniDQ v0.1.0-alpha"
)

$ErrorActionPreference = 'Stop'

function Fail($msg) {
    Write-Host "ERROR: $msg" -ForegroundColor Red
    exit 1
}

# Pre-flight: must be run from a clean Git working tree
if ((git rev-parse --is-inside-work-tree 2>$null) -ne 'true') {
    Fail "Not inside a Git working tree. Run this from the source repo root."
}
$dirty = & git status --porcelain
if ($dirty) {
    Fail "Working tree is not clean. Commit or stash changes first.`n$dirty"
}

# Resolve paths
$srcRoot = (Resolve-Path .).Path
$dstRoot = $OutDir
if (-not [System.IO.Path]::IsPathRooted($dstRoot)) {
    $dstRoot = [System.IO.Path]::GetFullPath((Join-Path $srcRoot $dstRoot))
}

if (Test-Path $dstRoot) {
    Fail "Output directory already exists: $dstRoot. Pick a fresh path or remove it first."
}

Write-Host "Source: $srcRoot"
Write-Host "Target: $dstRoot"
Write-Host ""

# Step 1: enumerate tracked files at HEAD
Write-Host "[1/5] Enumerating tracked files..."
$files = & git ls-files
if (-not $files) {
    Fail "git ls-files returned no files."
}
Write-Host ("       {0} files" -f $files.Count)

# Step 2: extract tracked files at HEAD into the destination using `git archive`,
# which applies .gitattributes (correct line endings, exports, etc.).
Write-Host "[2/5] Extracting files via git archive (respects .gitattributes)..."
New-Item -ItemType Directory -Path $dstRoot | Out-Null
$tarPath = Join-Path ([System.IO.Path]::GetTempPath()) ("cognidq-snapshot-" + [guid]::NewGuid().ToString("N") + ".tar")
try {
    & git archive --worktree-attributes --format=tar -o $tarPath HEAD
    if ($LASTEXITCODE -ne 0) { Fail "git archive failed." }
    & tar -xf $tarPath -C $dstRoot
    if ($LASTEXITCODE -ne 0) { Fail "tar extraction failed (Windows 10+ ships tar; if missing, install BSD tar or use the bash version of this script)." }
}
finally {
    if (Test-Path $tarPath) { Remove-Item $tarPath -Force }
}
$copied = (Get-ChildItem -Path $dstRoot -Recurse -File | Measure-Object).Count
Write-Host ("       extracted {0} files" -f $copied)

# Step 3: init a fresh Git repo
Write-Host "[3/5] Initialising fresh Git repo..."
Push-Location $dstRoot
try {
    & git init --initial-branch=main | Out-Null
    & git config user.email "release-bot@cognidq.local"
    & git config user.name "CogniDQ Release"

    # Step 4: commit
    Write-Host "[4/5] Creating initial commit..."
    & git add -A
    & git -c commit.gpgsign=false commit -m $CommitMessage | Out-Null

    # Step 5: tag
    Write-Host "[5/5] Tagging $ReleaseTag..."
    & git tag -a $ReleaseTag -m "CogniDQ $ReleaseTag" | Out-Null

    Write-Host ""
    Write-Host "DONE." -ForegroundColor Green
    Write-Host ""
    Write-Host "Snapshot at: $dstRoot"
    Write-Host ""
    Write-Host "Next steps:"
    Write-Host "  cd $dstRoot"
    Write-Host "  git remote add origin git@github.com:<your-org>/cognidq.git"
    Write-Host "  git push -u origin main"
    Write-Host "  git push origin $ReleaseTag"
}
finally {
    Pop-Location
}
