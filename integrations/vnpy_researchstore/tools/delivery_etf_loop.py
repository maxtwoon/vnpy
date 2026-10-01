"""WP10 delivery04f — real ETF same-snapshot consumer loop.

Runs ONE fresh process that binds the repository vnpy path and an isolated
runtime cwd BEFORE any ``vnpy.trader.utility`` import, then reads the SAME
research-store snapshot through every qualified consumer surface:

* core ``SnapshotReader.bars`` (observational row identity / source values),
* native ``Database.load_bar_data`` with BARE native symbols
  (``510130``/``510300`` + ``Exchange.SSE`` — the documented post-native06
  contract; compound vendor symbols are never a consumer input),
* ``ResearchAlphaLab.load_bar_data`` (Alpha raw) and
* ``ResearchAlphaLab.load_bar_df`` (extended_days windowing, OHLC
  first-close normalization, VWAP preprocessing),
* offline CTA and Portfolio bootstrap + bar loading against the SAME
  snapshot in a fresh child process (no strategies, orders, gateways,
  accounts, or network),
* read-only ``research_store verify`` of the bound snapshot.

Checks compare inclusive / nonaligned / extended windows, original VWAP and
OHLC math, zero-volume behavior, source END-label mapping, pinned source
rows, snapshot overview counts, import idempotency receipts and the 133-key
repair-index evidence. Every check result is recorded; any failed check
makes the run FAIL (exit 2) — a failed consumer is never reported as PASS
and no compatibility trick forces a pass.

No gateway, account, strategy, or network access. Store writes happen only
through public read-only APIs; the lab directory is snapshot-bound.

Usage:
    python tools/delivery_etf_loop.py --config <instance delivery_etf_loop.json>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
import tracemalloc
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CONFIG_KEYS = {
    "store_root",
    "snapshot_id",
    "runtime_dir",
    "repo_path",
    "integration_path",
    "database_timezone",
    "exchange_map",
    "allow_missing_auxiliary",
    "dataset_ids",
    "symbols",
    "source_identities",
    "windows",
    "lab_path",
    "bootstrap",
    "source_reference",
}

REQUIRED_KEYS = (
    "store_root",
    "snapshot_id",
    "runtime_dir",
    "repo_path",
    "symbols",
    "windows",
)

BOOTSTRAP_BACKTESTERS = ("cta", "portfolio")

DF_COLUMNS = [
    "datetime",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "turnover",
    "open_interest",
    "vwap",
    "vt_symbol",
]


def load_config(path: str | Path) -> tuple[dict[str, Any], str]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SystemExit(f"config {path} must be a JSON object")
    unknown = sorted(k for k in raw if k not in CONFIG_KEYS and not k.startswith("_"))
    if unknown:
        raise SystemExit(f"config {path} has unknown keys {unknown}")
    for key in REQUIRED_KEYS:
        if not raw.get(key):
            raise SystemExit(f"config {path} missing required key {key!r}")
    bootstrap = raw.get("bootstrap")
    if bootstrap is not None:
        if not isinstance(bootstrap, dict):
            raise SystemExit(f"config {path} bootstrap must be an object")
        bad = sorted(set(bootstrap) - {"backtesters", "range"})
        if bad:
            raise SystemExit(f"config {path} bootstrap has unknown keys {bad}")
        for name in bootstrap.get("backtesters", BOOTSTRAP_BACKTESTERS):
            if name not in BOOTSTRAP_BACKTESTERS:
                raise SystemExit(
                    f"config {path} bootstrap backtester {name!r} unknown; "
                    f"known: {list(BOOTSTRAP_BACKTESTERS)}"
                )
    identity = hashlib.sha256(
        json.dumps(raw, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return raw, identity


def derive_bootstrap_config(config: dict[str, Any]) -> dict[str, Any]:
    """Derive the ``vnpy_researchstore.bootstrap`` config from the loop config.

    Same store root, snapshot, repo/integration paths, timezone and auxiliary
    policy — the child process binds the IDENTICAL snapshot. Only the
    bootstrap-specific ``backtesters``/``range`` keys are added.
    """

    derived: dict[str, Any] = {
        "store_root": config["store_root"],
        "snapshot_id": config["snapshot_id"],
        "runtime_dir": config["runtime_dir"],
        "repo_path": config["repo_path"],
        "integration_path": config.get("integration_path")
        or str(Path(__file__).resolve().parents[1]),
        "allow_missing_auxiliary": bool(config.get("allow_missing_auxiliary", False)),
        "database_timezone": config.get("database_timezone"),
    }
    if config.get("exchange_map"):
        derived["exchange_map"] = config["exchange_map"]
    bootstrap = config.get("bootstrap") or {}
    derived["backtesters"] = list(bootstrap.get("backtesters", BOOTSTRAP_BACKTESTERS))
    if bootstrap.get("range"):
        derived["range"] = bootstrap["range"]
    return derived


# ---------------------------------------------------------------------------
# Pure window / expectation helpers (unit-testable, native-independent)
# ---------------------------------------------------------------------------


def parse_dt(text: str) -> datetime:
    return datetime.strptime(text[:19].replace("T", " "), "%Y-%m-%d %H:%M:%S")


def minute_nonaligned_end(end_text: str) -> str:
    """Nonaligned inclusive-end probe: base minute end minus 30 seconds.

    The bar stamped ``end`` (e.g. 14:59) must then be EXCLUDED while 14:58
    stays the last returned bar — an end between two minute stamps is never
    rounded up to include the next bar.
    """

    return (parse_dt(end_text) - timedelta(seconds=30)).strftime("%Y-%m-%d %H:%M:%S")


def expanded_window(start_text: str, end_text: str, extended_days: int) -> tuple[str, str]:
    """Alpha ``load_bar_df`` window expansion (native semantics).

    ``start - extended_days`` days and ``end + extended_days // 10`` days.
    """

    start = parse_dt(start_text) - timedelta(days=extended_days)
    end = parse_dt(end_text) + timedelta(days=extended_days // 10)
    return start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")


def canonical_rows_digest(rows: list[dict[str, Any]]) -> str:
    """Order-sensitive sha256 over canonical JSON lines of row dicts."""

    lines = [json.dumps(row, sort_keys=True, separators=(",", ":")) for row in rows]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


VALUE_KEYS = ("open", "high", "low", "close", "volume", "turnover")
PROVENANCE_KEYS = VALUE_KEYS + ("source_label", "trading_date")


def _selected_rows_digest(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> str:
    lines = []
    for row in rows:
        line = json.dumps(
            {"datetime": row["datetime"], **{k: row[k] for k in keys}},
            sort_keys=True,
            separators=(",", ":"),
        )
        lines.append(line)
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def value_rows_digest(rows: list[dict[str, Any]]) -> str:
    """Digest over the VALUE identity of consumer rows (source OHLCV/turnover)."""

    return _selected_rows_digest(rows, VALUE_KEYS)


def consumer_rows_digest(rows: list[dict[str, Any]]) -> str:
    """Digest over value identity PLUS source_label/trading_date provenance."""

    return _selected_rows_digest(rows, PROVENANCE_KEYS)


def is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def normalize_expectation(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Independently derived Alpha dataframe expectation (plan section 2).

    Per symbol: OHLC divided by the FIRST close in the actual expanded
    window; volume/turnover/open_interest unchanged; VWAP = turnover/volume
    in original price units, missing (NaN) when volume is zero; a fully zero
    row (suspended) would be masked to NaN. NaN propagates through the
    native ``sum_horizontal`` mask, so an all-zero row that already carries
    a NaN VWAP is never masked in practice — and this ETF window contains
    no all-zero row (asserted separately), keeping mask semantics out of
    scope for this loop.
    """

    if not rows:
        return []
    close_0 = rows[0]["close"]
    expected: list[dict[str, Any]] = []
    for row in rows:
        all_zero = (
            row["open"] == 0
            and row["high"] == 0
            and row["low"] == 0
            and row["close"] == 0
            and row["volume"] == 0
            and (row["turnover"] == 0 or is_missing(row["turnover"]))
            and row["open_interest"] == 0
        )
        normalized: dict[str, Any] = {"datetime": row["datetime"]}
        if all_zero:
            normalized.update({
                "open": math.nan,
                "high": math.nan,
                "low": math.nan,
                "close": math.nan,
                "volume": math.nan,
                "turnover": math.nan,
                "open_interest": math.nan,
                "vwap": math.nan,
            })
        else:
            normalized.update({
                "open": row["open"] / close_0,
                "high": row["high"] / close_0,
                "low": row["low"] / close_0,
                "close": row["close"] / close_0,
                "volume": row["volume"],
                "turnover": row["turnover"],
                "open_interest": row["open_interest"],
                "vwap": (
                    math.nan
                    if row["volume"] == 0
                    else row["turnover"] / row["volume"]
                ),
            })
        expected.append(normalized)
    return expected


