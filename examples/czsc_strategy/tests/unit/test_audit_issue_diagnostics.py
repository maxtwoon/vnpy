import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))

from audit_issue_diagnostics import (
    SIGNAL_HISTORY_FILENAME_MARKERS,
    _resolve_db_path,
    analyze_continuous_contract_assumptions,
    analyze_cost_consistency,
    analyze_divergence_failure_reachability,
    analyze_stop_loss_overshoot,
    build_audit_issue_report,
    collect_cost_inputs_from_project,
    collect_parameter_evidence_from_diagnostics,
    collect_signal_records_from_diagnostics,
    collect_stop_loss_pairs_from_diagnostics,
    contains_sensitive_data,
    detect_high_precision_weights,
    write_json_report,
    write_markdown_report,
)
from chan_strategy.config import BACKTEST_CONFIG
from platform_final_candidate import candidate_summary


def test_detect_high_precision_weights_flags_847():
    params = [
        {"name": "short_sc_multiplier", "value": 0.847},
        {"name": "short_sc_multiplier", "value": 1.0},
    ]
    result = detect_high_precision_weights(params)
    assert result["issue"] == "H1"
    assert result["high_precision_weight"] is True
    assert any(p["value"] == 0.847 for p in result["suspicious_params"])
    assert all(p["value"] != 1.0 for p in result["suspicious_params"])


def test_detect_high_precision_weights_ignores_integer_and_one_decimal():
    params = [
        {"name": "some_weight", "value": 1.0},
        {"name": "some_ratio", "value": 0.5},
        {"name": "int_param", "value": 3},
    ]
    result = detect_high_precision_weights(params)
    assert result["high_precision_weight"] is False
    assert result["suspicious_params"] == []


def test_analyze_stop_loss_overshoot_computes_overshoot():
    pairs = [
        {"symbol": "SC888", "pnl_pct": -0.126, "exit_reason": "stop_loss"},
        {"symbol": "SC888", "pnl_pct": -0.0477, "exit_reason": "stop_loss"},
        {"symbol": "SC888", "pnl_pct": -0.02, "exit_reason": "stop_loss"},
    ]
    result = analyze_stop_loss_overshoot(pairs, stop_loss_bp=300)
    assert result["issue"] == "H2"
    assert result["stop_loss_pct"] == -3.0
    assert abs(result["worst_loss_pct"] - (-12.6)) < 0.01
    assert result["max_overshoot_multiple"] >= 4.0
    assert result["overshoot_count"] == 2


def test_analyze_divergence_failure_reachability_zero_count():
    records = [
        {"dt": "2026-01-01", "signal": "buy1"},
        {"dt": "2026-01-02", "signal": "sell2"},
    ]
    result = analyze_divergence_failure_reachability(records)
    assert result["issue"] == "H3"
    assert result["count"] == 0
    assert result["reachable"] is False
    assert result["severity"] in ("high", "warning")


def test_analyze_divergence_failure_reachability_found():
    records = [
        {"dt": "2026-01-01", "signal": "背驰V260615_失效"},
    ]
    result = analyze_divergence_failure_reachability(records)
    assert result["count"] == 1
    assert result["reachable"] is True


def test_analyze_divergence_failure_reachability_no_records():
    result = analyze_divergence_failure_reachability([])
    assert result["status"] == "unavailable"


def test_analyze_continuous_contract_assumptions_unknown_when_no_metadata():
    result = analyze_continuous_contract_assumptions(db_path=None, symbols=["SC888"])
    assert result["issue"] == "H4"
    assert result["status"] in ("unknown", "unavailable")
    assert result.get("silently_pass") is not True


def test_analyze_continuous_contract_assumptions_unknown_with_missing_db():
    result = analyze_continuous_contract_assumptions(
        db_path="/tmp/simnow_audit_nonexistent.db", symbols=["SC888"]
    )
    assert result["issue"] == "H4"
    assert result["status"] in ("unknown", "unavailable")


