from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chan_strategy.config import BACKTEST_CONFIG, SQLITE_DB_PATH  # noqa: E402
from diagnostics.backtest_matrix_report import run_one  # noqa: E402
from diagnostics.declassify_historical_reports import build_banner  # noqa: E402


DEFAULT_SYMBOLS = ["RB888", "SC888"]
DEFAULT_START = "2024-01-01"
DEFAULT_END = "2024-12-31"
COST_MULTIPLIERS = (1.0, 1.5, 2.0)


def _fmt_pct(value: float | int | None) -> str:
    if value is None:
        return "-"
    return f"{float(value):.2f}%"


def _fmt_num(value: float | int | None, digits: int = 2) -> str:
    if value is None:
        return "-"
    if isinstance(value, int):
        return f"{value:,}"
    return f"{float(value):,.{digits}f}"


def run_cost_sensitivity(
    db_path: Path,
    symbols: list[str],
    start: str,
    end: str,
    multipliers: tuple[float, ...] = COST_MULTIPLIERS,
) -> dict[str, Any]:
    """Run the same backtest at several cost multiples and report sensitivity.

    This is an honest measurement gate: it reports how much headline metrics
    move when ``commission_rate`` and ``slippage`` are scaled together. No
    arbitrary pass/fail threshold is invented.

    Note: the companion ``cost_sensitivity_gate_verdict()`` function below
    layers protective thresholds on top of this measurement.
    """
    base_commission = float(BACKTEST_CONFIG.get("commission_rate", 0.0))
    base_slippage = float(BACKTEST_CONFIG.get("slippage", 0.0))

    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_path": str(db_path),
        "start": start,
        "end": end,
        "base_commission_rate": base_commission,
        "base_slippage": base_slippage,
        "multipliers": list(multipliers),
        "symbols": {},
    }

    for symbol in symbols:
        payload["symbols"][symbol] = {}
        baseline_report: dict[str, Any] | None = None
        for mult in multipliers:
            report = run_one(
                db_path,
                symbol,
                start,
                end,
                quiet=True,
                commission_rate=base_commission * mult,
                slippage=base_slippage * mult,
            )
            payload["symbols"][symbol][f"x{mult}"] = report
            if mult == 1.0:
                baseline_report = report

        payload["symbols"][symbol]["deltas"] = _compute_deltas(
            baseline_report, payload["symbols"][symbol], multipliers
        )

    return payload


def _compute_deltas(
    baseline_report: dict[str, Any] | None,
    reports: dict[str, Any],
    multipliers: tuple[float, ...],
) -> dict[str, Any]:
    """Return absolute/relative deltas in headline metrics vs the baseline."""
    deltas: dict[str, Any] = {}
    if baseline_report is None or "error" in baseline_report:
        deltas["error"] = "baseline report unavailable"
        return deltas

    baseline_ret = float(baseline_report.get("total_return_pct", 0))
    baseline_dd = float(baseline_report.get("max_drawdown_pct", 0))
    baseline_sharpe = float(baseline_report.get("sharpe_ratio", 0))

    for mult in multipliers:
        key = f"x{mult}"
        report = reports.get(key, {})
        if "error" in report:
            deltas[key] = {"error": report["error"]}
            continue

        ret = float(report.get("total_return_pct", 0))
        dd = float(report.get("max_drawdown_pct", 0))
        sharpe = float(report.get("sharpe_ratio", 0))
        deltas[key] = {
            "delta_return_pct": ret - baseline_ret,
            "delta_max_drawdown_pct": dd - baseline_dd,
            "delta_sharpe": sharpe - baseline_sharpe,
            "relative_return_pct": ((ret - baseline_ret) / baseline_ret * 100)
            if baseline_ret != 0 else None,
        }
    return deltas


#: Extreme protective ceiling for relative return erosion at 2x costs.
#: A -90% relative return means doubling costs has erased 90% of the baseline
#: headline return. Chosen as a conservative, self-evidently unsafe sensitivity
#: level; not calibrated to any observed diagnostics data.
COST_RELATIVE_RETURN_WARN_PCT: float = -90.0


