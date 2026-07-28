param(
    [switch]$Preflight,
    [switch]$LiveCapture,
    [switch]$PostProcessOnly,
    [switch]$RefreshReplay,
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
    [string]$KlineDbPath = "",
    [string]$PythonExe = ""
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

function Test-PythonImports {
    param([string]$Candidate, [string]$Modules)

    # Probe a candidate interpreter without tripping the script-wide
    # $ErrorActionPreference="Stop" (native stderr becomes NativeCommandError
    # in Windows PowerShell 5.1 when EAP=Stop).
    if (-not (Get-Command $Candidate -ErrorAction SilentlyContinue)) { return $false }
    $saved = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    try {
        & $Candidate -c "import $Modules" *>$null
        return ($LASTEXITCODE -eq 0)
    } finally {
        $ErrorActionPreference = $saved
    }
}

function Resolve-PythonExe {
    param([string]$Explicit)

    # The workflow needs a Python with the project deps (pytest, pandas, czsc
    # for offline steps; vnpy_ctp for live capture). Bare "python" can resolve
    # to an interpreter without these deps (e.g. sandboxed runtimes that have
    # pytest but not czsc), so probe candidates explicitly. Override with
    # -PythonExe or the SIMNOW_PYTHON env var.
    $required = @()
    if ($Explicit) { $required += $Explicit }
    if ($env:SIMNOW_PYTHON) { $required += $env:SIMNOW_PYTHON }
    foreach ($candidate in $required) {
        if (Test-PythonImports -Candidate $candidate -Modules "pytest, pandas, czsc") { return $candidate }
        throw "specified Python interpreter '$candidate' is not runnable or cannot import the project deps (pytest, pandas, czsc); install the project deps or fix -PythonExe/SIMNOW_PYTHON"
    }
    foreach ($candidate in @("python", "C:\Python314\python.exe")) {
        if (Test-PythonImports -Candidate $candidate -Modules "pytest, pandas, czsc") { return $candidate }
    }
    throw "no usable Python interpreter found (needs pytest, pandas, czsc); pass -PythonExe or set SIMNOW_PYTHON"
}

$Py = Resolve-PythonExe -Explicit $PythonExe
Write-Step "Using Python interpreter: $Py"
if ($LiveCapture) {
    if (-not (Test-PythonImports -Candidate $Py -Modules "vnpy_ctp")) {
        throw "resolved Python '$Py' cannot import vnpy_ctp; live SimNow capture requires the CTP gateway package - pass -PythonExe or set SIMNOW_PYTHON"
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

function Assert-NoPendingRiskHaltDecision {
    param([string]$OutDir)

    $DecisionFiles = Get-ChildItem -LiteralPath $OutDir -Filter "simnow_risk_halt_decision_*.json" -File -ErrorAction SilentlyContinue |
        Sort-Object Name
    foreach ($DecisionFile in $DecisionFiles) {
        $Decision = Get-Content -LiteralPath $DecisionFile.FullName -Raw | ConvertFrom-Json
        $DecisionStatus = [string]$Decision.decision_status
        $NextAllowed = $false
        if ($Decision.PSObject.Properties.Name -contains "next_formal_observation_allowed") {
            $NextAllowed = [bool]$Decision.next_formal_observation_allowed
        }
        if ($DecisionStatus -ne "decided" -or -not $NextAllowed) {
            throw "pending risk halt decision blocks live capture: $($DecisionFile.FullName). Fill and validate the decision record before starting another live observation."
        }

        $Errors = [System.Collections.Generic.List[string]]::new()
        $AllowedDecisions = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
        if ($Decision.PSObject.Properties.Name -contains "allowed_decisions") {
            foreach ($Allowed in @($Decision.allowed_decisions)) {
                if (-not [string]::IsNullOrWhiteSpace([string]$Allowed)) {
                    [void]$AllowedDecisions.Add([string]$Allowed)
                }
            }
        }
        if ($AllowedDecisions.Count -eq 0) {
            foreach ($Allowed in @(
                "keep_halted",
                "adjust_thresholds_with_documented_rationale",
                "retire_candidate",
                "reset_observation_window_after_strategy_change"
            )) {
                [void]$AllowedDecisions.Add($Allowed)
            }
        }

        $SelectedDecision = [string]$Decision.selected_decision
        if (-not $AllowedDecisions.Contains($SelectedDecision)) {
            [void]$Errors.Add("selected_decision_not_allowed")
        }
        if ([string]::IsNullOrWhiteSpace([string]$Decision.operator_name)) {
            [void]$Errors.Add("operator_name_required")
        }
        if ([string]::IsNullOrWhiteSpace([string]$Decision.rationale)) {
            [void]$Errors.Add("rationale_required")
        }
        if (-not ($Decision.PSObject.Properties.Name -contains "requires_observation_window_reset") -or $null -eq $Decision.requires_observation_window_reset) {
            [void]$Errors.Add("requires_observation_window_reset_required")
        }
        if ($Errors.Count -gt 0) {
            throw "invalid risk halt decision blocks live capture: $($DecisionFile.FullName); errors=$([string]::Join(',', $Errors))"
        }
    }
}

function Invoke-ReplaySnapshotRefresh {
    param(
        [string]$Date,
        [string]$ReplayReadinessJson,
        [string]$ReplayJson,
        [int]$ReplayTimeoutSeconds
    )

    Write-Step "Check replay DB readiness"
    $ReplayReadinessOutput = & $Py ".\examples\czsc_strategy\diagnostics\simnow_replay_readiness.py" --date $Date
    $ReplayReadinessExitCode = $LASTEXITCODE
    $ReplayReadinessOutput | Set-Content -LiteralPath $ReplayReadinessJson -Encoding UTF8
    $ReplayReady = $ReplayReadinessExitCode -eq 0
    if ($ReplayReady) {
        Invoke-CheckedProcess `
            -Label "Export same-day replay snapshot" `
            -FilePath $Py `
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
        [int]$MinKlineBarsPerSymbol,
        [object]$ContractMap = $null
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
    $EffectiveWindowEnd = $WindowEnd
    $SessionKey = "night"
    if ($MatchedSpec.window_name -like "day_*") {
        $SessionKey = "day"
    }

    if ($null -ne $ContractMap) {
        $Entries = @()
        if ($ContractMap -is [System.Collections.IDictionary]) {
            $Entries = $ContractMap.GetEnumerator()
        } else {
            $Entries = $ContractMap.PSObject.Properties
        }

        $EffectiveCutoffRows = [System.Collections.Generic.List[object]]::new()
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

            $CaptureEndMap = $null
            if ($Row -is [System.Collections.IDictionary]) {
                if ($Row.Contains("formal_session_capture_end")) {
                    $CaptureEndMap = $Row["formal_session_capture_end"]
                }
            } elseif ($Row.PSObject.Properties.Name -contains "formal_session_capture_end") {
                $CaptureEndMap = $Row.formal_session_capture_end
            }

            if ($null -eq $CaptureEndMap) {
                continue
            }

            $CutoffText = $null
            if ($CaptureEndMap -is [System.Collections.IDictionary]) {
                if ($CaptureEndMap.Contains($MatchedSpec.window_name)) {
                    $CutoffText = $CaptureEndMap[$MatchedSpec.window_name]
                } elseif ($CaptureEndMap.Contains($SessionKey)) {
                    $CutoffText = $CaptureEndMap[$SessionKey]
                }
            } else {
                if ($CaptureEndMap.PSObject.Properties.Name -contains $MatchedSpec.window_name) {
                    $CutoffText = $CaptureEndMap.$($MatchedSpec.window_name)
                } elseif ($CaptureEndMap.PSObject.Properties.Name -contains $SessionKey) {
                    $CutoffText = $CaptureEndMap.$($SessionKey)
                }
            }

            if ([string]::IsNullOrWhiteSpace([string]$CutoffText)) {
                continue
            }

            $CutoffTime = [timespan]::Parse([string]$CutoffText)
            $CutoffDateTime = $LocalNow.Date + $CutoffTime
            if ($SessionKey -eq "night" -and $CutoffTime -lt $MatchedSpec.trigger_start) {
                $CutoffDateTime = $CutoffDateTime.AddDays(1)
            }
            [void]$EffectiveCutoffRows.Add([pscustomobject]@{
                symbol = $Symbol
                cutoff_text = [string]$CutoffText
                cutoff = $CutoffDateTime
            })
        }

        if ($EffectiveCutoffRows.Count -gt 0) {
            $EarliestCutoff = $EffectiveCutoffRows | Sort-Object cutoff, symbol | Select-Object -First 1
            if ($EarliestCutoff.cutoff -lt $EffectiveWindowEnd) {
                $EffectiveWindowEnd = $EarliestCutoff.cutoff
            }
        }
    }

    $RemainingSeconds = [int][math]::Floor(($EffectiveWindowEnd - $LocalNow.DateTime).TotalSeconds)

    if ($RemainingSeconds -lt $RequiredSeconds) {
        if ($EffectiveWindowEnd -lt $WindowEnd -and $null -ne $EarliestCutoff) {
            throw "Formal observation window rejected: enabled symbol $($EarliestCutoff.symbol) uses an earlier $SessionKey capture cutoff ($($EarliestCutoff.cutoff_text)), leaving only $RemainingSeconds seconds before the effective window close. MinKlineBarsPerSymbol ($MinKlineBarsPerSymbol) requires at least $RequiredSeconds seconds."
        }
        throw "Formal observation window rejected: remaining window seconds ($RemainingSeconds) are shorter than MinKlineBarsPerSymbol ($MinKlineBarsPerSymbol); require at least $RequiredSeconds seconds before the window close."
    }

    return [ordered]@{
        window_name = [string]$MatchedSpec.window_name
        trigger_label = [string]$MatchedSpec.trigger_label
        window_start = ([datetime]$WindowStart).ToString("yyyy-MM-ddTHH:mm:sszzz")
        window_end = ([datetime]$EffectiveWindowEnd).ToString("yyyy-MM-ddTHH:mm:sszzz")
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
    -LiveCapture ($LiveCapture.IsPresent -and -not $PostProcessOnly.IsPresent) `
    -SkipKlineUpdate $SkipKlineUpdate.IsPresent `
    -Now (Get-Date) `
    -MinKlineBarsPerSymbol $MinKlineBarsPerSymbol `
    -ContractMap $ContractMap

if ($null -ne $FormalCapturePlan) {
    $DurationSeconds = [int]$FormalCapturePlan.duration_seconds
}

if ([string]::IsNullOrWhiteSpace($Date)) {
    $Date = Get-Date -Format "yyyy-MM-dd"
}

if ($RefreshReplay.IsPresent -and $SkipReplay.IsPresent) {
    throw "RefreshReplay cannot be combined with SkipReplay."
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
$RiskHaltReviewJson = Join-Path $OutDir "simnow_risk_halt_review_$Date.json"
$RiskHaltReviewMd = Join-Path $OutDir "simnow_risk_halt_review_$Date.md"
$RiskHaltDecisionJson = Join-Path $OutDir "simnow_risk_halt_decision_$Date.json"
$RiskHaltDecisionMd = Join-Path $OutDir "simnow_risk_halt_decision_$Date.md"
$SessionRecordJson = $null
$SessionReportMd = $null
$SessionRunSummaryJson = $null
$SessionDailyBriefMd = $null
$LedgerSummaryJson = Join-Path $OutDir "simnow_ledger_summary.json"
$HistoricalDbUpdateJson = Join-Path $OutDir "simnow_historical_db_update_$Date.json"
$ThresholdsJson = Join-Path $ScriptPath "simnow_risk_thresholds.json"
$LedgerPath = Join-Path $ScriptPath "simnow_observation_ledger.jsonl"

if ($LiveCapture.IsPresent -and -not $PostProcessOnly.IsPresent) {
    Assert-NoPendingRiskHaltDecision -OutDir $OutDir
}

if ($null -ne $FormalCapturePlan) {
    $SessionRecordJson = Join-Path $OutDir "simnow_record_${Date}_$($FormalCapturePlan.window_name).json"
    $SessionReportMd = Join-Path $OutDir "simnow_report_${Date}_$($FormalCapturePlan.window_name).md"
    $SessionRunSummaryJson = Join-Path $OutDir "simnow_run_summary_${Date}_$($FormalCapturePlan.window_name).json"
    $SessionDailyBriefMd = Join-Path $OutDir "simnow_daily_brief_${Date}_$($FormalCapturePlan.window_name).md"
}

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
    -LiveCapture ($LiveCapture.IsPresent -and -not $PostProcessOnly.IsPresent) `
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
        $Py,
        "-m",
        "py_compile",
        ".\examples\czsc_strategy\diagnostics\simnow_daily_capture.py",
        ".\examples\czsc_strategy\diagnostics\simnow_replay_readiness.py",
        ".\examples\czsc_strategy\diagnostics\export_simnow_replay_snapshot.py",
        ".\examples\czsc_strategy\diagnostics\simnow_backfill_pending_replays.py",
        ".\examples\czsc_strategy\diagnostics\simnow_tick_bars.py",
        ".\examples\czsc_strategy\diagnostics\simnow_strategy_surface.py",
        ".\examples\czsc_strategy\diagnostics\simnow_observation_window.py",
        ".\examples\czsc_strategy\diagnostics\simnow_20d_aggregate.py",
        ".\examples\czsc_strategy\diagnostics\simnow_artifact_loader.py",
        ".\examples\czsc_strategy\diagnostics\simnow_automation_policy.py",
        ".\examples\czsc_strategy\diagnostics\simnow_halt_metadata.py",
        ".\examples\czsc_strategy\diagnostics\simnow_reason_governance.py",
        ".\examples\czsc_strategy\diagnostics\simnow_structured_access.py",
        ".\examples\czsc_strategy\diagnostics\simnow_ledger_summary_schema.py",
        ".\examples\czsc_strategy\diagnostics\simnow_daily_brief_default_summary.py",
        ".\examples\czsc_strategy\diagnostics\simnow_daily_brief_schema.py",
        ".\examples\czsc_strategy\diagnostics\simnow_daily_brief_sections.py",
        ".\examples\czsc_strategy\diagnostics\simnow_contract_map_meta.py",
        ".\examples\czsc_strategy\diagnostics\simnow_run_summary.py",
        ".\examples\czsc_strategy\diagnostics\simnow_daily_brief.py",
        ".\examples\czsc_strategy\diagnostics\simnow_risk_halt_review.py",
        ".\examples\czsc_strategy\diagnostics\simnow_risk_halt_decision.py",
        ".\examples\czsc_strategy\diagnostics\simnow_ledger_summary.py",
        ".\examples\czsc_strategy\diagnostics\simnow_summary_consistency.py"
    )
} finally {
    Remove-Item -Path $PyCompileCache -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item Env:\PYTHONPYCACHEPREFIX -ErrorAction SilentlyContinue
}

Invoke-Checked "Run SimNow workflow unit tests" @(
    $Py,
    "-m",
    "pytest",
    ".\examples\czsc_strategy\tests\unit\test_simnow_connection_probe.py",
    ".\examples\czsc_strategy\tests\unit\test_simnow_daily_capture.py",
    ".\examples\czsc_strategy\tests\unit\test_simnow_daily_monitor.py",
    ".\examples\czsc_strategy\tests\unit\test_simnow_replay_readiness.py",
    ".\examples\czsc_strategy\tests\unit\test_export_simnow_replay_snapshot.py",
    ".\examples\czsc_strategy\tests\unit\test_simnow_backfill_pending_replays.py",
    ".\examples\czsc_strategy\tests\unit\test_simnow_tick_bars.py",
    ".\examples\czsc_strategy\tests\unit\test_simnow_strategy_surface.py",
    ".\examples\czsc_strategy\tests\unit\test_simnow_20d_aggregate.py",
    ".\examples\czsc_strategy\tests\unit\test_simnow_artifact_loader.py",
    ".\examples\czsc_strategy\tests\unit\test_simnow_automation_policy.py",
    ".\examples\czsc_strategy\tests\unit\test_simnow_helper_boundaries.py",
    ".\examples\czsc_strategy\tests\unit\test_simnow_structured_access.py",
    ".\examples\czsc_strategy\tests\unit\test_simnow_ledger_summary_schema.py",
    ".\examples\czsc_strategy\tests\unit\test_simnow_daily_brief_default_summary.py",
    ".\examples\czsc_strategy\tests\unit\test_simnow_daily_brief_schema.py",
    ".\examples\czsc_strategy\tests\unit\test_simnow_daily_brief_sections.py",
    ".\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py",
    ".\examples\czsc_strategy\tests\unit\test_simnow_docs.py",
    ".\examples\czsc_strategy\tests\unit\test_simnow_run_summary.py",
    ".\examples\czsc_strategy\tests\unit\test_simnow_daily_brief.py",
    ".\examples\czsc_strategy\tests\unit\test_simnow_risk_halt_review.py",
    ".\examples\czsc_strategy\tests\unit\test_simnow_risk_halt_decision.py",
    ".\examples\czsc_strategy\tests\unit\test_simnow_daily_brief_policy_sharing.py",
    ".\examples\czsc_strategy\tests\unit\test_simnow_ledger_summary.py",
    ".\examples\czsc_strategy\tests\unit\test_simnow_summary_consistency.py",
    "-q"
)

Invoke-Checked "Build pending replay backfill plan" @(
    $Py,
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
            -FilePath $Py `
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
            & $Py @KlineArgs
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
        & $Py @StrategySurfaceArgs
        if ($LASTEXITCODE -ne 0) {
            throw "Strategy surface enrichment failed with exit code $LASTEXITCODE"
        }

        if (-not $SkipReplay) {
            Invoke-ReplaySnapshotRefresh `
                -Date $Date `
                -ReplayReadinessJson $ReplayReadinessJson `
                -ReplayJson $ReplayJson `
                -ReplayTimeoutSeconds $ReplayTimeoutSeconds
        }
    } else {
        Write-Step "Resume live post-processing from existing artifacts"
        Assert-LiveArtifactExists -Path $CaptureJson -Label "capture JSON"
        if (-not $SkipKlineUpdate) {
            Assert-LiveArtifactExists -Path $KlineSummaryJson -Label "kline summary JSON"
        }
        if ($RefreshReplay.IsPresent -and -not $SkipReplay.IsPresent) {
            Invoke-ReplaySnapshotRefresh `
                -Date $Date `
                -ReplayReadinessJson $ReplayReadinessJson `
                -ReplayJson $ReplayJson `
                -ReplayTimeoutSeconds $ReplayTimeoutSeconds
        } elseif (-not $SkipReplay) {
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
    & $Py @AppendArgs
    $MonitorExitCode = $LASTEXITCODE
    if (($MonitorExitCode -ne 0) -and ($MonitorExitCode -ne 2)) {
        throw "Daily monitor append failed with exit code $LASTEXITCODE"
    }

    Write-Step "Generate ledger summary"
    & $Py ".\examples\czsc_strategy\diagnostics\simnow_ledger_summary.py" `
        --ledger $LedgerPath `
        --out-json $LedgerSummaryJson
    if ($LASTEXITCODE -ne 0) {
        throw "Ledger summary generation failed with exit code $LASTEXITCODE"
    }

    Write-Step "Generate promotion decision"
    & $Py ".\examples\czsc_strategy\diagnostics\simnow_promotion_decision.py" `
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
    & $Py @SummaryArgs
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
    & $Py @BriefArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Daily brief generation failed with exit code $LASTEXITCODE"
    }

    $RunSummaryPayload = Get-Content -LiteralPath $RunSummaryJson -Raw | ConvertFrom-Json
    $AutomationStatus = [string]$RunSummaryPayload.automation_status
    if ($AutomationStatus -eq "halt") {
        Write-Step "Generate risk halt review pack"
        $RiskHaltReviewArgs = @(
            ".\examples\czsc_strategy\diagnostics\simnow_risk_halt_review.py",
            "--date", $Date,
            "--run-summary", $RunSummaryJson,
            "--out-json", $RiskHaltReviewJson,
            "--out-md", $RiskHaltReviewMd
        )
        & $Py @RiskHaltReviewArgs
        if ($LASTEXITCODE -ne 0) {
            throw "Risk halt review generation failed with exit code $LASTEXITCODE"
        }

        Write-Step "Generate risk halt decision template"
        $RiskHaltDecisionArgs = @(
            ".\examples\czsc_strategy\diagnostics\simnow_risk_halt_decision.py",
            "--date", $Date,
            "--review-json", $RiskHaltReviewJson,
            "--out-json", $RiskHaltDecisionJson,
            "--out-md", $RiskHaltDecisionMd
        )
        & $Py @RiskHaltDecisionArgs
        if ($LASTEXITCODE -ne 0) {
            throw "Risk halt decision template generation failed with exit code $LASTEXITCODE"
        }
    } else {
        Write-Step "Skip risk halt review/decision generation (automation_status=$AutomationStatus; per ACCEPTANCE.md the decision gate applies to halt days only)"
    }

    Write-Step "Mirror session-scoped artifacts"
    if ($null -ne $SessionRecordJson) {
        Copy-Item -LiteralPath $RecordJson -Destination $SessionRecordJson -Force
    }
    if ($null -ne $SessionReportMd) {
        Copy-Item -LiteralPath $ReportMd -Destination $SessionReportMd -Force
    }
    if ($null -ne $SessionRunSummaryJson) {
        Copy-Item -LiteralPath $RunSummaryJson -Destination $SessionRunSummaryJson -Force
    }
    if ($null -ne $SessionDailyBriefMd) {
        Copy-Item -LiteralPath $DailyBriefMd -Destination $SessionDailyBriefMd -Force
    }

    Write-Step "Validate summary consistency"
    $ConsistencyArgs = @(
        ".\examples\czsc_strategy\diagnostics\simnow_summary_consistency.py",
        "--date", $Date,
        "--run-summary", $RunSummaryJson,
        "--record-json", $RecordJson,
        "--ledger-summary", $LedgerSummaryJson,
        "--daily-brief", $DailyBriefMd,
        "--report-md", $ReportMd
    )
    if ((-not $SkipKlineUpdate) -and (Test-Path -LiteralPath $KlineSummaryJson)) {
        $ConsistencyArgs += @("--kline-json", $KlineSummaryJson)
    }
    & $Py @ConsistencyArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Summary consistency validation failed with exit code $LASTEXITCODE"
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
    Write-Host "Risk halt review JSON: $RiskHaltReviewJson"
    Write-Host "Risk halt review MD: $RiskHaltReviewMd"
    Write-Host "Risk halt decision JSON: $RiskHaltDecisionJson"
    Write-Host "Risk halt decision MD: $RiskHaltDecisionMd"
    Write-Host "Ledger summary JSON: $LedgerSummaryJson"
    Write-Host "Historical DB update JSON: $HistoricalDbUpdateJson"
    if ($MonitorExitCode -eq 2) {
        exit 30
    }
    exit 0
}

Write-Step "No live action requested. Use -LiveCapture to run read-only SimNow capture."
