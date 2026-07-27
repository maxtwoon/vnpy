import json
import sys
from pathlib import Path


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))

from simnow_backfill_pending_kline import _run_checked, build_backfill_plan, execute_backfill, pending_kline_dates  # noqa: E402


def _write_ledger(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")


def _write_export(path: Path, *, ap_enabled: bool = True, sc_enabled: bool = True) -> None:
    payload = {
        "meta": {
            "contract_map": {
                "AP888": {"symbol": "ap610", "exchange": "CZCE", "enabled": ap_enabled},
                "SC888": {"symbol": "sc2608", "exchange": "INE", "enabled": sc_enabled},
            }
        },
        "raw": {
            "ticks": [
                {
                    "dt": "2026-07-01 09:00:10+08:00",
                    "symbol": "sc2608",
                    "exchange": "INE",
                    "last_price": 450.0,
                    "volume": 200,
                },
                {
                    "dt": "2026-07-01 09:01:10+08:00",
                    "symbol": "sc2608",
                    "exchange": "INE",
                    "last_price": 451.0,
                    "volume": 205,
                },
            ]
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_pending_kline_dates_only_selects_kline_pending_rows():
    rows = [
        {"date": "2026-07-01", "status": "pending", "consistency": {"reason": "kline_coverage_incomplete"}},
        {"date": "2026-07-02", "status": "pending", "consistency": {"reason": "historical_db_lag"}},
        {"date": "2026-07-03", "status": "pending", "consistency": {"reason": "kline_coverage_too_short"}},
        {"date": "2026-07-04", "status": "halt", "consistency": {"reason": "kline_coverage_too_short"}},
    ]

    assert pending_kline_dates(rows) == ["2026-07-01", "2026-07-03"]
    assert pending_kline_dates(rows, requested_dates={"2026-07-03"}) == ["2026-07-03"]


def test_build_backfill_plan_marks_ready_when_current_contract_map_clears_missing_symbol(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    out_dir = tmp_path / "diagnostics"
    out_dir.mkdir()
    contract_map = tmp_path / "contract_map.json"
    contract_map.write_text(json.dumps({
        "_meta": {"version": "V1", "effective_date": "2026-07-22"},
        "AP888": {"symbol": "ap610", "exchange": "CZCE", "enabled": False},
        "SC888": {"symbol": "sc2608", "exchange": "INE", "enabled": True},
    }), encoding="utf-8")
    _write_ledger(ledger, [
        {"date": "2026-07-01", "status": "pending", "consistency": {"reason": "kline_coverage_incomplete"}},
    ])
    _write_export(out_dir / "simnow_export_2026-07-01.json")

    plan = build_backfill_plan(
        ledger_path=ledger,
        out_dir=out_dir,
        contract_map_path=contract_map,
        min_bars_per_symbol=2,
    )

    row = plan["rows"][0]
    assert plan["contract_map_provenance"]["version"] == "V1"
    assert plan["contract_map_provenance"]["enabled_symbols"] == ["SC888"]
    assert row["date"] == "2026-07-01"
    assert row["action"] == "ready_to_recompute"
    assert row["current_expected_symbols"] == ["SC888"]
    assert row["recomputed_missing_symbols"] == []
    assert row["recomputed_short_symbols"] == []
    assert row["simnow_json_exists"] is True


def test_build_backfill_plan_marks_still_blocked_when_short_symbols_remain(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    out_dir = tmp_path / "diagnostics"
    out_dir.mkdir()
    contract_map = tmp_path / "contract_map.json"
    contract_map.write_text(json.dumps({
        "_meta": {"version": "V1", "effective_date": "2026-07-22"},
        "SC888": {"symbol": "sc2608", "exchange": "INE", "enabled": True},
    }), encoding="utf-8")
    _write_ledger(ledger, [
        {"date": "2026-07-03", "status": "pending", "consistency": {"reason": "kline_coverage_too_short"}},
    ])
    _write_export(out_dir / "simnow_export_2026-07-03.json")

    plan = build_backfill_plan(
        ledger_path=ledger,
        out_dir=out_dir,
        contract_map_path=contract_map,
        min_bars_per_symbol=3,
    )

    row = plan["rows"][0]
    assert row["action"] == "still_blocked_after_recompute"
    assert row["recomputed_missing_symbols"] == []
    assert row["recomputed_short_symbols"] == ["SC888"]


def test_build_backfill_plan_requires_capture_export(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    out_dir = tmp_path / "diagnostics"
    out_dir.mkdir()
    contract_map = tmp_path / "contract_map.json"
    contract_map.write_text(json.dumps({
        "_meta": {"version": "V1", "effective_date": "2026-07-22"},
        "SC888": {"symbol": "sc2608", "exchange": "INE", "enabled": True},
    }), encoding="utf-8")
    _write_ledger(ledger, [
        {"date": "2026-07-05", "status": "pending", "consistency": {"reason": "kline_coverage_incomplete"}},
    ])

    plan = build_backfill_plan(
        ledger_path=ledger,
        out_dir=out_dir,
        contract_map_path=contract_map,
        min_bars_per_symbol=1,
    )

    row = plan["rows"][0]
    assert row["action"] == "missing_simnow_export"
    assert row["simnow_json_exists"] is False


def test_run_checked_accepts_monitor_halt_exit_code(monkeypatch):
    class _Result:
        returncode = 2

    def _fake_run(args, cwd, check):  # type: ignore[no-untyped-def]
        return _Result()

    monkeypatch.setattr("simnow_backfill_pending_kline.subprocess.run", _fake_run)

    _run_checked(["python", "simnow_daily_monitor.py"], accepted_exit_codes={0, 2})


def test_execute_backfill_refreshes_summary_artifacts(monkeypatch, tmp_path):
    commands: list[list[str]] = []

    def _fake_run_checked(args, accepted_exit_codes=None):  # type: ignore[no-untyped-def]
        commands.append(list(args))

    monkeypatch.setattr("simnow_backfill_pending_kline._run_checked", _fake_run_checked)
    replay_json = tmp_path / "simnow_replay_2026-07-16.json"
    replay_json.write_text("{}", encoding="utf-8")
    plan = {
        "contract_map": str(tmp_path / "contract_map.json"),
        "min_bars_per_symbol": 30,
        "rows": [
            {
                "date": "2026-07-16",
                "action": "ready_to_recompute",
                "simnow_json": str(tmp_path / "simnow_export_2026-07-16.json"),
                "kline_json": str(tmp_path / "simnow_kline_update_2026-07-16.json"),
                "replay_json": str(replay_json),
                "record_json": str(tmp_path / "simnow_record_2026-07-16.json"),
                "report_md": str(tmp_path / "simnow_report_2026-07-16.md"),
            }
        ]
    }
    ledger = tmp_path / "ledger.jsonl"
    thresholds = tmp_path / "thresholds.json"
    promotion = tmp_path / "promotion.md"

    result = execute_backfill(plan, thresholds, ledger, promotion)

    assert result["rows"][0]["action"] == "recomputed"
    joined = [" ".join(cmd) for cmd in commands]
    assert any("simnow_tick_bars.py" in cmd for cmd in joined)
    assert any("simnow_daily_monitor.py" in cmd for cmd in joined)
    assert any("simnow_ledger_summary.py" in cmd for cmd in joined)
    assert any("simnow_promotion_decision.py" in cmd for cmd in joined)
    assert any("simnow_run_summary.py" in cmd for cmd in joined)
    assert any("simnow_daily_brief.py" in cmd for cmd in joined)
    assert any("simnow_summary_consistency.py" in cmd for cmd in joined)