def cost_sensitivity_gate_verdict(result: dict[str, Any]) -> dict[str, Any]:
    """Return a pass/warn/fail verdict on top of ``run_cost_sensitivity`` output.

    Threshold reasoning (recorded in HANDOFF.md Decision Log):
    - If 2.0x costs flip the sign of ``total_return_pct`` vs the 1.0x baseline,
      the strategy's edge is not robust to transaction assumptions -> fail.
    - If 2.0x costs erode more than 90% of the baseline return (relative decline
      below -90%), this is an extreme sensitivity warning. The 90% level is a
      protective ceiling, not derived from any historical diagnostics output.
    - The relative-decline warning is only evaluated when the baseline return is
      positive, because the metric is otherwise directionally misleading.
    """
    symbols: dict[str, Any] = {}
    summary_reasons: list[str] = []
    has_fail = False
    has_warn = False

    for symbol, reports in result.get("symbols", {}).items():
        deltas = reports.get("deltas", {})
        if "error" in deltas:
            issue = deltas["error"]
            symbols[symbol] = {
                "status": "fail",
                "reasons": [issue],
            }
            has_fail = True
            summary_reasons.append(f"{symbol}: {issue}")
            continue

        baseline = reports.get("x1.0", {})
        baseline_ret = float(baseline.get("total_return_pct", 0)) if "error" not in baseline else 0.0
        x2 = deltas.get("x2.0", {})
        if "error" in x2:
            issue = f"2.0x cost delta unavailable: {x2['error']}"
            symbols[symbol] = {
                "status": "fail",
                "reasons": [issue],
            }
            has_fail = True
            summary_reasons.append(f"{symbol}: {issue}")
            continue

        x2_ret = float(reports.get("x2.0", {}).get("total_return_pct", 0))
        reasons: list[str] = []
        status = "pass"

        sign_flip = (baseline_ret >= 0 and x2_ret < 0) or (baseline_ret < 0 and x2_ret >= 0)
        if sign_flip:
            reasons.append(
                f"2.0x cost return sign flip: baseline={baseline_ret:.2f}%, 2.0x={x2_ret:.2f}%"
            )
            status = "fail"
            has_fail = True

        relative_return_pct = x2.get("relative_return_pct")
        if (
            status != "fail"
            and baseline_ret > 0
            and relative_return_pct is not None
            and relative_return_pct < COST_RELATIVE_RETURN_WARN_PCT
        ):
            reasons.append(
                f"2.0x cost relative return decline {relative_return_pct:.2f}% "
                f"exceeds {COST_RELATIVE_RETURN_WARN_PCT}% ceiling"
            )
            status = "warn"
            has_warn = True

        symbols[symbol] = {
            "status": status,
            "reasons": reasons,
            "baseline_return_pct": baseline_ret,
            "x2_return_pct": x2_ret,
            "x2_relative_return_pct": relative_return_pct,
        }
        if reasons:
            summary_reasons.append(f"{symbol}: {'; '.join(reasons)}")

    overall_status = "fail" if has_fail else ("warn" if has_warn else "pass")
    return {
        "symbols": symbols,
        "overall_status": overall_status,
        "reasons": summary_reasons,
    }


def write_markdown(payload: dict[str, Any], out: Path) -> None:
    banner_lines = build_banner().splitlines()
    while banner_lines and banner_lines[-1] == "":
        banner_lines.pop()

    lines = [
        "# 成本/滑点敏感性报告",
        "",
        *banner_lines,
        "- 本报告为 honest measurement：仅展示放大手续费与滑点后的指标变化，不作为盈利能力证明。",
        "",
        f"- 生成时间：{payload['generated_at']}",
        f"- 区间：{payload['start']} ~ {payload['end']}",
        f"- 品种：{' / '.join(payload['symbols'].keys())}",
        f"- 基准手续费率：{payload['base_commission_rate']}",
        f"- 基准滑点：{payload['base_slippage']}",
        "- 成本倍数：" + " / ".join(f"{m}x" for m in payload["multipliers"]),
        "",
        "## 敏感性汇总",
        "",
        "| 品种 | 成本倍数 | 收益率 | 相对基线(收益率) | 最大回撤 | 相对基线(回撤) | 夏普 | 相对基线(夏普) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for symbol, reports in payload["symbols"].items():
        baseline = reports.get("x1.0", {})
        base_ret = baseline.get("total_return_pct", 0) if "error" not in baseline else None
        base_dd = baseline.get("max_drawdown_pct", 0) if "error" not in baseline else None
        base_sharpe = baseline.get("sharpe_ratio", 0) if "error" not in baseline else None
        deltas = reports.get("deltas", {})
        for mult in payload["multipliers"]:
            key = f"x{mult}"
            report = reports.get(key, {})
            if "error" in report:
                lines.append(f"| {symbol} | {mult}x | error | - | - | - | - | - |")
                continue
            delta = deltas.get(key, {})
            lines.append(
                "| {symbol} | {mult}x | {ret} | {delta_ret} | {dd} | {delta_dd} | {sharpe} | {delta_sharpe} |".format(
                    symbol=symbol,
                    mult=mult,
                    ret=_fmt_pct(report.get("total_return_pct", 0)),
                    delta_ret=_fmt_pct(delta.get("delta_return_pct", 0)),
                    dd=_fmt_pct(report.get("max_drawdown_pct", 0)),
                    delta_dd=_fmt_pct(delta.get("delta_max_drawdown_pct", 0)),
                    sharpe=_fmt_num(report.get("sharpe_ratio", 0)),
                    delta_sharpe=_fmt_num(delta.get("delta_sharpe", 0)),
                )
            )
        if base_ret is not None:
            lines.append(
                f"| {symbol} | 小结 | 基准={_fmt_pct(base_ret)} | - | "
                f"基准={_fmt_pct(base_dd)} | - | 基准={_fmt_num(base_sharpe)} | - |"
            )
    lines.extend(
        [
            "",
            "## 判读规则",
            "",
            "- 若放大成本后收益符号翻转或夏普大幅恶化，说明策略对交易成本敏感，需优先审查换手频率与滑点假设。",
            "- 本报告不设定成本敏感性的自动阈值，仅提供可重复的测量机制。",
            "",
        ]
    )
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run cost/slippage sensitivity diagnostics.")
    parser.add_argument("--db-path", type=Path, default=Path(SQLITE_DB_PATH))
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--out-json", type=Path, default=Path(__file__).with_name("cost_sensitivity_20240101_20241231.json"))
    parser.add_argument("--out-md", type=Path, default=Path(__file__).with_name("cost_sensitivity_20240101_20241231.md"))
    args = parser.parse_args()

    payload = run_cost_sensitivity(args.db_path, args.symbols, args.start, args.end)
    args.out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, args.out_md)
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()
