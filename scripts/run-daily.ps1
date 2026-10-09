<#
================================================================================
  Future Workbench - daily run entry point
================================================================================
  This is the ONLY entry point invoked by Windows Task Scheduler every day at
  18:00 Asia/Shanghai.

  Design notes (why it looks like this):
  * ASCII-only source. Windows PowerShell 5.1 decodes BOM-less .ps1 files with
    the system ANSI code page; any non-ASCII literal here would be mis-decoded
    and turn into a parse error. All Chinese user-facing text therefore comes
    from Python (scripts/selfcheck.py) or from the collector's own output.
  * Idempotent and re-entrant: it only writes files under web/data and can be
    re-run at any time without damaging history (the collector merges state).
  * Failures are visible: output goes to the console AND to
    web/data/logs/harness-YYYY-MM-DD.log.
      exit 0 = full success
      exit 2 = partial (some channels failed, data was still written)
      exit 1 = fatal (data layer untouched)
  * Secrets never land on disk: GITHUB_TOKEN etc. are read from the process
    environment only. Login-walled sites (Xiaohongshu / BOSS Zhipin / Lagou /
    Shixiseng) are NEVER scraped automatically.
  * Two layers: layer 1 is deterministic collection (stdlib, must work);
    layer 2 is an optional agent deep-read that can never break layer 1.

  Usage:
    powershell -ExecutionPolicy Bypass -File scripts\run-daily.ps1
    powershell -ExecutionPolicy Bypass -File scripts\run-daily.ps1 -SkipAgent
    powershell -ExecutionPolicy Bypass -File scripts\run-daily.ps1 -Only arxiv,hf_papers
    powershell -ExecutionPolicy Bypass -File scripts\run-daily.ps1 -Status