def test_analyze_cost_consistency_detects_conflict():
    config_values = {"commission": 0.0001, "slippage": 0.0005}
    engine_defaults = {"commission": 0.0003, "slippage": 0.001}
    position_defaults = {"commission": 0.0001, "slippage": 0.0005}
    result = analyze_cost_consistency(config_values, engine_defaults, position_defaults)
    assert result["issue"] == "M1"
    assert result["consistent"] is False
    assert "engine_default" in result["conflicts"]
    assert result["recommended_source"] == "BACKTEST_CONFIG"


def test_analyze_cost_consistency_true_when_all_equal():
    config_values = {"commission": 0.0001, "slippage": 0.0005}
    engine_defaults = {"commission": 0.0001, "slippage": 0.0005}
    position_defaults = {"commission": 0.0001, "slippage": 0.0005}
    result = analyze_cost_consistency(config_values, engine_defaults, position_defaults)
    assert result["consistent"] is True
    assert result["conflicts"] == []


def test_build_audit_issue_report_contains_all_issues():
    report = build_audit_issue_report(
        date="2026-07-03",
        params=[{"name": "short_sc_multiplier", "value": 0.847}],
        pairs=[{"symbol": "SC888", "pnl_pct": -0.126, "exit_reason": "stop_loss"}],
        stop_loss_bp=300,
        signal_records=[],
        db_path=None,
        symbols=["SC888"],
        cost_config={"commission": 0.0001, "slippage": 0.0005},
        engine_defaults={"commission": 0.0003, "slippage": 0.001},
        position_defaults={"commission": 0.0001, "slippage": 0.0005},
    )
    issues = report["issues"]
    for key in ("H1", "H2", "H3", "H4", "M1"):
        assert key in issues
    assert issues["H1"]["high_precision_weight"] is True
    assert issues["H2"]["worst_loss_pct"] <= -12.0
    assert issues["H3"]["status"] == "unavailable"
    assert issues["H4"]["status"] in ("unknown", "unavailable")
    assert issues["M1"]["consistent"] is False


def test_write_reports_render_json_and_markdown(tmp_path):
    report = build_audit_issue_report(
        date="2026-07-03",
        params=[{"name": "short_sc_multiplier", "value": 0.847}],
        pairs=[{"symbol": "SC888", "pnl_pct": -0.126, "exit_reason": "stop_loss"}],
        stop_loss_bp=300,
        signal_records=[],
        db_path=None,
        symbols=["SC888"],
        cost_config={"commission": 0.0001, "slippage": 0.0005},
        engine_defaults={"commission": 0.0003, "slippage": 0.001},
        position_defaults={"commission": 0.0001, "slippage": 0.0005},
    )
    json_path = tmp_path / "audit.json"
    md_path = tmp_path / "audit.md"
    write_json_report(report, json_path)
    write_markdown_report(report, md_path)

    json_text = json_path.read_text(encoding="utf-8")
    md_text = md_path.read_text(encoding="utf-8")

    loaded = json.loads(json_text)
    for key in ("H1", "H2", "H3", "H4", "M1"):
        assert key in loaded["issues"]

    assert "# Audit Issue Diagnostics" in md_text or "# 审核问题诊断" in md_text
    for key in ("H1", "H2", "H3", "H4", "M1"):
        assert key in md_text
    assert "GOAL PASSED" not in md_text.upper()


def test_source_does_not_contain_order_calls():
    src = (DIAG / "audit_issue_diagnostics.py").read_text(encoding="utf-8")
    for call in ("send_order", "cancel_order", "buy(", "sell(", "short(", "cover("):
        assert call not in src, f"found forbidden trading call: {call}"


def test_contains_sensitive_data_detects_leak():
    bad = {"password": "secret", "account_id": "12345"}
    assert contains_sensitive_data(bad) is True

    good = {"issue": "H1", "status": "detected"}
    assert contains_sensitive_data(good) is False


