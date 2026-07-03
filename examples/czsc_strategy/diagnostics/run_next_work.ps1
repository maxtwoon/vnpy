param(
    [switch]$Preflight,
    [switch]$LiveCapture,
    [switch]$SkipReplay,
    [switch]$SkipKlineUpdate,
    [int]$DurationSeconds = 1800,
    [int]$CaptureTimeoutSeconds = 0,
    [int]$ReplayTimeoutSeconds = 1200,
    [int]$MinKlineBarsPerSymbol = 30,
    [string]$Date = "",
    [string]$OutDir = "",
    [string]$KlineDbPath = ""
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message"
}

function Invoke-Checked {
    param(
        [string]$Label,
        [string[]]$Command
    )
    Write-Step $Label
    & $Command[0] @($Command[1..($Command.Length - 1)])
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE"
    }
}

function Invoke-CheckedProcess {
    param(
        [string]$Label,
        [string]$FilePath,
        [string[]]$Arguments,
        [int]$TimeoutSeconds
    )
    Write-Step $Label
    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $FilePath
    $startInfo.UseShellExecute = $false
    $startInfo.Arguments = (($Arguments | ForEach-Object {
        '"' + $_.Replace('"', '\"') + '"'
    }) -join " ")

    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo

    [void]$process.Start()

    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        $process.Kill($true)
        throw "$Label timed out after $TimeoutSeconds seconds"
    }
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) {
        throw "$Label failed with exit code $($process.ExitCode)"
    }
}

function Assert-KlineCoverageWindow {
    param(
        [bool]$LiveCapture,
        [bool]$SkipKlineUpdate,
        [int]$DurationSeconds,
        [int]$MinKlineBarsPerSymbol
    )

    if ($LiveCapture -and -not $SkipKlineUpdate) {
        $RequiredSeconds = $MinKlineBarsPerSymbol * 60
        if ($DurationSeconds -lt $RequiredSeconds) {
            throw "DurationSeconds ($DurationSeconds) is shorter than MinKlineBarsPerSymbol ($MinKlineBarsPerSymbol); require at least $RequiredSeconds seconds or use -SkipKlineUpdate for a smoke test."
        }
    }
}

$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptPath "..\..\..")
Set-Location $RepoRoot

if ([string]::IsNullOrWhiteSpace($Date)) {
    $Date = Get-Date -Format "yyyy-MM-dd"
}

if ([string]::IsNullOrWhiteSpace($OutDir)) {
    $OutDir = $ScriptPath
}
$OutDir = (Resolve-Path $OutDir).Path

$CaptureJson = Join-Path $OutDir "simnow_export_$Date.json"
$ReplayJson = Join-Path $OutDir "simnow_replay_$Date.json"
$ReplayReadinessJson = Join-Path $OutDir "simnow_replay_readiness_$Date.json"
$KlineSummaryJson = Join-Path $OutDir "simnow_kline_update_$Date.json"
$RecordJson = Join-Path $OutDir "simnow_record_$Date.json"
$ReportMd = Join-Path $OutDir "simnow_report_$Date.md"
$PromotionMd = Join-Path $OutDir "simnow_20d_promotion_decision.md"
$RunSummaryJson = Join-Path $OutDir "simnow_run_summary_$Date.json"
$DailyBriefMd = Join-Path $OutDir "simnow_daily_brief_$Date.md"
$LedgerSummaryJson = Join-Path $OutDir "simnow_ledger_summary.json"
$ThresholdsJson = Join-Path $ScriptPath "simnow_risk_thresholds.json"
$LedgerPath = Join-Path $ScriptPath "simnow_observation_ledger.jsonl"

if ($CaptureTimeoutSeconds -le 0) {
    $CaptureTimeoutSeconds = $DurationSeconds + 180
}

Assert-KlineCoverageWindow `
    -LiveCapture $LiveCapture.IsPresent `
    -SkipKlineUpdate $SkipKlineUpdate.IsPresent `
    -DurationSeconds $DurationSeconds `
    -MinKlineBarsPerSymbol $MinKlineBarsPerSymbol

