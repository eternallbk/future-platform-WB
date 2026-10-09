<#
================================================================================
  publish-workbuddy.ps1 - audit dist/ and hand it to the WorkBuddy publish step.
================================================================================
  WHAT CHANGED (2026-10-03)
    This script replaces the former publish-gh-pages.ps1. The workbench no longer
    commits or pushes anything to GitHub and has no gh-pages branch, no git
    remote, no *.github.io URL. The public site is served by WorkBuddy.

    Publishing on WorkBuddy is a PLATFORM ACTION, not a shell command: the
    WorkBuddy agent tool uploads a directory and keeps one stable share link per
    directory. A .ps1 cannot call it, so this script does the deterministic half
    (verify + privacy audit + emit the exact request) and the daily automation
    performs the upload immediately afterwards.

    Why keep a script at all: the privacy audit is the last gate before the
    content becomes public. It must run on EVERY publish, unattended, not only
    when a human remembers. That is exactly what this file preserves.

  WHAT IT DOES
    1. Confirms dist/ exists and holds an index.html (i.e. build_site.py ran).
    2. Re-runs the privacy / credential audit over dist/ (independent of
       build_site.py's own allow-list - two cheap checks, an unrecoverable leak).
    3. Prints a machine-readable request line for the automation:
         [WORKBUDDY-PUBLISH] directory=<abs dist path> status=ready
    4. Prints the Chinese hand-off text via scripts/handoff_workbuddy.py.

  FAILURE SEMANTICS (unchanged from the gh-pages era)
    exit 0 = dist/ is audited and ready; the caller may publish.
    exit 1 = audit failed or dist/ is missing/empty. NOTHING is published, and
             the previously published (good) site stays online untouched.
    A publish failure never invalidates the local data refresh.

  ASCII-ONLY SOURCE, deliberately: Windows PowerShell 5.1 decodes a BOM-less
  .ps1 with the system ANSI code page, so any Chinese literal here would be
  mis-decoded into invalid syntax. All Chinese output comes from
  scripts/handoff_workbuddy.py, which prints UTF-8.

  Usage:
    powershell -ExecutionPolicy Bypass -File scripts\publish-workbuddy.ps1
    powershell -ExecutionPolicy Bypass -File scripts\publish-workbuddy.ps1 -Rebuild
    powershell -ExecutionPolicy Bypass -File scripts\publish-workbuddy.ps1 -SkipAudit
================================================================================
#>
[CmdletBinding()]
param(
    [switch]$Rebuild,     # run build_site.py first
    [switch]$SkipAudit    # debugging only - never use for a real publish
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
Set-Location $Root

function Say([string]$Message, [string]$Color = 'Gray') { Write-Host $Message -ForegroundColor $Color }

# Python needs UTF-8 explicitly: its stdout otherwise uses the system code page and
# the Chinese hand-off text becomes mojibake.
$env:PYTHONIOENCODING = 'utf-8'
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch { }

$Python = (Get-Command py -ErrorAction SilentlyContinue).Source
if (-not $Python) { $Python = (Get-Command python -ErrorAction SilentlyContinue).Source }

$Dist = Join-Path $Root 'dist'

Say ''
Say '==== 1/3  Build dist/ ==============================================' 'Cyan'
if ($Rebuild -or -not (Test-Path $Dist)) {
    if (-not $Python) { Say 'Python not found; cannot build' 'Red'; exit 1 }
    & $Python (Join-Path $ScriptDir 'build_site.py')
    if ($LASTEXITCODE -ne 0) { Say 'build_site.py failed' 'Red'; exit 1 }
} else {
    Say '  dist/ already exists (use -Rebuild to regenerate)' 'DarkGray'
}
if (-not (Test-Path (Join-Path $Dist 'index.html'))) { Say 'dist/index.html missing' 'Red'; exit 1 }

if (-not $SkipAudit) {
    Say ''
    Say '==== 2/3  Privacy audit before publishing ==========================' 'Cyan'
    # Filename-based checks on purpose: matching on CONTENT would false-positive,
    # because the word "inbox" legitimately appears inside sources.json etc.
    foreach ($frag in @('collector-state.json', 'harness-')) {
        $hit = Get-ChildItem $Dist -Recurse -File -ErrorAction SilentlyContinue |
               Where-Object { $_.Name -like "*$frag*" }
        if ($hit) { Say "  AUDIT FAILED: $frag present in dist/" 'Red'; exit 1 }
    }
    if (Test-Path (Join-Path $Dist 'data\inbox')) {
        Say '  AUDIT FAILED: dist/data/inbox exists' 'Red'; exit 1
    }
    $susp = @()
    Get-ChildItem $Dist -Recurse -File | ForEach-Object {
        $t = Get-Content $_.FullName -Raw -ErrorAction SilentlyContinue
        if ($t -and $t -match 'sk-[A-Za-z0-9]{20,}') { $susp += $_.Name }
    }
    if ($susp.Count) { Say '  AUDIT FAILED: credential-shaped string in dist/' 'Red'; exit 1 }
    $files = (Get-ChildItem $Dist -Recurse -File | Measure-Object).Count
    $bytes = (Get-ChildItem $Dist -Recurse -File | Measure-Object -Property Length -Sum).Sum
    Say ("  audit OK: {0} files, {1:N2} MB, no private paths or credentials" -f $files, ($bytes / 1MB)) 'Green'
} else {
    Say ''
    Say '  -SkipAudit: privacy audit SKIPPED (debugging only)' 'Yellow'
}

Say ''
Say '==== 3/3  Hand off to the WorkBuddy publish step ===================' 'Cyan'
$absolute = (Resolve-Path $Dist).Path
# The single line the daily automation keys off. It names the directory, which is
# all the WorkBuddy publish tool needs: the tool resolves the target app from the
# directory, so the same link is updated every day and no URL is stored anywhere.
Say "[WORKBUDDY-PUBLISH] directory=$absolute status=ready" 'Green'

if ($Python) { & $Python (Join-Path $ScriptDir 'handoff_workbuddy.py') --ready }
Say ''
exit 0