================================================================================
#>
[CmdletBinding()]
param(
    [switch]$SkipAgent,        # run the deterministic layer only
[switch]$SkipPublish,      # do not hand dist/ to the WorkBuddy publish step this run
[switch]$SkipGuards,       # skip the product guards (formula gate + layout audit)
[switch]$SkipTune,         # skip the auto-applicable keyword self-tuning
    [string]$Only = '',        # comma-separated channel ids (debugging)
    [int]$Limit = 0,           # per-channel item cap; 0 = use config value
    [switch]$Status,           # print current status and exit
    [switch]$Force,            # ignore the freshness guard and fetch anyway
    [switch]$Init              # first-time setup: dirs + config template
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

# ---------------------------------------------------------------------------
# 0. Paths and Shanghai time (fixed UTC+8, independent of host time zone)
# ---------------------------------------------------------------------------
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root      = Split-Path -Parent $ScriptDir
$DataDir   = Join-Path $Root 'web\data'
$LogDir    = Join-Path $DataDir 'logs'
$StateDir  = Join-Path $DataDir 'state'
$DigestDir = Join-Path $DataDir 'digest'
$ItemsDir  = Join-Path $DataDir 'items'
$InboxDir  = Join-Path $DataDir 'inbox'
$ProposalDir = Join-Path $DataDir 'proposals'

$ShanghaiTZ = [System.TimeZoneInfo]::FindSystemTimeZoneById('China Standard Time')
$Now = [System.TimeZoneInfo]::ConvertTimeFromUtc([DateTime]::UtcNow, $ShanghaiTZ)
$Day = $Now.ToString('yyyy-MM-dd')
$LogFile = Join-Path $LogDir "harness-$Day.log"

foreach ($d in @($DataDir, $LogDir, $StateDir, $DigestDir, $ItemsDir, $InboxDir, $ProposalDir)) {
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
}

function Write-Log {
    param([string]$Message, [string]$Level = 'INFO')
    $stamp = (Get-Date).ToString('HH:mm:ss')
    $line = "[$stamp][$Level] $Message"
    switch ($Level) {
        'OK'    { Write-Host $line -ForegroundColor Green }
        'WARN'  { Write-Host $line -ForegroundColor Yellow }
        'ERROR' { Write-Host $line -ForegroundColor Red }
        'STEP'  { Write-Host $line -ForegroundColor Cyan }
        default { Write-Host $line }
    }
    Write-LogLine $line
}

# Append one already-formatted line to the log file as UTF-8 WITHOUT a BOM.
# Do NOT use Tee-Object -Append for this: on Windows PowerShell 5.1 it writes
# UTF-16LE, which both mojibakes Chinese and alternates encodings inside one
# file, making the log unreadable.
function Write-LogLine {
    param([string]$Line)
    try {
        [System.IO.File]::AppendAllText($LogFile, $Line + [Environment]::NewLine,
            (New-Object System.Text.UTF8Encoding($false)))
    } catch { }
}

# Run a native command: echo its output to the console AND append it to the log
# as UTF-8, preserving exit code. This replaces `| Tee-Object -FilePath ... -Append`.
function Invoke-Logged {
    param([string]$Exe, [string[]]$Arguments)
    $text = & $Exe @Arguments 2>&1 | Out-String
    $code = $LASTEXITCODE
    if ($text) {
        Write-Host $text.TrimEnd()
        Write-LogLine $text.TrimEnd()
    }
    return $code
}

# ---------------------------------------------------------------------------
# 1. Locate Python (py launcher first, then python)
# ---------------------------------------------------------------------------
$PythonExe = $null
foreach ($cand in @('py', 'python')) {
    $cmd = Get-Command $cand -ErrorAction SilentlyContinue
    if ($cmd) { $PythonExe = $cmd.Source; break }
}
if (-not $PythonExe) {
    Write-Log 'Python not found. Install Python 3.9+ and make sure py or python is on PATH.' 'ERROR'
    exit 1
}

# Force UTF-8 for Python I/O so Chinese never mojibakes in the console/log.
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch { }

$Collector = Join-Path $ScriptDir 'collect.py'
$SelfCheck = Join-Path $ScriptDir 'selfcheck.py'
$Planner   = Join-Path $ScriptDir 'plan_deep_read.py'
if (-not (Test-Path $Collector)) {
    Write-Log "Collector not found: $Collector" 'ERROR'
    exit 1
}

# ---------------------------------------------------------------------------
# 2. Status mode
# ---------------------------------------------------------------------------
if ($Status) {
    if (Test-Path $SelfCheck) { $null = Invoke-Logged $PythonExe @($SelfCheck, '--status') }
    else { Write-Log 'selfcheck.py missing' 'WARN' }
    exit 0
}

Write-Log "===== Future daily run started | Shanghai $($Now.ToString('yyyy-MM-dd HH:mm:ss')) =====" 'STEP'
Write-Log "Python: $PythonExe"

# ---------------------------------------------------------------------------
# 2b. Freshness guard - the ONLY duplicate-run protection.
#
#     ARCHITECTURE (changed 2026-10-02): there is now exactly ONE trigger - the DSH
#     automation task, which runs this script when it fires. The Windows Task
#     Scheduler trigger is DISABLED, so a single-instance mutex used to guard against
#     two simultaneous triggers was removed as dead code.
#
#     NOTE ON MANUAL RUNS: a disabled scheduled task cannot be started with
#     `schtasks /Run` (it fails with "could not run because it is disabled", even
#     though AllowDemandStart is true). The manual entry point is therefore to run
#     THIS SCRIPT directly:
#         powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run-daily.ps1 -Force
#     Re-enable the task first (Enable-ScheduledTask) if you specifically want to
#     exercise the Task Scheduler path.
#
#     What remains is the cheap idempotency check that protects against the real
#     remaining risk: an accidental double fire (a retry, a resumed schedule). If the
#     data layer was refreshed moments ago there is nothing to gain from redoing the
#     whole pipeline. The window is small (5 min) so it stays out of the way - any
#     legitimate re-run is at least that far apart - and `-Force` bypasses it.
# ---------------------------------------------------------------------------
$FreshnessMinutes = 5
if (-not $Force) {
    $lastIso = & $PythonExe -c "import json;d=json.load(open(r'$DataDir\manifest.json',encoding='utf-8')) if __import__('os').path.exists(r'$DataDir\manifest.json') else {};print(d.get('lastRunAt') or '')" 2>$null
    $lastIso = ("$lastIso").Trim()
    if ($lastIso) {
        try {
            $lastDt = [DateTimeOffset]::Parse($lastIso).ToOffset([TimeSpan]::FromHours(8))
            $ageMin = [math]::Round(([DateTimeOffset]::new($Now, [TimeSpan]::FromHours(8)) - $lastDt).TotalMinutes, 1)
            if ($ageMin -ge 0 -and $ageMin -lt $FreshnessMinutes) {
                Write-Log ("data was refreshed $ageMin min ago (< $FreshnessMinutes min) - standing down; " +
                           "pass -Force to fetch anyway") 'WARN'
                exit 0
            }
            Write-Log "last successful data refresh: $lastIso ($ageMin min ago) - proceeding" 'INFO'
        } catch {
            Write-Log "could not parse lastRunAt ('$lastIso') - proceeding anyway" 'WARN'
        }
    }
}

# ---------------------------------------------------------------------------
# 3. Optional first-time init
# ---------------------------------------------------------------------------
if ($Init) {
    Write-Log 'Init: writing config template and data skeleton' 'STEP'
    $null = Invoke-Logged $PythonExe @($Collector, '--init-config')
}

# ---------------------------------------------------------------------------
# 4. Layer 1 - deterministic collection (must succeed)
# ---------------------------------------------------------------------------
$collectArgs = @($Collector)
# Tag the run so logs/runs.json can tell the automatic 18:00 schedule apart from
# human/dev invocations. Without this, a debugging afternoon reads exactly like
# "the schedule fired ten times".
if ($env:FUTURE_TRIGGER) {
    $collectArgs += @('--trigger', $env:FUTURE_TRIGGER)
} else {
    $collectArgs += @('--trigger', 'manual')
}
if ($Only) { $collectArgs += @('--only', $Only) }
if ($Limit -gt 0) { $collectArgs += @('--limit', "$Limit") }

Write-Log "collect args: $($collectArgs -join ' ')" 'STEP'
$sw = [System.Diagnostics.Stopwatch]::StartNew()
$collectExit = Invoke-Logged $PythonExe $collectArgs
$sw.Stop()
if ($collectExit -eq 0) {
    Write-Log ("layer 1 finished, exit 0, {0:n1}s" -f $sw.Elapsed.TotalSeconds) 'OK'
} else {
    Write-Log ("layer 1 FAILED with exit $collectExit after {0:n1}s" -f $sw.Elapsed.TotalSeconds) 'ERROR'
    Write-Log 'Existing data files were NOT overwritten. Checks: 1) network/proxy 2) python scripts\collect.py --only arxiv --dry-run -v 3) log above' 'WARN'
}

# ---------------------------------------------------------------------------
# 5. Redundancy gate - catch the "same thing, many versions" accumulation.
#
#     WHY this is here: the collector's four-layer de-duplication works WITHIN a run
#     (stable id / canonical url / title fingerprint / simhash), so it cannot see a
#     model re-uploaded under three repo names or the same paper appearing on arXiv
#     and OpenAlex. dedupe_deep.py is the second pass for exactly that, but it was
#     never called by the daily job - so redundancy could only ever be found by a
#     human remembering to run it by hand.
#
#     Both steps are REPORT-ONLY by default. Auto-deleting content from the corpus is
#     not something an unattended nightly job should do; the report goes into the run
#     log and the proposals file, and the worklist is for the human to action.
# ---------------------------------------------------------------------------
$DedupeDeep = Join-Path $ScriptDir 'dedupe_deep.py'
$Redundancy = Join-Path $ScriptDir 'analyze_redundancy.py'
if (Test-Path $DedupeDeep) {
    Write-Log 'redundancy: scanning for same-content duplicates (report only)' 'STEP'
    $dedupeExit = Invoke-Logged $PythonExe @($DedupeDeep, '--show', '8')
    if ($dedupeExit -ne 0) {
        Write-Log "dedupe_deep.py returned $dedupeExit" 'WARN'
    }
} else {
    Write-Log 'dedupe_deep.py not found, skipping content de-duplication' 'WARN'
}
if (Test-Path $Redundancy) {
    Write-Log 'redundancy: auditing entity repetition, topic saturation, low-info items' 'STEP'
    $redunReport = Join-Path $Root 'web\data\redundancy-report.json'
    $redunExit = Invoke-Logged $PythonExe @($Redundancy, '--top', '8', '--json', $redunReport)
    if ($redunExit -ne 0) {
        Write-Log "analyze_redundancy.py returned $redunExit (its findings are also asserted by selfcheck)" 'WARN'
    }
} else {
    Write-Log 'analyze_redundancy.py not found, skipping the redundancy audit' 'WARN'
}

# Interview extract. Interview write-ups are the most perishable content here, so the
# problem-bank page leads with what is still fresh (company / round / outcome / topics).
# Deterministic rules, no LLM - so it runs every day and every field is checkable.
$InterviewIdx = Join-Path $ScriptDir 'build_interview_index.py'
if (Test-Path $InterviewIdx) {
    Write-Log 'interview index: extracting company / round / outcome / topics' 'STEP'
    $ivExit = Invoke-Logged $PythonExe @($InterviewIdx, '--show')
    if ($ivExit -ne 0) {
        Write-Log "build_interview_index.py returned $ivExit" 'WARN'
    }
} else {
    Write-Log 'build_interview_index.py not found, skipping the interview index' 'WARN'
}

# Problem bank. The reader's requirement is explicit: a 手撕题 / 笔试题 must arrive as a
# SOLVED problem (runnable code + complexity + pitfalls + diagram), not as a repo link.
# This step merges three sources into one entity per problem - CodeTop's real
# "company x question x frequency" data, the algorithm knowledge-base 题解 pages, and the
# hand-curated 题库 in jobs.json - and attaches whatever deep-read analysis exists.
# Deterministic (no LLM), so it runs every day and every field is checkable.
$ProblemBank = Join-Path $ScriptDir 'build_problem_bank.py'
if (Test-Path $ProblemBank) {
    Write-Log 'problem bank: merging CodeTop frequency + 题解 + curated 题库 + deep-read code' 'STEP'
    $pbExit = Invoke-Logged $PythonExe @($ProblemBank, '--show')
    if ($pbExit -ne 0) {
        Write-Log "build_problem_bank.py returned $pbExit" 'WARN'
    }
} else {
    Write-Log 'build_problem_bank.py not found, skipping the problem bank' 'WARN'
}

# ---------------------------------------------------------------------------
# 5a. Self-check - integrity / authenticity gate over the produced artifacts
#     (this also asserts the redundancy thresholds, so a growing pile of
#     unclassified or saturated content turns up as a warning here)
# ---------------------------------------------------------------------------
$checkExit = 0
if (Test-Path $SelfCheck) {
    Write-Log 'self-check: validating produced artifacts' 'STEP'
    $checkExit = Invoke-Logged $PythonExe @($SelfCheck)
} else {
    Write-Log 'selfcheck.py not found, skipping the integrity gate' 'WARN'
}

# ---------------------------------------------------------------------------
# 5b. Deep-read plan - decide WHAT deserves a deep analysis, and how many.
#
# Separating "collect" from "decide what to analyse" is deliberate: a daily pass
# that never ends up analysing anything useful is the main failure mode of this
# kind of workbench. This step refuses low-value items (job-venting, generic
# questions, referral spam) and hands the agent an explicit quota-limited queue
# of 2-10 items per category, so depth is spent where it pays off.
# ---------------------------------------------------------------------------
if (Test-Path $Planner) {
    Write-Log 'planning the deep-read queue (quality gate + per-category quota)' 'STEP'
    # --all is deliberate. Without it the planner considers only today's fresh
    # items, so the queue described at most one day of work and every run threw
    # away the backlog of cards that had never been deep-read. Observed effect:
    # the agent analysed exactly 1 item while 103 cards sat unanalysed.
    $planExit = Invoke-Logged $PythonExe @($Planner, '--all')
    if ($planExit -ne 0) {
        Write-Log "planner returned $planExit; the agent will have no work list this run" 'WARN'
    }
} else {
    Write-Log 'plan_deep_read.py not found, skipping the deep-read plan' 'WARN'
}

# ---------------------------------------------------------------------------
# 6. Layer 2 (optional) - agent deep read
#    Produces enrichment / formulas / proposals. A failure here never affects
#    the data layer 1 already wrote.
# ---------------------------------------------------------------------------
if (-not $SkipAgent) {
    $promptFile = Join-Path $ScriptDir 'daily-agent.md'

    # Locate dsh (DeepSeek Harness CLI). The desktop app does not necessarily add
    # itself to PATH, so probe, in order: PATH, scripts/dsh.cmd wrapper, the
    # Program Files locations, then the registry's uninstall records (works for
    # custom install drives such as D:\).
    $dshExe = $null
    $onPath = Get-Command dsh -ErrorAction SilentlyContinue
    if ($onPath) { $dshExe = $onPath.Source }

    $localDsh = Join-Path $ScriptDir 'dsh.cmd'
    if (-not $dshExe -and (Test-Path $localDsh)) { $dshExe = $localDsh }

    if (-not $dshExe) {
        foreach ($base in @($env:ProgramFiles, ${env:ProgramFiles(x86)}, "$env:LOCALAPPDATA\Programs")) {
            if (-not $base) { continue }
            $p = Join-Path $base 'DeepSeek Harness\resources\runtime\cli\bin\dsh.cmd'
            if (Test-Path $p) { $dshExe = $p; break }
        }
    }

    if (-not $dshExe) {
        try {
            $roots = @('HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
                       'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
                       'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*')
            foreach ($r in $roots) {
                foreach ($item in (Get-ItemProperty $r -ErrorAction SilentlyContinue)) {
                    if ($item.DisplayName -like '*DeepSeek Harness*' -and $item.InstallLocation) {
                        $p = Join-Path $item.InstallLocation 'resources\runtime\cli\bin\dsh.cmd'
                        if (Test-Path $p) { $dshExe = $p; break }
                    }
                }
                if ($dshExe) { break }
            }
        } catch { }
    }

    $agentStamp = Join-Path $StateDir "agent-$Day.stamp"
    if ((Test-Path $agentStamp) -and (-not $Only)) {
        Write-Log 'layer 2: already ran today, skipping (delete state\agent-*.stamp to force)' 'WARN'
    }
    elseif (-not (Test-Path $promptFile)) {
        Write-Log "layer 2: prompt file missing ($promptFile), skipping" 'WARN'
    }
    elseif (-not $dshExe) {
        Write-Log 'layer 2: dsh (DeepSeek Harness CLI) not found, skipping' 'WARN'
    }
    else {
        # Credential pre-flight. `dsh` resolves LLM credentials from two places:
        #   1. an environment variable (DEEPSEEK_API_KEY), which a scheduled task
        #      only sees if it was set BEFORE the logon session started, and
        #   2. the harness credential store (~/.dsh/.credentials.yaml), written by
        #      the DSH web Models page - this one survives logon and reboots.
        # Checking only the environment variable produced a false "no credential"
        # report while the store already had a working key, so probe both and let
        # dsh make the final call.
        $credStore = Join-Path $env:USERPROFILE '.dsh\.credentials.yaml'
        $hasEnv = [bool]($env:DEEPSEEK_API_KEY -or $env:DSH_HEADLESS_API_KEY)
        $hasStore = $false
        if (Test-Path $credStore) {
            try {
                $credText = [System.IO.File]::ReadAllText($credStore)
                $hasStore = $credText -match 'DEEPSEEK'
            } catch { $hasStore = $false }
        }

        if (-not $hasEnv -and -not $hasStore) {
            Write-Log 'layer 2: SKIPPED - no LLM credential found in this environment or the harness store.' 'WARN'
            Write-Log '         Set one of these, then the daily deep-read will start working:' 'WARN'
            Write-Log '           (a) [Environment]::SetEnvironmentVariable("DEEPSEEK_API_KEY","sk-...","User")  then sign out/in once' 'WARN'
            Write-Log '           (b) open the DSH web Models page and fill it in once (stored in ~\.dsh\.credentials.yaml)' 'WARN'
            Write-Log '         Layer 1 data was written normally; only the deep-read enrichment is missing.' 'WARN'
        }
        else {
            $src = if ($hasEnv) { 'environment variable' } else { 'harness credential store' }
            Write-Log "layer 2: agent deep read starting (credential source: $src) | $dshExe" 'STEP'
            $task = (Get-Content $promptFile -Raw -Encoding UTF8).Replace('{{DATE}}', $Day).Replace('{{ROOT}}', $Root)
            try {
                $agentSw = [System.Diagnostics.Stopwatch]::StartNew()
                # The prompt goes in on stdin; output is captured, echoed, and logged
                # as UTF-8 (never via Tee-Object, which would write UTF-16).
                #
                # $ErrorActionPreference is lowered for this call. With 'Stop',
                # Windows PowerShell 5.1 turns ANY native stderr line into a
                # terminating error, so a harmless Node notice such as
                # "ExperimentalWarning: stripTypeScriptTypes is an experimental
                # feature" was caught by the block below and reported as
                # "layer 2 threw, skipped" - even though the agent had completed
                # successfully and written all of its output. The exit code is the
                # only reliable signal here.
                $prevEap = $ErrorActionPreference
                $ErrorActionPreference = 'Continue'
                try {
                    $agentOut = $task | & $dshExe headless --json '-' 2>&1 | Out-String
                    $agentExit = $LASTEXITCODE
                } finally {
                    $ErrorActionPreference = $prevEap
                }
                $agentSw.Stop()
                if ($agentOut) {
                    Write-Host $agentOut.TrimEnd()
                    Write-LogLine $agentOut.TrimEnd()
                }
                if ($agentExit -eq 0) {
                    New-Item -ItemType File -Path $agentStamp -Force | Out-Null
                    Write-Log ("layer 2 finished, {0:n1}s" -f $agentSw.Elapsed.TotalSeconds) 'OK'
                } else {
                    Write-Log "layer 2 returned exit $agentExit (data layer unaffected)" 'WARN'
                }
            } catch {
                Write-Log "layer 2 threw, skipped: $($_.Exception.Message)" 'WARN'
            }
        }
    }
} else {
    Write-Log 'layer 2: skipped by -SkipAgent' 'WARN'
}

# ---------------------------------------------------------------------------
# 6. Self-tuning: apply the ONE change class that is allowed to auto-apply.
#
#     reviewPolicy has always declared that minor keyword adjustments may take
#     effect automatically while everything else (category changes, channel
#     add/drop, scoring weights, dedupe thresholds, blocklist) needs human approval.
#     That auto channel had no implementation, so "self-improvement" stopped at
#     "detect a problem" and never "fix a problem".
#
#     tune_keywords.py consumes the keywordProposals the deep-read agent produced
#     and applies them under hard guardrails: length/shape checks, a stopword list,
#     no keyword shared with another category, protected core keywords, and caps of
#     5 per category and 12 per run. Every change is appended to
#     web/data/proposals/keyword-tune-log.jsonl with its reason, so it is auditable
#     and reversible.
#
#     Non-fatal: a tuning failure must never break the data refresh.
# ---------------------------------------------------------------------------
$Tuner = Join-Path $ScriptDir 'tune_keywords.py'
if ((Test-Path $Tuner) -and -not $SkipTune) {
    Write-Log 'self-tuning: applying minor keyword adjustments (auto-applicable class)' 'STEP'
    $tuneExit = Invoke-Logged $PythonExe @($Tuner)
    if ($tuneExit -ne 0) {
        Write-Log "tune_keywords.py returned $tuneExit; keyword set left unchanged" 'WARN'
    }
} elseif ($SkipTune) {
    Write-Log 'self-tuning skipped by -SkipTune' 'WARN'
} else {
    Write-Log 'tune_keywords.py not found, skipping self-tuning' 'WARN'
}

# ---------------------------------------------------------------------------
# 6a. Product guards.
#
#     WHY THIS STEP EXISTS: check-formulas.mjs and audit-layout.mjs were written
#     in response to two real outages (a completely blank formula-analysis page,
#     and clipped/overflowing panels), but they only ran when a human remembered to
#     run them. A guard that is not on the daily path does not protect anything.
#
#     The formula check is a GATE: one malformed LaTeX string thrown by tex()
#     replaces the whole page with an error card, and the deep-read agent writes new
#     formulas unattended every night, so this must be checked before publishing.
#     The layout audit is advisory only and never blocks a data refresh.
# ---------------------------------------------------------------------------
$Guards = Join-Path $ScriptDir 'run_guards.py'
$guardFailed = $false
if ((Test-Path $Guards) -and -not $SkipGuards) {
    Write-Log 'product guards: formula renderer + layout overflow' 'STEP'
    $guardExit = Invoke-Logged $PythonExe @($Guards)
    if ($guardExit -ne 0) {
        $guardFailed = $true
        Write-Log 'FORMULA GATE FAILED: a malformed formula would blank the formula-analysis page. Fix web/data/formulas.json before publishing.' 'WARN'
    } else {
        Write-Log 'guards passed' 'OK'
    }
} elseif ($SkipGuards) {
    Write-Log 'product guards skipped by -SkipGuards' 'WARN'
} else {
    Write-Log 'run_guards.py not found, skipping product guards' 'WARN'
}

# ---------------------------------------------------------------------------
# 6b. Rebuild the publishable site (dist/).
#
#     Deliberately non-fatal: publishing is a convenience, and a failure here
#     (e.g. a transient file lock) must never mark the data refresh as failed.
# ---------------------------------------------------------------------------
$SiteBuilder = Join-Path $ScriptDir 'build_site.py'
$siteOk = $false
if (Test-Path $SiteBuilder) {
    Write-Log 'rebuilding the publishable site (dist/)' 'STEP'
    $siteExit = Invoke-Logged $PythonExe @($SiteBuilder)
    if ($siteExit -ne 0) {
        Write-Log "build_site.py returned $siteExit (the data refresh itself is unaffected)" 'WARN'
    } else {
        $siteOk = $true
        Write-Log 'dist/ rebuilt' 'OK'
    }
} else {
    Write-Log 'build_site.py not found, skipping the site build' 'WARN'
}

# A failed formula gate means the published page would be broken, so skip the
# publish but keep the locally refreshed data. Publishing a blank page is worse
# than publishing yesterday's good page.
if ($guardFailed) {
    $siteOk = $false
    Write-Log 'publish held back because the formula gate failed (local data is still up to date)' 'WARN'
}

# ---------------------------------------------------------------------------
# 6c. Publish dist/ to WorkBuddy so the hosted site tracks this run.
#
#     WHY THIS STEP EXISTS: the hosted site never reads this machine's disk. A
#     successful local collection does NOT update the website - only a publish
#     does. Without this step the site silently freezes at the last manual
#     publish while the local workbench keeps moving.
#
#     WHAT CHANGED (2026-10-03): the publish target moved from GitHub Pages to
#     WorkBuddy. There is no commit, no push, no gh-pages branch and no
#     *.github.io URL any more. Publishing on WorkBuddy is a PLATFORM ACTION an
#     agent tool performs, so this step does the deterministic half: verify +
#     privacy audit + print the machine-readable request
#         [WORKBUDDY-PUBLISH] directory=<abs dist path> status=ready
#     The daily automation reads that line and uploads the directory right away.
#     One directory maps to exactly one stable share link, so re-publishing
#     overwrites the same link and no URL ever needs to be stored.
#
#     NON-FATAL BY DESIGN: an audit failure, an unreachable network or a
#     platform-side error must not make the data refresh look failed. The
#     failure is logged loudly and the local dist/ is untouched; the previously
#     published (good) site stays online and the next run retries.
# ---------------------------------------------------------------------------
$Publisher = Join-Path $ScriptDir 'publish-workbuddy.ps1'
if ($siteOk -and -not $SkipPublish) {
    if (Test-Path $Publisher) {
        Write-Log 'publishing dist/ to WorkBuddy (audit + hand-off)' 'STEP'
        # No -Rebuild: dist/ was just built above. The publish script re-runs its
        # own privacy audit before handing off, which is intentional - that is the
        # last gate before the content becomes public.
        $pubExit = Invoke-Logged 'powershell.exe' @('-NoProfile', '-ExecutionPolicy', 'Bypass',
                                                   '-File', $Publisher)
        if ($pubExit -eq 0) {
            Write-Log 'dist/ audited and handed off; the daily automation now uploads it to WorkBuddy' 'OK'
        } else {
            Write-Log "publish hand-off FAILED (exit $pubExit): run scripts\handoff_workbuddy.py --trouble for the checklist. The local data refresh succeeded." 'WARN'
        }
    } else {
        Write-Log 'publish-workbuddy.ps1 not found, skipping the publish step' 'WARN'
    }
} elseif ($SkipPublish) {
    Write-Log 'publish step skipped by -SkipPublish' 'WARN'
}

# ---------------------------------------------------------------------------
# 7. Wrap up
# ---------------------------------------------------------------------------
if (Test-Path $SelfCheck) { $null = Invoke-Logged $PythonExe @($SelfCheck, '--summary') }

$final = 0
if ($collectExit -ne 0) { $final = 1 }
elseif ($checkExit -ne 0) { $final = 2 }
Write-Log "===== finished, exit code $final =====" 'STEP'
exit $final
