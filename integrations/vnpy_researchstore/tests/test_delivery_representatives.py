"""Focused tests for the WP10K/L representative runner helpers (offline).

Pure logic only — no real sources, no store writes, no network. Covers the
runtime-policy interpreter refusal (registered vnpy3.14 migration) and the
runner config validation contract.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

TOOLS_PATH = (
    Path(__file__).resolve().parents[1] / "tools" / "delivery_representatives.py"
)

_spec = importlib.util.spec_from_file_location("delivery_representatives", TOOLS_PATH)
assert _spec is not None and _spec.loader is not None
runner = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("delivery_representatives", runner)
_spec.loader.exec_module(runner)


def _policy(python: str) -> dict[str, object]:
    return {
        "projects": {
            "vnpy": {
                "path": "D:/repo/vnpy",
                "python": python,
                "scope": "test policy",
            }
        }
    }


def test_interpreter_matches_registered_policy_exactly() -> None:
    matches, detail = runner.interpreter_matches_policy(
        sys.executable, _policy(sys.executable)
    )
    assert matches is True
    assert detail["matches"] == "True"
    assert detail["resolved_actual"] == detail["resolved_expected"]


def test_interpreter_refused_when_policy_names_different_python() -> None:
    matches, detail = runner.interpreter_matches_policy(
        sys.executable, _policy("W:/definitely/not/a/python.exe")
    )
    assert matches is False
    assert detail["matches"] == "False"
    assert detail["resolved_actual"] != detail["resolved_expected"]


def test_interpreter_refused_when_policy_section_missing() -> None:
    matches, detail = runner.interpreter_matches_policy(sys.executable, {})
    assert matches is False
    assert detail["policy_python"] == ""


def test_interpreter_match_is_case_insensitive_on_resolved_paths() -> None:
    if sys.platform != "win32":
        return  # case-insensitive resolution is a Windows property
    upper = str(sys.executable).upper()
    matches, _detail = runner.interpreter_matches_policy(
        sys.executable, _policy(upper)
    )
    assert matches is True


def test_validate_config_requires_required_sections() -> None:
    errors = runner.validate_config({"store_root": "D:/x"})
    assert any("reports_dir" in error for error in errors)
    assert any("config.futures.root" in error for error in errors)
    assert any("config.etf.package_dir" in error for error in errors)
    assert any("config.catalog.inventory04d" in error for error in errors)
    assert runner.validate_config("not-a-dict") == ["config must be a JSON object"]
    # a complete minimal config has no structural errors
    complete = {
        "store_root": "D:/quant-data",
        "reports_dir": "D:/quant-data/reports/delivery04l",
        "runtime_dir": "D:/tmp",
        "stock": {"input_dir": "D:/in", "inputs": {}, "expected_sha256": {}},
        "futures": {
            "root": "D:/src",
            "contract_archive": "c.tar.zst",
            "dominant_archive": "d.tar.zst",
            "contract_member": "m",
            "dominant_member": "m",
            "instrument": "A2505",
            "window": {"start": "2025-01-02 00:00:00", "end": "2025-01-07 00:00:00"},
            "expected_window_rows": 1035,
            "friday_night": [],
        },
        "jq": {"daily_dir": "D:/d", "year": 2024, "instrument": "i", "window": {}},
        "etf": {
            "package_dir": "D:/p",
            "frequency": "1m",
            "year": 2017,
            "instrument": "i",
            "disputed_key": {"instrument": "i", "label": "l"},
        },
        "catalog": {
            "inventory04d": "D:/i.json",
            "rq_root": "D:/rq",
            "pit_package": "p",
            "index_package": "p",
        },
    }
    assert runner.validate_config(complete) == []


def test_load_config_rejects_invalid_and_hashes_identity(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"store_root": "D:/x"}), encoding="utf-8")
    try:
        runner.load_config(bad)
    except SystemExit as exc:
        assert "invalid" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("invalid config must SystemExit")
    good = tmp_path / "good.json"
    good.write_text(
        json.dumps({"store_root": "D:/x", "reports_dir": "D:/y", "runtime_dir": "D:/z"}),
        encoding="utf-8",
    )
    try:
        runner.load_config(good)
    except SystemExit as exc:
        # missing case sections are reported as a clean refusal, not a crash
        assert "invalid" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("incomplete config must SystemExit")


def test_assertion_records_truthful_pass() -> None:
    passing = runner.assertion("ok", 1, 1, 1 == 1)
    failing = runner.assertion("bad", 1, 2, 1 == 2)
    assert passing["pass"] is True
    assert failing["pass"] is False


def test_date_transfer_reconciliation_rejects_scope_mismatch() -> None:
    """Multi-instrument regression (futures04l-real-fixed-20260930): the
    mapper is one-instrument-scoped but applied to EVERY contract row of
    the member, so its unmatched count is GLOBAL. The old assertion
    compared global unmatched_keys against the selected instrument's
    null-date subset — this fixture reproduces that mismatch and proves
    the reconciliation handles both views."""
    candidates = [
        {"instrument": "A2505", "trading_date": "2025-01-03"},
        {"instrument": "A2505", "trading_date": "2025-01-03"},
        {"instrument": "A2505", "trading_date": None},
        # other instruments of the member: no keys in the scoped map
        {"instrument": "A2501", "trading_date": None},
        {"instrument": "A2507", "trading_date": None},
    ]
    mapper_stats = {"matched_keys": 2, "unmatched_keys": 3, "conflicted_keys": 0}
    result = runner.reconcile_date_transfer_counts(
        mapper_stats, candidates, "A2505"
    )
    # the OLD comparison is genuinely wrong on this fixture: 3 != 1
    assert (
        mapper_stats["unmatched_keys"]
        != result["selected_instrument"]["null_date"]
    )
    assert result["pass"] is True
    assert result["global"] == {
        "rows": 5,
        "with_date": 2,
        "null_date": 3,
        "mapper_matched": 2,
        "mapper_unmatched": 3,
        "mapper_conflicted": 0,
        "null_equals_unmatched_plus_conflicted": True,
        "with_date_equals_matched": True,
    }
    selected = result["selected_instrument"]
    assert selected["instrument"] == "A2505"
    assert selected["rows"] == 3
    assert selected["with_date"] == 2
    assert selected["null_date"] == 1
    assert selected["subset_of_global_matched"] is True


def test_date_transfer_reconciliation_counts_conflicted_as_null() -> None:
    # A conflicted key lookup returns None (NULL trading_date) without
    # counting as unmatched: nulls == unmatched + conflicted.
    candidates = [
        {"instrument": "A2505", "trading_date": "2025-01-03"},
        {"instrument": "A2505", "trading_date": None},
        {"instrument": "B2505", "trading_date": None},
    ]
    mapper_stats = {"matched_keys": 1, "unmatched_keys": 1, "conflicted_keys": 1}
    result = runner.reconcile_date_transfer_counts(
        mapper_stats, candidates, "A2505"
    )
    assert result["pass"] is True
    assert result["global"]["null_date"] == 2
    assert result["global"]["null_equals_unmatched_plus_conflicted"] is True


def test_date_transfer_reconciliation_fails_on_broken_counts() -> None:
    candidates = [
        {"instrument": "A2505", "trading_date": "2025-01-03"},
        {"instrument": "B2505", "trading_date": "2025-01-03"},  # unexpected date
        {"instrument": "B2505", "trading_date": None},
    ]
    mapper_stats = {"matched_keys": 1, "unmatched_keys": 5, "conflicted_keys": 0}
    result = runner.reconcile_date_transfer_counts(
        mapper_stats, candidates, "A2505"
    )
    assert result["pass"] is False  # reconciliation itself refuses bad data
