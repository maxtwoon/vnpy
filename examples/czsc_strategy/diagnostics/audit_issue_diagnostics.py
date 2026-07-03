"""Read-only diagnostics for audit issues H1/H2/H3/H4/M1.

This script only inspects existing files and parameters. It does not connect to
any broker, send orders, or modify strategy logic.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Make the czsc_strategy package importable from this diagnostics script
_CZSC_STRATEGY_ROOT = Path(__file__).resolve().parent.parent
if str(_CZSC_STRATEGY_ROOT) not in sys.path:
    sys.path.insert(0, str(_CZSC_STRATEGY_ROOT))

from chan_strategy.data_adapter import SqliteDataAdapter


HERE = Path(__file__).resolve().parent
DEFAULT_OUT_DIR = HERE
DEFAULT_REPO_ROOT = HERE.parents[2]
DEFAULT_DIAGNOSTICS_DIR = HERE
SENSITIVE_KEY_PATTERNS = {
    "password",
    "auth_code",
    "api_key",
    "account_id",
    "setting_masked",
    "密码",
    "授权码",
    "认证码",
}
HIGH_PRECISION_PARAM_NAMES = {"weight", "multiplier", "ratio"}
CONTINUOUS_CONTRACT_KEYWORDS = {
    "rollover",
    "roll",
    "adjust",
    "adjustment",
    "factor",
    "back_adjust",
    "front_adjust",
    "contract",
    "main_contract",
    "dominant",
    "复权",
    "换月",
}
ADJUSTMENT_KEYWORDS = {
    "adjust",
    "adjustment",
    "factor",
    "back_adjust",
    "front_adjust",
    "roll_adj",
    "continuous_adj",
}
ROLLOVER_KEYWORDS = {
    "rollover",
    "roll_date",
    "contract",
    "real_symbol",
    "source_symbol",
    "active_contract",
}
METADATA_TABLE_KEYWORDS = {"meta", "info", "config", "contract", "mapping"}
PARAM_EVIDENCE_FILENAME_MARKERS = (
    "sc_short_weight",
    "portfolio_goal_expanded_short_sc",
    "platform_optimization_round",
)
STOP_LOSS_REASON_TOKENS = ("stop_loss", "止损")
SIGNAL_HISTORY_FILENAME_MARKERS = ("signal_history_",)
SIGNAL_CONTAINER_KEYS = ("signals", "signal", "signal_snapshot", "signal_history", "signal_records")
PNL_PCT_KEYS = ("pnl_pct", "return_pct", "profit_pct", "pnl_rate")
EXIT_REASON_KEYS = ("exit_reason", "reason", "reason_code", "close_reason", "exit_signal")
READABLE_EXTENSIONS = (".json", ".md", ".txt")


def _iter_nodes(obj: Any, path: str = "") -> Any:
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield from _iter_nodes(value, f"{path}.{key}" if path else str(key))
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            yield from _iter_nodes(value, f"{path}[{index}]")
    else:
        yield path, obj


def contains_sensitive_data(obj: Any) -> bool:
    """Return True if the object may contain private credentials."""
    for path, value in _iter_nodes(obj):
        last_key = path.split(".")[-1] if "." in path else path
        if any(pattern.lower() in last_key.lower() for pattern in SENSITIVE_KEY_PATTERNS):
            return True
        if isinstance(value, str):
            lower_value = value.lower()
            for pattern in SENSITIVE_KEY_PATTERNS:
                if pattern.lower() in lower_value:
                    return True
    return False


def _is_high_precision(value: float) -> bool:
    try:
        f = float(value)
    except Exception:
        return False
    return abs(round(f, 1) - f) > 1e-9


def _scan_evidence_files(evidence_dir: Path | None) -> list[str]:
    """Look for existing diagnostics files that mention H1-relevant SC weight scans."""
    if evidence_dir is None or not evidence_dir.exists():
        return []
    found: list[str] = []
    for path in evidence_dir.iterdir():
        if not path.is_file():
            continue
        lower = path.name.lower()
        if any(marker in lower for marker in PARAM_EVIDENCE_FILENAME_MARKERS):
            found.append(str(path))
    return sorted(found)


def detect_high_precision_weights(
    params: list[dict[str, Any]], evidence_dir: Path | None = None
) -> dict[str, Any]:
    """Detect weight-like parameters with more than one decimal place (H1)."""
    suspicious: list[dict[str, Any]] = []
    for param in params or []:
        name = str(param.get("name", "")).lower()
        value = param.get("value")
        if not any(token in name for token in HIGH_PRECISION_PARAM_NAMES):
            continue
        if isinstance(value, (int, float)) and _is_high_precision(value):
            suspicious.append({"name": param.get("name"), "value": value})

    evidence_files = _scan_evidence_files(evidence_dir)
    return {
        "issue": "H1",
        "status": "detected" if suspicious else "unknown",
        "high_precision_weight": bool(suspicious),
        "suspicious_params": suspicious,
        "evidence_files": evidence_files,
        "note": "Three-decimal weights adjacent to failing values are a textbook over-fit signature.",
    }


def analyze_stop_loss_overshoot(
    pairs: list[dict[str, Any]], stop_loss_bp: int = 300
) -> dict[str, Any]:
    """Measure how often actual stop-loss losses exceed the nominal stop (H2).

    pnl_pct is treated as a fraction (e.g. -0.126 => -12.6%) and converted to
    percentage points for reporting.
    """
    stop_loss_pct = -stop_loss_bp * 0.01
    stop_trades: list[dict[str, Any]] = []
    for pair in pairs or []:
        reason = str(pair.get("exit_reason", pair.get("reason", ""))).lower()
        if "stop_loss" not in reason:
            continue
        pnl = pair.get("pnl_pct")
        if not isinstance(pnl, (int, float)):
            continue
        normalized = float(pnl) * 100.0 if abs(float(pnl)) <= 1.0 else float(pnl)
        stop_trades.append({**pair, "pnl_pct": normalized})

    if not stop_trades:
        return {
            "issue": "H2",
            "status": "unavailable",
            "stop_loss_bp": stop_loss_bp,
            "stop_loss_pct": stop_loss_pct,
            "worst_loss_pct": None,
            "max_overshoot_multiple": None,
            "overshoot_count": 0,
            "sample_trades": [],
            "note": "No stop-loss trades provided.",
        }

    worst_loss_pct = min(t["pnl_pct"] for t in stop_trades)
    overshoot_trades = [t for t in stop_trades if t["pnl_pct"] < stop_loss_pct - 1e-9]
    overshoot_count = len(overshoot_trades)
    max_overshoot_multiple = 0.0
    if overshoot_trades:
        max_overshoot_multiple = max(
            t["pnl_pct"] / stop_loss_pct for t in overshoot_trades
        )

    sorted_trades = sorted(stop_trades, key=lambda t: t["pnl_pct"])[:3]
    return {
        "issue": "H2",
        "status": "detected",
        "stop_loss_bp": stop_loss_bp,
        "stop_loss_pct": stop_loss_pct,
        "worst_loss_pct": worst_loss_pct,
        "max_overshoot_multiple": max_overshoot_multiple,
        "overshoot_count": overshoot_count,
        "sample_trades": sorted_trades,
        "note": "Closing-price stop checks can gap through the nominal stop in overnight sessions.",
    }


def analyze_divergence_failure_reachability(
    signal_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Check whether the 'divergence failure' classification is ever observed (H3)."""
    if not signal_records:
        return {
            "issue": "H3",
            "status": "unavailable",
            "count": 0,
            "reachable": False,
            "severity": "high",
            "sample_dates": [],
            "note": "No signal history provided.",
        }

    count = 0
    sample_dates: list[str] = []
    for record in signal_records:
        signal = str(record.get("signal", ""))
        if "背驰" in signal and "失效" in signal:
            count += 1
            dt = record.get("dt") or record.get("date")
            if dt and len(sample_dates) < 5:
                sample_dates.append(str(dt))

    reachable = count > 0
    return {
        "issue": "H3",
        "status": "detected",
        "count": count,
        "reachable": reachable,
        "severity": "info" if reachable else "high",
        "sample_dates": sample_dates,
        "note": "Unreachable divergence-failure branch is dead code; reachable branch must be validated on real data.",
    }


