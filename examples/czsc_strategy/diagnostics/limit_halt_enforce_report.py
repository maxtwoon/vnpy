"""A67 — Limit/halt unexecutable-fill enforce-mode diagnostic report.

Read-only comparison of ``limit_halt_model`` values (``off`` / ``aware`` /
``enforce``) on the honest post-2026-04-24 window.  Reported as honest
measurement, not a superiority claim.

RESEARCH-ONLY — Diagnostic only, not a trading recommendation.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

# Make the czsc_strategy package importable from this diagnostics script
_CZSC_STRATEGY_ROOT = Path(__file__).resolve().parent.parent
if str(_CZSC_STRATEGY_ROOT) not in sys.path:
    sys.path.insert(0, str(_CZSC_STRATEGY_ROOT))

from chan_strategy.backtest_engine import BacktestEngine  # noqa: E402
from chan_strategy.config import SQLITE_DB_PATH, STRATEGY_CONFIG  # noqa: E402
from diagnostics.declassify_historical_reports import build_banner  # noqa: E402


HERE = Path(__file__).resolve().parent
DEFAULT_OUT_DIR = HERE
SYMBOLS = ["AP888", "RB888", "SC888", "A888", "ZN888"]
WINDOW_START = "2026-04-24"
WINDOW_END = "2026-07-09"

METHODOLOGY = (
    "Methodology — each backtest is run with the same strategy configuration and the same "
    "post-2026-04-24 price window, varying only ``limit_halt_model``. "
    "``off`` is the legacy baseline with no limit/halt tagging. "
    "``aware`` tags fills that occur at the directionally-relevant daily limit band but does "
    "not block them. ``enforce`` rejects fills that occur at the unexecutable limit band "
    "(long entry at upper limit, long exit at lower limit, short entry at lower limit, "
    "short exit at upper limit) and retries on the next bar. "
    "The comparison is reported as honest measurement, not as evidence that any mode is superior."
)


@dataclass
class ModeMetrics:
    """Per-mode summary extracted from a backtest report."""
    trade_count: int
    win_count: int
    loss_count: int
    total_return_pct: float
    win_rate: float
    profit_factor: float
    max_drawdown_pct: float
    sharpe_ratio: float


def _run_backtest(
    symbol: str,
    mode: str,
    db_path: Path,
    start_date: str,
    end_date: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Run a single-symbol backtest under the requested limit_halt_model."""
    original_mode = STRATEGY_CONFIG.get("limit_halt_model")
    try:
        STRATEGY_CONFIG["limit_halt_model"] = mode
        engine = BacktestEngine(
            symbol=symbol,
            freq="1",
            start_date=start_date,
            end_date=end_date,
            db_path=str(db_path),
            table_name=f"{symbol.lower()}_1M_raw",
        )
        report = engine.run()
        combined_pairs = engine.strategy.get_combined_trades() if engine.strategy else []
        return report, combined_pairs
    finally:
        if original_mode is None:
            STRATEGY_CONFIG.pop("limit_halt_model", None)
        else:
            STRATEGY_CONFIG["limit_halt_model"] = original_mode


def _extract_metrics(report: dict[str, Any], pairs: list[dict[str, Any]]) -> ModeMetrics:
    """Extract comparable metrics from a completed backtest."""
    return ModeMetrics(
        trade_count=report.get("total_trades", 0),
        win_count=report.get("win_count", 0),
        loss_count=report.get("loss_count", 0),
        total_return_pct=report.get("total_return_pct", 0.0),
        win_rate=report.get("win_rate", 0.0),
        profit_factor=report.get("profit_factor", 0.0),
        max_drawdown_pct=report.get("max_drawdown_pct", 0.0),
        sharpe_ratio=report.get("sharpe_ratio", 0.0),
    )


def _empty_metrics() -> ModeMetrics:
    return ModeMetrics(0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0)


def _metrics_to_dict(m: ModeMetrics) -> dict[str, Any]:
    return {
        "trade_count": m.trade_count,
        "win_count": m.win_count,
        "loss_count": m.loss_count,
        "total_return_pct": m.total_return_pct,
        "win_rate": m.win_rate,
        "profit_factor": m.profit_factor,
        "max_drawdown_pct": m.max_drawdown_pct,
        "sharpe_ratio": m.sharpe_ratio,
    }


