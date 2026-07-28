from pathlib import Path
import json
import shutil
import subprocess
import tempfile

import pytest


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
RUN_NEXT_WORK = DIAG / "run_next_work.ps1"


def test_run_powershell_script_skips_when_powershell_is_unavailable(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)

    with pytest.raises(pytest.skip.Exception):
        _run_powershell_script("Write-Host 'unreachable'")


def _powershell_executable() -> str:
    for name in ("powershell", "pwsh"):
        executable = shutil.which(name)
        if executable:
            return executable
    pytest.skip("PowerShell executable is not available in this test environment")


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
        [_powershell_executable(), "-NoProfile", "-File", path],
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


def test_assert_live_artifact_exists_accepts_existing_file():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    helper = _extract_function(script_text, "Assert-LiveArtifactExists")
    command = "\n".join([
        "$ErrorActionPreference = 'Stop'",
        helper,
        "$path = [System.IO.Path]::GetTempFileName()",
        "Assert-LiveArtifactExists -Path $path -Label 'capture'",
        "Write-Host 'artifact-check-finished'",
    ])

    completed = _run_powershell_script(command)
    output = _decode_output(completed.stdout + completed.stderr)

    assert completed.returncode == 0, output
    assert "artifact-check-finished" in output


def test_assert_live_artifact_exists_rejects_missing_file():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    helper = _extract_function(script_text, "Assert-LiveArtifactExists")
    command = "\n".join([
        "$ErrorActionPreference = 'Stop'",
        helper,
        "$path = Join-Path $env:TEMP 'definitely_missing_simnow_artifact.json'",
        "Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue",
        "Assert-LiveArtifactExists -Path $path -Label 'capture'",
    ])

    completed = _run_powershell_script(command)
    output = _decode_output(completed.stdout + completed.stderr)

    assert completed.returncode != 0
    assert "capture artifact is missing" in output


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


def test_formal_window_validation_rejects_night_session_when_enabled_symbol_is_day_only():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert_formal_window = _extract_function(script_text, "Assert-FormalObservationWindow")
    command = "\n".join([
        "$ErrorActionPreference = 'Stop'",
        assert_formal_window,
        "$contractMap = @{ AP888 = @{ enabled = $true; exchange = 'CZCE'; formal_sessions = @('day') } }",
        "$now = [datetimeoffset]::Parse('2026-07-10T21:48:02+08:00')",
        "Assert-FormalObservationWindow -LiveCapture $true -SkipKlineUpdate $false -Now $now -ContractMap $contractMap",
    ])

    completed = _run_powershell_script(command)
    output = _decode_output(completed.stdout + completed.stderr)

    assert completed.returncode != 0
    assert "AP888" in output
    assert "night session" in output


def test_formal_window_validation_allows_day_session_when_ap888_enabled():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert_formal_window = _extract_function(script_text, "Assert-FormalObservationWindow")
    command = "\n".join([
        "$ErrorActionPreference = 'Stop'",
        assert_formal_window,
        "$contractMap = @{ AP888 = @{ enabled = $true; exchange = 'CZCE'; formal_sessions = @('day') } }",
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
        "$contractMap = @{ AP888 = @{ enabled = $true; exchange = 'CZCE'; formal_sessions = @('day') } }",
        "$now = [datetimeoffset]::Parse('2026-07-10T21:48:02+08:00')",
        "Assert-FormalObservationWindow -LiveCapture $true -SkipKlineUpdate $true -Now $now -ContractMap $contractMap",
        "Write-Host 'smoke-window-finished'",
    ])

    completed = _run_powershell_script(command)
    output = _decode_output(completed.stdout + completed.stderr)

    assert completed.returncode == 0, output
    assert "smoke-window-finished" in output


