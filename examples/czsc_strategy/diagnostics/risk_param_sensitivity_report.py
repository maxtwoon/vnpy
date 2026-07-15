from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chan_strategy.config import SQLITE_DB_PATH, STRATEGY_CONFIG  # noqa: E402
from diagnostics.backtest_matrix_report import run_one  # noqa: E402


DEFAULT_SYMBOLS = ["RB888", "SC888"]
DEFAULT_START = "2024-01-01"
DEFAULT_END = "2024-12-31"


VARIANTS: dict[str, dict[str, Any]] = {
    "baseline": {},
    "stop_loss_tight": {
        "stop_loss_1buy": 150,
        "stop_loss_2buy": 225,
        "stop_loss_3buy": 260,
    },
    "stop_loss_loose": {
        "stop_loss_1buy": 300,
        "stop_loss_2buy": 450,
        "stop_loss_3buy": 525,
    },
    "timeout_short": {
        "timeout_1buy": 300,
        "timeout_2buy": 500,
        "timeout_3buy": 750,
    },
    "timeout_long": {
        "timeout_1buy": 900,
        "timeout_2buy": 1500,
        "timeout_3buy": 2250,
    },
    "trailing_tight": {
        "trailing_start_bp": 200,
        "trailing_drawback_pct": 0.20,
    },
    "trailing_loose": {
        "trailing_start_bp": 500,
        "trailing_drawback_pct": 0.35,
    },
}


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


def _run_variant(db_path: Path, symbol: str, start: str, end: str, overrides: dict[str, Any]) -> dict[str, Any]:
    original = copy.deepcopy(STRATEGY_CONFIG)
    try:
        STRATEGY_CONFIG.update(overrides)
        return run_one(db_path, symbol, start, end, quiet=True)
    finally:
        STRATEGY_CONFIG.clear()
        STRATEGY_CONFIG.update(original)


def run_sensitivity(db_path: Path, symbols: list[str], start: str, end: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_path": str(db_path),
        "start": start,
        "end": end,
        "symbols": {},
        "variants": VARIANTS,
    }
    for symbol in symbols:
        payload["symbols"][symbol] = {}
        for name, overrides in VARIANTS.items():
            report = _run_variant(db_path, symbol, start, end, overrides)
            payload["symbols"][symbol][name] = report
    payload["perturbation_gate"] = evaluate_perturbation_gate(payload)
    return payload


def evaluate_perturbation_gate(payload: dict[str, Any]) -> dict[str, Any]:
    """Check whether any parameter variant flips the sign of total return vs baseline.

    This is a measurement/reporting gate: it reports sign flips and the maximum
    absolute return delta across variants, but does not invent an arbitrary
    pass/fail threshold.

    Note: the companion ``perturbation_gate_verdict()`` function below layers
    protective thresholds on top of this measurement.
    """
    results: dict[str, Any] = {}
    for symbol, reports in payload.get("symbols", {}).items():
        baseline_report = reports.get("baseline", {})
        if "error" in baseline_report:
            results[symbol] = {"ok": False, "issues": ["baseline report contains error"]}
            continue

        baseline_ret = float(baseline_report.get("total_return_pct", 0))
        issues: list[str] = []
        max_abs_delta: float = 0.0
        for name, report in reports.items():
            if name == "baseline" or "error" in report:
                continue
            variant_ret = float(report.get("total_return_pct", 0))
            delta = variant_ret - baseline_ret
            max_abs_delta = max(max_abs_delta, abs(delta))
            sign_flip = (baseline_ret >= 0 and variant_ret < 0) or (baseline_ret < 0 and variant_ret >= 0)
            if sign_flip:
                issues.append(
                    f"variant '{name}' return sign flip: baseline={baseline_ret:.2f}%, variant={variant_ret:.2f}%"
                )

        results[symbol] = {
            "ok": not issues,
            "issues": issues,
            "baseline_return_pct": baseline_ret,
            "max_abs_delta_pct": max_abs_delta,
        }
    return results


