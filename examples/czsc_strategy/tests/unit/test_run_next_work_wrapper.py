from pathlib import Path
import subprocess
import tempfile


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
RUN_NEXT_WORK = DIAG / "run_next_work.ps1"


def _extract_function(script_text: str, name: str) -> str:
    marker = f"function {name} {{"
    start = script_text.index(marker)
    lines = script_text[start:].splitlines()
    depth = 0
    collected: list[str] = []

    for line in lines:
        collected.append(line)
        depth += line.count("{")
        depth -= line.count("}")
        if depth == 0:
            break

    return "\n".join(collected)


def _run_powershell_script(script_text: str) -> subprocess.CompletedProcess[bytes]:
    with tempfile.NamedTemporaryFile("w", suffix=".ps1", encoding="utf-8", delete=False) as handle:
        handle.write(script_text)
        path = handle.name
    return subprocess.run(
        ["powershell", "-NoProfile", "-File", path],
        capture_output=True,
        text=False,
        timeout=15,
        check=False,
    )


def _decode_output(data: bytes) -> str:
    for encoding in ("utf-8", "gbk"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def test_invoke_checked_process_treats_completed_child_as_success():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    write_step = _extract_function(script_text, "Write-Step")
    invoke_checked_process = _extract_function(script_text, "Invoke-CheckedProcess")
    command = "\n".join([
        "$ErrorActionPreference = 'Stop'",
        write_step,
        invoke_checked_process,
        "Invoke-CheckedProcess -Label 'quick child' -FilePath 'python' -Arguments @('-c', 'print(123)') -TimeoutSeconds 5",
        "Write-Host 'wrapper-finished'",
    ])

    completed = _run_powershell_script(command)
    output = _decode_output(completed.stdout + completed.stderr)

    assert completed.returncode == 0, output
    assert "wrapper-finished" in output


def test_invoke_checked_process_preserves_nonzero_exit_code():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    write_step = _extract_function(script_text, "Write-Step")
    invoke_checked_process = _extract_function(script_text, "Invoke-CheckedProcess")
    command = "\n".join([
        "$ErrorActionPreference = 'Stop'",
        write_step,
        invoke_checked_process,
        "Invoke-CheckedProcess -Label 'failing child' -FilePath 'python' -Arguments @('-c', 'import sys; sys.exit(7)') -TimeoutSeconds 5",
    ])

    completed = _run_powershell_script(command)
    output = _decode_output(completed.stdout + completed.stderr)

    assert completed.returncode != 0
    assert "exit code 7" in output


def test_kline_window_validation_rejects_short_live_capture():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert_kline_window = _extract_function(script_text, "Assert-KlineCoverageWindow")
    command = "\n".join([
        "$ErrorActionPreference = 'Stop'",
        assert_kline_window,
        "Assert-KlineCoverageWindow -LiveCapture $true -SkipKlineUpdate $false -DurationSeconds 300 -MinKlineBarsPerSymbol 30",
    ])

    completed = _run_powershell_script(command)
    output = _decode_output(completed.stdout + completed.stderr)

    assert completed.returncode != 0
    assert "DurationSeconds" in output
    assert "MinKlineBarsPerSymbol" in output


def test_kline_window_validation_allows_smoke_when_kline_update_skipped():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert_kline_window = _extract_function(script_text, "Assert-KlineCoverageWindow")
    command = "\n".join([
        "$ErrorActionPreference = 'Stop'",
        assert_kline_window,
        "Assert-KlineCoverageWindow -LiveCapture $true -SkipKlineUpdate $true -DurationSeconds 300 -MinKlineBarsPerSymbol 30",
        "Write-Host 'validation-finished'",
    ])

    completed = _run_powershell_script(command)
    output = _decode_output(completed.stdout + completed.stderr)

    assert completed.returncode == 0, output
    assert "validation-finished" in output


def test_formal_window_validation_rejects_night_session_when_ap888_enabled():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert_formal_window = _extract_function(script_text, "Assert-FormalObservationWindow")
    command = "\n".join([
        "$ErrorActionPreference = 'Stop'",
        assert_formal_window,
        "$contractMap = @{ AP888 = @{ enabled = $true; exchange = 'CZCE' } }",
        "$now = [datetimeoffset]::Parse('2026-07-10T21:48:02+08:00')",
        "Assert-FormalObservationWindow -LiveCapture $true -SkipKlineUpdate $false -Now $now -ContractMap $contractMap",
    ])

    completed = _run_powershell_script(command)
    output = _decode_output(completed.stdout + completed.stderr)

    assert completed.returncode != 0
    assert "AP888" in output
    assert "day-session" in output


def test_formal_window_validation_allows_day_session_when_ap888_enabled():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert_formal_window = _extract_function(script_text, "Assert-FormalObservationWindow")
    command = "\n".join([
        "$ErrorActionPreference = 'Stop'",
        assert_formal_window,
        "$contractMap = @{ AP888 = @{ enabled = $true; exchange = 'CZCE' } }",
        "$now = [datetimeoffset]::Parse('2026-07-10T10:15:00+08:00')",
        "Assert-FormalObservationWindow -LiveCapture $true -SkipKlineUpdate $false -Now $now -ContractMap $contractMap",
        "Write-Host 'window-finished'",
    ])

    completed = _run_powershell_script(command)
    output = _decode_output(completed.stdout + completed.stderr)

    assert completed.returncode == 0, output
    assert "window-finished" in output


def test_formal_window_validation_allows_smoke_at_night():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert_formal_window = _extract_function(script_text, "Assert-FormalObservationWindow")
    command = "\n".join([
        "$ErrorActionPreference = 'Stop'",
        assert_formal_window,
        "$contractMap = @{ AP888 = @{ enabled = $true; exchange = 'CZCE' } }",
        "$now = [datetimeoffset]::Parse('2026-07-10T21:48:02+08:00')",
        "Assert-FormalObservationWindow -LiveCapture $true -SkipKlineUpdate $true -Now $now -ContractMap $contractMap",
        "Write-Host 'smoke-window-finished'",
    ])

    completed = _run_powershell_script(command)
    output = _decode_output(completed.stdout + completed.stderr)

    assert completed.returncode == 0, output
    assert "smoke-window-finished" in output


def test_formal_window_validation_allows_night_when_ap888_disabled():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert_formal_window = _extract_function(script_text, "Assert-FormalObservationWindow")
    command = "\n".join([
        "$ErrorActionPreference = 'Stop'",
        assert_formal_window,
        "$contractMap = @{ AP888 = @{ enabled = $false; exchange = 'CZCE' }; SC888 = @{ enabled = $true; exchange = 'INE' } }",
        "$now = [datetimeoffset]::Parse('2026-07-10T21:48:02+08:00')",
        "Assert-FormalObservationWindow -LiveCapture $true -SkipKlineUpdate $false -Now $now -ContractMap $contractMap",
        "Write-Host 'night-window-finished'",
    ])

    completed = _run_powershell_script(command)
    output = _decode_output(completed.stdout + completed.stderr)

    assert completed.returncode == 0, output
    assert "night-window-finished" in output


def test_live_capture_runs_daily_monitor_once_for_formal_ledger_write():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")

    assert "Create daily monitor record without appending ledger" not in script_text
    assert "Daily monitor dry-run failed" not in script_text
    assert script_text.count("Upsert daily record into formal ledger") == 1


def test_run_summary_json_variable_defined():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "$RunSummaryJson = Join-Path $OutDir" in script_text


def test_run_summary_script_called_after_promotion():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    promo_index = script_text.index("Generate promotion decision")
    summary_index = script_text.index("Generate run summary")
    assert summary_index > promo_index
    assert "simnow_run_summary.py" in script_text


def test_run_summary_output_hosted():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "Run summary JSON:" in script_text


def test_daily_brief_md_variable_defined():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "$DailyBriefMd = Join-Path $OutDir" in script_text


def test_daily_brief_step_after_run_summary():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    summary_index = script_text.index("Generate run summary")
    brief_index = script_text.index("Generate daily brief")
    assert brief_index > summary_index


def test_daily_brief_script_called_with_run_summary_and_output():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "simnow_daily_brief.py" in script_text
    step_index = script_text.index("Generate daily brief")
    brief_block = script_text[step_index:step_index + 600]
    assert "simnow_daily_brief.py" in brief_block
    assert "--run-summary" in brief_block
    assert "$RunSummaryJson" in brief_block
    assert "--out-md" in brief_block
    assert "$DailyBriefMd" in brief_block


def test_daily_brief_output_hosted():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "Daily brief MD:" in script_text


def test_preflight_pytest_includes_daily_brief_tests():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "test_simnow_daily_brief.py" in script_text


def test_preflight_py_compile_includes_daily_brief_script():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "simnow_daily_brief.py" in script_text


def test_ledger_summary_json_variable_defined():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "$LedgerSummaryJson = Join-Path $OutDir \"simnow_ledger_summary.json\"" in script_text


def test_preflight_py_compile_includes_ledger_summary_script():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "simnow_ledger_summary.py" in script_text


def test_preflight_py_compile_includes_observation_window_script():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "simnow_observation_window.py" in script_text


def test_preflight_py_compile_includes_strategy_surface_script():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "simnow_strategy_surface.py" in script_text


def test_preflight_pytest_includes_ledger_summary_tests():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "test_simnow_ledger_summary.py" in script_text


def test_preflight_pytest_includes_strategy_surface_tests():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "test_simnow_strategy_surface.py" in script_text


def test_ledger_summary_step_after_monitor_and_before_promotion():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    monitor_index = script_text.index("Upsert daily record into formal ledger")
    ledger_index = script_text.index("Generate ledger summary")
    promo_index = script_text.index("Generate promotion decision")
    assert ledger_index > monitor_index
    assert promo_index > ledger_index


def test_ledger_summary_script_called_with_ledger_and_output():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "simnow_ledger_summary.py" in script_text
    step_index = script_text.index("Generate ledger summary")
    ledger_block = script_text[step_index:step_index + 600]
    assert "simnow_ledger_summary.py" in ledger_block
    assert "--ledger" in ledger_block
    assert "$LedgerPath" in ledger_block
    assert "--out-json" in ledger_block
    assert "$LedgerSummaryJson" in ledger_block


def test_ledger_summary_output_hosted():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "Ledger summary JSON:" in script_text


def test_strategy_surface_step_after_capture_before_monitor():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    capture_index = script_text.index("Run read-only SimNow capture")
    surface_index = script_text.index("Build live strategy event surface")
    monitor_index = script_text.index("Upsert daily record into formal ledger")
    assert surface_index > capture_index
    assert monitor_index > surface_index


def test_strategy_surface_script_called_with_capture_and_date():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    step_index = script_text.index("Build live strategy event surface")
    block = script_text[step_index:step_index + 700]
    assert "simnow_strategy_surface.py" in block
    assert "--capture-json" in block
    assert "$CaptureJson" in block
    assert "--date" in block
    assert "$Date" in block


def test_formal_window_validation_called_before_live_capture():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    formal_window_index = script_text.index("Assert-FormalObservationWindow")
    capture_index = script_text.index("Run read-only SimNow capture")
    assert formal_window_index < capture_index


def test_run_summary_step_after_ledger_summary():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    ledger_index = script_text.index("Generate ledger summary")
    summary_index = script_text.index("Generate run summary")
    assert summary_index > ledger_index


def test_run_summary_script_receives_ledger_summary_argument():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "simnow_run_summary.py" in script_text
    step_index = script_text.index("Generate run summary")
    summary_block = script_text[step_index:step_index + 700]
    assert "--ledger-summary" in summary_block
    assert "$LedgerSummaryJson" in summary_block


def test_halt_monitor_does_not_stop_summary_generation():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    monitor_index = script_text.index("Upsert daily record into formal ledger")
    ledger_index = script_text.index("Generate ledger summary")
    summary_index = script_text.index("Generate run summary")
    brief_index = script_text.index("Generate daily brief")
    halt_guard_index = script_text.index("if ($MonitorExitCode -eq 2)")

    assert halt_guard_index > brief_index
    assert ledger_index > monitor_index
    assert summary_index > ledger_index
    assert brief_index > summary_index


def test_historical_db_update_parameters_defined():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "[switch]$UpdateHistoricalDb" in script_text
    assert "[string]$HistoricalDbUpdateCommand" in script_text
    assert "[int]$HistoricalDbUpdateTimeoutSeconds" in script_text


def test_historical_db_update_json_variable_defined():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "$HistoricalDbUpdateJson = Join-Path $OutDir" in script_text


def test_historical_db_update_runs_before_capture_when_enabled():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    update_index = script_text.index("Run historical DB auto update")
    capture_index = script_text.index("Run read-only SimNow capture")
    assert update_index < capture_index


def test_historical_db_update_can_be_explicitly_skipped():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    update_index = script_text.index("Run historical DB auto update")
    update_block = script_text[update_index:update_index + 1800]
    assert "[switch]$SkipHistoricalDbUpdate" in script_text
    assert "$ShouldUpdateHistoricalDb" in update_block
    assert "if ($ShouldUpdateHistoricalDb)" in update_block
    assert "$HistoricalDbUpdateJson" in update_block
    assert "skipped" in update_block


def test_formal_live_capture_defaults_to_historical_db_update():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")

    assert "$ShouldUpdateHistoricalDb = $UpdateHistoricalDb.IsPresent -or (" in script_text
    assert "$LiveCapture.IsPresent" in script_text
    assert "-not $SkipKlineUpdate.IsPresent" in script_text
    assert "-not $SkipHistoricalDbUpdate.IsPresent" in script_text


def test_run_summary_receives_historical_db_update_argument():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    step_index = script_text.index("Generate run summary")
    summary_block = script_text[step_index:step_index + 900]
    assert "--historical-db-update" in summary_block
    assert "$HistoricalDbUpdateJson" in summary_block
