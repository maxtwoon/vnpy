from __future__ import annotations

import argparse
import contextlib
import io
import json
import math
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chan_strategy.backtest_engine import BacktestEngine  # noqa: E402
from chan_strategy.config import SQLITE_DB_PATH, STRATEGY_CONFIG  # noqa: E402
from diagnostics.declassify_historical_reports import build_banner  # noqa: E402


DEFAULT_SYMBOLS = ["AP888", "RB888", "SC888", "A888", "ZN888"]
DEFAULT_START = "2022-01-01"
DEFAULT_END = "2026-04-24"
DEFAULT_IS_START = "2022-01-01"
DEFAULT_IS_END = "2024-12-31"
DEFAULT_OOS_START = "2025-01-01"
DEFAULT_OOS_END = "2026-04-24"


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return str(value)
    return value


def _fmt_pct(value: float | int | str | None) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    return f"{float(value):.2f}%"


def _fmt_num(value: float | int | str | None, digits: int = 2) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return f"{value:,}"
    return f"{float(value):,.{digits}f}"


def _dominant_symbol(db_path: Path, table_name: str, start: str, end: str) -> str:
    """Select the symbol whose data covers the end of the backtest range.

    Some continuous-contract tables contain mixed symbols (e.g. historical
    'AP888' rows plus newer 'ap888' rows). We must choose the symbol whose
    latest bar reaches ``end`` so that the backtest actually processes the
    target trading day. If no symbol covers ``end``, fall back to the one
    with the latest available bar.
    """
    end_inclusive = str(end)
    if len(end_inclusive) <= 10 and " " not in end_inclusive:
        end_inclusive = f"{end_inclusive} 23:59:59"
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            f"""
            select symbol, min(datetime) as mindt, max(datetime) as maxdt, count(*) as n
            from {table_name}
            where datetime >= ? and datetime <= ?
            group by symbol
            """,
            (start, end_inclusive),
        ).fetchall()
    if not rows:
        raise RuntimeError(f"{table_name} has no rows for {start} ~ {end}")

    # Prefer symbols whose max datetime reaches the requested end date.
    covering = [
        row for row in rows
        if row[2] is not None and str(row[2]) >= str(end)
    ]
    if covering:
        # Among covering symbols, pick the one with the most rows (likely the
        # primary continuous series); tie-break by latest max datetime.
        best = max(covering, key=lambda r: (r[3], str(r[2]) if r[2] else ""))
        return str(best[0])

    # No symbol covers the end date: fall back to the latest available bar.
    best = max(
        rows,
        key=lambda r: (str(r[2]) if r[2] else "", r[3]),
    )
    return str(best[0])


def run_one(db_path: Path, symbol: str, start: str, end: str, quiet: bool = True) -> dict[str, Any]:
    table_name = f"{symbol.lower()}_1M_raw"
    data_symbol = _dominant_symbol(db_path, table_name, start, end)
    engine = BacktestEngine(
        symbol=data_symbol,
        db_path=str(db_path),
        table_name=table_name,
        start_date=start,
        end_date=end,
    )
    if quiet:
        with contextlib.redirect_stdout(io.StringIO()):
            report = engine.run()
    else:
        report = engine.run()
    report = dict(report)
    report["requested_symbol"] = symbol
    report["data_symbol"] = data_symbol
    report["table_name"] = table_name
    report["start_date"] = start
    report["end_date"] = end
    return report


def _period_checks(report: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if "error" in report:
        issues.append(str(report["error"]))
        return issues
    if report.get("total_bars", 0) <= 100:
        issues.append("raw bars <= 100")
    if report.get("traded_bars", 0) <= 0:
        issues.append("traded bars empty")
    if report.get("final_equity", 0) <= 0:
        issues.append("final equity <= 0")
    if report.get("total_trades", 0) <= 0:
        issues.append("total trades empty")
    return issues


def build_matrix(db_path: Path, symbols: list[str], quiet: bool = True) -> dict[str, Any]:
    periods = {
        "full": (DEFAULT_START, DEFAULT_END),
        "in_sample": (DEFAULT_IS_START, DEFAULT_IS_END),
        "out_sample": (DEFAULT_OOS_START, DEFAULT_OOS_END),
    }
    matrix: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_path": str(db_path),
        "periods": {name: {"start": start, "end": end} for name, (start, end) in periods.items()},
        "symbols": {},
        "checks": {},
    }
    for symbol in symbols:
        matrix["symbols"][symbol] = {}
        matrix["checks"][symbol] = {}
        for period_name, (start, end) in periods.items():
            try:
                report = run_one(db_path, symbol, start, end, quiet=quiet)
            except Exception as exc:  # pragma: no cover - diagnostic failure path
                report = {"requested_symbol": symbol, "start_date": start, "end_date": end, "error": str(exc)}
            matrix["symbols"][symbol][period_name] = report
            issues = _period_checks(report)
            matrix["checks"][symbol][period_name] = {"ok": not issues, "issues": issues}
    return matrix