def compare_numeric(expected: Any, actual: Any, rel_tol: float = 1e-9) -> str | None:
    """Numeric comparison treating NaN/None as mutually missing."""

    if is_missing(expected) or is_missing(actual):
        if is_missing(expected) and is_missing(actual):
            return None
        return f"expected={expected!r} actual={actual!r}"
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        if expected == actual:
            return None
        scale = max(abs(float(expected)), abs(float(actual)), 1e-300)
        if abs(float(expected) - float(actual)) <= rel_tol * scale:
            return None
    return f"expected={expected!r} actual={actual!r}"


def compare_rows(
    expected_rows: list[dict[str, Any]],
    actual_rows: list[dict[str, Any]],
    fields: list[str],
    rel_tol: float = 1e-9,
) -> list[str]:
    """Row-by-row field comparison; returns human-readable mismatch list."""

    problems: list[str] = []
    if len(expected_rows) != len(actual_rows):
        problems.append(
            f"row count expected={len(expected_rows)} actual={len(actual_rows)}"
        )
        return problems
    for i, (exp, act) in enumerate(zip(expected_rows, actual_rows, strict=True)):
        if exp["datetime"] != act["datetime"]:
            problems.append(
                f"row {i} datetime expected={exp['datetime']!r} actual={act['datetime']!r}"
            )
            continue
        for field in fields:
            mismatch = compare_numeric(exp[field], act[field], rel_tol)
            if mismatch:
                problems.append(f"row {i} @ {act['datetime']} {field}: {mismatch}")
                if len(problems) > 20:
                    problems.append("... (mismatch list truncated at 20)")
                    return problems
    return problems