Write-Host "Repository: $RepoRoot"
Write-Host "Diagnostics: $ScriptPath"
Write-Host "Date: $Date"

Invoke-Checked "Compile SimNow capture script" @(
    "python",
    "-m",
    "py_compile",
    ".\examples\czsc_strategy\diagnostics\simnow_daily_capture.py",
    ".\examples\czsc_strategy\diagnostics\simnow_replay_readiness.py",
    ".\examples\czsc_strategy\diagnostics\simnow_backfill_pending_replays.py",
    ".\examples\czsc_strategy\diagnostics\simnow_tick_bars.py",
    ".\examples\czsc_strategy\diagnostics\simnow_run_summary.py",
    ".\examples\czsc_strategy\diagnostics\simnow_daily_brief.py",
    ".\examples\czsc_strategy\diagnostics\simnow_ledger_summary.py"
)

Invoke-Checked "Run SimNow workflow unit tests" @(
    "python",
    "-m",
    "pytest",
    ".\examples\czsc_strategy\tests\unit\test_simnow_connection_probe.py",
    ".\examples\czsc_strategy\tests\unit\test_simnow_daily_capture.py",
    ".\examples\czsc_strategy\tests\unit\test_simnow_daily_monitor.py",
    ".\examples\czsc_strategy\tests\unit\test_simnow_replay_readiness.py",
    ".\examples\czsc_strategy\tests\unit\test_simnow_backfill_pending_replays.py",
    ".\examples\czsc_strategy\tests\unit\test_simnow_tick_bars.py",
    ".\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py",
    ".\examples\czsc_strategy\tests\unit\test_simnow_docs.py",
    ".\examples\czsc_strategy\tests\unit\test_simnow_run_summary.py",
    ".\examples\czsc_strategy\tests\unit\test_simnow_daily_brief.py",
    ".\examples\czsc_strategy\tests\unit\test_simnow_ledger_summary.py",
    "-q"
)

Invoke-Checked "Build pending replay backfill plan" @(
    "python",
    ".\examples\czsc_strategy\diagnostics\simnow_backfill_pending_replays.py"
)

if ($Preflight -and -not $LiveCapture) {
    Write-Step "Preflight complete; live SimNow capture was not requested"
    exit 0
}