def test_formal_window_validation_allows_night_when_enabled_symbols_allow_night():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert_formal_window = _extract_function(script_text, "Assert-FormalObservationWindow")
    command = "\n".join([
        "$ErrorActionPreference = 'Stop'",
        assert_formal_window,
        "$contractMap = @{ AP888 = @{ enabled = $true; exchange = 'CZCE'; formal_sessions = @('day', 'night') }; SC888 = @{ enabled = $true; exchange = 'INE'; formal_sessions = @('night') } }",
        "$now = [datetimeoffset]::Parse('2026-07-10T21:48:02+08:00')",
        "Assert-FormalObservationWindow -LiveCapture $true -SkipKlineUpdate $false -Now $now -ContractMap $contractMap",
        "Write-Host 'night-window-finished'",
    ])

    completed = _run_powershell_script(command)
    output = _decode_output(completed.stdout + completed.stderr)

    assert completed.returncode == 0, output
    assert "night-window-finished" in output


def test_formal_window_validation_allows_night_when_formal_sessions_missing():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert_formal_window = _extract_function(script_text, "Assert-FormalObservationWindow")
    command = "\n".join([
        "$ErrorActionPreference = 'Stop'",
        assert_formal_window,
        "$contractMap = @{ AP888 = @{ enabled = $true; exchange = 'CZCE' }; SC888 = @{ enabled = $true; exchange = 'INE' } }",
        "$now = [datetimeoffset]::Parse('2026-07-10T21:48:02+08:00')",
        "Assert-FormalObservationWindow -LiveCapture $true -SkipKlineUpdate $false -Now $now -ContractMap $contractMap",
        "Write-Host 'default-night-window-finished'",
    ])

    completed = _run_powershell_script(command)
    output = _decode_output(completed.stdout + completed.stderr)

    assert completed.returncode == 0, output
    assert "default-night-window-finished" in output


def test_wrapper_reads_json_artifacts_with_utf8_encoding():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")

    assert 'Get-Content -LiteralPath $DecisionFile.FullName -Raw -Encoding UTF8 | ConvertFrom-Json' in script_text
    assert 'Get-Content -LiteralPath $ReplayReadinessJson -Raw -Encoding UTF8 | ConvertFrom-Json' in script_text
    assert 'Get-Content -LiteralPath $RunSummaryJson -Raw -Encoding UTF8 | ConvertFrom-Json' in script_text


def test_formal_capture_plan_day_open_window_uses_1130_close():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    get_formal_plan = _extract_function(script_text, "Get-FormalCapturePlan")
    command = "\n".join([
        "$ErrorActionPreference = 'Stop'",
        get_formal_plan,
        "$now = [datetimeoffset]::Parse('2026-07-21T09:05:00+08:00')",
        "$plan = Get-FormalCapturePlan -LiveCapture $true -SkipKlineUpdate $false -Now $now -MinKlineBarsPerSymbol 30",
        "$plan | ConvertTo-Json -Compress",
    ])

    completed = _run_powershell_script(command)
    output = _decode_output(completed.stdout + completed.stderr)

    assert completed.returncode == 0, output
    assert '"window_name":"day_open"' in output
    assert '"duration_seconds":8700' in output


def test_formal_capture_plan_afternoon_window_uses_1500_close():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    get_formal_plan = _extract_function(script_text, "Get-FormalCapturePlan")
    command = "\n".join([
        "$ErrorActionPreference = 'Stop'",
        get_formal_plan,
        "$now = [datetimeoffset]::Parse('2026-07-21T13:35:00+08:00')",
        "$plan = Get-FormalCapturePlan -LiveCapture $true -SkipKlineUpdate $false -Now $now -MinKlineBarsPerSymbol 30",
        "$plan | ConvertTo-Json -Compress",
    ])

    completed = _run_powershell_script(command)
    output = _decode_output(completed.stdout + completed.stderr)

    assert completed.returncode == 0, output
    assert '"window_name":"day_afternoon"' in output
    assert '"duration_seconds":5100' in output