def _sub_strategy_rows(symbol: str, period_name: str, report: dict[str, Any]) -> list[str]:
    rows = []
    for name, stats in report.get("sub_strategies", {}).items():
        rows.append(
            "| {symbol} | {period} | {name} | {trades} | {win_rate} | {pf} | {avg_profit} | {avg_loss} |".format(
                symbol=symbol,
                period=period_name,
                name=name,
                trades=_fmt_num(stats.get("total_trades"), 0),
                win_rate=_fmt_pct(float(stats.get("win_rate", 0)) * 100),
                pf=_fmt_num(stats.get("profit_factor")),
                avg_profit=_fmt_pct(float(stats.get("avg_profit", 0)) * 100),
                avg_loss=_fmt_pct(float(stats.get("avg_loss", 0)) * 100),
            )
        )
    return rows


def _sizing_caveat(sizing_model: str) -> str:
    if sizing_model == "research":
        return (
            "⚠️ 当前仓位模型为 `research`（研究模式）：报告中的收益率使用固定 1 手 / "
            "1 倍合约乘数计算，仅为百分比回报代理，不是真实资金 P&L 曲线。"
        )
    return (
        "⚠️ 当前仓位模型为 `risk`（风险仓位模式）：手数、合约乘数与保证金按配置计算，"
        "但仍是回测结果，未经验证于实盘，不可直接用于生产资金分配。"
    )


def write_markdown(matrix: dict[str, Any], path: Path) -> None:
    sizing_model = STRATEGY_CONFIG.get("sizing_model", "research")
    banner_lines = build_banner().splitlines()
    while banner_lines and banner_lines[-1] == "":
        banner_lines.pop()

    lines = [
        "# 真实数据回测矩阵报告",
        "",
        *banner_lines,
        _sizing_caveat(sizing_model),
        "",
        f"- 生成时间：{matrix['generated_at']}",
        f"- 数据库：`{matrix['db_path']}`",
        f"- 覆盖品种：{' / '.join(matrix['symbols'].keys())}",
        f"- 全样本：{DEFAULT_START} ~ {DEFAULT_END}",
        f"- 样本内：{DEFAULT_IS_START} ~ {DEFAULT_IS_END}",
        f"- 样本外：{DEFAULT_OOS_START} ~ {DEFAULT_OOS_END}",
        "",
        "## 总览",
        "",
        "| 品种 | 区间 | 原始K线 | 交易K线 | 交易数 | 胜率 | 收益率 | 最大回撤 | 夏普 | 最大总敞口 | 多空同持bar | 检查 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for symbol, reports in matrix["symbols"].items():
        for period_name, report in reports.items():
            check = matrix["checks"][symbol][period_name]
            if "error" in report:
                lines.append(f"| {symbol} | {period_name} | - | - | - | - | - | - | - | - | - | 失败：{report['error']} |")
                continue
            lines.append(
                "| {symbol} | {period} | {bars} | {traded_bars} | {trades} | {win_rate} | {ret} | {dd} | {sharpe} | {gross} | {both} | {check} |".format(
                    symbol=symbol,
                    period=period_name,
                    bars=_fmt_num(report.get("total_bars"), 0),
                    traded_bars=_fmt_num(report.get("traded_bars"), 0),
                    trades=_fmt_num(report.get("total_trades"), 0),
                    win_rate=_fmt_pct(float(report.get("win_rate", 0)) * 100),
                    ret=_fmt_pct(report.get("total_return_pct", 0)),
                    dd=_fmt_pct(report.get("max_drawdown_pct", 0)),
                    sharpe=_fmt_num(report.get("sharpe_ratio", 0)),
                    gross=_fmt_pct(float(report.get("max_gross_exposure", 0)) * 100),
                    both=_fmt_num(report.get("both_long_short_bars", 0), 0),
                    check="通过" if check["ok"] else "告警：" + "; ".join(check["issues"]),
                )
            )
    lines.extend(
        [
            "",
            "## 子策略质量",
            "",
            "| 品种 | 区间 | 子策略 | 交易数 | 胜率 | 盈亏比 | 平均盈利 | 平均亏损 |",
            "|---|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for symbol, reports in matrix["symbols"].items():
        for period_name, report in reports.items():
            if "error" not in report:
                lines.extend(_sub_strategy_rows(symbol, period_name, report))
    lines.extend(
        [
            "",
            "## 结论口径",
            "",
            "- 本报告只固化真实 DB 上的收益与交易数事实，不把收益率作为自动门禁。",
            "- 自动检查只覆盖：数据非空、回测无 error、交易K线非空、最终权益为正、至少有交易。",
            "- 若策略逻辑、成本、日线过滤或中枢算法再变化，本报告必须重跑。",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run real-data backtest matrix and write JSON/Markdown reports.")
    parser.add_argument("--db-path", type=Path, default=Path(SQLITE_DB_PATH))
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--out-json", type=Path, default=Path(__file__).with_name("backtest_matrix_20220101_20260424.json"))
    parser.add_argument("--out-md", type=Path, default=Path(__file__).with_name("backtest_matrix_20220101_20260424.md"))
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if not args.db_path.exists():
        raise SystemExit(f"DB not found: {args.db_path}")

    matrix = build_matrix(args.db_path, args.symbols, quiet=not args.verbose)
    args.out_json.write_text(json.dumps(_json_safe(matrix), ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(matrix, args.out_md)

    failed = [
        (symbol, period, check["issues"])
        for symbol, periods in matrix["checks"].items()
        for period, check in periods.items()
        if not check["ok"]
    ]
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")
    if failed:
        for symbol, period, issues in failed:
            print(f"WARNING {symbol} {period}: {'; '.join(issues)}")


if __name__ == "__main__":
    main()