# A32: real project input collectors


def test_collect_cost_inputs_from_project_resolves_none_to_config():
    inputs = collect_cost_inputs_from_project(REPO_ROOT)
    assert "BACKTEST_CONFIG" in inputs
    assert "engine_defaults" in inputs
    assert "position_defaults" in inputs
    for source in ("BACKTEST_CONFIG", "engine_defaults", "position_defaults"):
        assert "commission" in inputs[source]
        assert "slippage" in inputs[source]

    # After Phase 1, None defaults resolve to BACKTEST_CONFIG, so M1 is consistent.
    assert inputs["engine_defaults"]["commission"] == BACKTEST_CONFIG["commission_rate"]
    assert inputs["engine_defaults"]["slippage"] == BACKTEST_CONFIG["slippage"]
    assert inputs["position_defaults"]["commission"] == BACKTEST_CONFIG["commission_rate"]
    assert inputs["position_defaults"]["slippage"] == BACKTEST_CONFIG["slippage"]

    result = analyze_cost_consistency(
        inputs["BACKTEST_CONFIG"],
        inputs["engine_defaults"],
        inputs["position_defaults"],
    )
    assert result["consistent"] is True
    assert result["conflicts"] == []
    assert result["recommended_source"] == "BACKTEST_CONFIG"


def test_collect_signal_records_from_diagnostics(tmp_path):
    data = [
        {
            "dt": "2026-01-01 10:00:00",
            "signals": {
                "30分钟_背驰V260615_状态_任意_任意_0": "30分钟_背驰V260615_状态_失效_任意_0"
            },
        }
    ]
    (tmp_path / "signals.json").write_text(json.dumps(data), encoding="utf-8")

    records = collect_signal_records_from_diagnostics(tmp_path)
    assert len(records) == 1
    assert "失效" in records[0]["signal"]

    result = analyze_divergence_failure_reachability(records)
    assert result["count"] == 1
    assert result["reachable"] is True

    empty = collect_signal_records_from_diagnostics(tmp_path / "empty")
    assert empty == []


def test_collect_stop_loss_pairs_from_diagnostics(tmp_path):
    data = {
        "pairs": [
            {
                "symbol": "SC888",
                "exit_reason": "stop_loss",
                "pnl_pct": -0.126,
                "open_dt": "2026-04-07",
                "close_dt": "2026-04-08",
            }
        ]
    }
    (tmp_path / "pairs.json").write_text(json.dumps(data), encoding="utf-8")

    pairs = collect_stop_loss_pairs_from_diagnostics(tmp_path)
    assert len(pairs) == 1
    assert pairs[0]["symbol"] == "SC888"

    result = analyze_stop_loss_overshoot(pairs, stop_loss_bp=300)
    assert result["overshoot_count"] == 1
    assert result["max_overshoot_multiple"] >= 4.0


def test_collect_parameter_evidence_from_diagnostics(tmp_path):
    md = (
        "# SC short weight neighborhood\n\n"
        "| multiplier | pass |\n|------------|------|\n"
        "| 0.847      | True |\n"
        "| 0.85       | False|\n"
    )
    (tmp_path / "sc_short_weight_neighborhood.md").write_text(md, encoding="utf-8")

    evidence = collect_parameter_evidence_from_diagnostics(tmp_path)
    assert len(evidence["evidence_files"]) >= 1

    params = evidence.get("params", [])
    h1 = detect_high_precision_weights(params)
    assert h1["high_precision_weight"] is True or any(
        "0.847" in str(p.get("value", "")) for p in h1["suspicious_params"]
    )