def _inspect_sqlite_for_adjustment(db_path: Path, symbols: list[str]) -> list[str]:
    """Return table/column evidence if the SQLite DB declares rollover/adjustment metadata."""
    evidence: list[str] = []
    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cur.fetchall()]
        for table in tables:
            cur.execute(f"PRAGMA table_info({table})")
            for _, col_name, *_ in cur.fetchall():
                lower = str(col_name).lower()
                if any(kw in lower for kw in CONTINUOUS_CONTRACT_KEYWORDS):
                    evidence.append(f"{db_path}::{table}::{col_name}")
        conn.close()
    except Exception:
        pass
    return evidence


def _scan_diagnostics_for_continuous_contract_evidence(
    diagnostics_dir: Path | None, max_file_mb: float = 50.0
) -> list[str]:
    """List diagnostics files that discuss continuous contract/rollover/adjustment."""
    if diagnostics_dir is None or not diagnostics_dir.exists():
        return []
    found: list[str] = []
    max_bytes = max_file_mb * 1024 * 1024
    file_keywords = {"888", "continuous", "rollover", "adjustment", "复权", "换月"}
    for path in diagnostics_dir.iterdir():
        if not path.is_file() or path.suffix.lower() not in READABLE_EXTENSIONS:
            continue
        if path.stat().st_size > max_bytes:
            continue
        try:
            text = path.read_text(encoding="utf-8").lower()
        except Exception:
            continue
        if any(kw in text for kw in file_keywords):
            found.append(str(path))
    return sorted(found)