def test_formal_capture_plan_night_window_uses_2300_close():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    get_formal_plan = _extract_function(script_text, "Get-FormalCapturePlan")
    command = "\n".join([
        "$ErrorActionPreference = 'Stop'",
        get_formal_plan,
        "$now = [datetimeoffset]::Parse('2026-07-21T21:05:00+08:00')",
        "$plan = Get-FormalCapturePlan -LiveCapture $true -SkipKlineUpdate $false -Now $now -MinKlineBarsPerSymbol 30",
        "$plan | ConvertTo-Json -Compress",
    ])

    completed = _run_powershell_script(command)
    output = _decode_output(completed.stdout + completed.stderr)

    assert completed.returncode == 0, output
    assert '"window_name":"night_open"' in output
    assert '"duration_seconds":6900' in output


def test_formal_capture_plan_rejects_non_window_time():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    get_formal_plan = _extract_function(script_text, "Get-FormalCapturePlan")
    command = "\n".join([
        "$ErrorActionPreference = 'Stop'",
        get_formal_plan,
        "$now = [datetimeoffset]::Parse('2026-07-21T10:00:00+08:00')",
        "Get-FormalCapturePlan -LiveCapture $true -SkipKlineUpdate $false -Now $now -MinKlineBarsPerSymbol 30",
    ])

    completed = _run_powershell_script(command)
    output = _decode_output(completed.stdout + completed.stderr)

    assert completed.returncode != 0
    assert "09:05" in output
    assert "13:35" in output
    assert "21:05" in output


def test_formal_capture_plan_rejects_when_remaining_time_is_shorter_than_min_bars():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    get_formal_plan = _extract_function(script_text, "Get-FormalCapturePlan")
    command = "\n".join([
        "$ErrorActionPreference = 'Stop'",
        get_formal_plan,
        "$now = [datetimeoffset]::Parse('2026-07-21T09:05:00+08:00')",
        "Get-FormalCapturePlan -LiveCapture $true -SkipKlineUpdate $false -Now $now -MinKlineBarsPerSymbol 200",
    ])

    completed = _run_powershell_script(command)
    output = _decode_output(completed.stdout + completed.stderr)

    assert completed.returncode != 0
    assert "MinKlineBarsPerSymbol" in output
    assert "remaining" in output


def test_formal_capture_plan_rejects_when_symbol_specific_session_end_is_too_soon():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    get_formal_plan = _extract_function(script_text, "Get-FormalCapturePlan")
    command = "\n".join([
        "$ErrorActionPreference = 'Stop'",
        get_formal_plan,
        (
            "$contractMap = @{ "
            "A888 = @{ enabled = $true; formal_session_capture_end = @{ night = '21:30:00' } }; "
            "SC888 = @{ enabled = $true; formal_session_capture_end = @{ night = '23:00:00' } } "
            "}"
        ),
        "$now = [datetimeoffset]::Parse('2026-07-21T21:05:00+08:00')",
        (
            "Get-FormalCapturePlan -LiveCapture $true -SkipKlineUpdate $false "
            "-Now $now -MinKlineBarsPerSymbol 30 -ContractMap $contractMap"
        ),
    ])

    completed = _run_powershell_script(command)
    output = _decode_output(completed.stdout + completed.stderr)

    assert completed.returncode != 0
    assert "A888" in output
    assert "21:30:00" in output
    assert "MinKlineBarsPerSymbol" in output


def test_formal_capture_plan_night_window_supports_next_day_symbol_cutoff():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    get_formal_plan = _extract_function(script_text, "Get-FormalCapturePlan")
    command = "\n".join([
        "$ErrorActionPreference = 'Stop'",
        get_formal_plan,
        (
            "$contractMap = @{ "
            "ZN888 = @{ enabled = $true; formal_session_capture_end = @{ night = '01:00:00' } }; "
            "SC888 = @{ enabled = $true; formal_session_capture_end = @{ night = '02:30:00' } } "
            "}"
        ),
        "$now = [datetimeoffset]::Parse('2026-07-22T21:05:00+08:00')",
        (
            "$plan = Get-FormalCapturePlan -LiveCapture $true -SkipKlineUpdate $false "
            "-Now $now -MinKlineBarsPerSymbol 30 -ContractMap $contractMap"
        ),
        "$plan | ConvertTo-Json -Compress",
    ])

    completed = _run_powershell_script(command)
    output = _decode_output(completed.stdout + completed.stderr)

    assert completed.returncode == 0, output
    assert '"window_name":"night_open"' in output
    assert '"window_end":"2026-07-22T23:00:00+08:00"' in output
    assert '"duration_seconds":6900' in output


