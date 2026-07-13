"""A47 P8a — Exit-model diagnostic report.

Read-only report comparing ``exit_model="legacy"`` with
``exit_model="structural_atr"`` on the honest post-P1 baseline.  Per-symbol
per-trade give-back (peak-to-exit) and early-exit (exit-to-subsequent-extreme)
statistics are reported for research review.

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


HERE = Path(__file__).resolve().parent
DEFAULT_OUT_DIR = HERE
BANNER = "RESEARCH-ONLY — Diagnostic only, not a trading recommendation."
SYMBOLS = ["AP888", "RB888", "SC888", "A888", "ZN888"]
WINDOW_START = "2026-04-24"
WINDOW_END = "2026-07-09"
POST_EXIT_HORIZON_BARS = 20

METHODOLOGY = (
    "Methodology — exit_model='legacy' uses a fixed-percentage-giveback trailing stop that becomes "
    "active once trailing_start_bp is crossed. exit_model='structural_atr' uses a partial "
    "take-profit at the first directional target, followed by an ATR trailing stop on the "
    "remainder. Because the ATR trailing stop is evaluated only after a partial take-profit "
    "event has fired, positions that never reach a directional target rely solely on the fixed "
    "stop-loss and timeout for profit-side protection. This report compares the two models on "
    "the same post-2026-04-24 window; no threshold tuning is performed."
)


@dataclass
class ExitDiagnostics:
    """Per-trade diagnostic measurements."""
    open_dt: str
    close_dt: str
    strategy: str
    direction: str
    open_price: float
    close_price: float
    pnl_pct: float
    exit_reason: str
    peak_price: float
    trough_price: float
    give_back_pct: float
    subsequent_high: float
    subsequent_low: float
    early_exit_pct: float


def _direction_from_strategy(strategy: str) -> str:
    return "short" if "空头" in strategy else "long"


def _compute_trade_diagnostics(
    pairs: list[dict[str, Any]],
    trade_bars: list[Any],
) -> list[ExitDiagnostics]:
    """Compute give-back and early-exit stats for each closed pair."""
    diagnostics: list[ExitDiagnostics] = []
    if not trade_bars:
        return diagnostics

    bar_dts = [b.dt for b in trade_bars]

    for pair in pairs:
        open_dt = pair.get("open_dt")
        close_dt = pair.get("close_dt")
        if open_dt is None or close_dt is None:
            continue

        # Bars held during the trade
        in_trade_bars = [b for b in trade_bars if open_dt <= b.dt <= close_dt]
        if not in_trade_bars:
            continue

        peak_price = max(b.high for b in in_trade_bars)
        trough_price = min(b.low for b in in_trade_bars)

        # Bars after exit up to the horizon
        close_idx = bar_dts.index(close_dt) if close_dt in bar_dts else None
        if close_idx is not None:
            post_bars = trade_bars[close_idx + 1: close_idx + 1 + POST_EXIT_HORIZON_BARS]
        else:
            post_bars = []

        subsequent_high = max((b.high for b in post_bars), default=pair.get("close_price", 0.0))
        subsequent_low = min((b.low for b in post_bars), default=pair.get("close_price", 0.0))

        direction = _direction_from_strategy(pair.get("strategy", ""))
        open_price = pair.get("open_price", 0.0)
        close_price = pair.get("close_price", 0.0)

        if direction == "long":
            give_back_pct = (peak_price - close_price) / open_price if open_price else 0.0
            early_exit_pct = (subsequent_high - close_price) / open_price if open_price else 0.0
        else:
            give_back_pct = (close_price - trough_price) / open_price if open_price else 0.0
            early_exit_pct = (close_price - subsequent_low) / open_price if open_price else 0.0

        diagnostics.append(ExitDiagnostics(
            open_dt=open_dt.isoformat() if hasattr(open_dt, "isoformat") else str(open_dt),
            close_dt=close_dt.isoformat() if hasattr(close_dt, "isoformat") else str(close_dt),
            strategy=pair.get("strategy", ""),
            direction=direction,
            open_price=open_price,
            close_price=close_price,
            pnl_pct=pair.get("pnl_pct", 0.0),
            exit_reason=pair.get("reason", ""),
            peak_price=peak_price,
            trough_price=trough_price,
            give_back_pct=give_back_pct,
            subsequent_high=subsequent_high,
            subsequent_low=subsequent_low,
            early_exit_pct=early_exit_pct,
        ))

    return diagnostics


def _run_backtest(
    symbol: str,
    exit_model: str,
    db_path: Path,
    start_date: str,
    end_date: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[Any]]:
    """Run a single-symbol backtest under the requested exit model."""
    original_exit_model = STRATEGY_CONFIG.get("exit_model")
    try:
        STRATEGY_CONFIG["exit_model"] = exit_model
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
        return report, combined_pairs, getattr(engine, "trade_bars", [])
    finally:
        if original_exit_model is None:
            STRATEGY_CONFIG.pop("exit_model", None)
        else:
            STRATEGY_CONFIG["exit_model"] = original_exit_model


def _serialize_pair(pair: dict[str, Any]) -> dict[str, Any]:
    """Make a trade pair JSON-serializable (datetime -> iso string)."""
    out = {}
    for k, v in pair.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def _overall_metrics(
    report: dict[str, Any],
    combined_pairs: list[dict[str, Any]],
    trade_bars: list[Any],
) -> dict[str, Any]:
    """Extract overall strategy metrics and per-trade diagnostics."""
    diagnostics = _compute_trade_diagnostics(combined_pairs, trade_bars)
    wins = [d for d in diagnostics if d.pnl_pct > 0]
    losses = [d for d in diagnostics if d.pnl_pct <= 0]

    def _avg(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    return {
        "trade_count": report.get("total_trades", 0),
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate": report.get("win_rate", 0.0),
        "profit_factor": report.get("profit_factor", 0.0),
        "total_return_pct": report.get("total_return_pct", 0.0),
        "max_drawdown_pct": report.get("max_drawdown_pct", 0.0),
        "sharpe_ratio": report.get("sharpe_ratio", 0.0),
        "avg_give_back_pct": _avg([d.give_back_pct for d in diagnostics]),
        "avg_early_exit_pct": _avg([d.early_exit_pct for d in diagnostics]),
        "median_give_back_pct": (
            sorted(d.give_back_pct for d in diagnostics)[len(diagnostics) // 2]
            if diagnostics else 0.0
        ),
        "median_early_exit_pct": (
            sorted(d.early_exit_pct for d in diagnostics)[len(diagnostics) // 2]
            if diagnostics else 0.0
        ),
        "pairs": [_serialize_pair(p) for p in combined_pairs],
        "diagnostics": [d.__dict__ for d in diagnostics],
    }


def _empty_metrics() -> dict[str, Any]:
    return {
        "trade_count": 0,
        "win_count": 0,
        "loss_count": 0,
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "total_return_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "sharpe_ratio": 0.0,
        "avg_give_back_pct": 0.0,
        "avg_early_exit_pct": 0.0,
        "median_give_back_pct": 0.0,
        "median_early_exit_pct": 0.0,
        "pairs": [],
        "diagnostics": [],
    }


def _run_symbol(
    symbol: str,
    db_path: Path,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    """Run legacy and structural_atr variants for one symbol."""
    result: dict[str, Any] = {
        "symbol": symbol,
        "legacy": None,
        "structural_atr": None,
        "error": None,
    }

    if not db_path.exists():
        result["error"] = "database_not_found"
        for mode in ("legacy", "structural_atr"):
            result[mode] = _empty_metrics()
        return result

    try:
        legacy_report, legacy_pairs, legacy_bars = _run_backtest(
            symbol, "legacy", db_path, start_date, end_date
        )
        atr_report, atr_pairs, atr_bars = _run_backtest(
            symbol, "structural_atr", db_path, start_date, end_date
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        result["error"] = f"backtest_failed: {exc}"
        for mode in ("legacy", "structural_atr"):
            result[mode] = _empty_metrics()
        return result

    errors: list[str] = []
    for mode, report, pairs, bars in (
        ("legacy", legacy_report, legacy_pairs, legacy_bars),
        ("structural_atr", atr_report, atr_pairs, atr_bars),
    ):
        if "error" in report:
            errors.append(f"{mode}_error: {report['error']}")
            result[mode] = _empty_metrics()
        else:
            result[mode] = _overall_metrics(report, pairs, bars)

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
    for mode in ("legacy", "structural_atr"):
        totals[mode] = {
            "trade_count": sum(
                s[mode].get("trade_count", 0) for s in per_symbol if s.get(mode)
            ),
            "win_count": sum(
                s[mode].get("win_count", 0) for s in per_symbol if s.get(mode)
            ),
            "loss_count": sum(
                s[mode].get("loss_count", 0) for s in per_symbol if s.get(mode)
            ),
        }

    payload = {
        "disclaimer": BANNER,
        "generated_at": datetime.now().isoformat(),
        "exit_model": "legacy vs structural_atr",
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
        "# A47 P8a — Exit-Model Diagnostic",
        "",
        f"**{payload['disclaimer']}**",
        "",
        f"Generated: {payload['generated_at']}",
        f"Window: {payload['window']['start_date']} ~ {payload['window']['end_date']}",
        "",
        "## Totals",
        "",
        "| Mode | Trades | Wins | Losses |",
        "|------|-------:|-----:|-------:|",
    ]
    for mode, t in payload["totals"].items():
        lines.append(
            f"| {mode} | {t['trade_count']} | {t['win_count']} | {t['loss_count']} |"
        )

    lines.extend(["", "## Per-symbol summary", ""])
    lines.append(
        "| Symbol | Mode | Trades | Win Rate | Return | Max DD | Avg Give-Back | Avg Early-Exit |"
    )
    lines.append(
        "|--------|------|-------:|---------:|-------:|-------:|--------------:|---------------:|"
    )

    for symbol_data in payload["per_symbol"]:
        symbol = symbol_data["symbol"]
        error = symbol_data.get("error")
        if error:
            lines.append(
                f"| {symbol} | - | - | - | - | - | error: {error} | - |"
            )
            continue
        for mode in ("legacy", "structural_atr"):
            m = symbol_data[mode]
            lines.append(
                f"| {symbol} | {mode} | {m['trade_count']} | "
                f"{m['win_rate']*100:.1f}% | {m['total_return_pct']:.2f}% | "
                f"{m['max_drawdown_pct']:.2f}% | "
                f"{m['avg_give_back_pct']*100:.2f}% | {m['avg_early_exit_pct']*100:.2f}% |"
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
    """Generate the exit-model diagnostic report."""
    db_path = db_path or Path(SQLITE_DB_PATH)
    stamp = stamp or datetime.now().strftime("%Y-%m-%d")
    payload = _build_payload(db_path, symbols, start_date, end_date, stamp)

    json_path = out_dir / f"exit_model_report_{stamp}.json"
    md_path = out_dir / f"exit_model_report_{stamp}.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(_format_md(payload))

    print("Exit-model diagnostic report written to:")
    print(f"  JSON: {json_path}")
    print(f"  MD:   {md_path}")
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate A47 P8a exit-model diagnostic report."
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
