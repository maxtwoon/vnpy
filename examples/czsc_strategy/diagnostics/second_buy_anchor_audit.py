from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chan_strategy.backtest_engine import BacktestEngine
from chan_strategy.config import SQLITE_DB_PATH
from diagnostics.backtest_matrix_report import DEFAULT_END, DEFAULT_START, DEFAULT_SYMBOLS, _dominant_symbol


def _fmt_pct(value: float | int | None) -> str:
    if value is None:
        return "-"
    return f"{float(value) * 100:.2f}%"


def _fmt_num(value: float | int | None, digits: int = 2) -> str:
    if value is None:
        return "-"
    if isinstance(value, int):
        return f"{value:,}"
    return f"{float(value):,.{digits}f}"


def _dt_text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def _age_bucket(days: float | None) -> str:
    if days is None:
        return "no_anchor"
    if days <= 5:
        return "<=5d"
    if days <= 20:
        return "05-20d"
    return ">20d"


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"trades": 0, "pnl_sum": 0.0, "win_rate": 0.0, "profit_factor": 0.0}
    pnls = [float(x["pnl_pct"]) for x in rows]
    wins = [x for x in pnls if x > 0]
    losses = [x for x in pnls if x <= 0]
    loss_sum = abs(sum(losses))
    return {
        "trades": len(rows),
        "pnl_sum": sum(pnls),
        "win_rate": len(wins) / len(pnls),
        "avg_pnl": sum(pnls) / len(pnls),
        "profit_factor": sum(wins) / loss_sum if loss_sum else float("inf"),
        "avg_anchor_age_days": sum(x.get("anchor_age_days") or 0 for x in rows) / len(rows),
    }


def _latest_anchor(anchors: list[dict[str, Any]], open_dt: datetime) -> dict[str, Any] | None:
    candidates = [a for a in anchors if a.get("dt") and a["dt"] <= open_dt]
    if not candidates:
        return None
    return max(candidates, key=lambda a: a["dt"])


def collect_audit(db_path: Path, symbols: list[str], start: str, end: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_path": str(db_path),
        "start": start,
        "end": end,
        "trades": [],
        "symbols": {},
    }
    for symbol in symbols:
        table_name = f"{symbol.lower()}_1M_raw"
        data_symbol = _dominant_symbol(db_path, table_name, start, end)
        engine = BacktestEngine(
            symbol=data_symbol,
            db_path=str(db_path),
            table_name=table_name,
            start_date=start,
            end_date=end,
        )
        with contextlib.redirect_stdout(io.StringIO()):
            report = engine.run()
        if "error" in report:
            payload["symbols"][symbol] = {"error": report["error"]}
            continue

        buy2_pos = engine.strategy.positions[1]
        anchors = list(engine.strategy.buy1_history)
        rows = []
        for pair in buy2_pos.pairs:
            row = dict(pair)
            row["symbol"] = symbol
            row["strategy"] = buy2_pos.name
            anchor = _latest_anchor(anchors, row["open_dt"])
            if anchor:
                age_days = (row["open_dt"] - anchor["dt"]).total_seconds() / 86400
                row["anchor_dt"] = anchor["dt"]
                row["anchor_price"] = anchor.get("price")
                row["anchor_age_days"] = age_days
                row["anchor_bucket"] = _age_bucket(age_days)
                row["anchor_zs_zd"] = anchor.get("zs_zd")
                row["anchor_zs_zg"] = anchor.get("zs_zg")
            else:
                row["anchor_dt"] = None
                row["anchor_price"] = None
                row["anchor_age_days"] = None
                row["anchor_bucket"] = "no_anchor"
            rows.append(row)
            payload["trades"].append(row)
        payload["symbols"][symbol] = {
            "buy1_anchor_count": len(anchors),
            "buy2_trade_count": len(rows),
            "summary": _summarize(rows),
        }
    return payload