def test_enabled_night_symbols_define_formal_session_capture_end_in_contract_map():
    contract_map = json.loads((DIAG / "simnow_contract_map.json").read_text(encoding="utf-8"))

    missing = []
    for symbol, row in contract_map.items():
        if not row.get("enabled"):
            continue
        if "night" not in row.get("formal_sessions", []):
            continue
        cutoff = row.get("formal_session_capture_end", {}).get("night")
        if not cutoff:
            missing.append(symbol)

    assert missing == []


def test_historical_db_update_tables_include_enabled_symbols_only():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    get_update_tables = _extract_function(script_text, "Get-HistoricalDbUpdateTables")
    command = "\n".join([
        "$ErrorActionPreference = 'Stop'",
        get_update_tables,
        "$contractMap = @{ AP888 = @{ enabled = $true }; RB888 = @{ enabled = $true }; SC888 = @{ enabled = $false } }",
        "$tables = Get-HistoricalDbUpdateTables -ContractMap $contractMap",
        "$tables | ConvertTo-Json -Compress",
    ])

    completed = _run_powershell_script(command)
    output = _decode_output(completed.stdout + completed.stderr)

    assert completed.returncode == 0, output
    assert output.strip() == '["ap888_15M_raw","ap888_1M_raw","ap888_5M_raw","rb888_15M_raw","rb888_1M_raw","rb888_5M_raw"]'


def test_historical_db_update_tables_ignore_disabled_and_preserve_sorted_uniques():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    get_update_tables = _extract_function(script_text, "Get-HistoricalDbUpdateTables")
    command = "\n".join([
        "$ErrorActionPreference = 'Stop'",
        get_update_tables,
        "$contractMap = @{ ZN888 = @{ enabled = $false }; A888 = @{ enabled = $true }; AP888 = @{ enabled = $true } }",
        "$tables = Get-HistoricalDbUpdateTables -ContractMap $contractMap",
        "$tables | ConvertTo-Json -Compress",
    ])

    completed = _run_powershell_script(command)
    output = _decode_output(completed.stdout + completed.stderr)

    assert completed.returncode == 0, output
    assert output.strip() == '["a888_15M_raw","a888_1M_raw","a888_5M_raw","ap888_15M_raw","ap888_1M_raw","ap888_5M_raw"]'


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


def test_session_scoped_run_summary_json_variable_defined():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "$SessionRunSummaryJson = $null" in script_text


def test_session_scoped_daily_brief_md_variable_defined():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "$SessionDailyBriefMd = $null" in script_text


def test_session_scoped_record_json_variable_defined():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "$SessionRecordJson = $null" in script_text


def test_session_scoped_report_md_variable_defined():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "$SessionReportMd = $null" in script_text


def test_formal_window_initializes_session_scoped_artifacts():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert 'Join-Path $OutDir "simnow_run_summary_${Date}_$($FormalCapturePlan.window_name).json"' in script_text
    assert 'Join-Path $OutDir "simnow_daily_brief_${Date}_$($FormalCapturePlan.window_name).md"' in script_text
    assert 'Join-Path $OutDir "simnow_record_${Date}_$($FormalCapturePlan.window_name).json"' in script_text
    assert 'Join-Path $OutDir "simnow_report_${Date}_$($FormalCapturePlan.window_name).md"' in script_text


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


def test_session_scoped_artifact_copy_step_after_daily_brief():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    brief_index = script_text.index("Generate daily brief")
    session_copy_index = script_text.index("Mirror session-scoped artifacts")
    consistency_index = script_text.index("Validate summary consistency")
    assert session_copy_index > brief_index
    assert consistency_index > session_copy_index


