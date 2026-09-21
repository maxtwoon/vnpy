"""Focused tests for the delivery04f ETF loop helper config surface.

These tests cover ONLY the deterministic, native-independent logic of
``tools/delivery_etf_loop.py``: config validation, config-identity stability,
window derivation and the pure VWAP/OHLC expectation helpers. They do NOT
exercise the native Database/Alpha consumers or the real store — the real
same-snapshot loop is executed by the runner itself and recorded as machine
evidence under .coordination/delivery04f-dev (see
.coordination/opencode-delivery04f-handoff.md).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from tools.delivery_etf_loop import (
    BOOTSTRAP_BACKTESTERS,
    CONFIG_KEYS,
    compare_numeric,
    compare_rows,
    consumer_rows_digest,
    derive_bootstrap_config,
    expanded_window,
    lunch_edge_summary,
    load_config,
    minute_nonaligned_end,
    normalize_expectation,
    value_rows_digest,
)

INSTANCE_CONFIG = Path("D:/quant-data/configs/delivery_etf_loop.json")


def test_instance_config_exists_and_has_required_keys() -> None:
    assert INSTANCE_CONFIG.exists(), "instance config must be present under D:/quant-data/configs"
    raw = json.loads(INSTANCE_CONFIG.read_text(encoding="utf-8"))
    for key in ("store_root", "snapshot_id", "runtime_dir", "repo_path", "symbols", "windows"):
        assert raw.get(key), f"instance config missing required key {key!r}"
    assert raw["snapshot_id"] == "snap-030369f20bd18303"
    assert raw["store_root"] == "D:/quant-data"
    assert raw["dataset_ids"]["daily"] == "ds-d939147fd6b633fd348fa62ed1fef74c"
    assert raw["dataset_ids"]["minute"] == "ds-b9bbad83ec09f4b9dcef6ea9a81c4b51"
    assert raw["source_identities"] == ["510130.XSHG", "510300.XSHG"]


def test_instance_config_bootstrap_and_source_reference() -> None:
    raw = json.loads(INSTANCE_CONFIG.read_text(encoding="utf-8"))
    bootstrap = raw["bootstrap"]
    assert bootstrap["backtesters"] == ["cta", "portfolio"]
    reference = raw["source_reference"]
    for identity in ("510130.XSHG", "510300.XSHG"):
        windows = reference["windows"][identity]
        assert windows == {
            "minute_base_rows": 960,
            "minute_ext_rows": 2640,
            "daily_base_rows": 4,
            "daily_ext_rows": 11,
        }
    for native_symbol in ("510130", "510300"):
        minute = reference["overview"][native_symbol]["1m"]
        assert minute["count"] == 4800
        assert minute["start"] == "2016-01-04T09:30:00"
        assert minute["end"] == "2016-01-29T14:59:00"
        daily = reference["overview"][native_symbol]["1d"]
        assert daily["count"] == 244
        assert daily["start"] == "2016-01-04T00:00:00"
        assert daily["end"] == "2016-12-30T00:00:00"
    pinned = reference["pinned_source_rows"]
    assert pinned["510130.XSHG"]["2016-01-18 09:31:00"]["volume"] == 0.0
    assert pinned["510130.XSHG"]["2016-01-18 13:01:00"]["turnover"] == 655.0
    assert pinned["510300.XSHG"]["2016-01-18 09:31:00"]["volume"] == 11817500.0


def test_load_config_accepts_instance_config() -> None:
    config, identity = load_config(INSTANCE_CONFIG)
    assert config["snapshot_id"] == "snap-030369f20bd18303"
    assert config["symbols"] == ["510130.SSE", "510300.SSE"]
    assert config["windows"]["minute"] == {
        "start": "2016-01-18 09:30:00",
        "end": "2016-01-21 14:59:00",
    }
    assert config["windows"]["daily"] == {
        "start": "2016-01-18 00:00:00",
        "end": "2016-01-21 00:00:00",
    }
    assert identity and len(identity) == 64


def test_load_config_identity_is_stable() -> None:
    _, id_a = load_config(INSTANCE_CONFIG)
    _, id_b = load_config(INSTANCE_CONFIG)
    assert id_a == id_b


def test_load_config_rejects_unknown_keys(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps(
            {
                "store_root": "D:/quant-data",
                "snapshot_id": "snap-x",
                "runtime_dir": "D:/quant-data/runtime/x",
                "repo_path": "D:/repo/vnpy",
                "symbols": ["510130.SSE"],
                "windows": {"minute": {"start": "2016-01-18 09:30:00", "end": "2016-01-21 14:59:00"}},
                "not_a_real_key": 1,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        load_config(bad)


def test_load_config_rejects_missing_required(tmp_path: Path) -> None:
    bad = tmp_path / "missing.json"
    bad.write_text(json.dumps({"store_root": "D:/quant-data"}), encoding="utf-8")
    with pytest.raises(SystemExit):
        load_config(bad)


def test_load_config_rejects_bad_bootstrap(tmp_path: Path) -> None:
    base = {
        "store_root": "D:/quant-data",
        "snapshot_id": "snap-x",
        "runtime_dir": "D:/quant-data/runtime/x",
        "repo_path": "D:/repo/vnpy",
        "symbols": ["510130.SSE"],
        "windows": {"minute": {"start": "2016-01-18 09:30:00", "end": "2016-01-21 14:59:00"}},
    }
    bad_unknown = dict(base, bootstrap={"nope": 1})
    path1 = tmp_path / "boot1.json"
    path1.write_text(json.dumps(bad_unknown), encoding="utf-8")
    with pytest.raises(SystemExit):
        load_config(path1)
    bad_backtester = dict(base, bootstrap={"backtesters": ["gateway"]})
    path2 = tmp_path / "boot2.json"
    path2.write_text(json.dumps(bad_backtester), encoding="utf-8")
    with pytest.raises(SystemExit):
        load_config(path2)


def test_config_keys_set_is_explicit() -> None:
    # The helper must declare exactly the keys it consumes; no silent passthrough.
    expected = {
        "store_root", "snapshot_id", "runtime_dir", "repo_path", "integration_path",
        "database_timezone", "exchange_map", "allow_missing_auxiliary",
        "dataset_ids", "symbols", "source_identities", "windows", "lab_path",
        "bootstrap", "source_reference",
    }
    assert CONFIG_KEYS == expected


def test_derive_bootstrap_config_binds_same_snapshot() -> None:
    config, _ = load_config(INSTANCE_CONFIG)
    derived = derive_bootstrap_config(config)
    assert derived["snapshot_id"] == config["snapshot_id"]
    assert derived["store_root"] == config["store_root"]
    assert derived["runtime_dir"] == config["runtime_dir"]
    assert derived["repo_path"] == config["repo_path"]
    assert derived["integration_path"] == config["integration_path"]
    assert derived["allow_missing_auxiliary"] is False
    assert derived["backtesters"] == ["cta", "portfolio"]
    assert derived["range"] == {
        "start": "2016-01-18 09:30:00",
        "end": "2016-01-21 14:59:00",
    }
    assert set(derived) <= {
        "store_root", "snapshot_id", "runtime_dir", "repo_path", "integration_path",
        "allow_missing_auxiliary", "exchange_map", "database_timezone",
        "backtesters", "range",
    }


def test_derive_bootstrap_config_defaults_without_section(tmp_path: Path) -> None:
    config = {
        "store_root": "s",
        "snapshot_id": "snap-x",
        "runtime_dir": "r",
        "repo_path": "D:/repo/vnpy",
        "symbols": ["510130.SSE"],
        "windows": {"minute": {"start": "2016-01-18 09:30:00", "end": "2016-01-21 14:59:00"}},
    }
    derived = derive_bootstrap_config(config)
    assert derived["backtesters"] == list(BOOTSTRAP_BACKTESTERS)
    assert "range" not in derived
    assert derived["integration_path"].endswith("vnpy_researchstore")


def test_minute_nonaligned_end_excludes_next_minute() -> None:
    assert minute_nonaligned_end("2016-01-21 14:59:00") == "2016-01-21 14:58:30"


def test_expanded_window_native_semantics() -> None:
    assert expanded_window("2016-01-18 09:30:00", "2016-01-21 14:59:00", 0) == (
        "2016-01-18 09:30:00",
        "2016-01-21 14:59:00",
    )
    assert expanded_window("2016-01-18 09:30:00", "2016-01-21 14:59:00", 10) == (
        "2016-01-08 09:30:00",
        "2016-01-22 14:59:00",
    )


def test_normalize_expectation_first_close_and_vwap() -> None:
    rows = [
        {"datetime": "t0", "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.0,
         "volume": 200.0, "turnover": 2100.0, "open_interest": 0.0},
        {"datetime": "t1", "open": 10.5, "high": 10.5, "low": 10.5, "close": 10.5,
         "volume": 0.0, "turnover": 0.0, "open_interest": 0.0},
    ]
    expected = normalize_expectation(rows)
    assert expected[0]["datetime"] == "t0"
    assert expected[0]["close"] == 1.0
    assert expected[1]["open"] == 1.05
    assert expected[0]["vwap"] == 2100.0 / 200.0
    # zero volume yields MISSING vwap, never zero, and OHLC is preserved
    assert math.isnan(expected[1]["vwap"])
    assert expected[1]["close"] == 10.5 / 10.0
    assert expected[1]["volume"] == 0.0
    assert expected[1]["turnover"] == 0.0


def test_normalize_expectation_all_zero_row_masked() -> None:
    rows = [
        {"datetime": "t0", "open": 10.0, "high": 10.0, "low": 10.0, "close": 10.0,
         "volume": 100.0, "turnover": 1000.0, "open_interest": 0.0},
        {"datetime": "t1", "open": 0.0, "high": 0.0, "low": 0.0, "close": 0.0,
         "volume": 0.0, "turnover": 0.0, "open_interest": 0.0},
    ]
    expected = normalize_expectation(rows)
    assert expected[1]["datetime"] == "t1"
    for field in ("open", "high", "low", "close", "volume", "turnover", "vwap"):
        assert math.isnan(expected[1][field])


def test_compare_numeric_missing_and_tolerance() -> None:
    assert compare_numeric(math.nan, math.nan) is None
    assert compare_numeric(None, math.nan) is None
    assert compare_numeric(1.0, math.nan) is not None
    assert compare_numeric(3.0, 3.0) is None
    assert compare_numeric(1.0, 1.0 + 1e-12) is None
    assert compare_numeric(1.0, 1.001) is not None
    assert compare_numeric(5.0, 5.0, rel_tol=0.0) is None
    assert compare_numeric(5.0, 5.0000001, rel_tol=0.0) is not None


def test_compare_rows_reports_mismatch() -> None:
    exp = [
        {"datetime": "a", "open": 1.0, "vwap": math.nan},
        {"datetime": "b", "open": 2.0, "vwap": 3.0},
    ]
    act = [
        {"datetime": "a", "open": 1.0, "vwap": math.nan},
        {"datetime": "b", "open": 2.5, "vwap": 3.0},
    ]
    assert compare_rows(exp, act, ["open", "vwap"]) == [
        "row 1 @ b open: expected=2.0 actual=2.5"
    ]
    assert compare_rows(exp, exp, ["open", "vwap"]) == []
    assert compare_rows(exp, act[:1], ["open"]) == [
        "row count expected=2 actual=1"
    ]


def test_lunch_edge_summary() -> None:
    rows = [
        {"datetime": "2016-01-18T09:30:00"},
        {"datetime": "2016-01-18T11:29:00"},
        {"datetime": "2016-01-18T13:00:00"},
        {"datetime": "2016-01-18T14:59:00"},
    ]
    summary = lunch_edge_summary(rows)
    day = summary["days"]["2016-01-18"]
    assert day["count"] == 4
    assert day["first"].endswith("09:30:00")
    assert day["last"].endswith("14:59:00")
    assert day["lunch_bars"] == []
    assert summary["lunch_bars_total"] == 0
    rows.append({"datetime": "2016-01-18T12:30:00"})
    summary = lunch_edge_summary(rows)
    assert summary["days"]["2016-01-18"]["lunch_bars"] == ["12:30:00"]
    assert summary["lunch_bars_total"] == 1


def test_digests_are_order_and_value_sensitive() -> None:
    rows_a = [
        {"datetime": "t0", "open": 1.0, "high": 1.0, "low": 1.0,
         "close": 1.0, "volume": 1.0, "turnover": 1.0},
        {"datetime": "t1", "open": 2.0, "high": 2.0, "low": 2.0,
         "close": 2.0, "volume": 2.0, "turnover": 2.0},
    ]
    rows_same = [dict(r) for r in rows_a]
    rows_reordered = [dict(r) for r in reversed(rows_a)]
    rows_changed = [dict(r) for r in rows_a]
    rows_changed[1]["volume"] = 3.0
    assert value_rows_digest(rows_a) == value_rows_digest(rows_same)
    assert value_rows_digest(rows_a) != value_rows_digest(rows_reordered)
    assert value_rows_digest(rows_a) != value_rows_digest(rows_changed)
    # provenance digest separates on source_label/trading_date
    prov_a = [dict(r, source_label="l0", trading_date="d0") for r in rows_a]
    prov_b = [dict(r, source_label="l0", trading_date="d1") for r in rows_a]
    assert consumer_rows_digest(prov_a) != consumer_rows_digest(prov_b)
    assert consumer_rows_digest(prov_a) == consumer_rows_digest(
        [dict(r, source_label="l0", trading_date="d0") for r in rows_a]
    )
