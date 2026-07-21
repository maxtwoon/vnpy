param(
    [switch]$Preflight,
    [switch]$LiveCapture,
    [switch]$PostProcessOnly,
    [switch]$SkipReplay,
    [switch]$SkipKlineUpdate,
    [int]$DurationSeconds = 1800,
    [int]$CaptureTimeoutSeconds = 0,
    [int]$ReplayTimeoutSeconds = 1200,
    [int]$MinKlineBarsPerSymbol = 30,
    [switch]$UpdateHistoricalDb,
    [switch]$SkipHistoricalDbUpdate,
    [string]$HistoricalDbUpdateCommand = 'powershell.exe -ExecutionPolicy Bypass -File "D:\repo\ssquant\auto_update.ps1"',
    [int]$HistoricalDbUpdateTimeoutSeconds = 14400,
    [string]$Date = "",
    [string]$OutDir = "",
    [string]$KlineDbPath = ""
)

$ErrorActionPreference = "Stop"
$DefaultHistoricalDbUpdateCommand = 'powershell.exe -ExecutionPolicy Bypass -File "D:\repo\ssquant\auto_update.ps1"'
$HistoricalDbUpdateScriptPath = "D:\repo\ssquant\auto_update.ps1"

# Avoid permission-sensitive __pycache__ writes in the source tree.
$env:PYTHONDONTWRITEBYTECODE = '1'

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