def test_analyze_continuous_contract_assumptions_db_without_adjustment(tmp_path):
    db_path = tmp_path / "test.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "CREATE TABLE AP888_1M_raw ("
            "datetime TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL)"
        )
    result = analyze_continuous_contract_assumptions(db_path, ["AP888"])
    assert result["issue"] == "H4"
    assert result["status"] == "no_evidence"
    assert result.get("silently_pass") is False
    assert result["real_symbol_transitions"] == {}


def test_analyze_continuous_contract_assumptions_db_with_adjustment(tmp_path):
    db_path = tmp_path / "test.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "CREATE TABLE RB888_1M_raw ("
            "datetime TEXT, close REAL, adjustment_factor REAL)"
        )
    result = analyze_continuous_contract_assumptions(db_path, ["RB888"])
    assert result["issue"] == "H4"
    assert result["status"] == "found_adjusted"
    assert any("adjustment_factor" in e for e in result["evidence"])


def test_build_audit_issue_report_with_auto_collection_m1_not_unavailable(tmp_path):
    report = build_audit_issue_report(
        date="2026-07-03",
        repo_root=REPO_ROOT,
        diagnostics_dir=tmp_path,
        symbols=["AP888"],
    )
    assert report["issues"]["M1"]["status"] != "unavailable"
    assert "data_source" in report["issues"]["M1"]
    assert report["issues"]["H1"]["status"] in ("unknown", "detected")
    assert report["issues"]["H4"]["status"] in ("unknown", "unavailable")


def test_build_audit_issue_report_m1_consistent_with_repo_root(tmp_path):
    report = build_audit_issue_report(
        date="2026-07-03",
        repo_root=REPO_ROOT,
        diagnostics_dir=tmp_path,
        symbols=["AP888"],
    )
    assert report["issues"]["M1"]["consistent"] is True
    assert report["issues"]["M1"]["conflicts"] == []


def test_build_audit_issue_report_contains_declassification_metadata():
    report = build_audit_issue_report(
        date="2026-07-03",
        repo_root=REPO_ROOT,
        diagnostics_dir=Path(__file__).resolve().parents[2] / "diagnostics",
        symbols=["AP888"],
    )
    assert report["is_promotion_evidence"] is False
    assert report["research_only"] is True
    assert "used_data_windows" in report
    assert "decision_data_windows" in report
    assert BACKTEST_CONFIG["start_date"] in report["used_data_windows"][0]
    assert BACKTEST_CONFIG["end_date"] in report["used_data_windows"][0]
    assert "2026-04-24~present" in report["decision_data_windows"]

    h1 = report["issues"]["H1"]
    assert h1["is_promotion_evidence"] is False
    assert h1["research_only"] is True
    assert "used_data_windows" in h1
    assert "decision_data_windows" in h1
    assert "promotion evidence" in h1["note"].lower()


def test_platform_final_candidate_summary_has_declassification_metadata():
    summary = candidate_summary()
    assert summary["is_promotion_evidence"] is False
    assert summary["research_only"] is True
    assert "used_data_windows" in summary
    assert "decision_data_windows" in summary
    assert "note" in summary
    assert "2026-04-24" in summary["note"]
    assert "SimNow" in summary["note"]


# A33: signal-history replay and H4 DB metadata inspection