def test_session_scoped_artifact_copy_includes_run_summary_and_daily_brief():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    step_index = script_text.index("Mirror session-scoped artifacts")
    block = script_text[step_index:step_index + 1200]
    assert "Copy-Item -LiteralPath $RunSummaryJson -Destination $SessionRunSummaryJson -Force" in block
    assert "Copy-Item -LiteralPath $DailyBriefMd -Destination $SessionDailyBriefMd -Force" in block
    assert "Copy-Item -LiteralPath $RecordJson -Destination $SessionRecordJson -Force" in block
    assert "Copy-Item -LiteralPath $ReportMd -Destination $SessionReportMd -Force" in block


def test_preflight_pytest_includes_daily_brief_tests():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "test_simnow_daily_brief.py" in script_text


def test_preflight_pytest_includes_risk_halt_review_tests():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "test_simnow_risk_halt_review.py" in script_text


def test_preflight_pytest_includes_risk_halt_decision_tests():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "test_simnow_risk_halt_decision.py" in script_text


def test_preflight_pytest_includes_daily_brief_policy_sharing_tests():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "test_simnow_daily_brief_policy_sharing.py" in script_text


def test_preflight_py_compile_includes_daily_brief_script():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "simnow_daily_brief.py" in script_text


def test_preflight_py_compile_includes_risk_halt_review_script():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "simnow_risk_halt_review.py" in script_text


def test_preflight_py_compile_includes_risk_halt_decision_script():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "simnow_risk_halt_decision.py" in script_text


def test_preflight_py_compile_includes_summary_consistency_script():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "simnow_summary_consistency.py" in script_text


def test_ledger_summary_json_variable_defined():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "$LedgerSummaryJson = Join-Path $OutDir \"simnow_ledger_summary.json\"" in script_text


def test_preflight_py_compile_includes_ledger_summary_script():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "simnow_ledger_summary.py" in script_text


def test_preflight_py_compile_includes_observation_window_script():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "simnow_observation_window.py" in script_text


def test_preflight_py_compile_includes_20d_aggregate_script():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "simnow_20d_aggregate.py" in script_text


def test_preflight_py_compile_includes_artifact_loader_script():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "simnow_artifact_loader.py" in script_text


def test_preflight_py_compile_includes_structured_access_script():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "simnow_structured_access.py" in script_text


def test_preflight_py_compile_includes_automation_policy_script():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "simnow_automation_policy.py" in script_text


def test_preflight_py_compile_includes_halt_metadata_script():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "simnow_halt_metadata.py" in script_text


def test_preflight_py_compile_includes_reason_governance_script():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "simnow_reason_governance.py" in script_text


def test_preflight_py_compile_includes_ledger_summary_schema_script():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "simnow_ledger_summary_schema.py" in script_text


def test_preflight_py_compile_includes_daily_brief_default_summary_script():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "simnow_daily_brief_default_summary.py" in script_text


def test_preflight_py_compile_includes_daily_brief_schema_script():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "simnow_daily_brief_schema.py" in script_text


def test_preflight_py_compile_includes_daily_brief_sections_script():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "simnow_daily_brief_sections.py" in script_text


def test_preflight_py_compile_includes_contract_map_meta_script():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "simnow_contract_map_meta.py" in script_text


def test_preflight_py_compile_includes_strategy_surface_script():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "simnow_strategy_surface.py" in script_text


def test_preflight_py_compile_includes_replay_snapshot_script():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "export_simnow_replay_snapshot.py" in script_text


def test_preflight_pytest_includes_ledger_summary_tests():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "test_simnow_ledger_summary.py" in script_text


def test_preflight_pytest_includes_summary_consistency_tests():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "test_simnow_summary_consistency.py" in script_text


def test_preflight_pytest_includes_strategy_surface_tests():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "test_simnow_strategy_surface.py" in script_text


def test_preflight_pytest_includes_20d_aggregate_tests():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "test_simnow_20d_aggregate.py" in script_text


def test_preflight_pytest_includes_artifact_loader_tests():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "test_simnow_artifact_loader.py" in script_text