function Assert-LiveArtifactExists {
    param(
        [string]$Path,
        [string]$Label
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "$Label artifact is missing: $Path"
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

function Get-FormalCapturePlan {
    param(
        [bool]$LiveCapture,
        [bool]$SkipKlineUpdate,
        [datetimeoffset]$Now,
        [int]$MinKlineBarsPerSymbol
    )

    if (-not $LiveCapture -or $SkipKlineUpdate) {
        return $null
    }

    $LocalNow = $Now.ToLocalTime()
    $TimeOfDay = $LocalNow.TimeOfDay
    $RequiredSeconds = $MinKlineBarsPerSymbol * 60
    $WindowSpecs = @(
        [ordered]@{
            window_name = "day_open"
            trigger_label = "09:05"
            trigger_start = [timespan]::Parse("09:05:00")
            trigger_end = [timespan]::Parse("09:10:00")
            capture_end = [timespan]::Parse("11:30:00")
        },
        [ordered]@{
            window_name = "day_afternoon"
            trigger_label = "13:35"
            trigger_start = [timespan]::Parse("13:35:00")
            trigger_end = [timespan]::Parse("13:40:00")
            capture_end = [timespan]::Parse("15:00:00")
        },
        [ordered]@{
            window_name = "night_open"
            trigger_label = "21:05"
            trigger_start = [timespan]::Parse("21:05:00")
            trigger_end = [timespan]::Parse("21:10:00")
            capture_end = [timespan]::Parse("23:00:00")
        }
    )

    $MatchedSpec = $null
    foreach ($Spec in $WindowSpecs) {
        if ($TimeOfDay -ge $Spec.trigger_start -and $TimeOfDay -lt $Spec.trigger_end) {
            $MatchedSpec = $Spec
            break
        }
    }

    if ($null -eq $MatchedSpec) {
        throw "Formal observation window rejected: automatic formal runs must start in one of [09:05, 13:35, 21:05] with a 5-minute grace window. Current local time is $($LocalNow.ToString('yyyy-MM-dd HH:mm:ss zzz'))."
    }

    $WindowStart = $LocalNow.Date + $MatchedSpec.trigger_start
    $WindowEnd = $LocalNow.Date + $MatchedSpec.capture_end
    $RemainingSeconds = [int][math]::Floor(($WindowEnd - $LocalNow.DateTime).TotalSeconds)

    if ($RemainingSeconds -lt $RequiredSeconds) {
        throw "Formal observation window rejected: remaining window seconds ($RemainingSeconds) are shorter than MinKlineBarsPerSymbol ($MinKlineBarsPerSymbol); require at least $RequiredSeconds seconds before the window close."
    }

    return [ordered]@{
        window_name = [string]$MatchedSpec.window_name
        trigger_label = [string]$MatchedSpec.trigger_label
        window_start = ([datetime]$WindowStart).ToString("yyyy-MM-ddTHH:mm:sszzz")
        window_end = ([datetime]$WindowEnd).ToString("yyyy-MM-ddTHH:mm:sszzz")
        duration_seconds = $RemainingSeconds
    }
}

function Assert-FormalObservationWindow {
    param(
        [bool]$LiveCapture,
        [bool]$SkipKlineUpdate,
        [datetimeoffset]$Now,
        [object]$ContractMap
    )

    if (-not $LiveCapture -or $SkipKlineUpdate) {
        return
    }

    $LocalNow = $Now.ToLocalTime()
    $TimeOfDay = $LocalNow.TimeOfDay
    $DaySessionStart = [timespan]::Parse("08:45:00")
    $DaySessionEnd = [timespan]::Parse("15:30:00")

    $CurrentSession = "night"
    if ($TimeOfDay -ge $DaySessionStart -and $TimeOfDay -le $DaySessionEnd) {
        $CurrentSession = "day"
    }

    $BlockingSymbols = [System.Collections.Generic.List[string]]::new()
    $Entries = @()
    if ($ContractMap -is [System.Collections.IDictionary]) {
        $Entries = $ContractMap.GetEnumerator()
    } else {
        $Entries = $ContractMap.PSObject.Properties
    }

    foreach ($Entry in $Entries) {
        if ($ContractMap -is [System.Collections.IDictionary]) {
            $Symbol = [string]$Entry.Key
            $Row = $Entry.Value
        } else {
            $Symbol = [string]$Entry.Name
            $Row = $Entry.Value
        }

        if ($null -eq $Row) {
            continue
        }

        $Enabled = $false
        if ($Row -is [System.Collections.IDictionary]) {
            if ($Row.Contains("enabled")) {
                $Enabled = [bool]$Row["enabled"]
            }
        } elseif ($Row.PSObject.Properties.Name -contains "enabled") {
            $Enabled = [bool]$Row.enabled
        }
        if (-not $Enabled) {
            continue
        }

        $AllowedSessions = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
        $FormalSessions = $null
        if ($Row -is [System.Collections.IDictionary]) {
            if ($Row.Contains("formal_sessions")) {
                $FormalSessions = $Row["formal_sessions"]
            }
        } elseif ($Row.PSObject.Properties.Name -contains "formal_sessions") {
            $FormalSessions = $Row.formal_sessions
        }

        if ($null -eq $FormalSessions) {
            [void]$AllowedSessions.Add("day")
            [void]$AllowedSessions.Add("night")
        } else {
            foreach ($Session in @($FormalSessions)) {
                if ($null -ne $Session) {
                    [void]$AllowedSessions.Add([string]$Session)
                }
            }
        }

        if (-not $AllowedSessions.Contains($CurrentSession)) {
            [void]$BlockingSymbols.Add($Symbol)
        }
    }

    if ($BlockingSymbols.Count -gt 0) {
        $BlockingList = [string]::Join(", ", $BlockingSymbols)
        throw "Formal observation window rejected: enabled symbols [$BlockingList] do not allow the $CurrentSession session; current local time is $($LocalNow.ToString('yyyy-MM-dd HH:mm:ss zzz')). Use -SkipKlineUpdate for a smoke test or run during an allowed session."
    }
}

function Get-HistoricalDbUpdateTables {
    param([object]$ContractMap)

    $Periods = @("15M", "1M", "5M")
    $Tables = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    $Entries = @()
    if ($ContractMap -is [System.Collections.IDictionary]) {
        $Entries = $ContractMap.GetEnumerator()
    } else {
        $Entries = $ContractMap.PSObject.Properties
    }

    foreach ($Entry in $Entries) {
        if ($ContractMap -is [System.Collections.IDictionary]) {
            $Symbol = [string]$Entry.Key
            $Row = $Entry.Value
        } else {
            $Symbol = [string]$Entry.Name
            $Row = $Entry.Value
        }

        if ([string]::IsNullOrWhiteSpace($Symbol) -or $null -eq $Row) {
            continue
        }

        $Enabled = $false
        if ($Row -is [System.Collections.IDictionary]) {
            if ($Row.Contains("enabled")) {
                $Enabled = [bool]$Row["enabled"]
            }
        } elseif ($Row.PSObject.Properties.Name -contains "enabled") {
            $Enabled = [bool]$Row.enabled
        }

        if (-not $Enabled) {
            continue
        }

        $ContinuousSymbol = $Symbol.Trim().ToLowerInvariant()
        foreach ($Period in $Periods) {
            [void]$Tables.Add("${ContinuousSymbol}_${Period}_raw")
        }
    }

    return @($Tables | Sort-Object)
}

$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptPath "..\..\..")
Set-Location $RepoRoot
$ContractMapPath = Join-Path $ScriptPath "simnow_contract_map.json"
$ContractMap = Get-Content -LiteralPath $ContractMapPath -Raw | ConvertFrom-Json

$FormalCapturePlan = Get-FormalCapturePlan `
    -LiveCapture $LiveCapture.IsPresent `
    -SkipKlineUpdate $SkipKlineUpdate.IsPresent `
    -Now (Get-Date) `
    -MinKlineBarsPerSymbol $MinKlineBarsPerSymbol

if ($null -ne $FormalCapturePlan) {
    $DurationSeconds = [int]$FormalCapturePlan.duration_seconds
}

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
$HistoricalDbUpdateJson = Join-Path $OutDir "simnow_historical_db_update_$Date.json"
$ThresholdsJson = Join-Path $ScriptPath "simnow_risk_thresholds.json"
$LedgerPath = Join-Path $ScriptPath "simnow_observation_ledger.jsonl"

if ($CaptureTimeoutSeconds -le 0) {
    $CaptureTimeoutSeconds = $DurationSeconds + 180
}

$ShouldUpdateHistoricalDb = $UpdateHistoricalDb.IsPresent -or (
    $LiveCapture.IsPresent -and
    -not $SkipKlineUpdate.IsPresent -and
    -not $SkipHistoricalDbUpdate.IsPresent
)

Assert-KlineCoverageWindow `
    -LiveCapture $LiveCapture.IsPresent `
    -SkipKlineUpdate $SkipKlineUpdate.IsPresent `
    -DurationSeconds $DurationSeconds `
    -MinKlineBarsPerSymbol $MinKlineBarsPerSymbol

Assert-FormalObservationWindow `
    -LiveCapture $LiveCapture.IsPresent `
    -SkipKlineUpdate $SkipKlineUpdate.IsPresent `
    -Now (Get-Date) `
    -ContractMap $ContractMap

Write-Host "Repository: $RepoRoot"
Write-Host "Diagnostics: $ScriptPath"
Write-Host "Date: $Date"
if ($null -ne $FormalCapturePlan) {
    Write-Host "Formal window: $($FormalCapturePlan.window_name) ($($FormalCapturePlan.trigger_label) -> $($FormalCapturePlan.window_end)); auto duration: $($FormalCapturePlan.duration_seconds) seconds"
}

$PyCompileCache = Join-Path $env:TEMP "vnpy_py_compile_cache"
New-Item -ItemType Directory -Path $PyCompileCache -Force | Out-Null
try {
    $env:PYTHONPYCACHEPREFIX = $PyCompileCache
    Invoke-Checked "Compile SimNow capture script" @(
        "python",
        "-m",
        "py_compile",
        ".\examples\czsc_strategy\diagnostics\simnow_daily_capture.py",
        ".\examples\czsc_strategy\diagnostics\simnow_replay_readiness.py",
        ".\examples\czsc_strategy\diagnostics\simnow_backfill_pending_replays.py",
        ".\examples\czsc_strategy\diagnostics\simnow_tick_bars.py",
        ".\examples\czsc_strategy\diagnostics\simnow_strategy_surface.py",
        ".\examples\czsc_strategy\diagnostics\simnow_observation_window.py",
        ".\examples\czsc_strategy\diagnostics\simnow_run_summary.py",
        ".\examples\czsc_strategy\diagnostics\simnow_daily_brief.py",
        ".\examples\czsc_strategy\diagnostics\simnow_ledger_summary.py"
    )
} finally {
    Remove-Item -Path $PyCompileCache -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item Env:\PYTHONPYCACHEPREFIX -ErrorAction SilentlyContinue
}

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
    ".\examples\czsc_strategy\tests\unit\test_simnow_strategy_surface.py",
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
    if (-not $PostProcessOnly) {
        Write-Step "Run historical DB auto update"
        # skipped path is still supported below when the formal update is disabled.
        $HistoricalDbUpdateStartedAt = (Get-Date).ToString("o")
        $HistoricalDbUpdateTables = Get-HistoricalDbUpdateTables -ContractMap $ContractMap
        if ($ShouldUpdateHistoricalDb) {
            try {
                $HistoricalDbUpdateCommandForLog = $HistoricalDbUpdateCommand
                if ($HistoricalDbUpdateCommand -eq $DefaultHistoricalDbUpdateCommand) {
                    $HistoricalDbUpdateInlineTableArgs = ""
                    if ($HistoricalDbUpdateTables.Count -gt 0) {
                        $HistoricalDbUpdateInlineTableArgs = " -Table @(" + (($HistoricalDbUpdateTables | ForEach-Object { "'$_'" }) -join ", ") + ")"
                    }
                    $HistoricalDbUpdateArguments = @(
                        "-NoProfile",
                        "-ExecutionPolicy", "Bypass",
                        "-Command", "& `"$HistoricalDbUpdateScriptPath`"$HistoricalDbUpdateInlineTableArgs"
                    )
                    $HistoricalDbUpdateCommandForLog = "powershell.exe -NoProfile -ExecutionPolicy Bypass -Command `"& `"$HistoricalDbUpdateScriptPath`"$HistoricalDbUpdateInlineTableArgs`""
                    if ($HistoricalDbUpdateTables.Count -gt 0) {
                        $HistoricalDbUpdateCommandForLog += " # tables: " + ($HistoricalDbUpdateTables -join ", ")
                    }
                    Invoke-CheckedProcess `
                        -Label "Run historical DB auto update command" `
                        -FilePath "powershell.exe" `
                        -Arguments $HistoricalDbUpdateArguments `
                        -TimeoutSeconds $HistoricalDbUpdateTimeoutSeconds
                } else {
                    Invoke-CheckedProcess `
                        -Label "Run historical DB auto update command" `
                        -FilePath "powershell.exe" `
                        -Arguments @(
                            "-NoProfile",
                            "-ExecutionPolicy", "Bypass",
                            "-Command", "$HistoricalDbUpdateCommand"
                        ) `
                        -TimeoutSeconds $HistoricalDbUpdateTimeoutSeconds
                }
                $HistoricalDbUpdatePayload = [ordered]@{
                    status = "passed"
                    exit_code = 0
                    command = $HistoricalDbUpdateCommandForLog
                    started_at = $HistoricalDbUpdateStartedAt
                    ended_at = (Get-Date).ToString("o")
                }
                $HistoricalDbUpdatePayload | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $HistoricalDbUpdateJson -Encoding UTF8
            } catch {
                $HistoricalDbUpdatePayload = [ordered]@{
                    status = "failed"
                    exit_code = 1
                    command = $HistoricalDbUpdateCommandForLog
                    started_at = $HistoricalDbUpdateStartedAt
                    ended_at = (Get-Date).ToString("o")
                    reason = "$_"
                }
                $HistoricalDbUpdatePayload | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $HistoricalDbUpdateJson -Encoding UTF8
                throw "Historical DB auto update failed: $_"
            }
        } else {
            # Formal skip path still writes a status=skipped artifact for downstream summaries.
            $HistoricalDbUpdateReason = "Historical DB auto update skipped"
            if ($SkipKlineUpdate.IsPresent) {
                $HistoricalDbUpdateReason = "Smoke capture skips the formal historical DB auto update"
            } elseif ($SkipHistoricalDbUpdate.IsPresent) {
                $HistoricalDbUpdateReason = "SkipHistoricalDbUpdate switch set"
            }
            $HistoricalDbUpdatePayload = [ordered]@{
                status = "skipped"
                exit_code = $null
                command = $HistoricalDbUpdateCommand
                started_at = $HistoricalDbUpdateStartedAt
                ended_at = (Get-Date).ToString("o")
                reason = $HistoricalDbUpdateReason
            }
            $HistoricalDbUpdatePayload | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $HistoricalDbUpdateJson -Encoding UTF8
        }

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

        Write-Step "Build live strategy event surface"
        $StrategySurfaceArgs = @(
            ".\examples\czsc_strategy\diagnostics\simnow_strategy_surface.py",
            "--capture-json", "$CaptureJson",
            "--date", "$Date"
        )
        if (-not [string]::IsNullOrWhiteSpace($KlineDbPath)) {
            $StrategySurfaceArgs += @("--db-path", "$KlineDbPath")
        }
        & python @StrategySurfaceArgs
        if ($LASTEXITCODE -ne 0) {
            throw "Strategy surface enrichment failed with exit code $LASTEXITCODE"
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
    } else {
        Write-Step "Resume live post-processing from existing artifacts"
        Assert-LiveArtifactExists -Path $CaptureJson -Label "capture JSON"
        if (-not $SkipKlineUpdate) {
            Assert-LiveArtifactExists -Path $KlineSummaryJson -Label "kline summary JSON"
        }
        if (-not $SkipReplay) {
            Assert-LiveArtifactExists -Path $ReplayJson -Label "replay JSON"
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
    $MonitorExitCode = $LASTEXITCODE
    if (($MonitorExitCode -ne 0) -and ($MonitorExitCode -ne 2)) {
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
        "--ledger-summary", $LedgerSummaryJson,
        "--historical-db-update", $HistoricalDbUpdateJson
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
    Write-Host "Historical DB update JSON: $HistoricalDbUpdateJson"
    if ($MonitorExitCode -eq 2) {
        exit 30
    }
    exit 0
}

Write-Step "No live action requested. Use -LiveCapture to run read-only SimNow capture."