def test_generate_signal_history_creates_expected_schema(tmp_path, memory_db):
    output_dir = tmp_path / "out"
    cmd = [
        sys.executable,
        str(DIAG / "generate_signal_history.py"),
        "--symbols", "TEST",
        "--db-path", str(memory_db),
        "--start-date", "2024-01-01",
        "--end-date", "2024-01-03",
        "--warmup-bars", "1",
        "--output-dir", str(output_dir),
        "--combined",
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert result.returncode == 0, result.stderr

    files = list(output_dir.glob("signal_history_*.json"))
    assert len(files) == 1
    records = json.loads(files[0].read_text(encoding="utf-8"))
    assert len(records) >= 1

    required_keys = {
        "dt",
        "symbol",
        "price",
        "signal",
        "signal_key",
        "signal_value",
        "divergence_status",
        "source",
        "data_version",
    }
    for record in records:
        assert required_keys.issubset(record.keys())
        assert record["symbol"] == "TEST"
        assert record["source"] == "real_bar_replay"
        assert "背驰V260615" in record["signal_key"]
        assert record["divergence_status"] == record["signal_value"].split("_")[0]


def test_generate_signal_history_per_symbol(tmp_path, memory_db):
    output_dir = tmp_path / "out"
    cmd = [
        sys.executable,
        str(DIAG / "generate_signal_history.py"),
        "--symbols", "TEST",
        "--db-path", str(memory_db),
        "--start-date", "2024-01-01",
        "--end-date", "2024-01-03",
        "--warmup-bars", "1",
        "--output-dir", str(output_dir),
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert result.returncode == 0, result.stderr

    files = list(output_dir.glob("signal_history_TEST_*.json"))
    assert len(files) == 1
    records = json.loads(files[0].read_text(encoding="utf-8"))
    assert len(records) >= 1


def test_collect_signal_records_prefers_signal_history_files(tmp_path):
    signal_history = [
        {
            "dt": "2024-01-02 10:00:00",
            "symbol": "TEST",
            "signal": "30分钟_D1BI_背驰V260615_失效_任意_任意_20",
            "source": "real_bar_replay",
        }
    ]
    (tmp_path / "signal_history_TEST_20240101_20240103.json").write_text(
        json.dumps(signal_history), encoding="utf-8"
    )

    generic = {
        "dt": "2024-01-02 11:00:00",
        "signals": {
            "30分钟_D1BI_背驰V260615_状态_任意_任意_0": "30分钟_D1BI_背驰V260615_状态_失效_任意_0"
        },
    }
    (tmp_path / "other_signals.json").write_text(json.dumps(generic), encoding="utf-8")

    records = collect_signal_records_from_diagnostics(tmp_path)
    assert any(
        any(marker in str(r.get("source_file", "")) for marker in SIGNAL_HISTORY_FILENAME_MARKERS)
        for r in records
    )

    report = build_audit_issue_report(
        date="2026-07-03",
        diagnostics_dir=tmp_path,
        symbols=["TEST"],
    )
    assert report["issues"]["H3"]["data_source"] == "signal_history_replay"
    assert report["issues"]["H3"]["reachable"] is True


def test_analyze_continuous_contract_found_spliced(tmp_path):
    db_path = tmp_path / "test.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "CREATE TABLE AP888_1M_raw (datetime TEXT, open REAL, real_symbol TEXT)"
        )
        rows = [
            ("2024-01-02 09:00:00", 100.0, "AP2401"),
            ("2024-01-02 10:00:00", 101.0, "AP2401"),
            ("2024-06-03 09:00:00", 110.0, "AP2405"),
            ("2024-06-03 10:00:00", 111.0, "AP2405"),
        ]
        conn.executemany("INSERT INTO AP888_1M_raw VALUES (?,?,?)", rows)

    result = analyze_continuous_contract_assumptions(db_path, ["AP888"])
    assert result["status"] == "found_spliced"
    assert "AP888" in result["real_symbol_transitions"]
    assert result["real_symbol_transitions"]["AP888"]["distinct_count"] == 2
    transitions = result["real_symbol_transitions"]["AP888"]["transitions"]
    assert any(t["real_symbol"] == "AP2401" for t in transitions)
    assert any(t["real_symbol"] == "AP2405" for t in transitions)


def test_analyze_continuous_contract_found_single_contract(tmp_path):
    db_path = tmp_path / "test.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "CREATE TABLE ZN888_1M_raw (datetime TEXT, close REAL, real_symbol TEXT)"
        )
        rows = [
            ("2024-01-02 09:00:00", 100.0, "ZN2401"),
            ("2024-01-02 10:00:00", 101.0, "ZN2401"),
        ]
        conn.executemany("INSERT INTO ZN888_1M_raw VALUES (?,?,?)", rows)

    result = analyze_continuous_contract_assumptions(db_path, ["ZN888"])
    assert result["status"] == "found_single_contract"
    assert result["real_symbol_transitions"]["ZN888"]["distinct_count"] == 1