def test_preflight_pytest_includes_helper_boundary_tests():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "test_simnow_helper_boundaries.py" in script_text


def test_preflight_pytest_includes_structured_access_tests():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "test_simnow_structured_access.py" in script_text


def test_preflight_pytest_includes_automation_policy_tests():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "test_simnow_automation_policy.py" in script_text


def test_preflight_pytest_includes_ledger_summary_schema_tests():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "test_simnow_ledger_summary_schema.py" in script_text


def test_preflight_pytest_includes_daily_brief_default_summary_tests():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "test_simnow_daily_brief_default_summary.py" in script_text


def test_preflight_pytest_includes_daily_brief_schema_tests():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "test_simnow_daily_brief_schema.py" in script_text


def test_preflight_pytest_includes_daily_brief_sections_tests():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "test_simnow_daily_brief_sections.py" in script_text


def test_preflight_pytest_includes_replay_snapshot_tests():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "test_export_simnow_replay_snapshot.py" in script_text


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
    review_index = script_text.index("Generate risk halt review pack")
    decision_index = script_text.index("Generate risk halt decision template")
    consistency_index = script_text.index("Validate summary consistency")
    halt_guard_index = script_text.index("if ($MonitorExitCode -eq 2)")

    assert review_index > brief_index
    assert decision_index > review_index
    assert consistency_index > decision_index
    assert halt_guard_index > consistency_index
    assert ledger_index > monitor_index
    assert summary_index > ledger_index
    assert brief_index > summary_index


def test_risk_halt_review_paths_and_generation_step_present():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    step_index = script_text.index("Generate risk halt review pack")
    block = script_text[step_index:step_index + 900]

    assert "$RiskHaltReviewJson = Join-Path $OutDir \"simnow_risk_halt_review_$Date.json\"" in script_text
    assert "$RiskHaltReviewMd = Join-Path $OutDir \"simnow_risk_halt_review_$Date.md\"" in script_text
    assert "simnow_risk_halt_review.py" in block
    assert "--run-summary" in block
    assert "$RunSummaryJson" in block
    assert "--out-json" in block
    assert "$RiskHaltReviewJson" in block
    assert "--out-md" in block
    assert "$RiskHaltReviewMd" in block


def test_risk_halt_decision_paths_and_generation_step_present():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    step_index = script_text.index("Generate risk halt decision template")
    block = script_text[step_index:step_index + 900]

    assert "$RiskHaltDecisionJson = Join-Path $OutDir \"simnow_risk_halt_decision_$Date.json\"" in script_text
    assert "$RiskHaltDecisionMd = Join-Path $OutDir \"simnow_risk_halt_decision_$Date.md\"" in script_text
    assert "simnow_risk_halt_decision.py" in block
    assert "--review-json" in block
    assert "$RiskHaltReviewJson" in block
    assert "--out-json" in block
    assert "$RiskHaltDecisionJson" in block
    assert "--out-md" in block
    assert "$RiskHaltDecisionMd" in block


def test_pending_risk_halt_decision_gate_function_present():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")

    assert "function Assert-NoPendingRiskHaltDecision" in script_text
    assert "simnow_risk_halt_decision_*.json" in script_text
    assert "pending risk halt decision blocks live capture" in script_text


def test_pending_risk_halt_decision_gate_runs_before_live_capture():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")

    gate_index = script_text.index("Assert-NoPendingRiskHaltDecision -OutDir $OutDir")
    capture_index = script_text.index("Run read-only SimNow capture")
    assert gate_index < capture_index