def _resolve_db_path(
    db_path: str | Path | None, repo_root: Path | None = None
) -> Path | None:
    """Resolve the SQLite DB path using the project precedence chain.

    Precedence:
      1. Explicit ``db_path`` argument.
      2. ``CHAN_SQLITE_DB_PATH`` environment variable.
      3. ``chan_strategy.config.SQLITE_DB_PATH`` (relative to ``repo_root`` if
         the module is not already on ``sys.path``).
    """
    if db_path is not None:
        return Path(db_path)

    env_path = os.getenv("CHAN_SQLITE_DB_PATH")
    if env_path:
        return Path(env_path)

    try:
        from chan_strategy.config import SQLITE_DB_PATH as config_db_path
    except Exception:
        config_db_path = None
        if repo_root is not None:
            # Fallback: look for a configured path by importing the module
            # from the requested repo root.
            import sys

            root_str = str(repo_root)
            if root_str not in sys.path:
                sys.path.insert(0, root_str)
            try:
                from chan_strategy.config import SQLITE_DB_PATH as config_db_path
            except Exception:
                config_db_path = None

    if config_db_path:
        return Path(config_db_path)

    return None


def _find_symbol_table(adapter: Any, symbol: str) -> str | None:
    """Locate the raw-data table for ``symbol``.

    Reuses the matching strategy from ``BacktestEngine._find_table`` but prefers
    the 1-minute raw table when the DB contains multiple frequency tables for the
    same symbol. Returns ``None`` instead of raising when no unique table is found.
    """
    tables = adapter.get_tables()
    if not tables:
        return None

    norm_symbol = symbol.lower().strip()
    priority_patterns = [
        f"{norm_symbol}_1m_raw",
        f"{norm_symbol}_1min_raw",
    ]

    # 1. Prefer an exact 1-minute match first.
    for pattern in priority_patterns:
        candidates = [table for table in tables if table.lower().strip() == pattern]
        if len(candidates) == 1:
            return candidates[0]

    # 2. Other exact matches (5M, generic raw, symbol itself).
    exact_patterns = [
        f"{norm_symbol}_5m_raw",
        f"{norm_symbol}_5min_raw",
        f"{norm_symbol}_raw",
        norm_symbol,
    ]
    exact_candidates = [
        table for table in tables if table.lower().strip() in exact_patterns
    ]
    if exact_candidates:
        return exact_candidates[0] if len(exact_candidates) == 1 else None

    # 3. Prefix matches; again prefer a 1-minute table.
    prefix_candidates = [
        table for table in tables if table.lower().strip().startswith(norm_symbol + "_")
    ]
    if prefix_candidates:
        for pattern in priority_patterns:
            candidates = [
                table for table in prefix_candidates if table.lower().strip() == pattern
            ]
            if len(candidates) == 1:
                return candidates[0]
        return prefix_candidates[0] if len(prefix_candidates) == 1 else None

    return None


def _find_date_column(adapter: Any, table: str) -> str | None:
    """Return a likely datetime/date column name for ``table``."""
    schema = adapter.get_table_schema(table)
    candidates = ["datetime", "date", "trade_date", "dt", "time"]
    columns_lower = {col["name"].lower(): col["name"] for col in schema}
    for cand in candidates:
        if cand in columns_lower:
            return columns_lower[cand]
    return None