def _run_symbol(
    symbol: str,
    db_path: Path,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    """Run off/aware/enforce for one symbol."""
    result: dict[str, Any] = {
        "symbol": symbol,
        "off": None,
        "aware": None,
        "enforce": None,
        "error": None,
    }

    if not db_path.exists():
        result["error"] = "database_not_found"
        for mode in ("off", "aware", "enforce"):
            result[mode] = _metrics_to_dict(_empty_metrics())
        return result

    errors: list[str] = []
    for mode in ("off", "aware", "enforce"):
        try:
            report, pairs = _run_backtest(symbol, mode, db_path, start_date, end_date)
        except Exception as exc:  # pragma: no cover - defensive logging
            errors.append(f"{mode}_failed: {exc}")
            result[mode] = _metrics_to_dict(_empty_metrics())
            continue

        if "error" in report:
            errors.append(f"{mode}_error: {report['error']}")
            result[mode] = _metrics_to_dict(_empty_metrics())
        else:
            result[mode] = _metrics_to_dict(_extract_metrics(report, pairs))
            result[f"{mode}_rejected_count"] = sum(
                1 for p in pairs if p.get("fill_rejected_at_limit")
            )

    if errors:
        result["error"] = "; ".join(errors)

    return result


def _build_payload(
    db_path: Path,
    symbols: tuple[str, ...],
    start_date: str,
    end_date: str,
    stamp: str,
) -> dict[str, Any]:
    """Build the full report payload."""
    per_symbol = []
    for symbol in symbols:
        per_symbol.append(_run_symbol(symbol, db_path, start_date, end_date))

    totals = {}
    for mode in ("off", "aware", "enforce"):
        totals[mode] = {
            "trade_count": sum(
                s[mode]["trade_count"] for s in per_symbol if s.get(mode)
            ),
            "win_count": sum(
                s[mode]["win_count"] for s in per_symbol if s.get(mode)
            ),
            "loss_count": sum(
                s[mode]["loss_count"] for s in per_symbol if s.get(mode)
            ),
            "total_return_pct": sum(
                s[mode]["total_return_pct"] for s in per_symbol if s.get(mode)
            ),
        }

    payload = {
        "disclaimer": build_banner(),
        "generated_at": datetime.now().isoformat(),
        "limit_halt_model": "off vs aware vs enforce",
        "note": (
            "This report is evidence only and is not used to select or tune parameters. "
            "No threshold tuning is performed from this report in-task. "
            "Window chosen as the most recent continuous post-2026-04-24 period available."
        ),
        "window": {"start_date": start_date, "end_date": end_date},
        "total_symbols": len(symbols),
        "symbols_attempted": list(symbols),
        "methodology": METHODOLOGY,
        "totals": totals,
        "per_symbol": per_symbol,
    }
    return payload


def _format_md(payload: dict[str, Any]) -> str:
    """Render payload as Markdown for human review."""
    lines = [
        "# A67 — Limit/Halt Enforce-Mode Diagnostic",
        "",
        payload["disclaimer"],
        "",
        f"Generated: {payload['generated_at']}",
        f"Window: {payload['window']['start_date']} ~ {payload['window']['end_date']}",
        "",
        "## Totals",
        "",
        "| Mode | Trades | Wins | Losses | Total Return |",
        "|------|-------:|-----:|-------:|-------------:|",
    ]
    for mode, t in payload["totals"].items():
        lines.append(
            f"| {mode} | {t['trade_count']} | {t['win_count']} | {t['loss_count']} | "
            f"{t['total_return_pct']:.2f}% |"
        )

    lines.extend(["", "## Per-symbol summary", ""])
    lines.append(
        "| Symbol | Mode | Trades | Win Rate | Return | Max DD | Sharpe | Rejected |"
    )
    lines.append(
        "|--------|------|-------:|---------:|-------:|-------:|-------:|---------:|"
    )

    for symbol_data in payload["per_symbol"]:
        symbol = symbol_data["symbol"]
        error = symbol_data.get("error")
        if error:
            lines.append(
                f"| {symbol} | - | - | - | - | - | - | error: {error} |"
            )
            continue
        for mode in ("off", "aware", "enforce"):
            m = symbol_data[mode]
            rejected = symbol_data.get(f"{mode}_rejected_count", 0)
            lines.append(
                f"| {symbol} | {mode} | {m['trade_count']} | "
                f"{m['win_rate']*100:.1f}% | {m['total_return_pct']:.2f}% | "
                f"{m['max_drawdown_pct']:.2f}% | {m['sharpe_ratio']:.2f} | {rejected} |"
            )

    lines.extend(["", "## Note", "", payload["note"], ""])
    lines.extend(["## Methodology", "", payload.get("methodology", METHODOLOGY), ""])
    return "\n".join(lines)


def main(
    db_path: Path | None = None,
    out_dir: Path = DEFAULT_OUT_DIR,
    symbols: tuple[str, ...] = tuple(SYMBOLS),
    start_date: str = WINDOW_START,
    end_date: str = WINDOW_END,
    stamp: str | None = None,
) -> dict[str, Any]:
    """Generate the limit/halt enforce-mode diagnostic report."""
    db_path = db_path or Path(SQLITE_DB_PATH)
    stamp = stamp or datetime.now().strftime("%Y-%m-%d")
    payload = _build_payload(db_path, symbols, start_date, end_date, stamp)

    json_path = out_dir / f"limit_halt_enforce_report_{stamp}.json"
    md_path = out_dir / f"limit_halt_enforce_report_{stamp}.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(_format_md(payload))

    print("Limit/halt enforce-mode diagnostic report written to:")
    print(f"  JSON: {json_path}")
    print(f"  MD:   {md_path}")
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate A67 limit/halt enforce-mode diagnostic report."
    )
    parser.add_argument(
        "--db-path", type=Path, default=None,
        help="Path to the SQLite kline database.",
    )
    parser.add_argument(
        "--out-dir", type=Path, default=DEFAULT_OUT_DIR,
        help="Directory to write the report files.",
    )
    parser.add_argument(
        "--start-date", type=str, default=WINDOW_START,
        help="Backtest window start (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--end-date", type=str, default=WINDOW_END,
        help="Backtest window end (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--symbols", nargs="+", default=list(SYMBOLS),
        help="Symbols to include in the report.",
    )
    args = parser.parse_args()
    main(
        db_path=args.db_path,
        out_dir=args.out_dir,
        symbols=tuple(args.symbols),
        start_date=args.start_date,
        end_date=args.end_date,
    )