def test_pending_risk_halt_decision_gate_blocks_unreviewed_decision():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    helper = _extract_function(script_text, "Assert-NoPendingRiskHaltDecision")
    command = "\n".join([
        "$ErrorActionPreference = 'Stop'",
        helper,
        "$dir = Join-Path $env:TEMP ('simnow_decision_gate_' + [System.Guid]::NewGuid().ToString('N'))",
        "New-Item -ItemType Directory -Path $dir -Force | Out-Null",
        "$decision = Join-Path $dir 'simnow_risk_halt_decision_2026-07-24.json'",
        "@'",
        "{",
        '  "date": "2026-07-24",',
        '  "decision_status": "pending_decision",',
        '  "next_formal_observation_allowed": false',
        "}",
        "'@ | Set-Content -LiteralPath $decision -Encoding UTF8",
        "Assert-NoPendingRiskHaltDecision -OutDir $dir",
    ])

    completed = _run_powershell_script(command)
    output = _decode_output(completed.stdout + completed.stderr)

    assert completed.returncode != 0
    assert "pending risk halt decision blocks live capture" in output


def test_pending_risk_halt_decision_gate_blocks_invalid_decided_record():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    helper = _extract_function(script_text, "Assert-NoPendingRiskHaltDecision")
    command = "\n".join([
        "$ErrorActionPreference = 'Stop'",
        helper,
        "$dir = Join-Path $env:TEMP ('simnow_decision_gate_' + [System.Guid]::NewGuid().ToString('N'))",
        "New-Item -ItemType Directory -Path $dir -Force | Out-Null",
        "$decision = Join-Path $dir 'simnow_risk_halt_decision_2026-07-24.json'",
        "@'",
        "{",
        '  "date": "2026-07-24",',
        '  "decision_status": "decided",',
        '  "selected_decision": "resume_observation",',
        '  "next_formal_observation_allowed": true,',
        '  "operator_name": "",',
        '  "rationale": "",',
        '  "requires_observation_window_reset": null,',
        '  "allowed_decisions": ["keep_halted"]',
        "}",
        "'@ | Set-Content -LiteralPath $decision -Encoding UTF8",
        "Assert-NoPendingRiskHaltDecision -OutDir $dir",
    ])

    completed = _run_powershell_script(command)
    output = _decode_output(completed.stdout + completed.stderr)

    assert completed.returncode != 0
    assert "invalid risk halt decision blocks live capture" in output
    assert "selected_decision_not_allowed" in output
    assert "operator_name_required" in output
    assert "rationale_required" in output
    assert "requires_observation_window_reset_required" in output


def test_pending_risk_halt_decision_gate_allows_signed_allowed_decision():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    helper = _extract_function(script_text, "Assert-NoPendingRiskHaltDecision")
    command = "\n".join([
        "$ErrorActionPreference = 'Stop'",
        helper,
        "$dir = Join-Path $env:TEMP ('simnow_decision_gate_' + [System.Guid]::NewGuid().ToString('N'))",
        "New-Item -ItemType Directory -Path $dir -Force | Out-Null",
        "$decision = Join-Path $dir 'simnow_risk_halt_decision_2026-07-24.json'",
        "@'",
        "{",
        '  "date": "2026-07-24",',
        '  "decision_status": "decided",',
        '  "selected_decision": "keep_halted",',
        '  "next_formal_observation_allowed": true,',
        '  "operator_name": "risk-reviewer",',
        '  "rationale": "Signed decision.",',
        '  "requires_observation_window_reset": false',
        "}",
        "'@ | Set-Content -LiteralPath $decision -Encoding UTF8",
        "Assert-NoPendingRiskHaltDecision -OutDir $dir",
        "Write-Host 'decision-gate-ok'",
    ])

    completed = _run_powershell_script(command)
    output = _decode_output(completed.stdout + completed.stderr)

    assert completed.returncode == 0, output
    assert "decision-gate-ok" in output


def test_historical_db_update_parameters_defined():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert "[switch]$UpdateHistoricalDb" in script_text
    assert "[switch]$PostProcessOnly" in script_text
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
    update_block = script_text[update_index:update_index + 3200]
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