def perturbation_gate_verdict(perturbation_result: dict[str, Any]) -> dict[str, Any]:
    """Return a pass/fail verdict on top of ``evaluate_perturbation_gate`` output.

    This gate uses only the qualitative sign-flip criterion. There is no "warn"
    tier because sign flip is already a threshold-free, self-evidently unsafe
    outcome: a robust strategy should not change its profit/loss sign when
    risk-control parameters are perturbed within reasonable bands.

    Threshold reasoning (recorded in HANDOFF.md Decision Log):
    - Sign flip vs baseline is a qualitative failure.
    - No epsilon exemption for near-zero baselines is introduced, because any
      such epsilon would be an arbitrary threshold that could hide genuine
      fragility. If future data shows repeated spurious flips on noise-level
      baselines, this can be revisited.
    """
    symbols: dict[str, Any] = {}
    summary_reasons: list[str] = []
    has_fail = False

    for symbol, gate in perturbation_result.items():
        if not gate.get("ok"):
            issue = "; ".join(gate.get("issues", ["perturbation measurement unavailable"]))
            symbols[symbol] = {
                "status": "fail",
                "reasons": [issue],
                "baseline_return_pct": gate.get("baseline_return_pct"),
                "max_abs_delta_pct": gate.get("max_abs_delta_pct"),
            }
            has_fail = True
            summary_reasons.append(f"{symbol}: {issue}")
            continue

        symbols[symbol] = {
            "status": "pass",
            "reasons": [],
            "baseline_return_pct": gate.get("baseline_return_pct"),
            "max_abs_delta_pct": gate.get("max_abs_delta_pct"),
        }

    overall_status = "fail" if has_fail else "pass"
    return {
        "symbols": symbols,
        "overall_status": overall_status,
        "reasons": summary_reasons,
    }


def write_markdown(payload: dict[str, Any], out: Path) -> None:
    lines = [
        "# 风控参数敏感性报告",
        "",
        f"- 生成时间：{payload['generated_at']}",
        f"- 区间：{payload['start']} ~ {payload['end']}",
        f"- 品种：{' / '.join(payload['symbols'].keys())}",
        "- 说明：本报告用于判断策略是否对风控参数过度敏感，不作为调参最优解。",
        "",
        "| 品种 | 变体 | 交易数 | 收益率 | 相对基线 | 最大回撤 | 胜率 | 盈亏比 |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for symbol, reports in payload["symbols"].items():
        base_ret = reports["baseline"].get("total_return_pct", 0)
        for name, report in reports.items():
            if "error" in report:
                lines.append(f"| {symbol} | {name} | - | - | - | - | - | error: {report['error']} |")
                continue
            pf = report.get("profit_factor")
            pf_text = "inf" if pf == "inf" or pf == float("inf") else _fmt_num(pf)
            lines.append(
                "| {symbol} | {name} | {trades} | {ret} | {delta} | {dd} | {win} | {pf} |".format(
                    symbol=symbol,
                    name=name,
                    trades=_fmt_num(report.get("total_trades"), 0),
                    ret=_fmt_pct(report.get("total_return_pct", 0)),
                    delta=_fmt_pct(float(report.get("total_return_pct", 0)) - float(base_ret)),
                    dd=_fmt_pct(report.get("max_drawdown_pct", 0)),
                    win=_fmt_pct(float(report.get("win_rate", 0)) * 100),
                    pf=pf_text,
                )
            )
    gate = payload.get("perturbation_gate", {})
    if gate:
        lines.extend(
            [
                "",
                "## 参数扰动门禁",
                "",
                "| 品种 | 基线收益率 | 最大绝对偏差 | 符号翻转 |",
                "|---|---:|---:|---|",
            ]
        )
        for symbol, g in gate.items():
            flip_text = "; ".join(g["issues"]) if g["issues"] else "无"
            lines.append(
                f"| {symbol} | {_fmt_pct(g.get('baseline_return_pct', 0))} | "
                f"{_fmt_pct(g.get('max_abs_delta_pct', 0))} | {flip_text} |"
            )
    lines.extend(
        [
            "",
            "## 判读规则",
            "",
            "- 若轻微调整止损/超时/移动止损即导致收益符号大幅翻转，应优先回到信号定义和出场语义审查。",
            "- 若所有变体都亏损，问题通常不在单一风控参数，而在入场质量或适用品种。",
            "- 若只有某个参数族显著改善，可再做更细网格；当前报告只做第一层稳定性筛查。",
            "",
        ]
    )
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run risk parameter sensitivity diagnostics.")
    parser.add_argument("--db-path", type=Path, default=Path(SQLITE_DB_PATH))
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--out-json", type=Path, default=Path(__file__).with_name("risk_param_sensitivity_20240101_20241231.json"))
    parser.add_argument("--out-md", type=Path, default=Path(__file__).with_name("risk_param_sensitivity_20240101_20241231.md"))
    args = parser.parse_args()

    payload = run_sensitivity(args.db_path, args.symbols, args.start, args.end)
    args.out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, args.out_md)
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")
    failed = [
        (symbol, gate["issues"])
        for symbol, gate in payload.get("perturbation_gate", {}).items()
        if not gate["ok"]
    ]
    if failed:
        for symbol, issues in failed:
            print(f"PERTURBATION GATE {symbol}: {'; '.join(issues)}")


if __name__ == "__main__":
    main()