def test_resolve_db_path_cli_arg_over_env(tmp_path, monkeypatch):
    explicit = tmp_path / "explicit.db"
    env_path = tmp_path / "env.db"
    explicit.touch()
    env_path.touch()

    monkeypatch.setenv("CHAN_SQLITE_DB_PATH", str(env_path))
    assert _resolve_db_path(str(explicit)) == explicit
    assert _resolve_db_path(None) == env_path


def test_resolve_db_path_env_over_config(tmp_path, monkeypatch):
    env_path = tmp_path / "env.db"
    env_path.touch()
    monkeypatch.setenv("CHAN_SQLITE_DB_PATH", str(env_path))
    # Config path is patched to a different file
    config_path = tmp_path / "config.db"
    config_path.touch()
    monkeypatch.setattr("chan_strategy.config.SQLITE_DB_PATH", str(config_path))
    assert _resolve_db_path(None) == env_path


def test_resolve_db_path_falls_back_to_config(tmp_path, monkeypatch):
    monkeypatch.delenv("CHAN_SQLITE_DB_PATH", raising=False)
    config_path = tmp_path / "config.db"
    config_path.touch()
    monkeypatch.setattr("chan_strategy.config.SQLITE_DB_PATH", str(config_path))
    assert _resolve_db_path(None) == config_path


def test_resolve_db_path_explicit_nonexistent_wins(tmp_path, monkeypatch):
    explicit = tmp_path / "nonexistent.db"
    env_path = tmp_path / "env.db"
    env_path.touch()
    monkeypatch.setenv("CHAN_SQLITE_DB_PATH", str(env_path))
    assert _resolve_db_path(str(explicit)) == explicit


def test_historical_reports_are_declassified():
    from declassify_historical_reports import DECLASSIFY_MARKER, find_candidate_reports

    candidates = find_candidate_reports(DIAG)
    if not candidates:
        pytest.skip("no historical reports present in this checkout")
    missing = [
        p.name
        for p in candidates
        if DECLASSIFY_MARKER not in p.read_text(encoding="utf-8")
    ]
    assert not missing, f"historical reports missing declassification: {missing}"


def test_declassify_file_is_idempotent(tmp_path):
    from declassify_historical_reports import DECLASSIFY_MARKER, build_banner, declassify_file

    report = tmp_path / "test_report.md"
    report.write_text(
        "# Test Report\n\n| multiplier | pass |\n|---:|---|\n| 0.847 | True |\n",
        encoding="utf-8",
    )
    banner = build_banner()
    assert declassify_file(report, banner=banner) is True
    text = report.read_text(encoding="utf-8")
    assert DECLASSIFY_MARKER in text
    assert text.count(DECLASSIFY_MARKER) == 1
    assert declassify_file(report, banner=banner) is False
    assert report.read_text(encoding="utf-8").count(DECLASSIFY_MARKER) == 1


def test_find_candidate_reports_skips_logs_and_audit_diagnostics(tmp_path):
    from declassify_historical_reports import find_candidate_reports

    (tmp_path / "WORK_LOG.md").write_text("0.847 GOAL PASSED", encoding="utf-8")
    (tmp_path / "ACCEPTANCE.md").write_text("0.847 GOAL PASSED", encoding="utf-8")
    (tmp_path / "audit_issue_diagnostics_2026-07-03.md").write_text(
        "0.847 GOAL PASSED", encoding="utf-8"
    )
    (tmp_path / "candidate.md").write_text("0.847 pass", encoding="utf-8")
    found = find_candidate_reports(tmp_path)
    assert [p.name for p in found] == ["candidate.md"]
