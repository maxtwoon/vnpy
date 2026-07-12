"""A40 unified position sizing report.

Joins, for the same backtest run:
  (a) real risk-mode position sizes and currency PnL per closed trade,
  (b) the active stop_execution_model and touch-based vs close-based stop-exit counts,
  (c) a SimNow replay-derived risk-caliber placeholder (status "not_available_pending_A41"
      until A41 lands; never a fabricated number).

RESEARCH-ONLY: pnl_currency / total_open_margin / margin_utilization_pct use the
exchange-minimum margin rates in STRATEGY_CONFIG["contract_specs"], not production-ready
broker-marked-up numbers.

Example:
    python examples/czsc_strategy/diagnostics/run_position_sizing_report.py \
        --symbols AP888,RB888 --sizing-model risk --start-date 2024-01-01 --end-date 2024-12-31
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
HERE = Path(__file__).resolve().parent
for path in (REPO, ROOT, HERE):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from chan_strategy.backtest_engine import BacktestEngine  # noqa: E402
from chan_strategy.config import STRATEGY_CONFIG  # noqa: E402
from chan_strategy.positions import _research_contract_spec  # noqa: E402


BANNER = "Diagnostic only, not a trading recommendation."
OUT_DIR = HERE
DEFAULT_SYMBOLS = ["AP888", "RB888", "SC888", "A888", "ZN888"]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="A40 unified position sizing report")
    parser.add_argument(
        "--symbols",
        type=str,
        default=",".join(DEFAULT_SYMBOLS),
        help="Comma-separated list of symbols to backtest",
    )
    parser.add_argument(
        "--sizing-model",
        type=str,
        default="risk",
        choices=["research", "risk"],
        help="Sizing model to use for the report",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default="2024-01-01",
        help="Backtest start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default="2024-12-31",
        help="Backtest end date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--stop-execution-model",
        type=str,
        default=None,
        choices=["close", "intrabar"],
        help="Override STRATEGY_CONFIG['stop_execution_model']",
    )
    parser.add_argument(
        "--out-json",
        type=str,
        default=None,
        help="Output JSON path (default: auto-generated in diagnostics/)",
    )
    return parser.parse_args()


def _run_symbol(symbol: str, start_date: str, end_date: str) -> dict[str, Any]:
    engine = BacktestEngine(
        symbol=symbol,
        freq="1",
        start_date=start_date,
        end_date=end_date,
        table_name=f"{symbol}_1M_raw",
    )
    report = engine.run()
    return {"engine": engine, "report": report}


def _stop_trigger_price(open_price: float, stop_loss_bp: int, direction: str) -> float:
    """A38/A40 nominal stop trigger level in price terms."""
    if direction == "long":
        return open_price * (1 - stop_loss_bp / 10000)
    return open_price * (1 + stop_loss_bp / 10000)


def _classify_exit(pair: dict[str, Any], stop_execution_model: str) -> dict[str, Any]:
    """Label a closed pair as touch-based or close-based stop exit."""
    result = {
        "is_stop_exit": pair.get("reason_code") == "stop_loss",
        "exit_type": "n/a",
        "stop_distance_price": None,
    }
    if not result["is_stop_exit"]:
        return result

    stop_loss_bp = 0
    name = pair.get("strategy", "")
    if "一买" in name:
        stop_loss_bp = STRATEGY_CONFIG.get("stop_loss_1buy", 200)
    elif "二买" in name:
        stop_loss_bp = STRATEGY_CONFIG.get("stop_loss_2buy", 300)
    elif "三买" in name:
        stop_loss_bp = STRATEGY_CONFIG.get("stop_loss_3buy", 350)
    elif "一卖" in name:
        stop_loss_bp = STRATEGY_CONFIG.get("stop_loss_1sell", 200)
    elif "二卖" in name:
        stop_loss_bp = STRATEGY_CONFIG.get("stop_loss_2sell", 300)
    elif "三卖" in name:
        stop_loss_bp = STRATEGY_CONFIG.get("stop_loss_3sell", 350)

    direction = "short" if "卖" in name else "long"
    trigger = _stop_trigger_price(pair["open_price"], stop_loss_bp, direction)
    result["stop_distance_price"] = abs(pair["open_price"] - trigger)

    if stop_execution_model == "intrabar":
        # Intracomment: A38 fills at min/max(trigger, close).  If close equals trigger
        # within tolerance, this was a non-gap touch exit; otherwise it was a gap fill.
        tol = max(1e-6, abs(trigger) * 1e-6)
        if abs(pair["close_price"] - trigger) <= tol:
            result["exit_type"] = "touch_based"
        else:
            result["exit_type"] = "gap_fill"
    else:
        result["exit_type"] = "close_based"

    return result


def _build_trades_table(engine: BacktestEngine, stop_execution_model: str) -> list[dict[str, Any]]:
    """Closed trades with sizing and stop-exit classification."""
    trades = []
    for pair in engine.strategy.get_combined_trades():
        spec = _research_contract_spec(engine.symbol)
        exit_info = _classify_exit(pair, stop_execution_model)
        row = {
            "symbol": engine.symbol,
            "strategy": pair.get("strategy"),
            "direction": "short" if "卖" in pair.get("strategy", "") else "long",
            "open_dt": _fmt_dt(pair.get("open_dt")),
            "close_dt": _fmt_dt(pair.get("close_dt")),
            "open_price": pair.get("open_price"),
            "close_price": pair.get("close_price"),
            "stop_distance_price": exit_info["stop_distance_price"],
            "volume": pair.get("volume", 1),
            "contract_multiplier": pair.get("contract_multiplier", 1),
            "pnl_pct": pair.get("pnl_pct"),
            "pnl_currency": pair.get("pnl_currency"),
            "reason": pair.get("reason"),
            "reason_code": pair.get("reason_code"),
            "exit_type": exit_info["exit_type"],
            "margin_rate": spec.get("margin_rate"),
        }
        trades.append(row)
    return trades


def _fmt_dt(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def _simnow_risk_caliber() -> dict[str, Any]:
    """Placeholder until A41 provides a real SimNow replay risk caliber."""
    return {
        "status": "not_available_pending_A41",
        "note": "A41 will supply a replay-computed risk caliber; this field is intentionally not fabricated.",
    }


def _contract_spec_crosscheck() -> dict[str, Any]:
    """AC-A40-11: confirm sizing stop_distance equals A38 intrabar trigger distance."""
    specs = STRATEGY_CONFIG.get("contract_specs", {})
    result = {}
    for symbol, spec in specs.items():
        multiplier = spec.get("multiplier", 1)
        # Use a representative price of 100; the equality is proportional.
        price = 100.0
        stop_loss_bp = STRATEGY_CONFIG.get("stop_loss_1buy", 200)
        stop_distance = price * stop_loss_bp / 10000
        long_trigger = price * (1 - stop_loss_bp / 10000)
        short_trigger = price * (1 + stop_loss_bp / 10000)
        result[symbol] = {
            "multiplier": multiplier,
            "stop_loss_bp": stop_loss_bp,
            "stop_distance_price_at_100": stop_distance,
            "long_trigger_at_100": long_trigger,
            "short_trigger_at_100": short_trigger,
            "crosscheck_pass": abs((price - long_trigger) - stop_distance) < 1e-9
            and abs((short_trigger - price) - stop_distance) < 1e-9,
        }
    return result


def main() -> dict[str, Any]:
    args = _parse_args()
    STRATEGY_CONFIG["sizing_model"] = args.sizing_model
    if args.stop_execution_model is not None:
        STRATEGY_CONFIG["stop_execution_model"] = args.stop_execution_model
    stop_execution_model = STRATEGY_CONFIG.get("stop_execution_model", "close")

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    start_date = args.start_date
    end_date = args.end_date
    stamp = datetime.now(timezone.utc).isoformat()

    per_symbol: dict[str, Any] = {}
    all_trades: list[dict[str, Any]] = []
    summary = {
        "touch_based_stop_exits": 0,
        "gap_fill_stop_exits": 0,
        "close_based_stop_exits": 0,
        "total_stop_exits": 0,
        "total_trades": 0,
    }

    errors = []
    for symbol in symbols:
        try:
            data = _run_symbol(symbol, start_date, end_date)
        except Exception as exc:  # noqa: BLE001
            errors.append({"symbol": symbol, "error": str(exc)})
            continue

        engine = data["engine"]
        report = data["report"]
        if "error" in report:
            errors.append({"symbol": symbol, "error": report["error"]})
            continue

        trades = _build_trades_table(engine, stop_execution_model)
        all_trades.extend(trades)
        for t in trades:
            if t["exit_type"] == "touch_based":
                summary["touch_based_stop_exits"] += 1
            elif t["exit_type"] == "gap_fill":
                summary["gap_fill_stop_exits"] += 1
            elif t["exit_type"] == "close_based":
                summary["close_based_stop_exits"] += 1
        summary["total_trades"] += len(trades)

        per_symbol[symbol] = {
            "report": {
                k: v
                for k, v in report.items()
                if k not in ("sub_strategies",)
            },
            "trade_count": len(trades),
        }

    summary["total_stop_exits"] = (
        summary["touch_based_stop_exits"]
        + summary["gap_fill_stop_exits"]
        + summary["close_based_stop_exits"]
    )

    sizing_caveat = None
    for symbol_data in per_symbol.values():
        caveat = symbol_data.get("report", {}).get("sizing_caveat")
        if caveat:
            sizing_caveat = caveat
            break

    report_payload = {
        "disclaimer": BANNER,
        "scope": (
            "pnl_currency / total_open_margin / margin_utilization_pct are backtest research outputs "
            "under STRATEGY_CONFIG['contract_specs'] exchange-minimum margin rates, "
            "not production-ready capital-allocation numbers."
        ),
        "generated_at": stamp,
        "sizing_model": args.sizing_model,
        "stop_execution_model": stop_execution_model,
        "window": f"{start_date} ~ {end_date}",
        "symbols": symbols,
        "per_symbol": per_symbol,
        "trades": all_trades,
        "summary": summary,
        "sizing_caveat": sizing_caveat,
        "contract_spec_crosscheck": _contract_spec_crosscheck(),
        "simnow_risk_caliber": _simnow_risk_caliber(),
        "errors": errors,
    }

    out_path = args.out_json
    if out_path is None:
        out_path = OUT_DIR / f"position_sizing_report_{args.sizing_model}_{start_date}_{end_date}.json"
    Path(out_path).write_text(json.dumps(report_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"A40 position sizing report written to: {out_path}")
    return report_payload


if __name__ == "__main__":
    main()