if ($LiveCapture) {
    Invoke-CheckedProcess `
        -Label "Run read-only SimNow capture" `
        -FilePath "python" `
        -Arguments @(
        ".\examples\czsc_strategy\diagnostics\simnow_daily_capture.py",
        "--duration-seconds", "$DurationSeconds",
        "--out-json", "$CaptureJson"
    ) `
        -TimeoutSeconds $CaptureTimeoutSeconds

    if (-not $SkipKlineUpdate) {
        Write-Step "Aggregate SimNow ticks into local 1M replay bars"
        $KlineArgs = @(
            ".\examples\czsc_strategy\diagnostics\simnow_tick_bars.py",
            "--simnow-json", "$CaptureJson",
            "--summary-json", "$KlineSummaryJson",
            "--min-bars-per-symbol", "$MinKlineBarsPerSymbol"
        )
        if (-not [string]::IsNullOrWhiteSpace($KlineDbPath)) {
            $KlineArgs += @("--db-path", "$KlineDbPath")
        }
        & python @KlineArgs
        if ($LASTEXITCODE -ne 0) {
            throw "SimNow kline update failed with exit code $LASTEXITCODE"
        }
    }

    if (-not $SkipReplay) {
        Write-Step "Check replay DB readiness"
        & python ".\examples\czsc_strategy\diagnostics\simnow_replay_readiness.py" --date $Date > $ReplayReadinessJson
        $ReplayReady = $LASTEXITCODE -eq 0
        if ($ReplayReady) {
            Invoke-CheckedProcess `
                -Label "Export same-day replay snapshot" `
                -FilePath "python" `
                -Arguments @(
                ".\examples\czsc_strategy\diagnostics\export_simnow_replay_snapshot.py",
                "--end", "$Date",
                "--date", "$Date",
                "--out-json", "$ReplayJson"
            ) `
                -TimeoutSeconds $ReplayTimeoutSeconds
        } else {
            Write-Host "Replay DB is not ready for $Date; skipping expensive replay export."
            $Readiness = Get-Content -LiteralPath $ReplayReadinessJson -Raw | ConvertFrom-Json
            $ReplayPlaceholder = [ordered]@{
                signals = @()
                trades = @()
                positions = @()
                risk = @{}
                meta = [ordered]@{
                    date = $Date
                    replay_available = $false
                    replay_unavailable_reason = "historical_db_lag"
                    latest_db_date = $Readiness.latest_db_date
                    db_path = $Readiness.db_path
                    missing_or_lagged_symbols = $Readiness.missing_or_lagged_symbols
                    table_ranges = $Readiness.table_ranges
                }
            }
            $ReplayPlaceholder | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $ReplayJson -Encoding UTF8
        }
    }

    Write-Step "Upsert daily record into formal ledger"
    $AppendArgs = @(
        ".\examples\czsc_strategy\diagnostics\simnow_daily_monitor.py",
        "--date", $Date,
        "--simnow-json", $CaptureJson,
        "--thresholds", $ThresholdsJson,
        "--record-json", $RecordJson,
        "--report-md", $ReportMd
    )
    if ((-not $SkipReplay) -and (Test-Path -LiteralPath $ReplayJson)) {
        $AppendArgs += @("--replay-json", $ReplayJson)
    }
    if ((-not $SkipKlineUpdate) -and (Test-Path -LiteralPath $KlineSummaryJson)) {
        $AppendArgs += @("--kline-json", $KlineSummaryJson)
    }
    & python @AppendArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Daily monitor append failed with exit code $LASTEXITCODE"
    }

    Write-Step "Generate ledger summary"
    & python ".\examples\czsc_strategy\diagnostics\simnow_ledger_summary.py" `
        --ledger $LedgerPath `
        --out-json $LedgerSummaryJson
    if ($LASTEXITCODE -ne 0) {
        throw "Ledger summary generation failed with exit code $LASTEXITCODE"
    }

    Write-Step "Generate promotion decision"
    & python ".\examples\czsc_strategy\diagnostics\simnow_promotion_decision.py" `
        --ledger $LedgerPath `
        --report-md $PromotionMd
    if ($LASTEXITCODE -ne 0) {
        throw "Promotion decision failed with exit code $LASTEXITCODE"
    }

    Write-Step "Generate run summary"
    $SummaryArgs = @(
        ".\examples\czsc_strategy\diagnostics\simnow_run_summary.py",
        "--date", $Date,
        "--out-dir", $OutDir,
        "--out-json", $RunSummaryJson,
        "--ledger", $LedgerPath,
        "--ledger-summary", $LedgerSummaryJson
    )
    & python @SummaryArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Run summary generation failed with exit code $LASTEXITCODE"
    }

    Write-Step "Generate daily brief"
    $BriefArgs = @(
        ".\examples\czsc_strategy\diagnostics\simnow_daily_brief.py",
        "--date", $Date,
        "--run-summary", $RunSummaryJson,
        "--out-md", $DailyBriefMd
    )
    & python @BriefArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Daily brief generation failed with exit code $LASTEXITCODE"
    }

    Write-Step "Live capture workflow complete"
    Write-Host "Capture JSON: $CaptureJson"
    if (Test-Path -LiteralPath $ReplayJson) {
        Write-Host "Replay JSON: $ReplayJson"
    }
    if (Test-Path -LiteralPath $KlineSummaryJson) {
        Write-Host "Kline update JSON: $KlineSummaryJson"
    }
    Write-Host "Record JSON: $RecordJson"
    Write-Host "Report MD: $ReportMd"
    Write-Host "Promotion MD: $PromotionMd"
    Write-Host "Run summary JSON: $RunSummaryJson"
    Write-Host "Daily brief MD: $DailyBriefMd"
    Write-Host "Ledger summary JSON: $LedgerSummaryJson"
    exit 0
}

Write-Step "No live action requested. Use -LiveCapture to run read-only SimNow capture."