def lunch_edge_summary(minute_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-day minute-session edges: first/last bar, count, lunch-gap bars."""

    by_day: dict[str, list[datetime]] = {}
    for row in minute_rows:
        dt = parse_dt(row["datetime"])
        by_day.setdefault(dt.strftime("%Y-%m-%d"), []).append(dt)
    days: dict[str, Any] = {}
    lunch_bars = 0
    for day in sorted(by_day):
        stamps = sorted(by_day[day])
        in_lunch = [
            dt
            for dt in stamps
            if (dt.hour, dt.minute) >= (11, 30) and (dt.hour, dt.minute) <= (12, 59)
        ]
        lunch_bars += len(in_lunch)
        days[day] = {
            "count": len(stamps),
            "first": stamps[0].strftime("%Y-%m-%d %H:%M:%S"),
            "last": stamps[-1].strftime("%Y-%m-%d %H:%M:%S"),
            "lunch_bars": [dt.strftime("%H:%M:%S") for dt in in_lunch],
        }
    return {"days": days, "lunch_bars_total": lunch_bars}


# ---------------------------------------------------------------------------
# Offline CTA/Portfolio bootstrap child (fresh process, same snapshot)
# ---------------------------------------------------------------------------

BOOTSTRAP_CHILD_SCRIPT = r'''
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path


def _pdt(text):
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")


def main():
    boot_cfg_path = Path(sys.argv[1])
    main_cfg_path = Path(sys.argv[2])
    raw = json.loads(boot_cfg_path.read_text(encoding="utf-8"))
    sys.path.insert(0, str(Path(raw["integration_path"]).resolve()))
    sys.path.insert(0, str(Path(raw["repo_path"]).resolve()))
    from vnpy_researchstore.bootstrap import bootstrap_session, load_config
    config, identity = load_config(boot_cfg_path)
    session = bootstrap_session(config, identity)
    from vnpy.trader.constant import Interval
    from vnpy_ctastrategy.backtesting import BacktestingEngine as CtaEngine
    from vnpy_portfoliostrategy.backtesting import BacktestingEngine as PfEngine
    main_cfg = json.loads(main_cfg_path.read_text(encoding="utf-8"))
    windows = main_cfg["windows"]
    symbols = list(main_cfg["symbols"])
    engines = {}
    for interval_key, interval in (("minute", Interval.MINUTE), ("daily", Interval.DAILY)):
        win = windows[interval_key]
        start = _pdt(win["start"])
        end = _pdt(win["end"])
        for sym in symbols:
            engine = CtaEngine()
            engine.set_parameters(
                sym, interval, start, 0.0, 0.0, 1.0, 0.0,
                capital=1000000, end=end,
            )
            engine.load_data()
            bars = engine.history_data
            engines["cta/" + interval_key + "/" + sym] = {
                "rows": len(bars),
                "first": bars[0].datetime.isoformat() if bars else None,
                "last": bars[-1].datetime.isoformat() if bars else None,
                "module": type(engine).__module__,
            }
        engine = PfEngine()
        engine.set_parameters(
            symbols, interval, start, {}, {}, {}, {},
            capital=1000000, end=end,
        )
        engine.load_data()
        per_symbol = {}
        for key in engine.history_data:
            per_symbol[key[1]] = per_symbol.get(key[1], 0) + 1
        dts = sorted(engine.dts)
        engines["portfolio/" + interval_key] = {
            "rows": len(engine.history_data),
            "dts": len(engine.dts),
            "per_symbol": per_symbol,
            "first": dts[0].isoformat() if dts else None,
            "last": dts[-1].isoformat() if dts else None,
            "module": type(engine).__module__,
        }
    payload = {
        "config_identity": identity,
        "receipt": session.receipt,
        "engines": engines,
        "bootstrap_config_path": str(boot_cfg_path),
        "python": sys.executable,
    }
    print(json.dumps(payload, default=str))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
'''


# ---------------------------------------------------------------------------
# Process bootstrap ordering: path + cwd BEFORE any vnpy.trader import
# ---------------------------------------------------------------------------

def _prepare_process(config: dict[str, Any]) -> dict[str, Any]:
    if "vnpy.trader.utility" in sys.modules:
        raise SystemExit(
            "vnpy.trader.utility already imported; run this loop in a fresh process"
        )
    integration = str(
        Path(config.get("integration_path") or Path(__file__).resolve().parents[1]).resolve()
    )
    repo = str(Path(config["repo_path"]).resolve())
    for p in (integration, repo):
        if p not in sys.path:
            sys.path.insert(0, p)
    runtime_dir = Path(config["runtime_dir"]).resolve()
    (runtime_dir / ".vntrader").mkdir(parents=True, exist_ok=True)
    os.chdir(runtime_dir)

    import vnpy

    vnpy_file = Path(str(vnpy.__file__)).resolve()
    if Path(repo).resolve() not in vnpy_file.parents:
        raise SystemExit(f"vnpy origin {vnpy_file} is not under repo path {repo}")
    return {
        "vnpy_version": vnpy.__version__,
        "vnpy_module_file": str(vnpy_file),
        "repo_path": repo,
        "integration_path": integration,
        "cwd": str(runtime_dir),
        "python": sys.executable,
    }


def _receipt_to_dict(receipt: Any) -> Any:
    if is_dataclass(receipt):
        return asdict(receipt)
    return receipt


def _bar_value_row(bar: Any) -> dict[str, Any]:
    return {
        "datetime": bar.datetime.isoformat(),
        "open": bar.open_price,
        "high": bar.high_price,
        "low": bar.low_price,
        "close": bar.close_price,
        "volume": bar.volume,
        "turnover": bar.turnover,
        "open_interest": bar.open_interest,
    }


def _bar_provenance_row(bar: Any) -> dict[str, Any]:
    extra = dict(bar.extra or {})
    row = _bar_value_row(bar)
    row["source_label"] = extra.get("source_label")
    row["trading_date"] = extra.get("trading_date")
    return row


def _core_value_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "datetime": row["native_datetime"],
        "open": row["open"],
        "high": row["high"],
        "low": row["low"],
        "close": row["close"],
        "volume": row["volume"],
        "turnover": row["turnover"],
    }


def _core_provenance_row(row: dict[str, Any]) -> dict[str, Any]:
    merged = _core_value_row(row)
    merged["source_label"] = row["source_label"]
    merged["trading_date"] = row["trading_date"]
    return merged


def _bar_to_dict(bar: Any) -> dict[str, Any]:
    extra = dict(bar.extra or {})
    return {
        "datetime": bar.datetime.isoformat(),
        "symbol": bar.symbol,
        "exchange": bar.exchange.value,
        "interval": bar.interval.value,
        "open": bar.open_price,
        "high": bar.high_price,
        "low": bar.low_price,
        "close": bar.close_price,
        "volume": bar.volume,
        "turnover": bar.turnover,
        "open_interest": bar.open_interest,
        "trading_date": extra.get("trading_date"),
        "source_label": extra.get("source_label"),
        "source_symbol": extra.get("source_symbol"),
        "source_identity": extra.get("source_identity"),
        "source_exchange_label": extra.get("source_exchange_label"),
        "dataset_id": extra.get("dataset_id"),
        "snapshot_id": extra.get("snapshot_id"),
    }


class _Checks:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    def add(self, name: str, passed: bool, detail: Any) -> None:
        self.items.append({"name": name, "pass": bool(passed), "detail": detail})

    @property
    def all_pass(self) -> bool:
        return all(item["pass"] for item in self.items)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run(config: dict[str, Any], identity: str) -> dict[str, Any]:
    env = _prepare_process(config)
    checks = _Checks()

    # Process-local nonsecret SETTINGS, then explicit plugin import.
    from vnpy.trader.setting import SETTINGS

    SETTINGS["database.name"] = "researchstore"
    SETTINGS["researchstore.root"] = str(Path(config["store_root"]).resolve())
    SETTINGS["researchstore.snapshot_id"] = config["snapshot_id"]
    SETTINGS["researchstore.allow_missing_auxiliary"] = bool(
        config.get("allow_missing_auxiliary", False)
    )
    if config.get("exchange_map"):
        SETTINGS["researchstore.exchange_map"] = config["exchange_map"]
    if config.get("database_timezone"):
        SETTINGS["database.timezone"] = config["database_timezone"]

    import vnpy_researchstore.database as plugin_module
    from vnpy.trader import database as database_module
    from vnpy.trader.constant import Exchange, Interval

    database = database_module.get_database()
    if not isinstance(database, plugin_module.Database):
        raise SystemExit(
            f"get_database returned {type(database).__module__}.{type(database).__name__}, "
            "expected vnpy_researchstore.database.Database"
        )
    if database.snapshot_id != config["snapshot_id"]:
        raise SystemExit(
            f"plugin bound snapshot {database.snapshot_id} != configured {config['snapshot_id']}"
        )

    from research_store import open_snapshot, open_store

    store = open_store(config["store_root"])
    reader = open_snapshot(store, config["snapshot_id"])
    store_manifest = json.loads(
        (Path(config["store_root"]) / "store.json").read_text(encoding="utf-8")
    )

    from vnpy_researchstore.alpha import ResearchAlphaLab

    lab = ResearchAlphaLab(
        config["lab_path"],
        config["store_root"],
        config["snapshot_id"],
        allow_missing_auxiliary=bool(config.get("allow_missing_auxiliary", False)),
        exchange_map_path=config.get("exchange_map"),
    )

    symbols = list(config["symbols"])
    source_identities = list(config.get("source_identities") or symbols)
    windows = dict(config["windows"])
    dataset_ids = dict(config.get("dataset_ids", {}))
    source_reference = dict(config.get("source_reference") or {})
    tz = config.get("database_timezone") or "Asia/Shanghai"
    symbol_of = dict(zip(symbols, source_identities, strict=True))

    result: dict[str, Any] = {
        "status": "PASS",
        "runner": "tools/delivery_etf_loop.py",
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "config_identity": identity,
        "environment": env,
        "database_timezone": tz,
        "snapshot_id": config["snapshot_id"],
        "store_id": store_manifest.get("store_id"),
        "dataset_ids": dataset_ids,
        "symbols": symbols,
        "source_identities": source_identities,
        "adapter": {
            "module": type(database).__module__,
            "class": type(database).__name__,
            "database_file": str(Path(plugin_module.__file__).resolve()),
            "alpha_module": type(lab).__module__,
            "alpha_class": type(lab).__name__,
        },
        "consumers": {},
        "checks": checks.items,
    }

    try:
        _run_consumers(
            config, result, checks, database, reader, lab, symbols,
            source_identities, symbol_of, windows, dataset_ids,
            source_reference, Interval, Exchange,
        )
        _run_bootstrap(config, result, checks, env)
        _run_snapshot_verify(config, result, checks)
        _check_import_idempotency(config, result, checks)
    finally:
        result["checks"] = checks.items
        result["status"] = "PASS" if checks.all_pass else "FAIL"
        try:
            reader.close()
        finally:
            try:
                lab.close()
            finally:
                database.close()
                store.close()
    return result


def _core_reader_rows(
    reader: Any,
    dataset_id: str,
    source_identities: list[str],
    interval_key: str,
    start: datetime,
    end: datetime,
) -> list[dict[str, Any]]:
    """Core observational read using the same conversion the bridges use."""

    from vnpy_researchstore.native_common import _native_to_utc_aware, _ns_to_native_datetime

    start_utc = _native_to_utc_aware(start)
    end_utc = _native_to_utc_aware(end)
    internal_end = (
        end_utc + timedelta(days=1)
        if interval_key == "daily"
        else end_utc + timedelta(microseconds=1)
    )
    rows: list[dict[str, Any]] = []
    for batch in reader.bars(
        dataset_id,
        instruments=source_identities,
        start=start_utc,
        end=internal_end,
        required_fields=("open", "high", "low", "close", "volume", "turnover"),
        allow_missing_auxiliary=True,
    ):
        cols = {
            name: batch.column(name).to_pylist()
            for name in (
                "instrument_id", "bar_start", "trading_date", "symbol", "exchange",
                "source_label", "open", "high", "low", "close", "volume", "turnover",
            )
        }
        for i in range(batch.num_rows):
            native_dt = _ns_to_native_datetime(int(cols["bar_start"][i]))
            if interval_key == "daily":
                td = cols["trading_date"][i]
                key_dt = datetime.combine(td, datetime.min.time()) if td else native_dt
            else:
                key_dt = native_dt
            if key_dt < start or key_dt > end:
                continue
            rows.append({
                "instrument_id": cols["instrument_id"][i],
                "exchange": cols["exchange"][i],
                "native_datetime": key_dt.isoformat(),
                "open": cols["open"][i], "high": cols["high"][i],
                "low": cols["low"][i], "close": cols["close"][i],
                "volume": cols["volume"][i], "turnover": cols["turnover"][i],
                "source_label": cols["source_label"][i],
                "trading_date": (
                    str(cols["trading_date"][i]) if cols["trading_date"][i] else None
                ),
            })
    rows.sort(key=lambda r: (r["native_datetime"], r["instrument_id"]))
    return rows


def _run_consumers(
    config: dict[str, Any],
    result: dict[str, Any],
    checks: _Checks,
    database: Any,
    reader: Any,
    lab: Any,
    symbols: list[str],
    source_identities: list[str],
    symbol_of: dict[str, str],
    windows: dict[str, Any],
    dataset_ids: dict[str, str],
    source_reference: dict[str, Any],
    Interval: Any,
    Exchange: Any,
) -> None:
    consumers: dict[str, Any] = result["consumers"]
    windows_ref = source_reference.get("windows", {})
    overview_ref = source_reference.get("overview", {})
    pinned_rows = source_reference.get("pinned_source_rows", {})

    # -- core reader observational identity -----------------------------------
    core_reads: dict[str, Any] = {}
    core_rows_by_symbol: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for interval_key in ("minute", "daily"):
        win = windows[interval_key]
        core_rows = _core_reader_rows(
            reader,
            dataset_ids[interval_key],
            source_identities,
            interval_key,
            parse_dt(win["start"]),
            parse_dt(win["end"]),
        )
        core_reads[interval_key] = {
            "rows": len(core_rows),
            "digest": consumer_rows_digest(
                [_core_provenance_row(row) for row in core_rows]
            ),
            "data": core_rows,
        }
        for sym in symbols:
            core_rows_by_symbol[(interval_key, sym)] = [
                row for row in core_rows if row["instrument_id"] == symbol_of[sym]
            ]
    consumers["core_reader"] = core_reads

    # -- native Database.load_bar_data (BARE native symbols) -------------------
    db_reads: dict[str, Any] = {}
    db_bars_by_key: dict[tuple[str, str, str], list[Any]] = {}
    db_digest_by_key: dict[tuple[str, str, str], str] = {}
    for interval_key, interval in (("minute", Interval.MINUTE), ("daily", Interval.DAILY)):
        win = windows[interval_key]
        per_symbol: dict[str, Any] = {}
        for sym in symbols:
            bare, exch_text = sym.split(".")
            bars = database.load_bar_data(
                bare, Exchange(exch_text), interval,
                parse_dt(win["start"]), parse_dt(win["end"]),
            )
            key3 = (interval_key, sym, "base")
            db_bars_by_key[key3] = bars
            digest = consumer_rows_digest([_bar_provenance_row(b) for b in bars])
            db_digest_by_key[key3] = digest
            per_symbol[sym] = {
                "rows": len(bars),
                "first": _bar_to_dict(bars[0]) if bars else None,
                "last": _bar_to_dict(bars[-1]) if bars else None,
                "digest": digest,
                "receipt": _receipt_to_dict(database.last_receipt),
            }
        db_reads[interval_key] = per_symbol
    consumers["database"] = db_reads

    # core == database on values AND provenance (exact digest equality)
    identity_problems: list[str] = []
    identity_detail: dict[str, Any] = {}
    for interval_key in ("minute", "daily"):
        for sym in symbols:
            subset = core_rows_by_symbol[(interval_key, sym)]
            core_digest = consumer_rows_digest([_core_provenance_row(r) for r in subset])
            db_digest = db_digest_by_key[(interval_key, sym, "base")]
            db_rows = db_reads[interval_key][sym]["rows"]
            ok = subset and core_digest == db_digest and len(subset) == db_rows
            identity_detail[f"{interval_key}/{sym}"] = {
                "core_rows": len(subset),
                "database_rows": db_rows,
                "digest_equal": core_digest == db_digest,
            }
            if not ok:
                identity_problems.append(f"{interval_key}/{sym} core!=database")
    checks.add("core_database_value_identity", not identity_problems, identity_detail)

    # native stamping: bare native symbol/exchange, source identity in extra
    stamp_problems: list[str] = []
    for interval_key in ("minute", "daily"):
        for sym in symbols:
            info = db_reads[interval_key][sym]
            bare = sym.split(".")[0]
            for endpoint in ("first", "last"):
                row = info[endpoint]
                if row is None:
                    stamp_problems.append(f"{interval_key}/{sym} {endpoint} missing")
                    continue
                if row["symbol"] != bare or row["exchange"] != "SSE":
                    stamp_problems.append(
                        f"{interval_key}/{sym} {endpoint} stamped "
                        f"{row['symbol']}.{row['exchange']}"
                    )
                if row["source_identity"] != symbol_of[sym]:
                    stamp_problems.append(
                        f"{interval_key}/{sym} {endpoint} source_identity "
                        f"{row['source_identity']!r}"
                    )
                if row["dataset_id"] != dataset_ids[interval_key]:
                    stamp_problems.append(
                        f"{interval_key}/{sym} {endpoint} dataset_id "
                        f"{row['dataset_id']!r}"
                    )
                if row["snapshot_id"] != config["snapshot_id"]:
                    stamp_problems.append(
                        f"{interval_key}/{sym} {endpoint} snapshot_id "
                        f"{row['snapshot_id']!r}"
                    )
    checks.add("native_bare_symbol_stamping", not stamp_problems, stamp_problems)

    # window counts against the coordinator source references
    count_problems: list[str] = []
    for interval_key in ("minute", "daily"):
        for sym, identity in symbol_of.items():
            ref = windows_ref.get(identity, {}).get(f"{interval_key}_base_rows")
            actual = db_reads[interval_key][sym]["rows"]
            if ref is not None and actual != ref:
                count_problems.append(
                    f"{interval_key}/{sym} rows actual={actual} source_reference={ref}"
                )
    checks.add("base_window_source_reference_counts", not count_problems, count_problems)

    # minute session edges: 240 bars/day, 09:30..14:59, no lunch-gap bars
    minute_edge: dict[str, Any] = {}
    edge_problems: list[str] = []
    for sym in symbols:
        summary = lunch_edge_summary(
            [_bar_value_row(b) for b in db_bars_by_key[("minute", sym, "base")]]
        )
        minute_edge[sym] = summary
        if summary["lunch_bars_total"]:
            edge_problems.append(f"{sym} lunch-gap bars {summary['lunch_bars_total']}")
        for day, info in summary["days"].items():
            if info["count"] != 240:
                edge_problems.append(f"{sym} {day} count={info['count']} != 240")
            if not info["first"].endswith("09:30:00"):
                edge_problems.append(f"{sym} {day} first={info['first']}")
            if not info["last"].endswith("14:59:00"):
                edge_problems.append(f"{sym} {day} last={info['last']}")
    checks.add("minute_lunch_edges_and_session_shape", not edge_problems, minute_edge)

    # source END label -> native bar START mapping (every row, both intervals)
    label_problems: list[str] = []
    for sym in symbols:
        for bar in db_bars_by_key[("minute", sym, "base")]:
            label = (bar.extra or {}).get("source_label")
            expected_label = (bar.datetime + timedelta(minutes=1)).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            if label != expected_label:
                label_problems.append(
                    f"minute {sym} @ {bar.datetime} source_label={label!r} "
                    f"!= {expected_label!r}"
                )
                if len(label_problems) > 10:
                    break
        if len(label_problems) > 10:
            break
    for sym in symbols:
        for bar in db_bars_by_key[("daily", sym, "base")]:
            extra = bar.extra or {}
            if str(extra.get("trading_date")) != bar.datetime.strftime("%Y-%m-%d"):
                label_problems.append(
                    f"daily {sym} @ {bar.datetime} trading_date="
                    f"{extra.get('trading_date')!r} != {bar.datetime:%Y-%m-%d}"
                )
    checks.add("source_end_label_mapping", not label_problems, label_problems)

    # pinned source rows (coordinator observations) on native Database values
    pinned_problems: list[str] = []
    pinned_found: dict[str, Any] = {}
    for identity, pins in pinned_rows.items():
        sym = next(s for s, i in symbol_of.items() if i == identity)
        by_dt = {
            bar.datetime.strftime("%Y-%m-%d %H:%M:%S"): bar
            for bar in db_bars_by_key[("minute", sym, "base")]
        }
        for label, expected_values in pins.items():
            native_dt = (parse_dt(label) - timedelta(minutes=1)).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            bar = by_dt.get(native_dt)
            if bar is None:
                pinned_problems.append(f"{identity} {label}: native {native_dt} absent")
                continue
            actual_values = {
                "open": bar.open_price,
                "high": bar.high_price,
                "low": bar.low_price,
                "close": bar.close_price,
                "volume": bar.volume,
                "turnover": bar.turnover,
            }
            pinned_found[f"{identity}@{label}"] = actual_values
            for field, expected_value in expected_values.items():
                mismatch = compare_numeric(expected_value, actual_values[field], rel_tol=0.0)
                if mismatch:
                    pinned_problems.append(f"{identity} {label} {field}: {mismatch}")
    checks.add("pinned_source_rows", not pinned_problems, pinned_found)

    # zero-volume behavior for 510130 (documented sparse minutes)
    zv_problems: list[str] = []
    zv_report: dict[str, Any] = {}
    zsym = next(s for s in symbols if s.startswith("510130"))
    for stamp in ("2016-01-18 09:30:00", "2016-01-18 11:29:00"):
        match = [
            bar
            for bar in db_bars_by_key[("minute", zsym, "base")]
            if bar.datetime.strftime("%Y-%m-%d %H:%M:%S") == stamp
        ]
        if len(match) != 1:
            zv_problems.append(f"{zsym} zero-volume probe {stamp} found {len(match)}x")
            continue
        bar = match[0]
        zv_report[stamp] = {
            "open": bar.open_price,
            "high": bar.high_price,
            "low": bar.low_price,
            "close": bar.close_price,
            "volume": bar.volume,
            "turnover": bar.turnover,
        }
        if bar.volume != 0 or bar.turnover != 0:
            zv_problems.append(f"{zsym} {stamp} volume/turnover not zero")
        if not (bar.open_price == bar.high_price == bar.low_price == bar.close_price != 0):
            zv_problems.append(f"{zsym} {stamp} OHLC not uniformly nonzero")
    checks.add("zero_volume_source_rows_preserved", not zv_problems, zv_report)

    # nonaligned minute end (14:58:30): 14:59 excluded, 14:58 last
    nonaligned: dict[str, Any] = {}
    na_problems: list[str] = []
    na_end = minute_nonaligned_end(windows["minute"]["end"])
    for sym in symbols:
        bare, exch_text = sym.split(".")
        bars = database.load_bar_data(
            bare, Exchange(exch_text), Interval.MINUTE,
            parse_dt(windows["minute"]["start"]), parse_dt(na_end),
        )
        key3 = ("minute", sym, "nonaligned")
        db_bars_by_key[key3] = bars
        nonaligned[sym] = {
            "rows": len(bars),
            "first": _bar_to_dict(bars[0]) if bars else None,
            "last": _bar_to_dict(bars[-1]) if bars else None,
            "digest": consumer_rows_digest([_bar_provenance_row(b) for b in bars]),
        }
        base_bars = db_bars_by_key[("minute", sym, "base")]
        if len(bars) != len(base_bars) - 1:
            na_problems.append(
                f"{sym} nonaligned rows {len(bars)} != base-1 {len(base_bars) - 1}"
            )
        if bars and bars[-1].datetime.strftime("%H:%M:%S") != "14:58:00":
            na_problems.append(f"{sym} nonaligned last {bars[-1].datetime.isoformat()}")
        excluded_count = sum(
            1
            for bar in base_bars
            if bar.datetime.strftime("%Y-%m-%d %H:%M:%S") == "2016-01-21 14:59:00"
        )
        if excluded_count != 1:
            na_problems.append(
                f"{sym} expected exactly one 14:59 row in base window, found {excluded_count}"
            )
    checks.add("minute_nonaligned_inclusive_end", not na_problems, nonaligned)

    # -- ResearchAlphaLab.load_bar_data (raw) ---------------------------------
    alpha_raw: dict[str, Any] = {}
    alpha_problems: list[str] = []
    for interval_key, interval in (("minute", Interval.MINUTE), ("daily", Interval.DAILY)):
        win = windows[interval_key]
        per_symbol: dict[str, Any] = {}
        for sym in symbols:
            bars = lab.load_bar_data(
                sym, interval, parse_dt(win["start"]), parse_dt(win["end"])
            )
            digest = consumer_rows_digest([_bar_provenance_row(b) for b in bars])
            per_symbol[sym] = {
                "rows": len(bars),
                "first": _bar_to_dict(bars[0]) if bars else None,
                "last": _bar_to_dict(bars[-1]) if bars else None,
                "digest": digest,
                "receipt": _receipt_to_dict(lab.last_receipt),
            }
            if digest != db_digest_by_key[(interval_key, sym, "base")]:
                alpha_problems.append(
                    f"{interval_key}/{sym} alpha raw digest != database digest"
                )
        alpha_raw[interval_key] = per_symbol
    consumers["alpha_raw"] = alpha_raw
    checks.add("database_alpha_raw_value_identity", not alpha_problems, alpha_problems)

    # -- ResearchAlphaLab.load_bar_df (extended_days 0 and 10) ----------------
    import polars as pl

    alpha_df: dict[str, Any] = {}
    df_problems: list[str] = []
    for interval_key, interval in (("minute", Interval.MINUTE), ("daily", Interval.DAILY)):
        win = windows[interval_key]
        per_ext: dict[str, Any] = {}
        for ext in (0, 10):
            df = lab.load_bar_df(
                symbols, interval,
                parse_dt(win["start"]), parse_dt(win["end"]), extended_days=ext,
            )
            entry: dict[str, Any] = {"rows": 0 if df is None else df.height}
            if df is None:
                per_ext[str(ext)] = entry
                df_problems.append(f"{interval_key} ext={ext} returned None")
                continue
            if list(df.columns) != DF_COLUMNS:
                df_problems.append(
                    f"{interval_key} ext={ext} columns {list(df.columns)} != {DF_COLUMNS}"
                )
            exp_start, exp_end = expanded_window(win["start"], win["end"], ext)
            by_symbol_counts: dict[str, int] = {}
            for sym in symbols:
                frame_rows = (
                    df.filter(pl.col("vt_symbol") == sym)
                    .sort("datetime")
                    .to_dicts()
                )
                by_symbol_counts[sym] = len(frame_rows)
                # independent expectation from the verified Database raw rows
                bare, exch_text = sym.split(".")
                raw_bars = database.load_bar_data(
                    bare, Exchange(exch_text), interval,
                    parse_dt(exp_start), parse_dt(exp_end),
                )
                raw_value_rows = [_bar_value_row(b) for b in raw_bars]
                expected_rows = normalize_expectation(raw_value_rows)
                actual_rows = [
                    {
                        "datetime": row["datetime"].isoformat()
                        if hasattr(row["datetime"], "isoformat")
                        else str(row["datetime"]),
                        "open": row["open"], "high": row["high"],
                        "low": row["low"], "close": row["close"],
                        "volume": row["volume"], "turnover": row["turnover"],
                        "open_interest": row["open_interest"], "vwap": row["vwap"],
                    }
                    for row in frame_rows
                ]
                mismatches = compare_rows(
                    expected_rows,
                    actual_rows,
                    fields=[
                        "open", "high", "low", "close", "volume",
                        "turnover", "open_interest", "vwap",
                    ],
                )
                if mismatches:
                    df_problems.append(
                        f"{interval_key} ext={ext} {sym}: {mismatches[:10]}"
                    )
                entry[sym] = {
                    "rows": len(frame_rows),
                    "expanded_window": {"start": exp_start, "end": exp_end},
                    "first_close": raw_value_rows[0]["close"] if raw_value_rows else None,
                    "raw_reference_rows": len(raw_value_rows),
                }
                if ext == 0:
                    # Review finding 1: the df is NORMALIZED; a digest is
                    # recorded for BOTH sides against the normalized raw
                    # reference (same first-close math over the verified
                    # Database rows) — but equality is NOT asserted here:
                    # polars and Python division may differ in the last bit,
                    # and the authoritative check is the row-level
                    # tolerance comparison above (values AND vwap).
                    entry[sym]["df_value_digest"] = value_rows_digest(
                        [
                            {
                                "datetime": row["datetime"],
                                "open": row["open"], "high": row["high"],
                                "low": row["low"], "close": row["close"],
                                "volume": row["volume"], "turnover": row["turnover"],
                            }
                            for row in actual_rows
                        ]
                    )
                    entry[sym][
                        "normalized_reference_value_digest"
                    ] = value_rows_digest(expected_rows)
            entry["by_symbol"] = by_symbol_counts
            per_ext[str(ext)] = entry
        alpha_df[interval_key] = per_ext
    consumers["alpha_df"] = alpha_df

    # extended window counts against source references; ext0 identity vs base
    for interval_key in ("minute", "daily"):
        for sym, identity in symbol_of.items():
            ref = windows_ref.get(identity, {}).get(f"{interval_key}_ext_rows")
            actual = alpha_df[interval_key]["10"].get(sym, {}).get("rows")
            if ref is not None and actual != ref:
                df_problems.append(
                    f"{interval_key} ext=10 {sym} rows actual={actual} "
                    f"source_reference={ref}"
                )
    checks.add("alpha_df_windows_and_preprocessing", not df_problems, df_problems)

    # zero-volume minutes keep NaN VWAP and preserved OHLC in the dataframe
    zvdf_problems: list[str] = []
    zvdf_report: dict[str, Any] = {}
    df10_minute = lab.load_bar_df(
        [zsym], Interval.MINUTE,
        parse_dt(windows["minute"]["start"]), parse_dt(windows["minute"]["end"]),
        extended_days=10,
    )
    if df10_minute is None:
        zvdf_problems.append("510130 ext=10 minute df is None")
    else:
        rows = (
            df10_minute.filter(pl.col("vt_symbol") == zsym)
            .sort("datetime")
            .to_dicts()
        )
        # Review finding 2: the df is already normalized (its first close is
        # 1.0 by construction). The denominator MUST come from the raw
        # reference over the IDENTICAL expanded window, never from the df.
        zv_exp_start, zv_exp_end = expanded_window(
            windows["minute"]["start"], windows["minute"]["end"], 10
        )
        zv_raw = database.load_bar_data(
            zsym.split(".")[0], Exchange.SSE, Interval.MINUTE,
            parse_dt(zv_exp_start), parse_dt(zv_exp_end),
        )
        close_0 = zv_raw[0].close_price if zv_raw else None
        for stamp in ("2016-01-18 09:30:00", "2016-01-18 11:29:00"):
            match = [r for r in rows if str(r["datetime"])[:19] == stamp]
            if len(match) != 1:
                zvdf_problems.append(f"{zsym} df row {stamp} found {len(match)}x")
                continue
            row = match[0]
            zvdf_report[stamp] = {
                "open": row["open"], "high": row["high"],
                "low": row["low"], "close": row["close"],
                "volume": row["volume"], "vwap": row["vwap"],
            }
            if not is_missing(row["vwap"]):
                zvdf_problems.append(f"{zsym} df {stamp} vwap {row['vwap']!r} not missing")
            if close_0 is None:
                zvdf_problems.append(f"{zsym} raw reference first close missing")
                continue
            expected_ohlc = 3.25 / close_0
            for field in ("open", "high", "low", "close"):
                mismatch = compare_numeric(expected_ohlc, row[field])
                if mismatch:
                    zvdf_problems.append(f"{zsym} df {stamp} {field}: {mismatch}")
        stamp = "2016-01-18 13:00:00"
        match = [r for r in rows if str(r["datetime"])[:19] == stamp]
        if len(match) == 1:
            row = match[0]
            zvdf_report[stamp] = {
                "volume": row["volume"], "turnover": row["turnover"],
                "vwap": row["vwap"],
            }
            mismatch = compare_numeric(655.0 / 200.0, row["vwap"])
            if mismatch:
                zvdf_problems.append(f"{zsym} df {stamp} vwap: {mismatch}")
        else:
            zvdf_problems.append(f"{zsym} df row {stamp} found {len(match)}x")
    checks.add("alpha_df_zero_volume_vwap_missing", not zvdf_problems, zvdf_report)

    # -- suffixed stored-identity cross-check (diagnostic, not a workaround) ---
    # The BARE-symbol calls above are the documented consumer contract and the
    # pass criterion. This probe additionally confirms the store's ORIGINAL
    # vendor identity also resolves directly (native06 read-time resolution);
    # it is never used as a substitute for the bare calls.
    diag: dict[str, Any] = {}
    diag_problems: list[str] = []
    for interval_key, interval in (("minute", Interval.MINUTE), ("daily", Interval.DAILY)):
        win = windows[interval_key]
        per: dict[str, Any] = {}
        for src_id in source_identities:
            native_sym = src_id.rsplit(".", 1)[0] + ".SSE"
            try:
                bars = database.load_bar_data(
                    src_id, Exchange.SSE, interval,
                    parse_dt(win["start"]), parse_dt(win["end"]),
                )
                per[src_id] = {
                    "rows": len(bars),
                    "first": bars[0].datetime.isoformat() if bars else None,
                    "last": bars[-1].datetime.isoformat() if bars else None,
                }
                base_bars = db_bars_by_key[(interval_key, native_sym, "base")]
                if len(bars) != len(base_bars):
                    diag_problems.append(
                        f"{interval_key} {src_id} rows {len(bars)} != bare "
                        f"{len(base_bars)}"
                    )
            except Exception as exc:  # noqa: BLE001 - diagnostic captures refusal type
                per[src_id] = {"error": f"{type(exc).__name__}: {exc}"}
                diag_problems.append(f"{interval_key} {src_id}: {per[src_id]['error']}")
        diag[interval_key] = per
    result["symbol_resolution_diagnostic"] = diag
    checks.add("suffixed_identity_crosscheck", not diag_problems, diag_problems)

    # -- snapshot-bound overview ----------------------------------------------
    overview = [
        {
            "symbol": o.symbol,
            "exchange": o.exchange.value,
            "interval": o.interval.value,
            "count": o.count,
            "start": o.start.isoformat() if o.start else None,
            "end": o.end.isoformat() if o.end else None,
        }
        for o in database.get_bar_overview()
    ]
    result["overview"] = overview
    ov_problems: list[str] = []
    if overview_ref:
        seen: set[tuple[str, str, str]] = set()
        # Review finding 3: source_reference keys are CANONICAL store interval
        # names ("1m"/"1d"); the native overview reports the real vnpy enum
        # values (Interval.MINUTE.value == "1m", Interval.DAILY.value == "d").
        # Canonical "1d" stays distinct and is never rewritten anywhere.
        ref_to_native_interval = {
            "1m": Interval.MINUTE.value,
            "1d": Interval.DAILY.value,
        }
        for native_symbol, per_interval in overview_ref.items():
            for canonical_interval, ref in per_interval.items():
                native_interval = ref_to_native_interval.get(canonical_interval)
                if native_interval is None:
                    ov_problems.append(
                        f"unknown canonical interval {canonical_interval!r}"
                    )
                    continue
                key = (native_symbol, "SSE", native_interval)
                match = [
                    row
                    for row in overview
                    if (row["symbol"], row["exchange"], row["interval"]) == key
                ]
                if len(match) != 1:
                    ov_problems.append(f"overview entry {key} found {len(match)}x")
                    continue
                seen.add(key)
                row = match[0]
                if str(row["count"]) != str(ref["count"]):
                    ov_problems.append(
                        f"{key} count {row['count']} != {ref['count']}"
                    )
                if row["start"] != ref["start"] or row["end"] != ref["end"]:
                    ov_problems.append(
                        f"{key} range {row['start']}..{row['end']} != "
                        f"{ref['start']}..{ref['end']}"
                    )
        for row in overview:
            key = (row["symbol"], row["exchange"], row["interval"])
            if key not in seen:
                ov_problems.append(f"unexpected overview entry {key}")
        checks.add("snapshot_overview_scope", not ov_problems, ov_problems)
    else:
        checks.add(
            "snapshot_overview_scope", True, "recorded only (no source_reference.overview)"
        )


def _run_bootstrap(
    config: dict[str, Any], result: dict[str, Any], checks: _Checks, env: dict[str, Any]
) -> None:
    """Offline CTA/Portfolio bootstrap + loading in ONE fresh child process."""

    if config.get("bootstrap") is None:
        checks.add("offline_cta_portfolio_bootstrap", True, "skipped (no bootstrap key)")
        return
    runtime_dir = Path(config["runtime_dir"]).resolve()
    boot_cfg_path = runtime_dir / "delivery_etf_bootstrap.json"
    derived = derive_bootstrap_config(config)
    boot_identity = hashlib.sha256(
        json.dumps(derived, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    boot_cfg_path.write_text(
        json.dumps(derived, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    main_cfg_path = runtime_dir / "delivery_etf_loop_effective.json"
    main_cfg_path.write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    proc = subprocess.run(
        [sys.executable, "-c", BOOTSTRAP_CHILD_SCRIPT,
         str(boot_cfg_path), str(main_cfg_path)],
        capture_output=True,
        text=True,
        cwd=str(runtime_dir),
        timeout=900,
    )
    payload: dict[str, Any] = {
        "exit_code": proc.returncode,
        "bootstrap_config": derived,
        "bootstrap_config_identity": boot_identity,
        "bootstrap_config_path": str(boot_cfg_path),
    }
    problems: list[str] = []
    if proc.returncode != 0:
        problems.append(f"child exit {proc.returncode}; stderr tail: {proc.stderr[-2000:]}")
    else:
        try:
            child = json.loads(proc.stdout.strip().splitlines()[-1])
        except (json.JSONDecodeError, IndexError):
            child = None
            problems.append(f"unparseable child stdout: {proc.stdout[-2000:]}")
        if child is not None:
            payload["child"] = child
            receipt = child.get("receipt") or {}
            if receipt.get("snapshot_id") != config["snapshot_id"]:
                problems.append("child receipt snapshot mismatch")
            if receipt.get("database", {}).get("module") != "vnpy_researchstore.database":
                problems.append("child database module is not the researchstore plugin")
            if receipt.get("vnpy", {}).get("module_file") != env["vnpy_module_file"]:
                problems.append(
                    f"child vnpy origin {receipt.get('vnpy', {}).get('module_file')} "
                    f"!= runner origin {env['vnpy_module_file']}"
                )
            engines = child.get("engines") or {}
            expect = {
                "cta/minute/510130.SSE": (960, "2016-01-18T09:30:00", "2016-01-21T14:59:00"),
                "cta/minute/510300.SSE": (960, "2016-01-18T09:30:00", "2016-01-21T14:59:00"),
                "cta/daily/510130.SSE": (4, "2016-01-18T00:00:00", "2016-01-21T00:00:00"),
                "cta/daily/510300.SSE": (4, "2016-01-18T00:00:00", "2016-01-21T00:00:00"),
                "portfolio/minute": (1920, "2016-01-18T09:30:00", "2016-01-21T14:59:00"),
                "portfolio/daily": (8, "2016-01-18T00:00:00", "2016-01-21T00:00:00"),
            }
            for name, (rows, first, last) in expect.items():
                info = engines.get(name)
                if info is None:
                    problems.append(f"missing engine result {name}")
                    continue
                if info.get("rows") != rows:
                    problems.append(f"{name} rows {info.get('rows')} != {rows}")
                if info.get("first") != first or info.get("last") != last:
                    problems.append(
                        f"{name} range {info.get('first')}..{info.get('last')} != "
                        f"{first}..{last}"
                    )
            payload["engines"] = engines
            payload["receipt_path"] = receipt.get("receipt_path")
    checks.add("offline_cta_portfolio_bootstrap", not problems, payload)


def _run_snapshot_verify(
    config: dict[str, Any], result: dict[str, Any], checks: _Checks
) -> None:
    """Read-only ``research_store verify`` of the bound snapshot."""

    integration = str(
        Path(config.get("integration_path") or Path(__file__).resolve().parents[1]).resolve()
    )
    proc = subprocess.run(
        [
            sys.executable, "-m", "research_store",
            "--root", str(Path(config["store_root"]).resolve()),
            "verify", "--snapshot-id", config["snapshot_id"],
        ],
        capture_output=True,
        text=True,
        cwd=integration,
        timeout=900,
    )
    detail: dict[str, Any] = {"exit_code": proc.returncode}
    problems: list[str] = []
    if proc.returncode != 0:
        problems.append(f"verify exit {proc.returncode}; stderr: {proc.stderr[-2000:]}")
    else:
        try:
            payload = json.loads(proc.stdout)
            detail["payload"] = payload
            if payload.get("status") != "ok" or payload.get("failures"):
                problems.append(f"verify payload not clean: {payload}")
        except json.JSONDecodeError:
            problems.append(f"unparseable verify stdout: {proc.stdout[-2000:]}")
    result["snapshot_verify"] = detail
    checks.add("snapshot_verify", not problems, problems or detail.get("payload"))


def _read_evidence_json(path: Path) -> Any:
    """Read a preserved evidence JSON file without rewriting it.

    Preserved receipts were written by different owners' shells: UTF-8/ASCII,
    UTF-16LE with BOM (PowerShell redirection), or ASCII with GBK-encoded
    non-ASCII path bytes. Decode accordingly; the files stay read-only.
    """

    raw = path.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return json.loads(raw.decode("utf-16"))
    errors: list[str] = []
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return json.loads(raw.decode(encoding))
        except UnicodeDecodeError as exc:
            errors.append(f"{encoding}: {exc}")
    raise SystemExit(f"cannot decode evidence file {path}: {errors}")


def _check_import_idempotency(
    config: dict[str, Any], result: dict[str, Any], checks: _Checks
) -> None:
    """Cross-check preserved import/idempotency/repair-index receipts.

    Reads the preserved import evidence (original + repeat) and proves the
    published identity did not move: same dataset, same idempotency key,
    same counts, zero duplicates on repeat, and the 133-key repair index
    actually loaded before the base archives. Files are READ-ONLY inputs
    under .coordination/delivery04f-dev.
    """

    integration = Path(
        config.get("integration_path") or Path(__file__).resolve().parents[1]
    ).resolve()
    evidence = integration / ".coordination" / "delivery04f-dev"
    detail: dict[str, Any] = {}
    problems: list[str] = []
    for freq in ("1d", "1m"):
        original = evidence / f"import-{freq}.stdout.json"
        repeat = evidence / f"import-{freq}-repeat.stdout.json"
        if not original.is_file() or not repeat.is_file():
            problems.append(
                f"missing preserved import receipt for {freq}: "
                f"{original.name}/{repeat.name}"
            )
            continue
        first = _read_evidence_json(original)
        second = _read_evidence_json(repeat)
        try:
            a = first["imports"][0]
            b = second["imports"][0]
        except (KeyError, IndexError):
            problems.append(f"{freq} receipts have unexpected shape")
            continue
        pair = {
            "dataset_id": a.get("dataset_id") == b.get("dataset_id"),
            "idempotency_key": a.get("publish", {}).get("idempotency_key")
            == b.get("publish", {}).get("idempotency_key"),
            "input_rows": a.get("counts", {}).get("input_rows")
            == b.get("counts", {}).get("input_rows"),
            "accepted_rows": a.get("counts", {}).get("accepted_rows")
            == b.get("counts", {}).get("accepted_rows"),
            "duplicate_rows_zero": b.get("publish", {}).get("duplicate_rows") == 0,
        }
        repaired = (
            a.get("adapter_receipt", {})
            .get("extras", {})
            .get("repair_stats", {})
            .get("repaired_keys")
        )
        pair["repair_index_loaded_133"] = repaired == 133
        detail[freq] = {
            "dataset_id": a.get("dataset_id"),
            "idempotency_key": a.get("publish", {}).get("idempotency_key"),
            "input_rows": a.get("counts", {}).get("input_rows"),
            "accepted_rows": a.get("counts", {}).get("accepted_rows"),
            "duplicate_rows": b.get("publish", {}).get("duplicate_rows"),
            "repaired_keys": repaired,
            "identical": pair,
        }
        if not all(pair.values()):
            problems.append(f"{freq} idempotency/repair identity: {pair}")
    detail["note"] = (
        "repair index contains NO keys for 510130.XSHG/510300.XSHG (coordinator "
        "inspection); loading is still exercised and receipted before base archives"
    )
    checks.add("import_idempotency_and_repair_index", not problems, problems or detail)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="delivery04f real ETF consumer loop")
    parser.add_argument("--config", required=True, help="delivery_etf_loop config JSON")
    args = parser.parse_args(argv)
    started = time.time()
    tracemalloc.start()
    config, identity = load_config(args.config)
    try:
        result = run(config, identity)
    except SystemExit as exc:
        print(
            json.dumps(
                {
                    "status": "ERROR",
                    "error": str(exc),
                    "config_identity": identity,
                    "elapsed_seconds": round(time.time() - started, 3),
                },
                indent=2,
            )
        )
        return 3
    except Exception as exc:  # noqa: BLE001 - machine-readable failure
        import traceback

        print(
            json.dumps(
                {
                    "status": "ERROR",
                    "error": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc(),
                    "config_identity": identity,
                    "elapsed_seconds": round(time.time() - started, 3),
                },
                indent=2,
            )
        )
        return 3
    finally:
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    result["elapsed_seconds"] = round(time.time() - started, 3)
    result["python_heap_peak_bytes"] = peak
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