def build_groups(payload: dict[str, Any]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in payload["trades"]:
        groups[row["anchor_bucket"]].append(row)
        by_symbol[row["symbol"]].append(row)
    return {
        "by_anchor_age": {k: _summarize(v) for k, v in sorted(groups.items())},
        "by_symbol": {k: _summarize(v) for k, v in sorted(by_symbol.items())},
        "worst_trades": sorted(payload["trades"], key=lambda x: float(x["pnl_pct"]))[:20],
    }


def _row(name: str, stats: dict[str, Any]) -> str:
    pf = stats.get("profit_factor")
    pf_text = "inf" if pf == float("inf") else _fmt_num(pf)
    return (
        f"| {name} | {_fmt_num(stats.get('trades'), 0)} | {_fmt_pct(stats.get('pnl_sum'))} | "
        f"{_fmt_pct(stats.get('win_rate'))} | {_fmt_pct(stats.get('avg_pnl'))} | {pf_text} | "
        f"{_fmt_num(stats.get('avg_anchor_age_days'))} |"
    )


def write_markdown(payload: dict[str, Any], groups: dict[str, Any], out: Path) -> None:
    lines = [
        "# 二买锚点年龄审计",
        "",
        f"- 生成时间：{payload['generated_at']}",
        f"- 区间：{payload['start']} ~ {payload['end']}",
        f"- 品种：{' / '.join(payload['symbols'].keys())}",
        "- 口径：二买开仓时回找最近一买锚点，按锚点距开仓时间分组。",
        "",
        "## 按品种",
        "",
        "| 品种 | 二买交易 | 累计收益 | 胜率 | 平均单笔 | 盈亏比 | 平均锚点年龄(日) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for symbol, stats in groups["by_symbol"].items():
        lines.append(_row(symbol, stats))
    lines.extend([
        "",
        "## 按锚点年龄",
        "",
        "| 锚点年龄 | 二买交易 | 累计收益 | 胜率 | 平均单笔 | 盈亏比 | 平均锚点年龄(日) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ])
    for bucket, stats in groups["by_anchor_age"].items():
        lines.append(_row(bucket, stats))

    lines.extend([
        "",
        "## 二买亏损 Top20",
        "",
        "| 品种 | 开仓时间 | 平仓时间 | 盈亏 | 持仓bar | 原因 | 锚点时间 | 锚点年龄(日) | 锚点价 |",
        "|---|---|---|---:|---:|---|---|---:|---:|",
    ])
    for row in groups["worst_trades"]:
        lines.append(
            "| {symbol} | {open_dt} | {close_dt} | {pnl} | {bars} | {reason} | {anchor_dt} | {age} | {price} |".format(
                symbol=row["symbol"],
                open_dt=_dt_text(row["open_dt"]),
                close_dt=_dt_text(row["close_dt"]),
                pnl=_fmt_pct(row.get("pnl_pct")),
                bars=_fmt_num(row.get("bars_held"), 0),
                reason=row.get("reason_code") or row.get("reason", ""),
                anchor_dt=_dt_text(row.get("anchor_dt")),
                age=_fmt_num(row.get("anchor_age_days")),
                price=_fmt_num(row.get("anchor_price")),
            )
        )
    lines.extend([
        "",
        "## 判读",
        "",
        "- 若 `>20d` 组显著弱于其他组，应考虑给一买锚点增加过期规则。",
        "- 若亏损主要集中在 `stop_loss`，优先检查二买确认点是否过晚或止损阈值是否与品种波动不匹配。",
        "",
    ])
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit second-buy trades by latest first-buy anchor age.")
    parser.add_argument("--db-path", type=Path, default=Path(SQLITE_DB_PATH))
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--out-json", type=Path, default=Path(__file__).with_name("second_buy_anchor_audit_20220101_20260424.json"))
    parser.add_argument("--out-md", type=Path, default=Path(__file__).with_name("second_buy_anchor_audit_20220101_20260424.md"))
    args = parser.parse_args()

    payload = collect_audit(args.db_path, args.symbols, args.start, args.end)
    groups = build_groups(payload)
    args.out_json.write_text(json.dumps({"payload": payload, "groups": groups}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    write_markdown(payload, groups, args.out_md)
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()