def _inspect_table_for_continuous_contract(
    adapter: Any, table: str, symbol: str
) -> dict[str, Any]:
    """Inspect a single raw table for rollover/adjustment evidence (H4)."""
    schema = adapter.get_table_schema(table)
    col_names = [col["name"] for col in schema]
    columns_lower = {name.lower(): name for name in col_names}

    real_symbol_col: str | None = None
    for cand in ("real_symbol", "source_symbol"):
        if cand in columns_lower:
            real_symbol_col = columns_lower[cand]
            break

    adjustment_cols = [
        name for name in col_names if any(kw in name.lower() for kw in ADJUSTMENT_KEYWORDS)
    ]

    evidence = [
        f"{adapter.db_path}::{table}::{name}"
        for name in col_names
        if any(kw in name.lower() for kw in CONTINUOUS_CONTRACT_KEYWORDS)
    ]
    if real_symbol_col:
        evidence.append(f"{adapter.db_path}::{table}::{real_symbol_col}")

    result: dict[str, Any] = {
        "symbol": symbol,
        "table": table,
        "real_symbol_col": real_symbol_col,
        "adjustment_cols": adjustment_cols,
        "evidence": evidence,
        "distinct_count": 0,
        "transitions": [],
    }

    if real_symbol_col:
        date_col = _find_date_column(adapter, table)
        try:
            if date_col:
                query = (
                    f"SELECT {real_symbol_col}, MIN({date_col}), MAX({date_col}), COUNT(*) "
                    f"FROM {table} GROUP BY {real_symbol_col} ORDER BY MIN({date_col})"
                )
                rows = adapter.conn.execute(query).fetchall()
                result["transitions"] = [
                    {
                        "real_symbol": row[0],
                        "first_dt": row[1],
                        "last_dt": row[2],
                        "count": row[3],
                    }
                    for row in rows
                ]
            else:
                rows = adapter.conn.execute(
                    f"SELECT DISTINCT {real_symbol_col} FROM {table}"
                ).fetchall()
                result["transitions"] = [
                    {"real_symbol": row[0]} for row in rows
                ]
            result["distinct_count"] = len(result["transitions"])
        except Exception:
            result["distinct_count"] = 0
            result["transitions"] = []

    return result


def _find_metadata_tables(adapter: Any) -> list[dict[str, Any]]:
    """List DB tables whose names suggest continuous-contract metadata."""
    metadata_tables: list[dict[str, Any]] = []
    for table in adapter.get_tables():
        if any(kw in table.lower() for kw in METADATA_TABLE_KEYWORDS):
            schema = adapter.get_table_schema(table)
            metadata_tables.append(
                {
                    "table": table,
                    "columns": [col["name"] for col in schema],
                }
            )
    return metadata_tables


def _find_777_companion_tables(adapter: Any, symbols: list[str]) -> list[str]:
    """Detect per-symbol 777 individual-contract companion tables."""
    tables = adapter.get_tables()
    found: list[str] = []
    tables_lower = {t.lower(): t for t in tables}
    for symbol in symbols:
        root = symbol.lower().replace("888", "777")
        for lower_name, orig_name in tables_lower.items():
            if lower_name.startswith(root + "_") or lower_name == root:
                found.append(orig_name)
    return found


