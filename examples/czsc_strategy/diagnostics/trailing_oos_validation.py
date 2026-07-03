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

from chan_strategy.config import SQLITE_DB_PATH, STRATEGY_CONFIG
from diagnostics.backtest_matrix_report import run_one


DEFAULT_START = "2025-01-01"
DEFAULT_END = "2026-04-24"
TUNED_PARAMS = {
    "RB888": {"trailing_start_bp": 250, "trailing_drawback_pct": 0.15},
    "SC888": {"trailing_start_bp": 150, "trailing_drawback_pct": 0.15},
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


def _run(db_path: Path, symbol: str, start: str, end: str, overrides: dict[str, Any]) -> dict[str, Any]:
    original = copy.deepcopy(STRATEGY_CONFIG)
    try:
        STRATEGY_CONFIG.update(overrides)
        report = run_one(db_path, symbol, start, end, quiet=True)
        report["params"] = dict(overrides)
        return report
    finally:
        STRATEGY_CONFIG.clear()
        STRATEGY_CONFIG.update(original)


def run_validation(db_path: Path, start: str, end: str) -> dict[str, Any]:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_path": str(db_path),
        "start": start,
        "end": end,
        "symbols": {},
    }
    for symbol, params in TUNED_PARAMS.items():
        baseline = _run(db_path, symbol, start, end, {})
        tuned = _run(db_path, symbol, start, end, params)
        payload["symbols"][symbol] = {"baseline": baseline, "tuned": tuned}
    return payload


def write_markdown(payload: dict[str, Any], out: Path) -> None:
    lines = [
        "# 移动止损样本外验证",
        "",
        f"- 生成时间：{payload['generated_at']}",
        f"- 区间：{payload['start']} ~ {payload['end']}",
        "- 对照：默认 `trailing_start_bp=300 / trailing_drawback_pct=0.25`",
        "- 调参：RB888 使用 `250 / 0.15`；SC888 使用 `150 / 0.15`",
        "",
        "| 品种 | 版本 | 参数 | 交易数 | 收益率 | 相对基线 | 最大回撤 | 胜率 | 盈亏比 |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for symbol, reports in payload["symbols"].items():
        base_ret = reports["baseline"].get("total_return_pct", 0)
        for name in ["baseline", "tuned"]:
            report = reports[name]
            params = report.get("params", {}) or {"trailing_start_bp": 300, "trailing_drawback_pct": 0.25}
            pf = report.get("profit_factor")
            pf_text = "inf" if pf == float("inf") or pf == "inf" else _fmt_num(pf)
            lines.append(
                "| {symbol} | {name} | {params} | {trades} | {ret} | {delta} | {dd} | {win} | {pf} |".format(
                    symbol=symbol,
                    name=name,
                    params=f"{params.get('trailing_start_bp')}/{params.get('trailing_drawback_pct')}",
                    trades=_fmt_num(report.get("total_trades", 0), 0),
                    ret=_fmt_pct(report.get("total_return_pct", 0)),
                    delta=_fmt_pct(float(report.get("total_return_pct", 0)) - float(base_ret)),
                    dd=_fmt_pct(report.get("max_drawdown_pct", 0)),
                    win=_fmt_pct(float(report.get("win_rate", 0)) * 100),
                    pf=pf_text,
                )
            )
    lines.extend(
        [
            "",
            "## 判读",
            "",
            "- 若 tuned 在样本外继续改善收益与回撤，才进入更大范围品种验证。",
            "- 若 tuned 样本外退化，2024 细网格改善更可能是阶段性拟合。",
            "",
        ]
    )
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate tuned trailing-stop params out of sample.")
    parser.add_argument("--db-path", type=Path, default=Path(SQLITE_DB_PATH))
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--out-json", type=Path, default=Path(__file__).with_name("trailing_oos_validation_20250101_20260424.json"))
    parser.add_argument("--out-md", type=Path, default=Path(__file__).with_name("trailing_oos_validation_20250101_20260424.md"))
    args = parser.parse_args()

    payload = run_validation(args.db_path, args.start, args.end)
    args.out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, args.out_md)
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()