def test_historical_db_update_invokes_auto_update_script_with_single_table_parameter():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    update_index = script_text.index("Run historical DB auto update")
    update_block = script_text[update_index:update_index + 3200]

    assert "Get-HistoricalDbUpdateTables -ContractMap $ContractMap" in script_text
    assert '-FilePath "powershell.exe"' in update_block
    assert '-Command", "& `"$HistoricalDbUpdateScriptPath`"$HistoricalDbUpdateInlineTableArgs"' in update_block
    assert '$HistoricalDbUpdateInlineTableArgs = " -Table @(" + (($HistoricalDbUpdateTables | ForEach-Object { "\'$_\'" }) -join ", ") + ")"' in update_block


def test_run_summary_receives_historical_db_update_argument():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    step_index = script_text.index("Generate run summary")
    summary_block = script_text[step_index:step_index + 900]
    assert "--historical-db-update" in summary_block
    assert "$HistoricalDbUpdateJson" in summary_block


def test_post_process_only_resume_step_present():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")

    assert "Resume live post-processing from existing artifacts" in script_text
    assert "Assert-LiveArtifactExists -Path $CaptureJson -Label \"capture JSON\"" in script_text
    assert "Assert-LiveArtifactExists -Path $KlineSummaryJson -Label \"kline summary JSON\"" in script_text
    assert "Assert-LiveArtifactExists -Path $ReplayJson -Label \"replay JSON\"" in script_text


def test_refresh_replay_parameter_defined():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")

    assert "[switch]$RefreshReplay" in script_text


def test_refresh_replay_rejects_skip_replay_combination():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")

    assert "RefreshReplay cannot be combined with SkipReplay" in script_text


def test_replay_refresh_helper_is_reused_by_live_and_post_process():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")

    assert "function Invoke-ReplaySnapshotRefresh" in script_text
    assert script_text.count("Invoke-ReplaySnapshotRefresh `") >= 2


def test_post_process_only_can_refresh_replay_without_existing_replay_assertion():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    resume_index = script_text.index("Resume live post-processing from existing artifacts")
    resume_block = script_text[resume_index:resume_index + 1400]

    assert "if ($RefreshReplay.IsPresent -and -not $SkipReplay.IsPresent)" in resume_block
    assert "Invoke-ReplaySnapshotRefresh" in resume_block
    assert "elseif (-not $SkipReplay)" in resume_block
    assert "Assert-LiveArtifactExists -Path $ReplayJson -Label \"replay JSON\"" in resume_block


def test_post_process_only_bypasses_formal_capture_plan_gate():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")

    assert "-LiveCapture ($LiveCapture.IsPresent -and -not $PostProcessOnly.IsPresent)" in script_text


def test_post_process_only_bypasses_formal_observation_window_gate():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")

    assert "-LiveCapture ($LiveCapture.IsPresent -and -not $PostProcessOnly.IsPresent)" in script_text


def test_replay_readiness_json_written_with_utf8_set_content():
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")

    assert '> $ReplayReadinessJson' not in script_text
    assert 'Set-Content -LiteralPath $ReplayReadinessJson -Encoding UTF8' in script_text


def test_risk_halt_review_and_decision_generation_gated_on_halt_status():
    """ACCEPTANCE.md scopes the risk-halt review/decision gate to
    automation_status=halt. The wrapper must not emit pending decision records
    for non-halt days, or A38 would block every subsequent observation day.
    """
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    review_index = script_text.index("Generate risk halt review pack")
    decision_index = script_text.index("Generate risk halt decision template")
    gate_index = script_text.index('$AutomationStatus -eq "halt"')

    assert gate_index < review_index < decision_index
    # The automation status must be read from the run summary artifact.
    gate_context = script_text[max(0, gate_index - 600):gate_index]
    assert "automation_status" in gate_context
    assert "$RunSummaryJson" in gate_context
    # A skip note documents non-halt days instead of generating records.
    assert "Skip risk halt review/decision" in script_text


def test_python_probe_requires_full_project_deps():
    """A bare `python` with pytest but without czsc/pandas (e.g. sandboxed
    runtimes) must not be selected; conftest imports czsc, so a pytest-only
    probe fails at collection with exit code 4.
    """
    script_text = RUN_NEXT_WORK.read_text(encoding="utf-8")
    assert '"pytest, pandas, czsc"' in script_text