def analyze_continuous_contract_assumptions(
    db_path: str | Path | None,
    symbols: list[str],
    diagnostics_dir: Path | None = None,
    max_file_mb: float = 50.0,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Assess whether 888 continuous contract synthesis rules are documented (H4)."""
    evidence: list[str] = []
    real_symbol_transitions: dict[str, Any] = {}
    metadata_tables: list[dict[str, Any]] = []
    file_evidence: list[str] = []
    companion_tables: list[str] = []
    status = "unknown"
    resolved_db_path: Path | None = None

    # Only auto-resolve when the caller explicitly supplied a path. This keeps
    # the function deterministic for unit tests that pass db_path=None.
    if db_path is not None:
        resolved_db_path = _resolve_db_path(db_path, repo_root)

    if resolved_db_path is not None:
        if resolved_db_path.exists():
            try:
                adapter = SqliteDataAdapter(str(resolved_db_path))
                try:
                    tables = adapter.get_tables()
                    if not tables:
                        status = "unavailable"
                    else:
                        found_adjusted = False
                        found_spliced = False
                        found_single_contract = False
                        inspected_any = False

                        for symbol in symbols:
                            table = _find_symbol_table(adapter, symbol)
                            if table is None:
                                continue
                            inspected_any = True

                            info = _inspect_table_for_continuous_contract(
                                adapter, table, symbol
                            )
                            evidence.extend(info["evidence"])

                            if info["transitions"]:
                                real_symbol_transitions[symbol] = {
                                    "table": table,
                                    "distinct_count": info["distinct_count"],
                                    "transitions": info["transitions"],
                                }

                            if info["adjustment_cols"]:
                                found_adjusted = True
                                evidence.extend(
                                    [
                                        f"{resolved_db_path}::{table}::{col}"
                                        for col in info["adjustment_cols"]
                                    ]
                                )

                            if info["real_symbol_col"]:
                                if info["distinct_count"] > 1:
                                    found_spliced = True
                                elif info["distinct_count"] == 1:
                                    found_single_contract = True

                        metadata_tables = _find_metadata_tables(adapter)
                        companion_tables = _find_777_companion_tables(adapter, symbols)
                        if companion_tables:
                            evidence.extend(
                                [
                                    f"{resolved_db_path}::{table}::companion_777_table"
                                    for table in companion_tables
                                ]
                            )

                        if found_adjusted:
                            status = "found_adjusted"
                        elif found_spliced:
                            status = "found_spliced"
                        elif found_single_contract:
                            status = "found_single_contract"
                        elif inspected_any:
                            status = "no_evidence"
                        else:
                            status = "unavailable"
                finally:
                    adapter.close()
            except Exception:
                status = "unavailable"
        else:
            status = "unavailable"

    file_evidence = _scan_diagnostics_for_continuous_contract_evidence(
        diagnostics_dir, max_file_mb=max_file_mb
    )

    return {
        "issue": "H4",
        "status": status,
        "symbols": symbols,
        "db_path": str(resolved_db_path) if resolved_db_path else None,
        "evidence": evidence,
        "file_evidence": file_evidence,
        "real_symbol_transitions": real_symbol_transitions,
        "metadata_tables": metadata_tables,
        "companion_777_tables": companion_tables,
        "silently_pass": False,
        "note": "888 continuous contracts require explicit rollover/adjustment rules; missing metadata means the assumption is unverified.",
    }


def analyze_cost_consistency(
    config_values: dict[str, Any],
    engine_defaults: dict[str, Any],
    position_defaults: dict[str, Any],
) -> dict[str, Any]:
    """Detect contradictory cost assumptions across config, engine and position defaults (M1)."""
    if not config_values and not engine_defaults and not position_defaults:
        return {
            "issue": "M1",
            "status": "unavailable",
            "consistent": None,
            "conflicts": [],
            "conflict_details": [],
            "recommended_source": "BACKTEST_CONFIG",
            "note": "No cost inputs provided; cannot verify consistency.",
        }

    keys = ("commission", "slippage")
    conflict_sources: set[str] = set()
    conflict_details: list[str] = []
    for key in keys:
        vals = {
            "BACKTEST_CONFIG": config_values.get(key),
            "engine_default": engine_defaults.get(key),
            "position_default": position_defaults.get(key),
        }
        baseline = vals["BACKTEST_CONFIG"]
        unique = {v for v in vals.values() if v is not None}
        if len(unique) > 1:
            for source, value in vals.items():
                if source != "BACKTEST_CONFIG" and value != baseline:
                    conflict_sources.add(source)
            conflict_details.append(
                f"{key}: BACKTEST_CONFIG={vals['BACKTEST_CONFIG']}, "
                f"engine_default={vals['engine_default']}, "
                f"position_default={vals['position_default']}"
            )

    conflicts = sorted(conflict_sources)
    return {
        "issue": "M1",
        "status": "detected" if conflicts else "ok",
        "consistent": not conflicts,
        "conflicts": conflicts,
        "conflict_details": conflict_details,
        "recommended_source": "BACKTEST_CONFIG",
        "note": "Backtest costs must come from a single source; engine and position defaults should not override BACKTEST_CONFIG.",
    }


# ---------------------------------------------------------------------------
# Real-project input collectors (A32)
# ---------------------------------------------------------------------------


def _extract_dict_defaults(filepath: Path, target_name: str) -> dict[str, Any] | None:
    """Parse a top-level dict assignment such as BACKTEST_CONFIG = {...}."""
    if not filepath.exists():
        return None
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == target_name:
                    result: dict[str, Any] = {}
                    if isinstance(node.value, ast.Dict):
                        for k, v in zip(node.value.keys, node.value.values):
                            if isinstance(k, ast.Constant):
                                try:
                                    result[k.value] = ast.literal_eval(v)
                                except Exception:
                                    pass
                    return result
    return None


def _extract_init_defaults(filepath: Path, class_name: str) -> dict[str, Any] | None:
    """Parse class __init__ default argument values."""
    if not filepath.exists():
        return None
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                    defaults = [ast.literal_eval(d) for d in item.args.defaults]
                    args = item.args.args
                    offset = len(args) - len(defaults)
                    result: dict[str, Any] = {}
                    for i, default in enumerate(defaults):
                        arg_name = args[offset + i].arg
                        result[arg_name] = default
                    return result
    return None


def collect_cost_inputs_from_project(repo_root: Path) -> dict[str, Any]:
    """Introspect BACKTEST_CONFIG, BacktestEngine defaults and Position defaults."""
    chan = repo_root / "examples" / "czsc_strategy" / "chan_strategy"
    config = _extract_dict_defaults(chan / "config.py", "BACKTEST_CONFIG") or {}
    engine_init = _extract_init_defaults(chan / "backtest_engine.py", "BacktestEngine") or {}
    position_init = _extract_init_defaults(chan / "positions.py", "Position") or {}

    def rename(d: dict[str, Any]) -> dict[str, Any]:
        return {
            "commission": d.get("commission_rate"),
            "slippage": d.get("slippage"),
        }

    return {
        "BACKTEST_CONFIG": rename(config),
        "engine_defaults": rename(engine_init),
        "position_defaults": rename(position_init),
    }


def _is_stop_loss_record(record: dict[str, Any]) -> bool:
    for key in EXIT_REASON_KEYS:
        value = str(record.get(key, "")).lower()
        if any(token in value for token in STOP_LOSS_REASON_TOKENS):
            return True
    return False


def _extract_pnl_pct(record: dict[str, Any]) -> float | None:
    for key in PNL_PCT_KEYS:
        value = record.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _walk_json_for_lists(obj: Any, key_name: str | None = None) -> Any:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key_name and key == key_name and isinstance(value, list):
                yield from value
            else:
                yield from _walk_json_for_lists(value, key_name)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk_json_for_lists(item, key_name)


def _iter_dict_candidates(obj: Any) -> Any:
    if isinstance(obj, dict):
        for value in obj.values():
            yield from _iter_dict_candidates(value)
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict):
                yield item
            else:
                yield from _iter_dict_candidates(item)


def collect_stop_loss_pairs_from_diagnostics(
    diagnostics_dir: Path, max_file_mb: float = 50.0
) -> list[dict[str, Any]]:
    """Scan diagnostics JSON files for stop-loss trade records."""
    if not diagnostics_dir or not diagnostics_dir.exists():
        return []

    pairs: list[dict[str, Any]] = []
    max_bytes = max_file_mb * 1024 * 1024
    for path in diagnostics_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() != ".json":
            continue
        if path.name.startswith("audit_issue_diagnostics"):
            continue
        if path.stat().st_size > max_bytes:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue

        for record in _iter_dict_candidates(data):
            if not _is_stop_loss_record(record):
                continue
            pnl = _extract_pnl_pct(record)
            if pnl is None:
                continue
            pairs.append(
                {
                    "symbol": record.get("symbol"),
                    "strategy": record.get("strategy"),
                    "open_dt": record.get("open_dt") or record.get("open_time"),
                    "close_dt": record.get("close_dt") or record.get("close_time"),
                    "pnl_pct": pnl,
                    "exit_reason": next(
                        (record.get(k) for k in EXIT_REASON_KEYS if record.get(k)), None
                    ),
                    "source_file": str(path.relative_to(diagnostics_dir)),
                }
            )
    return pairs


def _contains_divergence(value: Any) -> bool:
    text = str(value)
    return "背驰" in text or "divergence" in text.lower()


def _extract_signal_records(data: Any, source_file: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if isinstance(data, dict):
        dt = data.get("dt") or data.get("date")
        direct_signal = data.get("signal")
        if dt and isinstance(direct_signal, str) and _contains_divergence(direct_signal):
            records.append({"dt": dt, "signal": direct_signal, "source_file": source_file})

        for key, value in data.items():
            if key in SIGNAL_CONTAINER_KEYS:
                if isinstance(value, dict):
                    for sub_key, sub_value in value.items():
                        if _contains_divergence(sub_key) or _contains_divergence(sub_value):
                            records.append(
                                {
                                    "dt": dt,
                                    "signal": f"{sub_key}={sub_value}",
                                    "source_file": source_file,
                                }
                            )
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            records.extend(_extract_signal_records(item, source_file))
                        elif isinstance(item, str) and _contains_divergence(item):
                            records.append({"dt": dt, "signal": item, "source_file": source_file})
            elif isinstance(value, (dict, list)):
                records.extend(_extract_signal_records(value, source_file))
    elif isinstance(data, list):
        for item in data:
            records.extend(_extract_signal_records(item, source_file))
    return records


def collect_signal_records_from_diagnostics(
    diagnostics_dir: Path, max_file_mb: float = 50.0
) -> list[dict[str, Any]]:
    """Scan diagnostics JSON files for divergence/failure signal records."""
    if not diagnostics_dir or not diagnostics_dir.exists():
        return []

    records: list[dict[str, Any]] = []
    max_bytes = max_file_mb * 1024 * 1024
    for path in diagnostics_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() != ".json":
            continue
        if path.name.startswith("audit_issue_diagnostics"):
            continue
        if path.stat().st_size > max_bytes:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        source_file = str(path.relative_to(diagnostics_dir))
        records.extend(_extract_signal_records(data, source_file))
    return records


def _parse_parameter_value(text: str) -> list[dict[str, Any]]:
    """Extract weight/multiplier values from markdown/json text."""
    import re

    params: list[dict[str, Any]] = []
    for line in text.splitlines():
        lower = line.lower()
        if not any(token in lower for token in ("multiplier", "weight", "ratio", "0.847", "0.85")):
            continue
        for match in re.finditer(
            r"(?:multiplier|weight|ratio)\s*[=:]\s*([0-9]+\.[0-9]+)", line, re.IGNORECASE
        ):
            params.append({"name": "parsed_weight", "value": float(match.group(1))})
        for match in re.finditer(r"\b(0\.\d{2,3})\b", line):
            val = float(match.group(1))
            if _is_high_precision(val):
                params.append({"name": "parsed_weight", "value": val})
    return params


def collect_parameter_evidence_from_diagnostics(
    diagnostics_dir: Path, max_file_mb: float = 50.0
) -> dict[str, Any]:
    """Collect H1-relevant parameter evidence from diagnostics filenames and text."""
    if not diagnostics_dir or not diagnostics_dir.exists():
        return {"params": [], "evidence_files": []}

    evidence_files: list[str] = []
    params: list[dict[str, Any]] = []
    max_bytes = max_file_mb * 1024 * 1024
    for path in diagnostics_dir.iterdir():
        if not path.is_file():
            continue
        lower = path.name.lower()
        if any(marker in lower for marker in PARAM_EVIDENCE_FILENAME_MARKERS):
            evidence_files.append(str(path))
            if path.suffix.lower() in READABLE_EXTENSIONS and path.stat().st_size <= max_bytes:
                try:
                    text = path.read_text(encoding="utf-8")
                except Exception:
                    continue
                params.extend(_parse_parameter_value(text))
    return {"params": params, "evidence_files": sorted(evidence_files)}


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------


def build_audit_issue_report(
    date: str,
    params: list[dict[str, Any]] | None = None,
    pairs: list[dict[str, Any]] | None = None,
    stop_loss_bp: int = 300,
    signal_records: list[dict[str, Any]] | None = None,
    db_path: str | Path | None = None,
    symbols: list[str] | None = None,
    cost_config: dict[str, Any] | None = None,
    engine_defaults: dict[str, Any] | None = None,
    position_defaults: dict[str, Any] | None = None,
    repo_root: Path | None = None,
    diagnostics_dir: Path | None = None,
    evidence_dir: Path | None = None,
    max_file_mb: float = 50.0,
) -> dict[str, Any]:
    """Aggregate all H1/H2/H3/H4/M1 diagnostics into one report."""
    used_diagnostics_dir = diagnostics_dir or evidence_dir

    # H1
    h1_data_source = "caller_input"
    h1_params = params
    h1_evidence_files: list[str] = []
    if h1_params is None and used_diagnostics_dir:
        param_evidence = collect_parameter_evidence_from_diagnostics(
            used_diagnostics_dir, max_file_mb=max_file_mb
        )
        h1_params = param_evidence.get("params", [])
        h1_evidence_files = param_evidence.get("evidence_files", [])
        h1_data_source = "diagnostics_filename_scan"
    h1 = detect_high_precision_weights(h1_params or [], evidence_dir=used_diagnostics_dir)
    if h1_evidence_files and not h1.get("evidence_files"):
        h1["evidence_files"] = h1_evidence_files
    h1["data_source"] = h1_data_source

    # H2
    h2_data_source = "caller_input"
    h2_pairs = pairs
    if h2_pairs is None and used_diagnostics_dir:
        h2_pairs = collect_stop_loss_pairs_from_diagnostics(
            used_diagnostics_dir, max_file_mb=max_file_mb
        )
        h2_data_source = "diagnostics_json_scan"
    h2 = analyze_stop_loss_overshoot(h2_pairs or [], stop_loss_bp=stop_loss_bp)
    h2["data_source"] = h2_data_source

    # H3
    h3_data_source = "caller_input"
    h3_records = signal_records
    if h3_records is None and used_diagnostics_dir:
        h3_records = collect_signal_records_from_diagnostics(
            used_diagnostics_dir, max_file_mb=max_file_mb
        )
        h3_data_source = "diagnostics_json_scan"
        if h3_records and any(
            any(marker in str(r.get("source_file", "")) for marker in SIGNAL_HISTORY_FILENAME_MARKERS)
            for r in h3_records
        ):
            h3_data_source = "signal_history_replay"
    h3 = analyze_divergence_failure_reachability(h3_records or [])
    h3["data_source"] = h3_data_source

    # H4
    h4 = analyze_continuous_contract_assumptions(
        db_path,
        symbols or [],
        diagnostics_dir=used_diagnostics_dir,
        max_file_mb=max_file_mb,
        repo_root=repo_root,
    )
    h4["data_source"] = "sqlite_metadata" if h4.get("db_path") else "unavailable"

    # M1
    m1_data_source = "caller_input"
    if cost_config is None and repo_root:
        cost_inputs = collect_cost_inputs_from_project(repo_root)
        cost_config = cost_inputs.get("BACKTEST_CONFIG", {})
        engine_defaults = cost_inputs.get("engine_defaults", {})
        position_defaults = cost_inputs.get("position_defaults", {})
        m1_data_source = "project_config_introspection"
    m1 = analyze_cost_consistency(
        cost_config or {}, engine_defaults or {}, position_defaults or {}
    )
    m1["data_source"] = m1_data_source

    return {
        "date": date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "disclaimer": "Diagnostic only, not a trading recommendation.",
        "issues": {
            "H1": h1,
            "H2": h2,
            "H3": h3,
            "H4": h4,
            "M1": m1,
        },
    }


def _format_issue_markdown(issue_id: str, issue: dict[str, Any]) -> str:
    lines = [f"## {issue_id}", ""]
    for key, value in issue.items():
        if key == "issue":
            continue
        if isinstance(value, (list, dict)):
            value_str = json.dumps(value, ensure_ascii=False, indent=2)
        else:
            value_str = str(value)
        lines.append(f"- **{key}**: {value_str}")
    lines.append("")
    return "\n".join(lines)


def write_json_report(report: dict[str, Any], path: Path) -> None:
    """Write the diagnostic report as JSON after a sensitive-data scan."""
    if contains_sensitive_data(report):
        raise RuntimeError("report contains sensitive data; will not write")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    path.write_text(payload, encoding="utf-8")


def write_markdown_report(report: dict[str, Any], path: Path) -> None:
    """Write the diagnostic report as Markdown."""
    lines = [
        "# Audit Issue Diagnostics",
        "",
        f"Date: {report['date']}",
        f"Generated at: {report['generated_at']}",
        "",
        f"> {report['disclaimer']}",
        "",
        "This report quantifies audit findings. It does **not** claim the strategy is profitable or that any issue is fixed.",
        "",
    ]
    for issue_id, issue in report["issues"].items():
        lines.append(_format_issue_markdown(issue_id, issue))
    lines.append("---")
    lines.append("")
    lines.append("End of diagnostic report.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _load_json(path: Path) -> Any:
    if not path or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only diagnostics for audit issues H1/H2/H3/H4/M1."
    )
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--date", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    parser.add_argument("--diagnostics-dir", type=Path, default=DEFAULT_DIAGNOSTICS_DIR)
    parser.add_argument("--db-path", type=Path, help="Path to SQLite DB for H4 inspection.")
    parser.add_argument(
        "--symbols",
        default="AP888,RB888,SC888,A888,ZN888",
        help="Comma-separated list of continuous contract symbols.",
    )
    parser.add_argument("--pairs-json", type=Path, help="JSON file with trade pairs for H2.")
    parser.add_argument(
        "--signals-json", type=Path, help="JSON file with signal history records for H3."
    )
    parser.add_argument("--params-json", type=Path, help="JSON file with parameter list for H1.")
    parser.add_argument(
        "--cost-config-json", type=Path, help="JSON file with BACKTEST_CONFIG cost values for M1."
    )
    parser.add_argument(
        "--engine-defaults-json", type=Path, help="JSON file with engine default cost values for M1."
    )
    parser.add_argument(
        "--position-defaults-json",
        type=Path,
        help="JSON file with position default cost values for M1.",
    )
    parser.add_argument("--stop-loss-bp", type=int, default=300)
    parser.add_argument("--max-file-mb", type=float, default=50.0)
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    params = _load_json(args.params_json)
    pairs = _load_json(args.pairs_json)
    signal_records = _load_json(args.signals_json)
    cost_config = _load_json(args.cost_config_json)
    engine_defaults = _load_json(args.engine_defaults_json)
    position_defaults = _load_json(args.position_defaults_json)

    resolved_db_path = _resolve_db_path(args.db_path, repo_root=args.repo_root)

    report = build_audit_issue_report(
        date=args.date,
        params=params,
        pairs=pairs,
        stop_loss_bp=args.stop_loss_bp,
        signal_records=signal_records,
        db_path=resolved_db_path,
        symbols=symbols,
        cost_config=cost_config,
        engine_defaults=engine_defaults,
        position_defaults=position_defaults,
        repo_root=args.repo_root,
        diagnostics_dir=args.diagnostics_dir,
        max_file_mb=args.max_file_mb,
    )

    json_path = args.out_dir / f"audit_issue_diagnostics_{args.date}.json"
    md_path = args.out_dir / f"audit_issue_diagnostics_{args.date}.md"
    write_json_report(report, json_path)
    write_markdown_report(report, md_path)
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")


if __name__ == "__main__":
    main()
